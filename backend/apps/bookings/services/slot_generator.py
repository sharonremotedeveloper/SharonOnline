import logging
from datetime import date, datetime, time, timedelta
from typing import Iterable, Iterator, Optional

from django.conf import settings
from django.db.models import Q

from apps.bookings.models import Booking
from apps.bookings.services.holds import live_hold_q
from apps.bookings.services.lock_service import is_slot_locked
from apps.bookings.services.notice import min_notice
from apps.common import clock
from apps.common.timezones import get_zone
from apps.teachers.models import TeacherProfile
from apps.teachers.services.schedule import UTC, InvalidTeacherTimezone, boundary_utc, load_plan, local_to_utc, teacher_zone

logger = logging.getLogger(__name__)

LESSON_DURATION_MINUTES = 25
BUFFER_MINUTES = 5
SLOT_STEP_MINUTES = LESSON_DURATION_MINUTES + BUFFER_MINUTES  # 30-minute pacing
LESSON = timedelta(minutes=LESSON_DURATION_MINUTES)
STEP = timedelta(minutes=SLOT_STEP_MINUTES)

# Only these two statuses leave the time free; every other outcome (paid, taught, no-show, disputed, interrupted...)
# has consumed it. Unpaid PENDING_PAYMENT bookings count while their hold is live (services.holds.live_hold_q).
# A refunded student cancellation frees the slot. A late student cancel and a tutor cancel keep it blocked: the late fee is
# earned by the tutor for that slot, and a tutor who cancels is not available then.
FREE_STATUSES = (Booking.Status.PENDING_PAYMENT, Booking.Status.CANCELLED, Booking.Status.CANCELLED_BY_STUDENT)


def horizon_days() -> int:
    """How many days ahead a slot can be listed, reserved or rescheduled (one setting, T2)."""
    return settings.BOOKING_HORIZON_DAYS


def horizon_scan_days() -> int:
    """`days_ahead` for validation scans (reserve, reschedule): the horizon plus the day the tutor-local calendar may lead UTC by."""
    return settings.BOOKING_HORIZON_DAYS + 1


def _viewer_zone(name):
    try:
        return get_zone(name or 'UTC')
    except ValueError:
        return UTC


def _overlaps(spans, start, end) -> bool:
    return any(s < end and e > start for s, e in spans)


def _booking_spans(teacher, range_start, range_end, now_utc):
    """(booked, held) UTC spans in the window, found by OVERLAP (not exact start), so an off-grid booking blocks every slot
    it touches. Live unpaid holds are 'reserved'; everything else is 'booked'."""
    occupying = Booking.objects.filter(
        teacher=teacher, start_time_utc__lte=range_end, end_time_utc__gte=range_start,
    ).filter(~Q(status__in=FREE_STATUSES) | live_hold_q(now_utc)).values_list('start_time_utc', 'end_time_utc', 'status')
    booked = [(s, e) for s, e, st in occupying if st != Booking.Status.PENDING_PAYMENT]
    held = [(s, e) for s, e, st in occupying if st == Booking.Status.PENDING_PAYMENT]
    return booked, held


def _window_starts(day: date, window_start: time, window_end: time, zone) -> Iterator[datetime]:
    """UTC starts of the 25-minute slots of one window. Naive wall-clock stepping: each slot is converted on its own, so a
    local time that does not exist (spring forward) is skipped and an ambiguous one (fall back) takes its first occurrence."""
    cursor, stop = datetime.combine(day, window_start), datetime.combine(day, window_end)
    while cursor + LESSON <= stop:
        start_utc = local_to_utc(day, cursor.time(), zone)
        cursor += STEP
        if start_utc is not None:
            yield start_utc


def generate_teacher_slots(
    teacher: TeacherProfile,
    start_date: Optional[date] = None,
    days_ahead: int = 7,
    viewer_tz_name: str = 'UTC',
    blocked_intervals: Optional[Iterable] = None,
) -> list:
    """
    Projects a teacher's availability (weekly rows + date overrides - time off) into concrete 25-minute UTC slots, annotated
    with local viewer time and booking/lock availability. `start_date` is a date on the TUTOR's calendar (default: their today).

    `blocked_intervals` is the generic hook for "this tutor is busy then" sources (Google busy times, Eskom outage windows):
    an iterable of (start_utc, end_utc); any slot it touches is not listed.
    """
    now_utc = clock.now()
    try:
        teacher_tz = teacher_zone(teacher)
    except InvalidTeacherTimezone as exc:
        # No guess (the old code fell back to Johannesburg and showed wrong slots): the tutor shows no slots until fixed.
        logger.error('Slot generation skipped, invalid timezone: teacher=%s user=%s', exc.teacher_id, exc.user_id)
        return []
    viewer_tz = _viewer_zone(viewer_tz_name)
    if start_date is None:
        start_date = now_utc.astimezone(teacher_tz).date()
    plan = load_plan(teacher, teacher_tz, since=start_date - timedelta(days=1))
    extra_blocked = list(blocked_intervals or [])
    booked, held = _booking_spans(teacher, boundary_utc(start_date, time.min, teacher_tz),
                                  boundary_utc(start_date + timedelta(days=days_ahead + 1), time.min, teacher_tz), now_utc)
    earliest = now_utc + min_notice()           # a slot must start MORE than the notice from now

    slots, seen = [], set()
    for day_offset in range(days_ahead):
        day = start_date + timedelta(days=day_offset)
        for window_start, window_end in plan.raw_windows(day):
            for start_utc in _window_starts(day, window_start, window_end, teacher_tz):
                end_utc, iso = start_utc + LESSON, start_utc.isoformat()
                if start_utc <= earliest or iso in seen or plan.blocked(start_utc, end_utc) or _overlaps(extra_blocked, start_utc, end_utc):
                    continue
                seen.add(iso)  # overlapping availability rows must not list one slot twice
                if _overlaps(booked, start_utc, end_utc):
                    state = 'booked'
                elif _overlaps(held, start_utc, end_utc) or is_slot_locked(str(teacher.id), iso):
                    state = 'reserved'
                else:
                    state = 'available'
                viewer_start, viewer_end = start_utc.astimezone(viewer_tz), end_utc.astimezone(viewer_tz)
                slots.append({
                    "start_time_utc": iso,
                    "end_time_utc": end_utc.isoformat(),
                    "local_date": viewer_start.strftime("%Y-%m-%d"),
                    "local_start_time": viewer_start.strftime("%H:%M"),
                    "local_end_time": viewer_end.strftime("%H:%M"),
                    "viewer_timezone": getattr(viewer_tz, 'key', 'UTC'),
                    "status": state,
                    "is_bookable": state == 'available',
                })
    slots.sort(key=lambda s: s["start_time_utc"])
    return slots
