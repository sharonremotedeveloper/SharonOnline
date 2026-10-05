"""The single place that builds a lesson's join link (Video SDK direction, D-9).

Mails, reminders, calendar events and the frontend all use this; none may use `zoom_join_url`/`zoom_start_url`
(legacy Meetings fields, retired in slice V5). Links come from FRONTEND_BASE_URL, never from request data.
"""
from django.conf import settings

_ROLE_TREES = {'student': 'student', 'teacher': 'teacher'}


def classroom_path(booking, role):
    try:
        tree = _ROLE_TREES[role]
    except KeyError:
        raise ValueError(f"Unknown classroom role: {role!r}") from None
    return f'/{tree}/classroom/{booking.id}'


def classroom_url(booking, role):
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}{classroom_path(booking, role)}"
