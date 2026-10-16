"""Batched public-directory availability, using the bookable slot grid's rules."""
import logging
from collections import defaultdict
from datetime import timedelta
from itertools import batched

from django.core.cache import cache
from django.db.models import Q

from apps.bookings.models import Booking
from apps.bookings.services.holds import live_hold_q
from apps.bookings.services.lock_service import build_slot_lock_key
from apps.bookings.services.notice import min_notice
from apps.bookings.services.slot_generator import FREE_STATUSES, LESSON, _overlaps, _window_starts
from apps.common import clock
from apps.integrations.google_calendar import external_busy_intervals_for_teachers
from apps.teachers.models import TeacherAvailability, TeacherDateOverride, TeacherTimeOff
from apps.teachers.services.schedule import InvalidTeacherTimezone, build_plan, teacher_zone

logger = logging.getLogger(__name__)
BATCH_SIZE = 100
# Public, unauthenticated scans must have a hard ceiling. These values allow a
# 500-tutor directory and its normal 24-hour grid, but return 503 when the
# request cannot be answered exactly within the budget. No count is truncated.
MAX_TUTORS = 500
MAX_SLOT_CANDIDATES = 30000
MAX_LOCK_KEYS = 2048       # total lock keys submitted to Redis in one request
MAX_MGET_KEYS = 128        # one Upstash MGET command


class DirectoryUnavailable(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _group(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.teacher_id].append(row)
    return grouped


def _candidate_keys(teachers, now, end, remaining_candidates):
    ids = [teacher.id for teacher in teachers]
    weekly = _group(TeacherAvailability.objects.filter(teacher_id__in=ids, is_active=True))
    overrides = _group(TeacherDateOverride.objects.filter(
        teacher_id__in=ids, date__gte=now.date() - timedelta(days=2),
        date__lte=end.date() + timedelta(days=2)))
    time_off = _group(TeacherTimeOff.objects.filter(
        teacher_id__in=ids, start_utc__lt=end, end_utc__gt=now))
    occupying = Booking.objects.filter(
        teacher_id__in=ids, start_time_utc__lt=end, end_time_utc__gt=now,
    ).filter(~Q(status__in=FREE_STATUSES) | live_hold_q(now)).values_list(
        'teacher_id', 'start_time_utc', 'end_time_utc')
    booked = defaultdict(list)
    for teacher_id, start, finish in occupying:
        booked[teacher_id].append((start, finish))

    # First eliminate slots with no schedule or a blocking database booking. This
    # avoids all cache work for a batch with no possible free lesson.
    candidate_keys = defaultdict(list)
    candidate_count = 0
    earliest = now + min_notice()
    for teacher in teachers:
        try:
            zone = teacher_zone(teacher)
        except InvalidTeacherTimezone as exc:
            logger.error('Directory availability skipped, invalid timezone: teacher=%s user=%s',
                         exc.teacher_id, exc.user_id)
            continue
        plan = build_plan(zone, weekly[teacher.id], overrides[teacher.id], time_off[teacher.id])
        day = now.astimezone(zone).date()
        last_day = end.astimezone(zone).date()
        seen = set()
        while day <= last_day:
            for window_start, window_end in plan.raw_windows(day):
                for start in _window_starts(day, window_start, window_end, zone):
                    finish = start + LESSON
                    iso = start.isoformat()
                    if (start <= earliest or finish > end or iso in seen or plan.blocked(start, finish)
                            or _overlaps(booked[teacher.id], start, finish)):
                        continue
                    seen.add(iso)
                    candidate_count += 1
                    if candidate_count > remaining_candidates:
                        raise DirectoryUnavailable('directory_budget_exceeded')
                    candidate_keys[teacher.id].append((start, finish, iso))
            day += timedelta(days=1)
    if not candidate_keys:
        return {}, candidate_count
    try:
        # Only tutors with a candidate slot need a calendar-credential lookup or
        # cached Google busy hint. This reads cache only; it calls no provider.
        selected = [teacher for teacher in teachers if teacher.id in candidate_keys]
        busy = external_busy_intervals_for_teachers(selected, strict=True)
    except Exception:
        logger.exception('Directory busy-hint cache unavailable')
        raise DirectoryUnavailable('directory_cache_unavailable') from None
    return {
        teacher_id: [build_slot_lock_key(str(teacher_id), iso)
                     for start, finish, iso in slots if not _overlaps(busy.get(teacher_id, ()), start, finish)]
        for teacher_id, slots in candidate_keys.items()
    }, candidate_count


def _unlocked_ids(candidate_keys):
    # Probe the first candidate of each tutor before asking for the next. Most
    # tutors need one Redis key; only tutors whose first slot is locked need more.
    # Keys are deduplicated per tutor, and every MGET is bounded independently.
    pending = {teacher_id: iter(dict.fromkeys(keys)) for teacher_id, keys in candidate_keys.items()}
    free = set()
    checked = 0
    while pending:
        wave = []
        for teacher_id, starts in list(pending.items()):
            key = next(starts, None)
            if key is None:
                del pending[teacher_id]
            else:
                wave.append((teacher_id, key))
        if checked + len(wave) > MAX_LOCK_KEYS:
            raise DirectoryUnavailable('directory_budget_exceeded')
        for chunk in batched(wave, MAX_MGET_KEYS):
            keys = [key for _, key in chunk]
            try:
                locked = cache.get_many(keys)
            except Exception:
                logger.exception('Directory slot-lock cache unavailable')
                raise DirectoryUnavailable('directory_cache_unavailable') from None
            checked += len(keys)
            for teacher_id, key in chunk:
                if locked.get(key) is None:
                    free.add(teacher_id)
                    del pending[teacher_id]
    return free


def free_teacher_ids(queryset):
    """Return all matches in queryset order; callers paginate only after this scan."""
    now = clock.now()
    end = now + timedelta(hours=24)
    # Fetch one beyond the tutor budget before doing any cache work. A 503 is
    # honest: paging a partial scan would give a false count and miss matches.
    teachers = list(queryset[:MAX_TUTORS + 1])
    if len(teachers) > MAX_TUTORS:
        raise DirectoryUnavailable('directory_budget_exceeded')

    candidate_keys = {}
    candidate_count = 0
    for batch in batched(teachers, BATCH_SIZE):
        batch_keys, generated = _candidate_keys(batch, now, end, MAX_SLOT_CANDIDATES - candidate_count)
        candidate_count += generated
        for teacher_id, keys in batch_keys.items():
            if keys:
                candidate_keys[teacher_id] = keys
    if not candidate_keys:
        return []
    if len(candidate_keys) > MAX_LOCK_KEYS:
        raise DirectoryUnavailable('directory_budget_exceeded')

    free = _unlocked_ids(candidate_keys)
    return [teacher.id for teacher in teachers if teacher.id in free]
