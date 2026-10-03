"""Task 10.1d: admin-maintained FX rate table (EUR/JPY -> ZAR) and EUR/JPY lesson checkout (option C)."""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.payments.gateways import paypal
from apps.payments.models import FxRate, LedgerEntry, PaymentTransaction
from apps.payments.services.fx import (
    FxRateSanityError, FxRateStale, FxRateUnavailable, current_rate, record_rate,
)
from apps.payments.services.funding import gateway_fx_snapshot

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def gateway_settings(settings):
    settings.PAYPAL_WEBHOOK_ID = 'WH-TEST'
    settings.PAYPAL_CLIENT_ID = 'cid'
    settings.PAYPAL_CLIENT_SECRET = 'sec'
    settings.PAYPAL_MODE = 'sandbox'


def _rate(currency, value, hours_old=0, source='manual'):
    return FxRate.objects.create(
        currency=currency, rate_to_zar=Decimal(value), source=source,
        valid_from=timezone.now() - timedelta(hours=hours_old))


# ---------- service ----------

def test_no_rate_is_unavailable():
    with pytest.raises(FxRateUnavailable):
        current_rate('EUR')


def test_latest_effective_rate_wins_and_future_rows_are_ignored():
    _rate('EUR', '19.000000', hours_old=5)
    newest = _rate('EUR', '19.500000', hours_old=1)
    FxRate.objects.create(currency='EUR', rate_to_zar=Decimal('25'), source='manual',
                          valid_from=timezone.now() + timedelta(hours=3))
    row = current_rate('EUR')
    assert row.pk == newest.pk and row.rate_to_zar == Decimal('19.500000')


def test_stale_rate_is_refused_and_age_limit_is_a_setting(settings):
    _rate('JPY', '0.125000', hours_old=25)
    with pytest.raises(FxRateStale):
        current_rate('JPY')
    settings.FX_RATE_MAX_AGE_HOURS = 48
    assert current_rate('JPY').rate_to_zar == Decimal('0.125000')


def test_only_eur_and_jpy_have_table_rates():
    for cur in ('USD', 'ZAR', 'GBP'):
        with pytest.raises(ValueError):
            record_rate(cur, Decimal('1'), set_by=None)


def test_record_rate_rejects_non_positive():
    for bad in (Decimal('0'), Decimal('-1')):
        with pytest.raises(ValueError):
            record_rate('EUR', bad, set_by=None)


def test_first_rate_is_accepted_then_large_jump_needs_confirmation():
    first = record_rate('EUR', Decimal('19.5'), set_by=None)
    assert first.source == 'manual' and first.rate_to_zar == Decimal('19.500000')
    with pytest.raises(FxRateSanityError):
        record_rate('EUR', Decimal('195'), set_by=None)            # the typo case
    with pytest.raises(FxRateSanityError):
        record_rate('EUR', Decimal('17.0'), set_by=None)           # > 10 % drop
    ok = record_rate('EUR', Decimal('20.0'), set_by=None)          # 2.6 % move
    assert ok.rate_to_zar == Decimal('20.000000')
    forced = record_rate('EUR', Decimal('30'), set_by=None, confirm=True)
    assert forced.rate_to_zar == Decimal('30.000000')
    assert FxRate.objects.filter(currency='EUR').count() == 3


def test_fx_rows_cannot_be_edited_or_deleted():
    row = _rate('EUR', '19.5')
    row.rate_to_zar = Decimal('1')
    with pytest.raises(Exception):
        row.save()
    with pytest.raises(Exception):
        row.delete()
    with pytest.raises(Exception):
        FxRate.objects.filter(pk=row.pk).update(rate_to_zar=Decimal('1'))


def test_gateway_fx_snapshot_uses_the_table_for_eur_and_jpy():
    eur = _rate('EUR', '19.800000')
    rate, source = gateway_fx_snapshot('EUR')
    assert rate == Decimal('19.800000') and source == f'fx_rate_table:{eur.pk}'
    with pytest.raises(FxRateUnavailable):
        gateway_fx_snapshot('JPY')


# ---------- checkout ----------

