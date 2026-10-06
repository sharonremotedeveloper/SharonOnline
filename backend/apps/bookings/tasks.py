import logging
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from celery import shared_task

from apps.bookings.models import Booking, LessonMemo
from apps.bookings.services.attendance_probe import (
    adjudicate_t10, dispute_without_verdict, end_of_window_reason, probe_t10_candidates,
)
from apps.bookings.services.holds import live_hold_q
from apps.bookings.services.lock_service import release_slot_lock
from apps.bookings.services.state_machine import InvalidTransition, transition_booking
from apps.payments.services.credits import grant_credit
from apps.teachers.models import TeacherStrike
from apps.teachers.strikes import add_strike
from apps.payments.services.settlement import successful_transaction
from apps.payments.services.funding import funding_for_settlement
from apps.payments.models import CreditWalletEntry
from apps.common.locks import distributed_task_lock
from apps.integrations.services.attendance import (
    TEACHER, credited_attendance_minutes, present_with_disconnect_grace,
)
from apps.notifications.alerts import alert_staff
from apps.notifications.service import booking_key, notify

logger = logging.getLogger(__name__)


@shared_task(name='apps.bookings.tasks.purge_expired_reservations_task')
@distributed_task_lock('lock:beat:purge_expired_reservations', timeout_seconds=50)
def purge_expired_reservations_task():
    """
    Periodic task running every 60s:
    Finds PENDING_PAYMENT bookings that no longer hold their slot (services.holds.live_hold_q: the 10-minute window has
    passed AND no payment is in flight), atomically transitions them to CANCELLED, and clears the Redis slot lock so the
    inventory is freed immediately. A booking whose customer is mid-payment is left alone until the gateway answers or the
    grace/hard cap runs out (Task 9.4); rows locked by a payment webhook are skipped this round.
    """
    now = timezone.now()
    purged_count = 0

    with transaction.atomic():
        expired_bookings = list(
            Booking.objects.select_for_update(skip_locked=True, of=('self',))
            .filter(status=Booking.Status.PENDING_PAYMENT)
            .exclude(live_hold_q(now))[:100]
        )

        for booking in expired_bookings:
            try:
                result = transition_booking(booking, Booking.Status.CANCELLED,
                                            actor='system:purge_expired_reservations', reason='10-minute hold expired')
            except InvalidTransition:
                continue  # paid/changed since the candidate query: leave it alone
            if not result.changed:
                continue

            # Free Redis pessimistic slot lock
            start_iso = booking.start_time_utc.isoformat()
            release_slot_lock(str(booking.teacher.id), start_iso, str(booking.student.id),
                              token=booking.slot_lock_token or None)

            purged_count += 1
            logger.info(
                f"Purged expired reservation for booking={booking.id}, "
                f"teacher={booking.teacher.id}, slot={start_iso}"
            )

    return {"purged_count": purged_count}


@shared_task(name='apps.bookings.tasks.purge_attendance_payloads_task')
@distributed_task_lock('lock:beat:purge_attendance_payloads', timeout_seconds=800)
def purge_attendance_payloads_task():
    from .retention import purge_attendance_payloads
    return purge_attendance_payloads()


@shared_task(name='apps.bookings.tasks.audit_attendance_and_noshows_task')
def audit_attendance_and_noshows_task():
    """
    Periodic task running every 60s:
    1. At T+5m: Evaluates teacher presence. If tutor hasn't joined, flags an alert.
    2. At T+10m: Adjudicates no-show conditions (services/attendance_probe.py):
       - Teacher absent and Zoom says the room never started: TEACHER_NO_SHOW, 100% refund + 1 bonus credit, strike.
       - Zoom status unknown: deferred to the next run; no meeting id at all: DISPUTED (never a no-show).
       - Student absent (tutor present): Sets STUDENT_NO_SHOW, tutor gets full lesson fee, student credit forfeited.
    3. At T+25m+: Verifies lesson completion based on attendance minutes (>=20m).
    The Zoom HTTP probes run first, holding no database lock and no task lock (bounded by ATTENDANCE_PROBE_BUDGET_SECONDS).
    """
    now = timezone.now()
    return _audit_attendance_locked(now, probe_t10_candidates(now))


@distributed_task_lock('lock:beat:audit_attendance_and_noshows', timeout_seconds=50)
def _audit_attendance_locked(now, probes):
    results = {
        "late_alerts": 0,
        "teacher_no_shows": 0,
        "student_no_shows": 0,
        "completed_sessions": 0,
    }
    _flag_late_tutors(now, results)                 # 1. T+5m
    # 2. T+10m No-Show Adjudication (row lock + status re-check per booking; the probes ran before, lock-free)
    adjudicate_t10(now, probes, results)
    _close_ended_lessons(now, results)              # 3. lesson end
    return results


