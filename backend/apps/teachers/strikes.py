"""
Tutor strikes (Task 9.6, decision D-6): a strike counts for STRIKE_WINDOW_DAYS (90) and STRIKE_LIMIT (3) of them inside that
window deactivate the tutor. Only an admin can reactivate: nothing here ever sets `is_active` back to True.

`TeacherProfile.sla_strikes` mirrors the windowed count so existing screens keep working; always change it through
`add_strike`, never by hand.
"""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.teachers.models import TeacherProfile, TeacherStrike


def active_strike_count(teacher, now=None) -> int:
    now = now or timezone.now()
    return TeacherStrike.objects.filter(teacher=teacher, created_at__gt=now - timedelta(days=settings.STRIKE_WINDOW_DAYS)).count()


def add_strike(teacher, kind: str, booking=None) -> int:
    """Record one strike (once per booking and kind) and return the tutor's strikes inside the window."""
    with transaction.atomic():
        locked = TeacherProfile.objects.select_for_update().get(pk=teacher.pk)
        if booking is not None:
            TeacherStrike.objects.get_or_create(teacher=locked, booking=booking, kind=kind)
        else:
            TeacherStrike.objects.create(teacher=locked, kind=kind)
        count = active_strike_count(locked)
        locked.sla_strikes = count
        fields = ['sla_strikes']
        if count >= settings.STRIKE_LIMIT and locked.is_active:
            locked.is_active = False
            fields.append('is_active')
        locked.save(update_fields=fields)
    teacher.sla_strikes, teacher.is_active = locked.sla_strikes, locked.is_active      # keep the caller's copy truthful
    return count
