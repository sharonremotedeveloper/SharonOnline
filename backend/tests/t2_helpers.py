"""Shared helpers of the slice T2 availability tests (plain functions; fixtures stay in each test module)."""
from datetime import datetime, time, timedelta, timezone as dt_tz
from zoneinfo import ZoneInfo

from rest_framework.test import APIClient

import factories as f
from apps.bookings.models import Booking
from apps.teachers.models import TeacherAvailability

SAST = ZoneInfo('Africa/Johannesburg')
BASE = '/api/v1/teachers/availability'


def client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def next_weekday_utc(weekday, hour, minute=0, min_days=3):
    day = (datetime.now(SAST) + timedelta(days=min_days)).date()
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return datetime.combine(day, time(hour, minute), SAST).astimezone(dt_tz.utc)


def lesson(tutor, student, start, status=Booking.Status.CONFIRMED):
    return f.make_booking(teacher=tutor, student=student, start=start, status=status)


def row(day=0, start='09:00', end='12:00', **extra):
    return {'day_of_week': day, 'start_time': start, 'end_time': end, **extra}


def monday_row(tutor):
    return TeacherAvailability.objects.get(teacher=tutor, day_of_week=0)
