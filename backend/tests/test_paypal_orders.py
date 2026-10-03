"""Task 10.2: PayPal order creation at checkout and the capture endpoint (shared verified path with the webhook)."""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.payments.gateways import paypal
from apps.payments.models import CreditBundle, CreditPack, FxRate, GatewayAnomaly, LedgerEntry, PaymentTransaction

pytestmark = pytest.mark.django_db

INIT = '/api/v1/payments/checkout/init/'
CAPTURE = '/api/v1/payments/paypal/capture/'
WEBHOOK = '/api/v1/payments/webhooks/paypal/'


@pytest.fixture
def booking(teacher_user, student_user):
    start = timezone.now() + timedelta(days=2)
    return Booking.objects.create(
        teacher=teacher_user, student=student_user, start_time_utc=start,
        end_time_utc=start + timedelta(minutes=25), status=Booking.Status.PENDING_PAYMENT)


def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def init(user, **body):
    return client(user).post(INIT, {'gateway': 'paypal', **body}, format='json')


def order_json(ref, *, status='COMPLETED', value='9.00', currency='USD', reason=None, capture_id='CAP-1',
               custom_id=None, payer=True):
    capture = {'id': capture_id, 'status': status, 'custom_id': custom_id or ref,
               'amount': {'value': value, 'currency_code': currency}}
    if reason:
        capture['status_details'] = {'reason': reason}
    order = {'id': f'ORDER-{ref}', 'status': 'COMPLETED',
             'purchase_units': [{'payments': {'captures': [capture]}}]}
    if payer:
        order['payer'] = {'payer_id': 'PAYER1', 'email_address': 'buyer@example.com'}
    return order


@pytest.fixture
def pp(monkeypatch):
    """Fake PayPal capture API; state['order'] is what capture_order returns (or state['raise'] raises)."""
    state = {'order': None, 'raise': None, 'calls': 0}

    def fake_capture_order(order_id, *, request_id):
        state['calls'] += 1
        if state['raise']:
            raise state['raise']
        return state['order']

    monkeypatch.setattr(paypal, 'capture_order', fake_capture_order)
    monkeypatch.setattr(paypal, 'verify_webhook_signature', lambda meta, body: True)
    monkeypatch.setattr(paypal, 'get_capture', lambda cid: state['order']['purchase_units'][0]['payments']['captures'][0])
    return state


def initialised(user, booking, **extra):
    res = init(user, booking_id=str(booking.id), **extra)
    assert res.status_code == 200, res.json()
    return res.json()


# ---------- order creation ----------

def test_init_creates_the_order_for_the_exact_amount(student_user, booking, fake_paypal_orders):
    data = initialised(student_user, booking)
    assert data['order_id'] == f"ORDER-{data['transaction_reference']}"
    tx = PaymentTransaction.objects.get(merchant_reference=data['transaction_reference'])
    assert tx.gateway_order_id == data['order_id']
    assert fake_paypal_orders[0]['amount'] == Decimal('9.00') and fake_paypal_orders[0]['currency'] == 'USD'


def test_init_creates_a_whole_yen_order_for_jpy(student_user, booking, fake_paypal_orders):
    FxRate.objects.create(currency='JPY', rate_to_zar=Decimal('0.125'), valid_from=timezone.now())
    data = initialised(student_user, booking, currency='JPY')
    assert data['amount'] == '1350' and fake_paypal_orders[0]['currency'] == 'JPY'


def test_payfast_init_creates_no_paypal_order(student_user, booking, fake_paypal_orders, settings):
    settings.PAYFAST_MERCHANT_ID, settings.PAYFAST_MERCHANT_KEY = '10000100', 'k'
    res = client(student_user).post(INIT, {'gateway': 'payfast', 'booking_id': str(booking.id)}, format='json')
    assert res.status_code == 200 and 'order_id' not in res.json() and fake_paypal_orders == []


def test_init_is_503_when_paypal_is_not_configured(student_user, booking, settings):
    settings.PAYPAL_CLIENT_ID = ''
    assert init(student_user, booking_id=str(booking.id)).status_code == 503
    assert PaymentTransaction.objects.count() == 0


def test_a_paypal_failure_at_order_creation_leaves_no_dangling_transaction(student_user, booking, monkeypatch):
    def boom(tx, description):
        raise paypal.PayPalError('down')
    monkeypatch.setattr('apps.payments.views.create_checkout_order', boom)
    res = init(student_user, booking_id=str(booking.id))
    assert res.status_code == 502
    assert PaymentTransaction.objects.count() == 0


