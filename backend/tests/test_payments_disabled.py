import pytest
from rest_framework.test import APIClient

from apps.payments.models import PaymentTransaction
import factories as f


@pytest.fixture
def student_client(db):
    booking = f.make_booking()
    api = APIClient()
    api.force_authenticate(booking.student)
    return api, booking


def test_checkout_init_refused_when_payments_disabled(student_client, settings):
    settings.PAYMENTS_ENABLED = False
    api, booking = student_client
    res = api.post('/api/v1/payments/checkout/init/', {'booking_id': str(booking.id), 'gateway': 'paypal'}, format='json')
    assert res.status_code == 503 and res.json()['code'] == 'payments_disabled'
    assert not PaymentTransaction.objects.exists()


def test_paypal_capture_refused_when_payments_disabled(student_client, settings):
    settings.PAYMENTS_ENABLED = False
    api, _ = student_client
    res = api.post('/api/v1/payments/paypal/capture/', {'order_id': 'ORDER-1'}, format='json')
    assert res.status_code == 503 and res.json()['code'] == 'payments_disabled'


def test_checkout_init_not_blocked_by_the_flag_when_enabled(student_client, settings):
    settings.PAYMENTS_ENABLED = True
    api, booking = student_client
    res = api.post('/api/v1/payments/checkout/init/', {'booking_id': str(booking.id), 'gateway': 'bogus'}, format='json')
    assert res.status_code == 400