@pytest.fixture
def pending(teacher_user, student_user):
    start = timezone.now() + timedelta(days=2)
    return Booking.objects.create(
        teacher=teacher_user, student=student_user, start_time_utc=start,
        end_time_utc=start + timedelta(minutes=25), status=Booking.Status.PENDING_PAYMENT)


def _init(student, booking, **extra):
    c = APIClient()
    c.force_authenticate(student)
    return c.post('/api/v1/payments/checkout/init/',
                  {'booking_id': str(booking.id), 'gateway': 'paypal', **extra}, format='json')


def test_paypal_eur_checkout_prices_from_catalog_and_stamps_the_rate(student_user, pending):
    row = _rate('EUR', '19.800000')
    res = _init(student_user, pending, currency='EUR')
    assert res.status_code == 200 and res.json()['amount'] == '8.50' and res.json()['currency'] == 'EUR'
    tx = PaymentTransaction.objects.get(merchant_reference=res.json()['transaction_reference'])
    assert tx.amount == Decimal('8.50') and tx.currency == 'EUR'
    assert tx.fx_rate_to_zar == Decimal('19.800000') and tx.fx_source == f'fx_rate_table:{row.pk}'


def test_paypal_jpy_checkout_is_whole_yen(student_user, pending):
    _rate('JPY', '0.125000')
    res = _init(student_user, pending, currency='JPY')
    assert res.status_code == 200 and res.json()['amount'] == '1350' and res.json()['currency'] == 'JPY'


def test_checkout_blocked_when_rate_missing_or_stale(student_user, pending):
    assert _init(student_user, pending, currency='EUR').status_code == 503
    _rate('EUR', '19.8', hours_old=30)
    res = _init(student_user, pending, currency='EUR')
    assert res.status_code == 503 and 'rate' in res.json()['error'].lower()
    assert PaymentTransaction.objects.count() == 0


def test_usd_and_zar_checkout_do_not_need_a_table_rate(student_user, pending):
    assert _init(student_user, pending).status_code == 200            # default USD
    assert _init(student_user, pending, currency='usd').status_code == 200


def test_unsupported_lesson_currency_rejected(student_user, pending):
    assert _init(student_user, pending, currency='GBP').status_code == 400


# ---------- capture, ledger ----------