def test_a_paypal_failure_for_a_pack_leaves_no_purchase_row(student_user, monkeypatch):
    pack = CreditPack.objects.create(code='p1', name='P', credits=1, price_usd=Decimal('8'), price_zar=Decimal('150'),
                                     price_eur=Decimal('7.5'), price_jpy=Decimal('1200'))
    from apps.payments.models import CreditPurchase

    def boom(tx, description):
        raise paypal.PayPalError('down')
    monkeypatch.setattr('apps.payments.views.create_checkout_order', boom)
    assert init(student_user, credit_pack_id=pack.id).status_code == 502
    assert CreditPurchase.objects.count() == 0 and PaymentTransaction.objects.count() == 0


# ---------- capture endpoint ----------

def capture(user, order_id):
    return client(user).post(CAPTURE, {'order_id': order_id}, format='json')


def test_completed_capture_confirms_the_booking_and_posts_the_ledger(student_user, booking, pp):
    data = initialised(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'])
    res = capture(student_user, data['order_id'])
    assert res.status_code == 200 and res.json()['outcome'] == 'confirmed'
    assert res.json()['booking_id'] == str(booking.id)
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED
    tx = PaymentTransaction.objects.get(merchant_reference=data['transaction_reference'])
    assert tx.status == 'success' and tx.gateway_reference == 'CAP-1'
    assert LedgerEntry.objects.filter(payment_transaction=tx).exists()


def test_replaying_the_capture_request_does_not_call_paypal_again(student_user, booking, pp):
    data = initialised(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'])
    capture(student_user, data['order_id'])
    again = capture(student_user, data['order_id'])
    assert again.status_code == 200 and again.json()['outcome'] == 'confirmed'
    assert pp['calls'] == 1
    assert PaymentTransaction.objects.count() == 1


def test_only_the_owner_can_capture(student_user, teacher_user, booking, pp):
    data = initialised(student_user, booking)
    assert capture(teacher_user.user, data['order_id']).status_code == 404
    assert pp['calls'] == 0


def test_unknown_order_is_404(student_user, pp):
    assert capture(student_user, 'ORDER-NOPE').status_code == 404


def test_missing_or_bad_order_id_is_400(student_user):
    c = client(student_user)
    assert c.post(CAPTURE, {}, format='json').status_code == 400
    assert c.post(CAPTURE, {'order_id': 123}, format='json').status_code == 400


def test_expired_hold_is_refused_before_paypal_is_called(student_user, booking, pp):
    data = initialised(student_user, booking)
    Booking.objects.filter(pk=booking.pk).update(status=Booking.Status.CANCELLED)
    res = capture(student_user, data['order_id'])
    assert res.status_code == 409 and pp['calls'] == 0


def test_amount_mismatch_is_not_applied_and_leaves_an_anomaly(student_user, booking, pp):
    data = initialised(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'], value='1.00')
    res = capture(student_user, data['order_id'])
    assert res.status_code == 422 and res.json()['outcome'] == 'failed'
    booking.refresh_from_db()
    assert booking.status == Booking.Status.PENDING_PAYMENT
    assert GatewayAnomaly.objects.filter(reason='amount_mismatch').exists()


def test_currency_mismatch_is_not_applied(student_user, booking, pp):
    data = initialised(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'], currency='EUR')
    assert capture(student_user, data['order_id']).status_code == 422


def test_capture_for_a_different_reference_is_rejected(student_user, booking, pp):
    data = initialised(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'], custom_id='TX-SOMEONEELSE')
    res = capture(student_user, data['order_id'])
    assert res.status_code == 409
    booking.refresh_from_db()
    assert booking.status == Booking.Status.PENDING_PAYMENT


def test_declined_instrument_is_retryable_and_keeps_the_transaction_open(student_user, booking, pp):
    data = initialised(student_user, booking)
    pp['raise'] = paypal.PayPalDeclined('declined', name='UNPROCESSABLE_ENTITY', issue='INSTRUMENT_DECLINED', status_code=422)
    res = capture(student_user, data['order_id'])
    assert res.status_code == 200 and res.json()['outcome'] == 'declined' and res.json()['retryable'] is True
    assert PaymentTransaction.objects.get().status == 'initialized'


def test_paypal_outage_is_retryable_and_changes_nothing(student_user, booking, pp):
    data = initialised(student_user, booking)
    pp['raise'] = paypal.PayPalError('timeout')
    res = capture(student_user, data['order_id'])
    assert res.status_code == 503 and res.json()['retryable'] is True
    assert PaymentTransaction.objects.get().status == 'initialized'
    booking.refresh_from_db()
    assert booking.status == Booking.Status.PENDING_PAYMENT


def test_pending_capture_is_recorded_but_does_not_confirm_yet(student_user, booking, pp):
    data = initialised(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason='ECHECK')
    res = capture(student_user, data['order_id'])
    assert res.status_code == 200 and res.json()['outcome'] == 'pending'
    tx = PaymentTransaction.objects.get()
    assert tx.status == 'pending_capture' and tx.pending_reason == 'ECHECK'
    assert (tx.payer_id, tx.payer_email) == ('PAYER1', 'buyer@example.com')
    booking.refresh_from_db()
    assert booking.status == Booking.Status.PENDING_PAYMENT
    assert not LedgerEntry.objects.filter(payment_transaction=tx).exists()      # no cash yet, nothing posted


def test_a_declined_capture_object_fails_the_transaction(student_user, booking, pp):
    data = initialised(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'], status='DECLINED')
    res = capture(student_user, data['order_id'])
    assert res.status_code == 200 and res.json()['outcome'] == 'failed'
    assert PaymentTransaction.objects.get().status == 'failed'


def test_missing_capture_object_in_the_response_is_a_502(student_user, booking, pp):
    data = initialised(student_user, booking)
    pp['order'] = {'id': data['order_id'], 'status': 'COMPLETED', 'purchase_units': [{}]}
    assert capture(student_user, data['order_id']).status_code == 502


# ---------- endpoint and webhook share one path ----------

def _webhook(pp):
    event = {'id': 'WH-1', 'event_type': 'PAYMENT.CAPTURE.COMPLETED', 'resource': {'id': 'CAP-1'}}
    return APIClient().generic('POST', WEBHOOK, json.dumps(event), content_type='application/json')


def test_webhook_after_the_endpoint_is_a_harmless_duplicate(student_user, booking, pp):
    data = initialised(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'])
    capture(student_user, data['order_id'])
    entries = LedgerEntry.objects.count()
    assert _webhook(pp).status_code == 200
    assert PaymentTransaction.objects.count() == 1 and LedgerEntry.objects.count() == entries


def test_endpoint_after_the_webhook_reports_confirmed_without_double_posting(student_user, booking, pp):
    data = initialised(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'])
    assert _webhook(pp).status_code == 200
    entries = LedgerEntry.objects.count()
    res = capture(student_user, data['order_id'])
    assert res.status_code == 200 and res.json()['outcome'] == 'confirmed'
    assert LedgerEntry.objects.count() == entries and PaymentTransaction.objects.count() == 1


def test_webhook_only_mode_leaves_confirmation_to_the_webhook(student_user, booking, pp, settings):
    settings.PAYPAL_CAPTURE_CONFIRMS = False
    data = initialised(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'])
    res = capture(student_user, data['order_id'])
    assert res.status_code == 200 and res.json()['outcome'] == 'pending'
    booking.refresh_from_db()
    assert booking.status == Booking.Status.PENDING_PAYMENT
    assert _webhook(pp).status_code == 200
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED


def test_pending_then_completed_webhook_confirms_a_normal_booking(student_user, booking, pp):
    data = initialised(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason='ECHECK')
    capture(student_user, data['order_id'])
    pp['order'] = order_json(data['transaction_reference'])           # PayPal later reports it cleared
    assert _webhook(pp).status_code == 200
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED
    assert PaymentTransaction.objects.get().status == 'success'


# ---------- credit pack ----------

def test_pack_capture_grants_the_credits(student_user, pp):
    pack = CreditPack.objects.create(code='p5', name='Five', credits=5, price_usd=Decimal('38'), price_zar=Decimal('700'),
                                     price_eur=Decimal('35.5'), price_jpy=Decimal('5700'))
    data = init(student_user, credit_pack_id=pack.id).json()
    pp['order'] = order_json(data['transaction_reference'], value='38.00')
    res = capture(student_user, data['order_id'])
    assert res.status_code == 200 and res.json()['outcome'] == 'confirmed'
    assert res.json()['credit_purchase_id'] == data['target_id'] and res.json()['booking_id'] is None
    assert sum(b.remaining_credits for b in CreditBundle.objects.filter(user=student_user)) == 5
