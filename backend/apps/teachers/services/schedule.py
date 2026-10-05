"""
A tutor's open hours as one value (T2, plan 3.5): weekly rows + specific-date overrides (INV TEA-03) + time off, read in the
tutor's own timezone with `zoneinfo`.

Used by BOTH the slot generator (which hours exist) and the conflict check (which confirmed lessons would be stranded by a
proposed change), so the two can never disagree. A `SchedulePlan` can be built from the database or from a proposal
(unsaved model instances), which is how "what if I saved this?" is answered without writing anything.

DST rule (the bug fix): every wall-clock time is converted on its own from NAIVE local time. A local time that does not
exist (spring forward) yields no slot; an ambiguous one (fall back) takes its first occurrence. Never add a timedelta to
an aware local datetime and never use pytz.
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone as dt_tz
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from apps.common import clock
from apps.common.timezones import get_zone

logger = logging.getLogger(__name__)
UTC = dt_tz.utc
Window = tuple  # (start: time, end: time) in the tutor's local clock


class InvalidTeacherTimezone(Exception):
    """The tutor's stored timezone is not an IANA zone. Carries ids only (they are what gets logged)."""

    def __init__(self, teacher_id, user_id):
        super().__init__('invalid teacher timezone')
        self.teacher_id, self.user_id = teacher_id, user_id


def teacher_zone(teacher) -> ZoneInfo:
    try:
        return get_zone(teacher.user.timezone)
    except ValueError:
        raise InvalidTeacherTimezone(teacher.id, teacher.user_id) from None


def local_to_utc(day: date, at: time, zone: ZoneInfo) -> Optional[datetime]:
    """Naive local wall time -> UTC. None when that wall time does not exist; the first occurrence when it is ambiguous."""
    naive = datetime.combine(day, at)
    utc = naive.replace(tzinfo=zone, fold=0).astimezone(UTC)
    return utc if utc.astimezone(zone).replace(tzinfo=None) == naive else None


def boundary_utc(day: date, at: time, zone: ZoneInfo) -> datetime:
    """A window EDGE as an instant: like local_to_utc, but a time inside a gap maps to the instant the gap starts at."""
    return datetime.combine(day, at).replace(tzinfo=zone, fold=0).astimezone(UTC)


def _merge(windows: Iterable[Window]) -> list:
    merged = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _subtract(window: Window, cuts: Iterable[Window]) -> list:
    pieces = [window]
    for cut_start, cut_end in cuts:
        remaining = []
        for start, end in pieces:
            if cut_end <= start or cut_start >= end:
                remaining.append((start, end))
                continue
            if start < cut_start:
                remaining.append((start, cut_start))
            if cut_end < end:
                remaining.append((cut_end, end))
        pieces = remaining
    return pieces


@dataclass
class SchedulePlan:
    zone: ZoneInfo
    weekly: dict = field(default_factory=dict)         # weekday -> [Window]
    opens: dict = field(default_factory=dict)          # date -> [Window]
    closed_days: set = field(default_factory=set)      # dates closed entirely
    closed: dict = field(default_factory=dict)         # date -> [Window] removed
    time_off: list = field(default_factory=list)       # [(start_utc, end_utc)]

    def raw_windows(self, day: date) -> list:
        """The windows slots are generated from (not merged, so an off-grid row keeps its own grid)."""
        if day in self.closed_days:
            return []
        cuts = self.closed.get(day, [])
        out = []
        for window in self.weekly.get(day.weekday(), []) + self.opens.get(day, []):
            out.extend(_subtract(window, cuts))
        return out

    def covered_utc(self, day: date) -> list:
        """The day's open hours as merged UTC intervals (a lesson spanning two touching rows is still covered)."""
        return [(boundary_utc(day, s, self.zone), boundary_utc(day, e, self.zone)) for s, e in _merge(self.raw_windows(day))]

    def blocked(self, start: datetime, end: datetime) -> bool:
        return any(s < end and e > start for s, e in self.time_off)

    def covers(self, start: datetime, end: datetime) -> bool:
        """True when [start, end) lies inside open hours and clear of time off."""
        if self.blocked(start, end):
            return False
        local_day = start.astimezone(self.zone).date()
        for day in (local_day - timedelta(days=1), local_day, local_day + timedelta(days=1)):
            if any(s <= start and e >= end for s, e in self.covered_utc(day)):
                return True
        return False


def build_plan(zone: ZoneInfo, weekly_rows: Iterable, override_rows: Iterable, time_off_rows: Iterable) -> SchedulePlan:
    """Rows are TeacherAvailability / TeacherDateOverride / TeacherTimeOff instances (saved or not)."""
    plan = SchedulePlan(zone=zone)
    for row in weekly_rows:
        if row.is_active:
            plan.weekly.setdefault(row.day_of_week, []).append((row.start_time, row.end_time))
    for row in override_rows:
        if row.kind == 'open':
            plan.opens.setdefault(row.date, []).append((row.start_time, row.end_time))
        elif row.start_time is None:
            plan.closed_days.add(row.date)
        else:
            plan.closed.setdefault(row.date, []).append((row.start_time, row.end_time))
    plan.time_off = [(row.start_utc, row.end_utc) for row in time_off_rows]
    return plan


def load_plan(teacher, zone: ZoneInfo, *, weekly_rows=None, override_rows=None, time_off_rows=None, since: date = None) -> SchedulePlan:
    """The tutor's plan from the database; any component can be replaced by a proposal (an iterable of unsaved rows)."""
    since = since or clock.now().astimezone(zone).date() - timedelta(days=1)
    if weekly_rows is None:
        weekly_rows = teacher.availabilities.filter(is_active=True)
    if override_rows is None:
        override_rows = teacher.date_overrides.filter(date__gte=since)
    if time_off_rows is None:
        time_off_rows = teacher.time_off.filter(end_utc__gt=clock.now() - timedelta(days=1))
    return build_plan(zone, weekly_rows, override_rows, time_off_rows)


def lesson_conflicts(teacher, plan: SchedulePlan, now: datetime = None) -> list:
    """Confirmed, not-yet-finished lessons that `plan` would leave outside the tutor's open hours."""
    from apps.bookings.models import Booking          # lazy: bookings.models imports teachers.models
    now = now or clock.now()
    lessons = (Booking.objects.filter(teacher=teacher, status=Booking.Status.CONFIRMED, end_time_utc__gt=now)
               .order_by('start_time_utc').values_list('id', 'start_time_utc', 'end_time_utc'))
    return [{'booking_id': str(pk), 'start_time_utc': start.isoformat(), 'end_time_utc': end.isoformat()}
            for pk, start, end in lessons if not plan.covers(start, end)]