def _pp_headers():
    return {
        'HTTP_PAYPAL_AUTH_ALGO': 'SHA256withRSA', 'HTTP_PAYPAL_CERT_URL': 'https://api.sandbox.paypal.com/cert',
        'HTTP_PAYPAL_TRANSMISSION_ID': 'tid', 'HTTP_PAYPAL_TRANSMISSION_SIG': 'sig',
        'HTTP_PAYPAL_TRANSMISSION_TIME': timezone.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


@pytest.fixture
def capture(monkeypatch, student_user, pending):
    """Returns capture(currency, value) -> response, after a real checkout/init in that currency."""
    def run(currency, value, before_webhook=None):
        res = _init(student_user, pending, currency=currency)
        assert res.status_code == 200, res.json()
        ref = res.json()['transaction_reference']

        class Resp:
            status_code = 200

            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                pass

            def json(self):
                return self.payload

        cap = {'id': 'CAP-1', 'status': 'COMPLETED', 'custom_id': ref,
               'amount': {'value': value, 'currency_code': currency}}
        monkeypatch.setattr(paypal.requests, 'post', lambda url, **kw: Resp({'access_token': 't', 'expires_in': 3600}))
        monkeypatch.setattr(paypal.requests, 'request', lambda method, url, **kw: (
            Resp({'verification_status': 'SUCCESS'}) if method == 'POST' else Resp(cap)))
        if before_webhook:
            before_webhook()
        event = {'id': 'WH-EVT', 'event_type': 'PAYMENT.CAPTURE.COMPLETED', 'resource': {'id': 'CAP-1'}}
        return ref, APIClient().generic('POST', '/api/v1/payments/webhooks/paypal/', json.dumps(event),
                                        content_type='application/json', **_pp_headers())
    return run


def test_jpy_capture_confirms_and_the_ledger_balances_in_yen_and_zar(capture, pending):
    _rate('JPY', '0.125000')
    ref, res = capture('JPY', '1350')                        # PayPal reports JPY with no decimals
    assert res.status_code == 200
    pending.refresh_from_db()
    assert pending.status == Booking.Status.CONFIRMED
    tx = PaymentTransaction.objects.get(merchant_reference=ref)
    assert tx.status == 'success' and tx.fx_rate_to_zar == Decimal('0.125000')
    rows = LedgerEntry.objects.filter(payment_transaction=tx)
    assert rows.exists() and {r.currency for r in rows} == {'JPY'}
    for kind in (LedgerEntry.EntryType.DEBIT, LedgerEntry.EntryType.CREDIT):
        assert sum(r.amount for r in rows if r.entry_type == kind) == Decimal('1350.00')
        assert sum(r.amount_zar for r in rows if r.entry_type == kind) == Decimal('168.75')


def test_eur_capture_values_at_the_checkout_snapshot_even_if_the_rate_moves(capture, pending):
    _rate('EUR', '19.800000')
    ref, res = capture('EUR', '8.50', before_webhook=lambda: _rate('EUR', '25.000000'))   # moves after checkout
    assert res.status_code == 200
    tx = PaymentTransaction.objects.get(merchant_reference=ref)
    rows = LedgerEntry.objects.filter(payment_transaction=tx, entry_type=LedgerEntry.EntryType.DEBIT)
    assert sum(r.amount_zar for r in rows) == Decimal('168.30')   # 8.50 x 19.8, not x 25


def test_underpaid_jpy_capture_is_rejected(capture, pending):
    _rate('JPY', '0.125')
    _, res = capture('JPY', '1349')
    assert res.status_code == 400
    pending.refresh_from_db()
    assert pending.status == Booking.Status.PENDING_PAYMENT


def test_capture_after_rate_goes_stale_still_settles(capture, pending, settings):
    """Money is already taken: a stale table must never make a verified capture fail."""
    _rate('EUR', '19.8')

    def go_stale():
        settings.FX_RATE_MAX_AGE_HOURS = 0

    ref, res = capture('EUR', '8.50', before_webhook=go_stale)
    assert res.status_code == 200
    pending.refresh_from_db()
    assert pending.status == Booking.Status.CONFIRMED


# ---------- admin API ----------

@pytest.fixture
def admin_client(admin_user):
    c = APIClient()
    c.force_authenticate(admin_user)
    return c


def test_admin_fx_api_requires_admin(student_user):
    c = APIClient()
    c.force_authenticate(student_user)
    assert c.get('/api/v1/admin/fx-rates/').status_code == 403
    assert c.post('/api/v1/admin/fx-rates/', {'currency': 'EUR', 'rate': '19.5'}, format='json').status_code == 403


def test_admin_fx_api_lists_missing_and_stale_rates(admin_client):
    body = admin_client.get('/api/v1/admin/fx-rates/').json()
    assert {r['currency']: r['stale'] for r in body['current']} == {'EUR': True, 'JPY': True}
    _rate('EUR', '19.5', hours_old=30)
    cur = {r['currency']: r for r in admin_client.get('/api/v1/admin/fx-rates/').json()['current']}
    assert cur['EUR']['stale'] is True and cur['EUR']['rate_to_zar'] == '19.500000' and cur['EUR']['age_hours'] >= 30


def test_admin_fx_api_post_records_rate_and_guards_typos(admin_client, admin_user):
    res = admin_client.post('/api/v1/admin/fx-rates/', {'currency': 'EUR', 'rate': '19.5'}, format='json')
    assert res.status_code == 201 and res.json()['set_by'] == admin_user.username and res.json()['stale'] is False
    typo = admin_client.post('/api/v1/admin/fx-rates/', {'currency': 'EUR', 'rate': '195'}, format='json')
    assert typo.status_code == 409 and typo.json()['code'] == 'confirmation_required'
    assert FxRate.objects.filter(currency='EUR').count() == 1
    ok = admin_client.post('/api/v1/admin/fx-rates/', {'currency': 'EUR', 'rate': '195', 'confirm': True}, format='json')
    assert ok.status_code == 201
    assert admin_client.post('/api/v1/admin/fx-rates/', {'currency': 'USD', 'rate': '1'}, format='json').status_code == 400
    assert admin_client.post('/api/v1/admin/fx-rates/', {'currency': 'EUR', 'rate': 'abc'}, format='json').status_code == 400
