"""Task 10.2 slice B: schema for PayPal orders and pending-capture (grace) bookings."""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bookings.models import Booking
from apps.payments.models import BookingFunding, PaymentTransaction
from apps.users.models import SupportInquiry

pytestmark = pytest.mark.django_db


@pytest.fixture
def mk(teacher_user, student_user):
    counter = {'n': 0}

    def make(**kw):
        counter['n'] += 1
        start = timezone.now() + timedelta(days=2, hours=counter['n'])
        booking = Booking.objects.create(teacher=teacher_user, student=student_user, start_time_utc=start,
                                         end_time_utc=start + timedelta(minutes=25))
        ref = f"TX-{uuid.uuid4().hex[:12].upper()}"
        return PaymentTransaction.objects.create(
            booking=booking, gateway='paypal', gateway_reference=f'INIT-{ref}', merchant_reference=ref,
            amount=Decimal('9.00'), currency='USD', **kw)
    return make


def test_transaction_can_be_pending_capture_with_order_and_payer(mk):
    tx = mk(status=PaymentTransaction.Status.PENDING_CAPTURE, gateway_order_id='ORDER-1',
             pending_reason='PENDING_REVIEW', payer_id='PAYER1', payer_email='buyer@example.com')
    tx.refresh_from_db()
    assert tx.status == 'pending_capture' and tx.gateway_order_id == 'ORDER-1'
    assert (tx.pending_reason, tx.payer_id, tx.payer_email) == ('PENDING_REVIEW', 'PAYER1', 'buyer@example.com')


def test_order_id_is_unique_when_set_but_many_rows_may_have_none(mk):
    mk()
    mk()                                           # two rows without an order id are fine (PayFast, unfilled)
    mk(gateway_order_id='ORDER-1')
    with pytest.raises(IntegrityError), transaction.atomic():
        mk(gateway_order_id='ORDER-1')


def test_pending_capture_is_not_a_settled_state():
    from apps.payments.views import SETTLED_STATES
    assert PaymentTransaction.Status.PENDING_CAPTURE not in SETTLED_STATES


def test_booking_funding_has_a_pending_gateway_source():
    assert BookingFunding.SourceType.GATEWAY_PENDING == 'gateway_pending'
    assert 'gateway_pending' in {c[0] for c in BookingFunding.SourceType.choices}


def test_support_inquiry_defaults_to_general_and_can_link_a_payment_failure(student_user, teacher_user):
    plain = SupportInquiry.objects.create(sender_name='A', sender_email='a@example.com', subject='s', message='m')
    assert plain.category == 'general' and plain.student_id is None and plain.related_booking_id is None
    start = timezone.now() + timedelta(days=2)
    booking = Booking.objects.create(teacher=teacher_user, student=student_user, start_time_utc=start,
                                     end_time_utc=start + timedelta(minutes=25))
    ticket = SupportInquiry.objects.create(
        sender_name='System', sender_email=student_user.email or 'student@example.com', subject='Payment failed',
        message='...', category=SupportInquiry.Category.PAYMENT_FAILURE, student=student_user,
        related_booking_id=booking.id, related_transaction_ref='TX-ABC')
    ticket.refresh_from_db()
    assert ticket.category == 'payment_failure' and ticket.related_booking_id == booking.id
    assert ticket.related_transaction_ref == 'TX-ABC' and ticket.student_id == student_user.id


def test_grace_and_confirmation_settings_have_safe_defaults(settings):
    assert settings.GRACE_MAX_OPEN == 5
    assert settings.PAYPAL_CAPTURE_CONFIRMS is True
