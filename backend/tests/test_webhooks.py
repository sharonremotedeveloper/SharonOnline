import pytest
from datetime import timedelta
from unittest.mock import patch
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.bookings.models import Booking
from apps.payments.models import PaymentTransaction, CreditBundle
from apps.payments.services.webhook_handler import process_payment_webhook
from apps.admin_api.models import DisputeCase
from apps.teachers.models import TeacherProfile

User = get_user_model()


@pytest.mark.django_db
@patch('apps.integrations.tasks.dispatch_booking_fulfillment.delay')
def test_webhook_idempotency(mock_dispatch, teacher_user, student_user):
    # Create pending booking
    start_utc = timezone.now() + timedelta(days=2)
    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=start_utc,
        end_time_utc=start_utc + timedelta(minutes=25),
        status=Booking.Status.PENDING_PAYMENT
    )

    tx_ref = "PAYPAL-TEST-ORDER-12345"
    payload = {"order_id": tx_ref, "amount": 9.00}

    # 1. First webhook delivery
    res1 = process_payment_webhook(
        booking_id=str(booking.id),
        gateway="paypal",
        transaction_id=tx_ref,
        amount=9.00,
        currency="USD",
        status="success",
        raw_payload=payload
    )
    assert res1["status"] == "success"

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED
    # Verify async fulfillment task was dispatched once
    assert mock_dispatch.call_count == 1

    # 2. Duplicate webhook retry (e.g. network retry from PayPal)
    res2 = process_payment_webhook(
        booking_id=str(booking.id),
        gateway="paypal",
        transaction_id=tx_ref,
        amount=9.00,
        currency="USD",
        status="success",
        raw_payload=payload
    )
    assert res2["status"] == "already_processed"

    # Verify no duplicate task dispatch was triggered
    assert mock_dispatch.call_count == 1

    # Only one PaymentTransaction record exists in the database
    assert PaymentTransaction.objects.filter(gateway_reference=tx_ref).count() == 1


@pytest.mark.django_db
@patch('apps.integrations.tasks.dispatch_booking_fulfillment.delay')
def test_def501_late_payment_after_rebooked_slot_collision(mock_dispatch, teacher_user, student_user):
    """
    DEF-501 Concurrency Guard:
    Student A reserves a slot, which expires at T+10m (status: CANCELLED).
    Student B books the same timeslot with the same teacher and pays (status: CONFIRMED).
    Student A's late payment webhook arrives afterwards.
    System MUST NOT raise IntegrityError, MUST quarantine Student A's booking to DISPUTED,
    MUST auto-credit Student A 1 lesson credit, and MUST create a DisputeCase.
    """
    teacher_profile = teacher_user if isinstance(teacher_user, TeacherProfile) else TeacherProfile.objects.get(user=teacher_user)
    student_b = User.objects.create_user(username="student_b_test", email="student_b@test.com", password="password123")

    slot_time = timezone.now() + timedelta(days=3)

    # 1. Student A's expired booking
    booking_a = Booking.objects.create(
        teacher=teacher_profile,
        student=student_user,
        start_time_utc=slot_time,
        end_time_utc=slot_time + timedelta(minutes=25),
        status=Booking.Status.CANCELLED
    )

    # 2. Student B reserves and confirms the same timeslot
    booking_b = Booking.objects.create(
        teacher=teacher_profile,
        student=student_b,
        start_time_utc=slot_time,
        end_time_utc=slot_time + timedelta(minutes=25),
        status=Booking.Status.CONFIRMED
    )

    # 3. Late payment arrives for Student A's booking
    late_tx_ref = "PAYFAST-DEF501-LATE-001"
    res = process_payment_webhook(
        booking_id=str(booking_a.id),
        gateway="payfast",
        transaction_id=late_tx_ref,
        amount=162.00,
        currency="ZAR",
        status="success",
        raw_payload={"pf_payment_id": late_tx_ref, "status": "COMPLETE"}
    )

    # 4. Assertions: Graceful handling without IntegrityError
    assert res["status"] == "collision_quarantined"
    assert res["reason"] == "slot_rebooked_by_another_student"

    booking_a.refresh_from_db()
    booking_b.refresh_from_db()

    # Student A's booking is quarantined to DISPUTED
    assert booking_a.status == Booking.Status.DISPUTED

    # Student B's active booking remains untouched and CONFIRMED
    assert booking_b.status == Booking.Status.CONFIRMED

    # Payment transaction recorded as SUCCESS
    tx = PaymentTransaction.objects.get(gateway_reference=late_tx_ref)
    assert tx.status == PaymentTransaction.Status.SUCCESS

    # Student A received 1 restitution lesson credit
    bundle = CreditBundle.objects.filter(user=student_user).first()
    assert bundle is not None
    assert bundle.remaining_credits >= 1

    # DisputeCase was created for arbitration
    dispute = DisputeCase.objects.filter(booking=booking_a).first()
    assert dispute is not None
    assert dispute.status == DisputeCase.Status.OPEN
    assert "DEF-501" in dispute.student_statement


