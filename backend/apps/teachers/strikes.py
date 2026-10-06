"""
Tutor strikes (Task 9.6, decision D-6): a strike counts for STRIKE_WINDOW_DAYS (90) and STRIKE_LIMIT (3) of them inside that
window suspend the tutor (`approved -> suspended` through teachers/vetting.py, actor 'system:strikes'). Only an admin can
reinstate (`suspended -> approved` is a staff-only edge). A tutor who is not `approved` still gets the strike recorded, but
the status does not change (plan §3.1: strikes never raise, `suspended -> suspended` is a no-op).

`TeacherProfile.sla_strikes` mirrors the windowed count so existing screens keep working; always change it through
`add_strike`, never by hand.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.teachers.models import TeacherProfile, TeacherStrike
from apps.teachers.vetting import transition_teacher

logger = logging.getLogger(__name__)


def active_strike_count(teacher, now=None) -> int:
    now = now or timezone.now()
    return TeacherStrike.objects.filter(teacher=teacher, created_at__gt=now - timedelta(days=settings.STRIKE_WINDOW_DAYS)).count()


def _alert_lessons_need_action(teacher_id, booking_ids) -> None:
    """
    No admin is present at an automatic suspension: after commit, log an admin alert (ids only) that N1a will route as
    `admin:suspended-lessons:{teacher}`. The tutor also appears in the staff work queue
    (GET /admin/teachers/suspended-with-lessons/) until the lessons are cancelled (slice T1b).
    """
    ids = ','.join(str(b) for b in booking_ids)
    transaction.on_commit(lambda: logger.warning(
        '[ADMIN ALERT] tutor %s suspended by strikes with %d future lessons needing action: %s',
        teacher_id, len(booking_ids), ids))


def add_strike(teacher, kind: str, booking=None) -> int:
    """Record one strike (once per booking and kind) and return the tutor's strikes inside the window."""
    with transaction.atomic():
        locked = TeacherProfile.objects.select_for_update().only('id', 'status', 'user_id', 'sla_strikes').get(pk=teacher.pk)
        if booking is not None:
            strike, _ = TeacherStrike.objects.get_or_create(teacher=locked, booking=booking, kind=kind)
        else:
            strike = TeacherStrike.objects.create(teacher=locked, kind=kind)
        count = active_strike_count(locked)
        locked.sla_strikes = count
        locked.save(update_fields=['sla_strikes'])
        from apps.notifications.service import notify
        notify(locked.user, 'strike_issued', key=f'strike:{strike.id}',
               payload={'strike_kind': str(kind), 'total_strikes': count}, booking=booking)
        if count >= settings.STRIKE_LIMIT and locked.status == TeacherProfile.Status.APPROVED:
            result = transition_teacher(locked, TeacherProfile.Status.SUSPENDED, actor='system:strikes',
                                        reason=f'{count} strikes inside {settings.STRIKE_WINDOW_DAYS} days')
            if result.affected_booking_ids:
                _alert_lessons_need_action(locked.pk, result.affected_booking_ids)
    teacher.refresh_from_db(fields=['sla_strikes', 'status', 'is_verified', 'is_active'])   # keep the caller's copy truthful
    return count