def _flag_late_tutors(now, results):
    # 1. T+5m Tutor Lateness Check
    t5_window_start = now - timedelta(minutes=10)
    t5_window_end = now - timedelta(minutes=5)
    late_candidates = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        start_time_utc__gte=t5_window_start,
        start_time_utc__lte=t5_window_end,
        tutor_late_alert_sent=False
    ).select_related('teacher__user', 'student')

    for booking in late_candidates:
        has_joined = present_with_disconnect_grace(booking, TEACHER, now)

        if not has_joined:
            booking.tutor_late_alert_sent = True
            booking.save(update_fields=['tutor_late_alert_sent', 'updated_at'])
            results["late_alerts"] += 1
            notify(booking.student, 'tutor_late_warning', key=booking_key('late', booking, 'student'),
                   payload={'booking_id': str(booking.id)}, booking=booking)
            alert_staff('tutor_late', key=f'admin:tutor-late:{booking.id}:{booking.reschedule_count}',
                        payload={'booking_id': str(booking.id), 'tutor_id': str(booking.teacher.id)})
            logger.warning(
                f"[RADAR ALERT] Tutor is 5+ minutes late for booking {booking.id}!"
            )


def _close_ended_lessons(now, results):
    # 3. Lesson End Dwell-Time Evaluation (T+25m)
    ended_candidates = Booking.objects.filter(
        status__in=[Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS],
        end_time_utc__lte=now
    ).select_related('teacher__user')

    for candidate in ended_candidates:
        with transaction.atomic():
            booking = Booking.objects.select_for_update().filter(id=candidate.id).first()
            if not booking or booking.status not in [Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS]:
                continue

            teacher_minutes = credited_attendance_minutes(booking, TEACHER, through=booking.end_time_utc)

            if teacher_minutes >= settings.LESSON_DELIVERED_MIN_TEACHER_MINUTES:
                transition_booking(booking, Booking.Status.COMPLETED_PENDING_MEMO,
                                   actor='system:attendance_audit', reason=f'teacher attended {teacher_minutes}m')
                results["completed_sessions"] += 1
                logger.info(
                    f"Booking {booking.id} verified with {teacher_minutes}m attendance -> COMPLETED_PENDING_MEMO."
                )
            elif booking.status == Booking.Status.CONFIRMED:
                # Never adjudicated (no meeting, or the Zoom probe stayed unknown): a human decides, nobody is scored.
                dispute_without_verdict(booking, end_of_window_reason(booking))
            else:
                # Less than 20 minutes without prior excused power outage report
                transition_booking(booking, Booking.Status.DISPUTED,
                                   actor='system:attendance_audit', reason=f'teacher attended only {teacher_minutes}m (<20m)')
                logger.warning(
                    f"Booking {booking.id} held in DISPUTED: teacher only logged {teacher_minutes}m (required: 20m)."
                )


@shared_task(name='apps.bookings.tasks.dispatch_pre_lesson_reminders_task')
@distributed_task_lock('lock:beat:dispatch_pre_lesson_reminders', timeout_seconds=240)
def dispatch_pre_lesson_reminders_task():
    """
    Periodic task running every 5 minutes:
    Dispatches automated pre-lesson reminders across 3 key time windows:
    1. T-24h Window: Calendar checklist and timezone verification.
    2. T-1h Window: WebRTC hardware AV preview test reminder.
    3. T-10m Window: High-priority lesson staging reminder with 1-click Zoom link.
    """
    now = timezone.now()
    dispatched = {"reminders_24h": 0, "reminders_1h": 0, "reminders_10m": 0}

    # 1. T-24h Reminders (Window: 23h50m to 24h10m ahead)
    t24_start = now + timedelta(hours=23, minutes=50)
    t24_end = now + timedelta(hours=24, minutes=10)
    bookings_24h = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        start_time_utc__gte=t24_start,
        start_time_utc__lte=t24_end,
        reminder_24h_sent=False
    ).select_related('student', 'teacher__user')

    for booking in bookings_24h:
        booking.reminder_24h_sent = True
        booking.save(update_fields=['reminder_24h_sent', 'updated_at'])
        dispatched["reminders_24h"] += 1
        notify(booking.student, 'reminder_24h', key=booking_key('reminder:24h', booking, 'student'),
               payload={'booking_id': str(booking.id)}, booking=booking)
        logger.info(f"Dispatched T-24h reminder for booking {booking.id}")

    # 2. T-1h Reminders (Window: 50m to 70m ahead)
    t1_start = now + timedelta(minutes=50)
    t1_end = now + timedelta(minutes=70)
    bookings_1h = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        start_time_utc__gte=t1_start,
        start_time_utc__lte=t1_end,
        reminder_1h_sent=False
    ).select_related('student', 'teacher__user')

    for booking in bookings_1h:
        booking.reminder_1h_sent = True
        booking.save(update_fields=['reminder_1h_sent', 'updated_at'])
        dispatched["reminders_1h"] += 1
        notify(booking.student, 'reminder_1h', key=booking_key('reminder:1h', booking, 'student'),
               payload={'booking_id': str(booking.id)}, booking=booking)
        notify(booking.teacher.user, 'reminder_1h', key=booking_key('reminder:1h', booking, 'teacher'),
               payload={'booking_id': str(booking.id)}, booking=booking)
        logger.info(f"Dispatched T-1h AV reminder for booking {booking.id}")

    # 3. T-10m Reminders (Window: 5m to 15m ahead)
    t10_start = now + timedelta(minutes=5)
    t10_end = now + timedelta(minutes=15)
    bookings_10m = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        start_time_utc__gte=t10_start,
        start_time_utc__lte=t10_end,
        reminder_10m_sent=False
    ).select_related('student', 'teacher__user')

    for booking in bookings_10m:
        booking.reminder_10m_sent = True
        booking.save(update_fields=['reminder_10m_sent', 'updated_at'])
        dispatched["reminders_10m"] += 1
        notify(booking.student, 'reminder_10m', key=booking_key('reminder:10m', booking, 'student'),
               payload={'booking_id': str(booking.id)}, booking=booking)
        notify(booking.teacher.user, 'reminder_10m', key=booking_key('reminder:10m', booking, 'teacher'),
               payload={'booking_id': str(booking.id)}, booking=booking)
        logger.info(f"Dispatched T-10m Zoom launch reminder for booking {booking.id}")

    return dispatched


