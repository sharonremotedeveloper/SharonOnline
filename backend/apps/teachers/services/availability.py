"""
Availability writes (T2, PRP 11.6): weekly rows, the atomic weekly matrix, time off and specific-date overrides.

Rules shared by every write here:
  * Every write runs in one transaction that first locks the TUTOR's row (`select_for_update(of=('self',))`), so concurrent
    edits by the same tutor serialise. Lock order is booking -> tutor everywhere else; lessons are READ here, never locked.
  * A change that would leave a CONFIRMED future lesson outside the tutor's open hours is a conflict. Unless the tutor sent
    `acknowledge_conflicts` it is refused with 409 {code: 'availability_conflicts', conflicts: [...]} and nothing changes;
    acknowledged, it is applied and the same list is returned. Editing availability never cancels or moves a booking: the
    tutor honours the lesson or cancels it through the penalty path (docs/CANCELLATION_AND_REFUNDS.md).
  * Windows are whole minutes, start < end and at least one lesson (25 min) long. The overlap check only looks at ACTIVE
    rows of the same weekday and excludes the row being edited, so legacy overlapping pairs can be repaired one row at a time.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound

from apps.common import clock
from apps.common.timezones import get_zone
from apps.teachers.models import TeacherAvailability, TeacherDateOverride, TeacherProfile, TeacherTimeOff
from apps.teachers.services.schedule import InvalidTeacherTimezone, lesson_conflicts, load_plan, teacher_zone

LESSON_MINUTES = 25                 # one lesson (bookings.services.slot_generator.LESSON_DURATION_MINUTES)
MAX_AVAILABILITY_ROWS = 70          # ten windows a day is more than any real schedule
MAX_TIME_OFF_ROWS = 100             # upcoming (not yet ended) absences
MAX_OVERRIDE_ROWS = 200             # upcoming date overrides
MAX_TIME_OFF_DAYS = 366
MAX_OVERRIDE_DAYS_AHEAD = 366


class AvailabilityConflict(APIException):
    """409: the change would strand confirmed lessons; resend with acknowledge_conflicts to apply it anyway."""
    status_code = 409
    default_code = 'availability_conflicts'

    def __init__(self, conflicts: list):
        self.detail = {
            'code': 'availability_conflicts',
            'detail': ('This change leaves confirmed lessons outside your open hours. Nothing was changed. '
                       'Resend with acknowledge_conflicts=true to apply it, then cancel those lessons or teach them.'),
            'conflicts': conflicts,
        }


@dataclass
class Outcome:
    obj: object
    conflicts: list


# ------------------------------------------------------------------ validation
def window_errors(start: Optional[time], end: Optional[time]) -> dict:
    """Field errors for one local window, {} when it is valid."""
    errors = {}
    for name, value in (('start_time', start), ('end_time', end)):
        if value is not None and (value.second or value.microsecond):
            errors[name] = ['Use whole minutes (HH:MM).']
    if errors or start is None or end is None:
        return errors
    if end <= start:
        errors['end_time'] = ['The end time must be after the start time.']
    elif (datetime.combine(date.min, end) - datetime.combine(date.min, start)) < timedelta(minutes=LESSON_MINUTES):
        errors['end_time'] = [f'A window must be at least one {LESSON_MINUTES}-minute lesson long.']
    return errors


def _clock_text(t: time) -> str:
    return t.strftime('%H:%M')


def first_overlap(rows: Iterable, start: time, end: time):
    return next((r for r in rows if r.start_time < end and start < r.end_time), None)


def check_row_limit(teacher) -> None:
    if teacher.availabilities.count() >= MAX_AVAILABILITY_ROWS:
        raise serializers.ValidationError({'non_field_errors': [f'You can have at most {MAX_AVAILABILITY_ROWS} availability windows.']})


def check_no_overlap(teacher, day: int, start: time, end: time, exclude_id=None) -> None:
    rows = teacher.availabilities.filter(is_active=True, day_of_week=day)
    if exclude_id is not None:
        rows = rows.exclude(pk=exclude_id)
    clash = first_overlap(rows, start, end)
    if clash:
        raise serializers.ValidationError({'end_time': [
            f'This window overlaps another active window on that day ({_clock_text(clash.start_time)}-{_clock_text(clash.end_time)}).']})


def validate_matrix(rows: list) -> list:
    """Whole-matrix checks for the replace endpoint (each row's own window was already validated)."""
    if len(rows) > MAX_AVAILABILITY_ROWS:
        raise serializers.ValidationError(f'You can send at most {MAX_AVAILABILITY_ROWS} availability windows.')
    by_day = {}
    for row in rows:
        if row.get('is_active', True):
            by_day.setdefault(row['day_of_week'], []).append(row)
    for day, day_rows in by_day.items():
        ordered = sorted(day_rows, key=lambda r: r['start_time'])
        for earlier, later in zip(ordered, ordered[1:], strict=False):
            if later['start_time'] < earlier['end_time']:
                raise serializers.ValidationError(f'Windows overlap on weekday {day} '
                                                  f"({_clock_text(earlier['start_time'])}-{_clock_text(earlier['end_time'])} and "
                                                  f"{_clock_text(later['start_time'])}-{_clock_text(later['end_time'])}).")
    return rows


def validate_override(data: dict, teacher) -> dict:
    kind, start, end = data['kind'], data.get('start_time'), data.get('end_time')
    if (start is None) != (end is None):
        raise serializers.ValidationError({'end_time' if start is not None else 'start_time': ['Give both start_time and end_time, or neither.']})
    if kind == TeacherDateOverride.Kind.OPEN and start is None:
        raise serializers.ValidationError({'start_time': ['Extra hours need a start_time and an end_time.']})
    if start is not None:
        errors = window_errors(start, end)
        if errors:
            raise serializers.ValidationError(errors)
    today = _tutor_today(teacher)
    if not today <= data['date'] <= today + timedelta(days=MAX_OVERRIDE_DAYS_AHEAD):
        raise serializers.ValidationError({'date': [f'Choose a date from today up to {MAX_OVERRIDE_DAYS_AHEAD} days ahead.']})
    return data


def validate_time_off(data: dict) -> dict:
    start, end, now = data['start_utc'], data['end_utc'], clock.now()
    if end <= start:
        raise serializers.ValidationError({'end_utc': ['The end must be after the start.']})
    if end <= now:
        raise serializers.ValidationError({'end_utc': ['Time off must end in the future.']})
    if end - start > timedelta(days=MAX_TIME_OFF_DAYS):
        raise serializers.ValidationError({'end_utc': [f'Time off can last at most {MAX_TIME_OFF_DAYS} days.']})
    return data


def _zone(teacher):
    try:
        return teacher_zone(teacher)
    except InvalidTeacherTimezone:
        raise serializers.ValidationError({'timezone': ['Your account timezone is not valid. Update it in your profile first.']}) from None


def _tutor_today(teacher) -> date:
    return clock.now().astimezone(_zone(teacher)).date()


# ------------------------------------------------------------------ conflicts
def conflicts_for(teacher, *, weekly=None, extra_overrides: Iterable = (), drop_override=None, extra_time_off: Iterable = (),
                  zone=None) -> list:
    """Confirmed lessons left uncovered by the tutor's CURRENT schedule changed as described (nothing is written).
    weekly: the proposed ACTIVE weekly rows (default: the stored ones); zone: a proposed new timezone (default: the stored one).
    Known limits (docs/slices/T2.md): live unpaid PENDING_PAYMENT holds (< 30 min) are ignored, and a lesson confirmed by a
    concurrent payment after this read is not seen (the check is advisory, not a lock on bookings)."""
    zone, now = zone or _zone(teacher), clock.now()
    since = now.astimezone(zone).date() - timedelta(days=1)
    overrides = [o for o in teacher.date_overrides.filter(date__gte=since) if o.pk != drop_override] + list(extra_overrides)
    time_off = list(teacher.time_off.filter(end_utc__gt=now - timedelta(days=1))) + list(extra_time_off)
    plan = load_plan(teacher, zone, weekly_rows=weekly, override_rows=overrides, time_off_rows=time_off, since=since)
    return lesson_conflicts(teacher, plan, now)


def require_acknowledgement(conflicts: list, acknowledged: bool) -> None:
    if conflicts and not acknowledged:
        raise AvailabilityConflict(conflicts)


def _or_404(queryset, pk, what: str = 'row'):
    try:
        return queryset.get(pk=pk)
    except ObjectDoesNotExist:        # a concurrent request deleted it between the view's lookup and the lock
        raise NotFound(f'This {what} no longer exists.') from None


def lock_teacher(teacher) -> None:
    """Serialise this tutor's schedule edits. Must run inside transaction.atomic()."""
    _or_404(TeacherProfile.objects.select_for_update(of=('self',)), teacher.pk, 'tutor profile')


def guard_timezone_change(user, new_timezone: str, acknowledged: bool) -> list:
    """A tutor moving their timezone shifts every weekly window in UTC. With confirmed future lessons that would fall outside
    the shifted hours: 409 (same contract as an availability edit) unless acknowledged. Call inside transaction.atomic()
    BEFORE saving the user; students and tutors without a profile or without such lessons are never affected."""
    profile = getattr(user, 'teacher_profile', None)
    if profile is None or new_timezone == user.timezone:
        return []
    lock_teacher(profile)
    conflicts = conflicts_for(profile, zone=get_zone(new_timezone))
    require_acknowledgement(conflicts, acknowledged)
    return conflicts


def _active_rows(teacher, *, exclude=None) -> list:
    return [r for r in teacher.availabilities.filter(is_active=True) if r.pk != exclude]


# ------------------------------------------------------------------ weekly rows
@transaction.atomic
def replace_weekly_matrix(teacher, rows: list, *, acknowledged: bool = False) -> Outcome:
    """Atomically swap the whole weekly matrix. `rows` are validated dicts (day_of_week, start_time, end_time[, is_active])."""
    lock_teacher(teacher)
    proposed = [TeacherAvailability(teacher=teacher, day_of_week=r['day_of_week'], start_time=r['start_time'],
                                    end_time=r['end_time'], is_active=r.get('is_active', True)) for r in rows]
    conflicts = conflicts_for(teacher, weekly=[p for p in proposed if p.is_active])
    require_acknowledgement(conflicts, acknowledged)
    teacher.availabilities.all().delete()
    TeacherAvailability.objects.bulk_create(proposed)
    return Outcome(list(teacher.availabilities.all()), conflicts)


def create_row(teacher, serializer) -> TeacherAvailability:
    """`serializer` was built with the tutor in its context; it is validated here, under the lock."""
    with transaction.atomic():
        lock_teacher(teacher)
        serializer.is_valid(raise_exception=True)
        return serializer.save(teacher=teacher)


def update_row(teacher, row: TeacherAvailability, serializer) -> Outcome:
    with transaction.atomic():
        lock_teacher(teacher)
        try:
            row.refresh_from_db()
        except ObjectDoesNotExist:
            raise NotFound('This row no longer exists.') from None
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        acknowledged = bool(data.pop('acknowledge_conflicts', False))
        merged = {name: data.get(name, getattr(row, name)) for name in ('day_of_week', 'start_time', 'end_time', 'is_active')}
        proposed = TeacherAvailability(id=row.pk, teacher=teacher, **merged)
        weekly = _active_rows(teacher, exclude=row.pk) + ([proposed] if proposed.is_active else [])
        conflicts = conflicts_for(teacher, weekly=weekly)
        require_acknowledgement(conflicts, acknowledged)
        for name, value in merged.items():
            setattr(row, name, value)
        row.save(update_fields=list(merged))
        return Outcome(row, conflicts)


def delete_row(teacher, row_id, *, acknowledged: bool) -> Outcome:
    with transaction.atomic():
        lock_teacher(teacher)
        row = _or_404(teacher.availabilities, row_id)
        conflicts = conflicts_for(teacher, weekly=_active_rows(teacher, exclude=row.pk))
        require_acknowledgement(conflicts, acknowledged)
        row.delete()
        return Outcome(None, conflicts)


# ------------------------------------------------------------------ time off
def create_time_off(teacher, data: dict, *, acknowledged: bool) -> Outcome:
    with transaction.atomic():
        lock_teacher(teacher)
        if teacher.time_off.filter(end_utc__gt=clock.now()).count() >= MAX_TIME_OFF_ROWS:
            raise serializers.ValidationError({'non_field_errors': [f'You can have at most {MAX_TIME_OFF_ROWS} upcoming time-off periods.']})
        proposed = TeacherTimeOff(teacher=teacher, **data)
        conflicts = conflicts_for(teacher, extra_time_off=[proposed])
        require_acknowledgement(conflicts, acknowledged)
        proposed.save()
        return Outcome(proposed, conflicts)


def delete_time_off(teacher, row_id) -> Outcome:
    with transaction.atomic():
        lock_teacher(teacher)
        _or_404(teacher.time_off, row_id).delete()      # ending an absence can only add hours: no conflicts
        return Outcome(None, [])


# ------------------------------------------------------------------ specific-date overrides
def create_override(teacher, data: dict, *, acknowledged: bool) -> Outcome:
    with transaction.atomic():
        lock_teacher(teacher)
        if teacher.date_overrides.filter(date__gte=_tutor_today(teacher)).count() >= MAX_OVERRIDE_ROWS:
            raise serializers.ValidationError({'non_field_errors': [f'You can have at most {MAX_OVERRIDE_ROWS} upcoming date overrides.']})
        proposed = TeacherDateOverride(teacher=teacher, **data)
        conflicts = conflicts_for(teacher, extra_overrides=[proposed])
        require_acknowledgement(conflicts, acknowledged)
        proposed.save()
        return Outcome(proposed, conflicts)


def delete_override(teacher, row_id, *, acknowledged: bool) -> Outcome:
    with transaction.atomic():
        lock_teacher(teacher)
        row = _or_404(teacher.date_overrides, row_id)
        conflicts = conflicts_for(teacher, drop_override=row.pk)      # removing extra hours can strand a lesson
        require_acknowledgement(conflicts, acknowledged)
        row.delete()
        return Outcome(None, conflicts)
