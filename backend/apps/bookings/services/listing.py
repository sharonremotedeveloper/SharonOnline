"""Booking list: who may see which bookings, and the query-string filters (Task 9.5).

The scope (`scoped_bookings`) is applied first and the filters only ever narrow it, so no combination of query
parameters can reach another user's lessons.
"""
from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination

from apps.bookings.models import Booking
from apps.bookings.services.holds import live_hold_q

S = Booking.Status
# Statuses that can never be "upcoming": nothing is going to happen at that slot.
NOT_UPCOMING = (S.CANCELLED, S.PENDING_PAYMENT)
ORDERINGS = ('start_time_utc', '-start_time_utc')


class BookingPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def scoped_bookings(user):
    """A tutor sees the lessons they teach, anyone else the lessons they booked. A tutor account with no profile sees nothing."""
    qs = Booking.objects.select_related('teacher__user', 'student', 'material', 'memo')
    if user.role == 'teacher':
        profile = getattr(user, 'teacher_profile', None)
        return qs.filter(teacher=profile) if profile else qs.none()
    return qs.filter(student=user)


def _bound(value, *, end):
    """A date means the whole UTC day; a datetime is taken as given (naive = UTC). Both ends are inclusive."""
    day = parse_date(value) if len(value) <= 10 else None   # raises ValueError for e.g. 2025-13-45
    if day is not None:
        start = datetime.combine(day, time.min, tzinfo=dt_timezone.utc)
        return start + timedelta(days=1) - timedelta(microseconds=1) if end else start
    moment = parse_datetime(value)
    if moment is None:
        raise ValueError(value)
    return moment.replace(tzinfo=dt_timezone.utc) if timezone.is_naive(moment) else moment


class BookingListQuerySerializer(serializers.Serializer):
    """Validates the query string; unknown parameters (page, page_size) are ignored here."""
    status = serializers.CharField(required=False, allow_blank=True)
    when = serializers.ChoiceField(choices=('upcoming', 'past'), required=False)
    ordering = serializers.ChoiceField(choices=ORDERINGS, required=False)

    def to_internal_value(self, data):
        raw = dict(data.lists()) if hasattr(data, 'lists') else {k: [v] for k, v in data.items()}
        statuses, errors = [], {}
        for chunk in raw.get('status', []):
            statuses += [s.strip() for s in chunk.split(',') if s.strip()]
        bad = sorted(set(statuses) - set(S.values))
        if bad:
            errors['status'] = [f"Unknown status: {', '.join(bad[:3])}. Choose from: {', '.join(S.values)}."]

        flat = {k: raw[k][-1] for k in ('when', 'ordering') if k in raw}
        try:
            out = super().to_internal_value(flat)
        except serializers.ValidationError as exc:
            errors.update(exc.detail)
            out = {}

        bounds = {}
        for key in ('from', 'to'):
            value = (raw.get(key) or [''])[-1].strip()
            if not value:
                continue
            try:
                bounds[key] = _bound(value, end=(key == 'to'))
            except ValueError:
                errors[key] = ['Use a date (2026-10-05) or an ISO date-time (2026-10-05T09:00:00Z).']
        if not errors and 'from' in bounds and 'to' in bounds and bounds['from'] > bounds['to']:
            errors['to'] = ['"to" must not be before "from".']
        if errors:
            raise serializers.ValidationError(errors)

        out['statuses'] = sorted(set(statuses))
        out['start_from'], out['start_to'] = bounds.get('from'), bounds.get('to')
        return out


def filter_bookings(qs, params, now=None):
    """Narrow `qs` by validated `params`; returns (queryset, ordering)."""
    now = now or timezone.now()
    if params['statuses']:
        qs = qs.filter(status__in=params['statuses'])
    when = params.get('when')
    if when == 'upcoming':
        qs = qs.filter(end_time_utc__gt=now).filter(~Q(status__in=NOT_UPCOMING) | live_hold_q(now))
    elif when == 'past':
        qs = qs.filter(end_time_utc__lte=now)
    if params['start_from']:
        qs = qs.filter(start_time_utc__gte=params['start_from'])
    if params['start_to']:
        qs = qs.filter(start_time_utc__lte=params['start_to'])
    # Soonest first when looking ahead, newest first otherwise (the model default).
    ordering = params.get('ordering') or ('start_time_utc' if when == 'upcoming' else '-start_time_utc')
    return qs.order_by(ordering, 'id'), ordering