@shared_task(name='apps.bookings.tasks.enforce_memo_sla_task')
@distributed_task_lock('lock:beat:enforce_memo_sla', timeout_seconds=800)
def enforce_memo_sla_task():
    """
    Periodic task running every 15 minutes:
    Enforces post-lesson feedback memo deadlines:
    1. At T+12h: Dispatches warning reminder to tutor if memo not yet submitted.
    2. At T+24h: Forfeits the memo (COMPLETED_MEMO_FORFEITED), records an SLA strike on tutor,
       and compensates student with 1 complimentary credit.
    """
    now = timezone.now()
    results = {"reminders_sent": 0, "memos_forfeited": 0}

    # Window A: T+12h to T+24h Warning
    w_12h = now - timedelta(hours=12)
    w_24h = now - timedelta(hours=24)

    pending_12h = Booking.objects.filter(
        status__in=[Booking.Status.COMPLETED, Booking.Status.COMPLETED_PENDING_MEMO],
        end_time_utc__lte=w_12h,
        end_time_utc__gt=w_24h,
        memo__isnull=True,
        memo_reminder_sent=False
    ).select_related('teacher__user')

    for booking in pending_12h:
        booking.memo_reminder_sent = True
        booking.save(update_fields=['memo_reminder_sent', 'updated_at'])
        results["reminders_sent"] += 1
        notify(booking.teacher.user, 'memo_reminder_12h', key=f'memo-warn:{booking.id}',
               payload={'booking_id': str(booking.id)}, booking=booking)
        logger.warning(
            f"[SLA WARNING] 12h elapsed since lesson {booking.id}. Reminder dispatched."
        )

    # Window B: T+24h SLA Breach & Forfeiture
    breached_24h = Booking.objects.filter(
        status__in=[Booking.Status.COMPLETED, Booking.Status.COMPLETED_PENDING_MEMO],
        end_time_utc__lte=w_24h,
        memo__isnull=True
    ).select_related('teacher__user', 'student')

    for booking in breached_24h:
        with transaction.atomic():
            # Re-check under the row lock: a memo (or an escrow-release status change) may have landed since the query.
            fresh = Booking.objects.select_for_update().get(pk=booking.pk)
            if LessonMemo.objects.filter(booking=fresh).exists():
                continue
            try:
                result = transition_booking(booking, Booking.Status.COMPLETED_MEMO_FORFEITED,
                                            actor='system:memo_sla', reason='memo not submitted within 24h')
            except InvalidTransition:
                continue
            if not result.changed:
                continue

            # Log strike on teacher (windowed, see apps/teachers/strikes.py)
            teacher = booking.teacher
            add_strike(teacher, TeacherStrike.Kind.MEMO_SLA, booking=booking)

            funding = funding_for_settlement(booking, context='memo_sla_compensation')
            if funding is None:
                logger.error('Memo SLA compensation stopped for booking %s: missing funding.', booking.id)
                continue
            # Compensate student with 1 free apology credit valued from the booking's immutable funding.
            from apps.payments.models import CreditBundle
            grant_credit(
                booking.student, credits=1, pack_name='Memo SLA apology credit', source=CreditBundle.Source.BONUS,
                unit_amount=funding.captured_amount, currency=funding.currency,
                fx_rate_to_zar=funding.fx_rate_to_zar, fx_source=funding.fx_source,
                booking=booking, idempotency_key=f'memo-sla:{booking.id}',
            )

            # Record platform-absorbed compensation entry
            from apps.payments.services.ledger_service import record_compensation_entry
            record_compensation_entry(
                user=booking.student,
                booking=booking,
                reason="Tutor 24h memo SLA forfeiture compensation"
            )

            results["memos_forfeited"] += 1
            logger.error(
                f"[SLA BREACH] 24h expired on booking {booking.id} without memo. "
                f"Tutor {teacher.user.username} penalized (strike={teacher.sla_strikes}). "
                f"Student {booking.student.username} compensated 1 credit."
            )

    return results
