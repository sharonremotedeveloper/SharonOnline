import pytest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.utils import timezone
from django.core.cache import cache

from apps.bookings.models import Booking, AttendanceAudit
from apps.bookings.services.lock_service import acquire_slot_lock, is_slot_locked
from apps.payments.models import PaymentTransaction, CreditBundle, GatewayAnomaly, RefundRequest
from apps.payments.services.funding import ensure_gateway_funding
from apps.admin_api.models import DisputeCase
from apps.teachers.models import TeacherProfile

from apps.bookings.tasks import (
    purge_expired_reservations_task,
    audit_attendance_and_noshows_task,
    dispatch_pre_lesson_reminders_task,
    enforce_memo_sla_task,
)
from apps.payments.tasks import (
    release_cleared_escrow_task,
    reconcile_pending_transactions_task,
)
from apps.integrations.tasks import sync_eskom_stages_task
from test_f0_fulfilment_probe import open_room, student_joined
from apps.common.locks import distributed_task_lock


@pytest.mark.django_db
class TestCeleryBeatAutomation:

    def test_purge_expired_reservations_task(self, teacher_user, student_user):
        """
        Verify that PENDING_PAYMENT reservations older than 10 minutes
        are cancelled and their Redis slot locks are released.
        """
        now = timezone.now()
        slot_time = now + timedelta(days=1)
        slot_iso = slot_time.isoformat()

        # Acquire lock in Redis
        acquire_slot_lock(str(teacher_user.id), slot_iso, str(student_user.id))
        assert is_slot_locked(str(teacher_user.id), slot_iso) is True

        # Expired booking (created 12 minutes ago)
        expired_booking = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=slot_time,
            end_time_utc=slot_time + timedelta(minutes=25),
            status=Booking.Status.PENDING_PAYMENT,
        )
        Booking.objects.filter(id=expired_booking.id).update(created_at=now - timedelta(minutes=12))

        # Recent booking (created 3 minutes ago)
        recent_slot = now + timedelta(days=2)
        recent_booking = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=recent_slot,
            end_time_utc=recent_slot + timedelta(minutes=25),
            status=Booking.Status.PENDING_PAYMENT,
        )
        Booking.objects.filter(id=recent_booking.id).update(created_at=now - timedelta(minutes=3))

        # Run reaper task
        res = purge_expired_reservations_task()
        assert res["purged_count"] >= 1

        expired_booking.refresh_from_db()
        assert expired_booking.status == Booking.Status.CANCELLED
        # Lock should be freed
        assert is_slot_locked(str(teacher_user.id), slot_iso) is False

        # Recent booking must remain unaffected
        recent_booking.refresh_from_db()
        assert recent_booking.status == Booking.Status.PENDING_PAYMENT

    def test_release_cleared_escrow_task_dual_verified(self, teacher_user, student_user):
        """
        Verify 24h dual verification:
        Both 24 hours elapsed and verified attendance (>=20m) required for escrow release.
        """
        now = timezone.now()
        lesson_start = now - timedelta(hours=26)
        lesson_end = lesson_start + timedelta(minutes=25)

        booking = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=lesson_start,
            end_time_utc=lesson_end,
            status=Booking.Status.COMPLETED_PENDING_MEMO,
        )
        # Successful payment transaction
        tx = PaymentTransaction.objects.create(
            booking=booking,
            gateway=PaymentTransaction.Gateway.PAYFAST,
            gateway_reference="tx-escrow-001",
            amount=Decimal('9.00'),
            currency='USD',
            status=PaymentTransaction.Status.SUCCESS,
            escrow_cleared=False,
        )

        # Attendance of 22 minutes
        AttendanceAudit.objects.create(
            booking=booking,
            participant_email=teacher_user.user.email,
            join_time_utc=lesson_start,
            leave_time_utc=lesson_start + timedelta(minutes=22),
            total_minutes=22
        )

        # Execute escrow release
        res = release_cleared_escrow_task()
        assert res["cleared_count"] >= 1

        booking.refresh_from_db()
        tx.refresh_from_db()

        assert booking.escrow_cleared_at is not None
        assert booking.status == Booking.Status.COMPLETED
        assert tx.escrow_cleared is True

    def test_escrow_hold_prevented_by_open_dispute(self, teacher_user, student_user):
        """
        Active student dispute halts escrow clearance even if 24h elapsed and attendance is verified.
        """
        now = timezone.now()
        lesson_start = now - timedelta(hours=26)
        lesson_end = lesson_start + timedelta(minutes=25)

        booking = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=lesson_start,
            end_time_utc=lesson_end,
            status=Booking.Status.COMPLETED,
        )

        tx = PaymentTransaction.objects.create(
            booking=booking,
            gateway=PaymentTransaction.Gateway.PAYPAL,
            gateway_reference="tx-dispute-001",
            amount=Decimal('9.00'),
            currency='USD',
            status=PaymentTransaction.Status.SUCCESS,
            escrow_cleared=False,
        )

        AttendanceAudit.objects.create(
            booking=booking,
            participant_email=teacher_user.user.email,
            join_time_utc=lesson_start,
            total_minutes=25
        )

        # Open dispute
        DisputeCase.objects.create(
            booking=booking,
            student=student_user,
            teacher=teacher_user,
            student_statement="Audio kept cutting out",
            status=DisputeCase.Status.OPEN
        )

        release_cleared_escrow_task()

        booking.refresh_from_db()
        tx.refresh_from_db()

        assert booking.escrow_cleared_at is None
        assert tx.escrow_cleared is False

    def test_escrow_hold_prevented_by_insufficient_attendance(self, teacher_user, student_user):
        """
        Teacher attendance < 20 minutes prevents automatic escrow release.
        """
        now = timezone.now()
        lesson_start = now - timedelta(hours=26)
        lesson_end = lesson_start + timedelta(minutes=25)

        booking = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=lesson_start,
            end_time_utc=lesson_end,
            status=Booking.Status.COMPLETED,
        )

        tx = PaymentTransaction.objects.create(
            booking=booking,
            gateway=PaymentTransaction.Gateway.PAYPAL,
            gateway_reference="tx-low-dwell-001",
            amount=Decimal('9.00'),
            status=PaymentTransaction.Status.SUCCESS,
            escrow_cleared=False,
        )

        # Only 10 minutes attendance logged
        AttendanceAudit.objects.create(
            booking=booking,
            participant_email=teacher_user.user.email,
            join_time_utc=lesson_start,
            total_minutes=10
        )

        release_cleared_escrow_task()

        booking.refresh_from_db()
        tx.refresh_from_db()

        assert booking.escrow_cleared_at is None
        assert tx.escrow_cleared is False

    def test_enforce_memo_sla_12h_warning(self, teacher_user, student_user):
        """
        At T+12h post-lesson without memo, warning reminder is dispatched.
        """
        now = timezone.now()
        lesson_start = now - timedelta(hours=14)
        lesson_end = lesson_start + timedelta(minutes=25)

        booking = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=lesson_start,
            end_time_utc=lesson_end,
            status=Booking.Status.COMPLETED_PENDING_MEMO,
            memo_reminder_sent=False,
        )

        res = enforce_memo_sla_task()
        assert res["reminders_sent"] >= 1

        booking.refresh_from_db()
        assert booking.memo_reminder_sent is True
        assert booking.status == Booking.Status.COMPLETED_PENDING_MEMO

    def test_enforce_memo_sla_24h_breach_and_compensation(self, teacher_user, student_user):
        """
        At T+24h post-lesson without memo, memo is forfeited, tutor receives strike,
        and student is awarded 1 compensation credit.
        """
        now = timezone.now()
        lesson_start = now - timedelta(hours=26)
        lesson_end = lesson_start + timedelta(minutes=25)

        booking = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=lesson_start,
            end_time_utc=lesson_end,
            status=Booking.Status.COMPLETED_PENDING_MEMO,
        )
        tx = PaymentTransaction.objects.create(
            booking=booking,
            gateway=PaymentTransaction.Gateway.PAYFAST,
            gateway_reference="tx-memo-sla-compensation",
            amount=Decimal("9.00"),
            currency="USD",
            status=PaymentTransaction.Status.SUCCESS,
        )
        ensure_gateway_funding(tx, booking)

        teacher_user.sla_strikes = 0
        teacher_user.save()

        initial_credits = CreditBundle.objects.filter(user=student_user).first()
        initial_count = initial_credits.remaining_credits if initial_credits else 0

        res = enforce_memo_sla_task()
        assert res["memos_forfeited"] >= 1

        booking.refresh_from_db()
        teacher_user.refresh_from_db()

        assert booking.status == Booking.Status.COMPLETED_MEMO_FORFEITED
        assert teacher_user.sla_strikes == 1

        bundle = CreditBundle.objects.get(user=student_user)
        assert bundle.remaining_credits == initial_count + 1

    def test_audit_attendance_t5_late_alert(self, teacher_user, student_user):
        """
        At T+5m past start time, if tutor is not logged in attendance, tutor_late_alert_sent is flagged.
        """
        now = timezone.now()
        start_time = now - timedelta(minutes=7)
        end_time = start_time + timedelta(minutes=25)

        booking = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=start_time,
            end_time_utc=end_time,
            status=Booking.Status.CONFIRMED,
            tutor_late_alert_sent=False
        )

        res = audit_attendance_and_noshows_task()
        assert res["late_alerts"] >= 1

        booking.refresh_from_db()
        assert booking.tutor_late_alert_sent is True

    def test_audit_attendance_t10_teacher_no_show(self, teacher_user, student_user, fake_daily):
        """
        At T+10m past start time, absent teacher triggers TEACHER_NO_SHOW,
        reliability strike, and 2 credits (refund + bonus) for student.
        """
        now = timezone.now()
        start_time = now - timedelta(minutes=15)
        end_time = start_time + timedelta(minutes=25)

        booking = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=start_time,
            end_time_utc=end_time,
            status=Booking.Status.CONFIRMED,
        )
        student_joined(booking)                        # no student join = no evidence the room was open: never a no-show (V4)
        open_room(fake_daily, booking, student_user.id)
        tx = PaymentTransaction.objects.create(
            booking=booking,
            gateway=PaymentTransaction.Gateway.PAYFAST,
            gateway_reference="tx-teacher-no-show-compensation",
            amount=Decimal("9.00"),
            currency="USD",
            status=PaymentTransaction.Status.SUCCESS,
        )
        ensure_gateway_funding(tx, booking)

        teacher_user.sla_strikes = 0
        teacher_user.save()

        # Daily positively reports the tutor is not in the room the student joined (only then is the tutor scored absent)
        res = audit_attendance_and_noshows_task()
        assert res["teacher_no_shows"] >= 1

        booking.refresh_from_db()
        teacher_user.refresh_from_db()

        assert booking.status == Booking.Status.TEACHER_NO_SHOW
        assert teacher_user.sla_strikes == 1

        # D-6: the captured payment goes back through the gateway; the apology is 1 bonus credit (not a second refund)
        assert RefundRequest.objects.get(booking=booking).reason == 'teacher_no_show'
        lots = CreditBundle.objects.filter(user=student_user)
        assert [(l.source, l.remaining_credits, l.unit_amount) for l in lots] == [('bonus', 1, Decimal('9.00'))]

    def test_audit_attendance_t10_student_no_show(self, teacher_user, student_user):
        """
        At T+10m past start time, present teacher and absent student triggers STUDENT_NO_SHOW.
        """
        now = timezone.now()
        start_time = now - timedelta(minutes=15)
        end_time = start_time + timedelta(minutes=25)

        booking = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=start_time,
            end_time_utc=end_time,
            status=Booking.Status.CONFIRMED,
        )

        # Teacher present
        AttendanceAudit.objects.create(
            booking=booking,
            participant_email=teacher_user.user.email,
            join_time_utc=start_time,
            total_minutes=15
        )

        res = audit_attendance_and_noshows_task()
        assert res["student_no_shows"] >= 1

        booking.refresh_from_db()
        assert booking.status == Booking.Status.STUDENT_NO_SHOW

    def test_dispatch_pre_lesson_reminders(self, teacher_user, student_user):
        """
        Verifies multi-stage pre-lesson reminder dispatch (T-24h, T-1h, T-10m).
        """
        now = timezone.now()

        b_24h = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=now + timedelta(hours=24),
            end_time_utc=now + timedelta(hours=24, minutes=25),
            status=Booking.Status.CONFIRMED,
        )

        b_1h = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=now + timedelta(minutes=60),
            end_time_utc=now + timedelta(minutes=85),
            status=Booking.Status.CONFIRMED,
        )

        b_10m = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=now + timedelta(minutes=10),
            end_time_utc=now + timedelta(minutes=35),
            status=Booking.Status.CONFIRMED,
        )

        res = dispatch_pre_lesson_reminders_task()
        assert res["reminders_24h"] >= 1
        assert res["reminders_1h"] >= 1
        assert res["reminders_10m"] >= 1

        b_24h.refresh_from_db()
        b_1h.refresh_from_db()
        b_10m.refresh_from_db()

        assert b_24h.reminder_24h_sent is True
        assert b_1h.reminder_1h_sent is True
        assert b_10m.reminder_10m_sent is True

    def test_sync_eskom_stages_and_proactive_shield(self, teacher_user, student_user, monkeypatch):
        """
        Verifies Eskom stage caching in Redis and scanning of vulnerable confirmed lessons.
        """
        now = timezone.now()
        teacher_user.has_inverter_backup = False
        teacher_user.eskom_area_id = 'jhb-block-3'
        teacher_user.save()

        # Vulnerable booking in 2 hours
        vulnerable_booking = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=now + timedelta(hours=2),
            end_time_utc=now + timedelta(hours=2, minutes=25),
            status=Booking.Status.CONFIRMED,
        )

        class Provider:
            def fetch_area_status(self, area_id):
                return {
                    'area_id': area_id,
                    'area_name': 'Provider test area',
                    'stage': 2,
                    'outages': [{
                        'start': (vulnerable_booking.start_time_utc - timedelta(minutes=5)).isoformat(),
                        'end': (vulnerable_booking.end_time_utc + timedelta(minutes=5)).isoformat(),
                        'note': 'provider fixture',
                    }],
                    'retrieved_at': now,
                }

        monkeypatch.setattr('apps.integrations.tasks.eskom_client', Provider())

        res = sync_eskom_stages_task()
        assert res["synced_areas"] >= 1
        assert res["vulnerable_bookings_flagged"] >= 1

        # Verify Redis cache contains stage info
        cached_stage = cache.get("eskom:stage:jhb-block-3")
        assert cached_stage is not None
        assert cached_stage["stage"] == 2

    def test_reconcile_pending_transactions(self, teacher_user, student_user):
        """
        Verifies that an old checkout is not guessed failed when the gateway has no status lookup.
        """
        now = timezone.now()
        booking = Booking.objects.create(
            teacher=teacher_user,
            student=student_user,
            start_time_utc=now + timedelta(days=1),
            end_time_utc=now + timedelta(days=1, minutes=25),
            status=Booking.Status.PENDING_PAYMENT,
        )

        abandoned_tx = PaymentTransaction.objects.create(
            booking=booking,
            gateway=PaymentTransaction.Gateway.PAYFAST,
            gateway_reference="tx-abandoned-001",
            amount=Decimal('9.00'),
            status=PaymentTransaction.Status.INITIALIZED
        )
        PaymentTransaction.objects.filter(id=abandoned_tx.id).update(created_at=now - timedelta(hours=3))

        res = reconcile_pending_transactions_task()
        assert res["reconciled_count"] >= 1
        assert res["unresolved"] >= 1

        abandoned_tx.refresh_from_db()
        assert abandoned_tx.status == PaymentTransaction.Status.INITIALIZED
        assert abandoned_tx.reconciliation_attempts == 1
        assert GatewayAnomaly.objects.filter(
            payment_transaction=abandoned_tx, reason='reconciliation_unresolved', resolved=False).exists()

    def test_distributed_task_lock_concurrency(self):
        """
        Simulate peer worker holding the lock in Redis; second worker should gracefully skip.
        """
        lock_key = 'lock:beat:purge_expired_reservations'
        cache.set(lock_key, 'LOCKED', timeout=60)

        # Call task while lock is held
        res = purge_expired_reservations_task()
        assert res == {"status": "skipped", "reason": "lock_active"}

        # Cleanup lock
        cache.delete(lock_key)

    def test_distributed_task_lock_does_not_release_successor(self):
        """An expired task must not delete a lock acquired by its successor."""
        lock_key = 'lock:test:ownership-rollover'

        @distributed_task_lock(lock_key, timeout_seconds=60)
        def replace_own_lock():
            cache.delete(lock_key)
            cache.add(lock_key, 'successor-token', timeout=60)
            return {'status': 'complete'}

        assert replace_own_lock() == {'status': 'complete'}
        assert cache.get(lock_key) == 'successor-token'
        cache.delete(lock_key)
