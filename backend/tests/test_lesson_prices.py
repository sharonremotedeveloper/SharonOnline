"""Task 10.1: platform-set flat lesson price catalog (D-1)."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.payments.models import LessonPrice
from apps.payments.services.pricing import (
    PriceNotConfigured, lesson_price, quantize_money, usd_to_zar_rate,
)

pytestmark = pytest.mark.django_db


def test_migration_seeds_all_four_currencies():
    assert {p.currency: p.amount for p in LessonPrice.objects.all()} == {
        'USD': Decimal('9.00'), 'EUR': Decimal('8.50'), 'ZAR': Decimal('162.00'), 'JPY': Decimal('1350.00'),
    }


def test_jpy_is_whole_yen_and_others_two_decimals():
    assert quantize_money('1350.5', 'JPY') == Decimal('1351')
    assert quantize_money('1350', 'JPY').as_tuple().exponent == 0
    assert quantize_money('9', 'USD') == Decimal('9.00')
    with pytest.raises(ValueError):
        quantize_money('1', 'GBP')


def test_lesson_price_returns_decimal_and_rejects_inactive_or_missing():
    assert lesson_price('jpy') == Decimal('1350')
    LessonPrice.objects.filter(currency='EUR').update(is_active=False)
    with pytest.raises(PriceNotConfigured):
        lesson_price('EUR')
    with pytest.raises(PriceNotConfigured):
        lesson_price('GBP')


def test_usd_to_zar_rate_is_derived_from_catalog():
    assert usd_to_zar_rate() == Decimal('18.000000')
    LessonPrice.objects.filter(currency='ZAR').update(amount=Decimal('171.00'))
    assert usd_to_zar_rate() == Decimal('19.000000')


def test_model_rejects_fractional_yen_unknown_currency_and_nonpositive():
    with pytest.raises(ValidationError):
        LessonPrice(currency='JPY', amount=Decimal('1350.50')).save()
    with pytest.raises(ValidationError):
        LessonPrice(currency='GBP', amount=Decimal('5.00')).save()
    with pytest.raises(IntegrityError), transaction.atomic():
        LessonPrice.objects.filter(currency='USD').update(amount=Decimal('0.00'))


def test_endpoint_is_public_and_exact():
    res = APIClient().get('/api/v1/payments/lesson-prices/')
    assert res.status_code == 200
    rows = {r['currency']: r for r in res.json()}
    assert rows['JPY'] == {'currency': 'JPY', 'amount': '1350', 'decimals': 0}
    assert rows['USD'] == {'currency': 'USD', 'amount': '9.00', 'decimals': 2}
    assert set(rows) == {'USD', 'EUR', 'ZAR', 'JPY'}


def test_endpoint_hides_inactive_prices():
    LessonPrice.objects.filter(currency='EUR').update(is_active=False)
    codes = {r['currency'] for r in APIClient().get('/api/v1/payments/lesson-prices/').json()}
    assert 'EUR' not in codes


# ---------- checkout and booking payloads read the catalog, not the tutor ----------
from apps.bookings.models import Booking  # noqa: E402
from apps.payments.models import PaymentTransaction  # noqa: E402
from django.utils import timezone  # noqa: E402
from datetime import timedelta  # noqa: E402


@pytest.fixture
def pending(teacher_user, student_user):
    start = timezone.now() + timedelta(days=2)
    return Booking.objects.create(
        teacher=teacher_user, student=student_user, start_time_utc=start,
        end_time_utc=start + timedelta(minutes=25), status=Booking.Status.PENDING_PAYMENT)


def _init(student_user, booking, gateway):
    c = APIClient()
    c.force_authenticate(student_user)
    return c.post('/api/v1/payments/checkout/init/', {'booking_id': str(booking.id), 'gateway': gateway}, format='json')


def test_checkout_ignores_tutor_price_and_follows_catalog(student_user, teacher_user, pending, settings):
    settings.PAYFAST_MERCHANT_ID = '10000100'
    settings.PAYFAST_MERCHANT_KEY = 'merchantkey'
    teacher_user.price_per_25min_usd = Decimal('3.00')
    teacher_user.save()
    LessonPrice.objects.filter(currency='ZAR').update(amount=Decimal('199.00'))
    LessonPrice.objects.filter(currency='USD').update(amount=Decimal('11.00'))
    zar = _init(student_user, pending, 'payfast')
    assert zar.status_code == 200 and zar.json()['amount'] == '199.00'
    usd = _init(student_user, pending, 'paypal')
    assert usd.status_code == 200 and usd.json()['amount'] == '11.00' and usd.json()['currency'] == 'USD'
    assert PaymentTransaction.objects.filter(booking=pending).count() == 2


def test_booking_payload_prices_come_from_catalog(student_user, teacher_user, pending):
    LessonPrice.objects.filter(currency='ZAR').update(amount=Decimal('171.00'))
    c = APIClient()
    c.force_authenticate(student_user)
    body = c.get(f'/api/v1/bookings/{pending.id}/').json()
    assert body['price_usd'] == '9.00' and body['price_zar'] == '171.00'
