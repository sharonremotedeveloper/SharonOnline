"""
Slice T2: TUTOR_MIN_NOTICE_MINUTES is enforced when the student PAYS, not only when the slot is listed (plan 3.5).

A hold made while the lesson was still bookable can be paid after the notice window has closed. The refusal must come
BEFORE any money moves (checkout init, PayPal capture, credit redemption), with the same 409 style as the other pay-time
guards (expired hold, tutor not bookable) and a stable `code`.
"""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.payments.gateways import paypal
from apps.payments.models import CreditBundle, PaymentTransaction
from apps.payments.services.credits import grant_credit

pytestmark = pytest.mark.django_db

INIT = '/api/v1/payments/checkout/init/'
CAPTURE = '/api/v1/payments/paypal/capture/'


def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def held(teacher, student, *, starts_in):
    start = timezone.now() + starts_in
    return Booking.objects.create(teacher=teacher, student=student, start_time_utc=start,
                                  end_time_utc=start + timedelta(minutes=25), status=Booking.Status.PENDING_PAYMENT)


def move_start(booking, starts_in):
    start = timezone.now() + starts_in
    Booking.objects.filter(pk=booking.pk).update(start_time_utc=start, end_time_utc=start + timedelta(minutes=25))
    booking.refresh_from_db()


def test_checkout_is_refused_inside_the_notice_window(teacher_user, student_user):
    booking = held(teacher_user, student_user, starts_in=timedelta(minutes=6))
    res = client(student_user).post(INIT, {'booking_id': str(booking.id), 'gateway': 'paypal'}, format='json')
    assert res.status_code == 409 and res.json()['code'] == 'too_close_to_start'
    assert not PaymentTransaction.objects.exists()


def test_checkout_just_outside_the_window_is_allowed(teacher_user, student_user):
    booking = held(teacher_user, student_user, starts_in=timedelta(minutes=12))
    res = client(student_user).post(INIT, {'booking_id': str(booking.id), 'gateway': 'paypal'}, format='json')
    assert res.status_code == 200


def test_the_notice_follows_the_setting(teacher_user, student_user, settings):
    booking = held(teacher_user, student_user, starts_in=timedelta(minutes=12))
    settings.TUTOR_MIN_NOTICE_MINUTES = 30
    res = client(student_user).post(INIT, {'booking_id': str(booking.id), 'gateway': 'paypal'}, format='json')
    assert res.status_code == 409 and res.json()['code'] == 'too_close_to_start'


def test_a_started_lesson_keeps_its_own_message(teacher_user, student_user):
    booking = held(teacher_user, student_user, starts_in=timedelta(minutes=-1))
    res = client(student_user).post(INIT, {'booking_id': str(booking.id), 'gateway': 'paypal'}, format='json')
    assert res.status_code == 409 and 'already started' in res.json()['error']


def test_the_capture_is_refused_before_paypal_is_called_when_the_window_closed_meanwhile(teacher_user, student_user, monkeypatch):
    booking = held(teacher_user, student_user, starts_in=timedelta(minutes=14))
    order = client(student_user).post(INIT, {'booking_id': str(booking.id), 'gateway': 'paypal'}, format='json').json()
    calls = []
    monkeypatch.setattr(paypal, 'capture_order', lambda *a, **k: calls.append(1))
    move_start(booking, timedelta(minutes=4))              # time passed while the student was on PayPal
    res = client(student_user).post(CAPTURE, {'order_id': order['order_id']}, format='json')
    assert res.status_code == 409 and res.json()['code'] == 'too_close_to_start' and res.json()['retryable'] is False
    assert calls == []                                      # refused before any capture, nothing to refund


def test_a_credit_cannot_be_redeemed_inside_the_window(teacher_user, student_user):
    grant_credit(student_user, credits=1)
    booking = held(teacher_user, student_user, starts_in=timedelta(minutes=5))
    res = client(student_user).post(f'/api/v1/bookings/{booking.id}/redeem-credit/')
    assert res.status_code == 409 and 'too close' in res.json()['error'].lower()
    booking.refresh_from_db()
    assert booking.status == Booking.Status.PENDING_PAYMENT
    assert CreditBundle.objects.get(user=student_user).remaining_credits == 1


def test_the_guard_has_one_definition_shared_with_the_slot_generator():
    from apps.bookings.services.notice import min_notice, notice_closed
    now = timezone.now()
    assert min_notice() == timedelta(minutes=10)
    assert notice_closed(now + timedelta(minutes=10), now) and not notice_closed(now + timedelta(minutes=11), now)
