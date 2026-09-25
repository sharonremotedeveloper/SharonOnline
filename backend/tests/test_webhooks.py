import pytest
from datetime import timedelta
from unittest.mock import patch
from django.utils import timezone
from apps.bookings.models import Booking
from apps.payments.models import PaymentTransaction
from apps.payments.services.webhook_handler import process_payment_webhook

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