@pytest.mark.django_db
@patch('apps.integrations.tasks.dispatch_booking_fulfillment.delay')
def test_def501_late_payment_past_lesson_window_quarantined(mock_dispatch, teacher_user, student_user):
    """
    DEF-501 Concurrency Guard:
    Late payment arrives for a cancelled booking whose start time has already elapsed.
    Must quarantine to DISPUTED, credit the student, and open a DisputeCase.
    """
    teacher_profile = teacher_user if isinstance(teacher_user, TeacherProfile) else TeacherProfile.objects.get(user=teacher_user)
    past_time = timezone.now() - timedelta(hours=2)

    booking = Booking.objects.create(
        teacher=teacher_profile,
        student=student_user,
        start_time_utc=past_time,
        end_time_utc=past_time + timedelta(minutes=25),
        status=Booking.Status.CANCELLED
    )

    late_tx = "PAYPAL-DEF501-PAST-002"
    res = process_payment_webhook(
        booking_id=str(booking.id),
        gateway="paypal",
        transaction_id=late_tx,
        amount=9.00,
        currency="USD",
        status="success",
        raw_payload={"id": late_tx}
    )

    assert res["status"] == "collision_quarantined"
    assert res["reason"] == "lesson_window_elapsed"

    booking.refresh_from_db()
    assert booking.status == Booking.Status.DISPUTED

    bundle = CreditBundle.objects.filter(user=student_user).first()
    assert bundle is not None
    assert bundle.remaining_credits >= 1


@pytest.mark.django_db
@patch('apps.integrations.tasks.dispatch_booking_fulfillment.delay')
def test_def501_late_payment_uncontested_slot_revived(mock_dispatch, teacher_user, student_user):
    """
    DEF-501 Concurrency Guard:
    Late payment arrives for a cancelled booking, BUT no one took the slot and lesson
    is in future. System revives booking to CONFIRMED and dispatches fulfillment.
    """
    teacher_profile = teacher_user if isinstance(teacher_user, TeacherProfile) else TeacherProfile.objects.get(user=teacher_user)
    future_time = timezone.now() + timedelta(days=4)

    booking = Booking.objects.create(
        teacher=teacher_profile,
        student=student_user,
        start_time_utc=future_time,
        end_time_utc=future_time + timedelta(minutes=25),
        status=Booking.Status.CANCELLED
    )

    tx_ref = "PAYPAL-DEF501-REVIVE-003"
    res = process_payment_webhook(
        booking_id=str(booking.id),
        gateway="paypal",
        transaction_id=tx_ref,
        amount=9.00,
        currency="USD",
        status="success",
        raw_payload={"id": tx_ref}
    )

    assert res["status"] == "success"

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED
    assert mock_dispatch.call_count == 1
