import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from urllib.parse import quote_plus, urlencode

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.payments.gateways import payfast, paypal
from apps.payments.models import LedgerAccount, LedgerEntry, PaymentTransaction

PASSPHRASE = 'unit-test-passphrase'
MERCHANT = '10000100'
ITN = '/api/v1/payments/webhooks/payfast/'
PP = '/api/v1/payments/webhooks/paypal/'


@pytest.fixture(autouse=True)
def gateway_settings(settings):
    settings.PAYFAST_MERCHANT_ID = MERCHANT
    settings.PAYFAST_MERCHANT_KEY = 'merchantkey'
    settings.PAYFAST_PASSPHRASE = PASSPHRASE
    settings.PAYFAST_SANDBOX = True
    settings.PAYFAST_SKIP_IP_CHECK = False
    settings.PAYFAST_TRUSTED_PROXY_COUNT = 0
    settings.PAYPAL_WEBHOOK_ID = 'WH-TEST'
    settings.PAYPAL_CLIENT_ID = 'cid'
    settings.PAYPAL_CLIENT_SECRET = 'sec'
    settings.PAYPAL_MODE = 'sandbox'


@pytest.fixture
def pending_booking(teacher_user, student_user):
    start = timezone.now() + timedelta(days=2)
    return Booking.objects.create(
        teacher=teacher_user, student=student_user, start_time_utc=start,
        end_time_utc=start + timedelta(minutes=25), status=Booking.Status.PENDING_PAYMENT)


def _checkout(student, booking, gateway):
    c = APIClient()
    c.force_authenticate(student)
    res = c.post('/api/v1/payments/checkout/init/', {'booking_id': str(booking.id), 'gateway': gateway}, format='json')
    assert res.status_code == 200, res.data
    return res.data


# ---------- Checkout persists the expected amount ----------

@pytest.mark.django_db
class TestCheckout:
    def test_payfast_checkout_persists_initialized_tx(self, student_user, pending_booking):
        data = _checkout(student_user, pending_booking, 'payfast')
        tx = PaymentTransaction.objects.get(merchant_reference=data['transaction_reference'])
        assert tx.status == 'initialized' and tx.currency == 'ZAR'
        assert tx.amount == Decimal('162.00')  # flat catalog price (D-1)
        assert data['fields']['signature']

    def test_checkout_rejects_non_pending_booking(self, student_user, pending_booking):
        pending_booking.status = Booking.Status.CONFIRMED
        pending_booking.save()
        c = APIClient()
        c.force_authenticate(student_user)
        res = c.post('/api/v1/payments/checkout/init/', {'booking_id': str(pending_booking.id)}, format='json')
        assert res.status_code == 409

    def test_checkout_cannot_pay_for_someone_elses_booking(self, pending_booking, teacher_user):
        c = APIClient()
        c.force_authenticate(teacher_user.user)
        res = c.post('/api/v1/payments/checkout/init/', {'booking_id': str(pending_booking.id)}, format='json')
        assert res.status_code == 404


# ---------- PayFast ITN ----------

def _signed_body(fields, passphrase=PASSPHRASE, tamper_sig=False):
    pairs = list(fields.items())
    string = '&'.join(f"{k}={quote_plus(str(v).strip())}" for k, v in pairs)
    if passphrase:
        string += f"&passphrase={quote_plus(passphrase)}"
    sig = hashlib.md5(string.encode()).hexdigest()
    if tamper_sig:
        sig = '0' * 32
    return urlencode(pairs + [('signature', sig)])


@pytest.fixture
def pf(monkeypatch, student_user, pending_booking):
    """Initialised PayFast tx + fake PayFast network; returns helper to post ITNs."""
    calls = {'postback': 0, 'answer': 'VALID'}

    class Resp:
        status_code = 200

        @property
        def text(self):
            return calls['answer']

    def fake_post(url, data=None, headers=None, timeout=None):
        calls['postback'] += 1
        calls['url'] = url
        return Resp()

    monkeypatch.setattr(payfast.requests, 'post', fake_post)
    monkeypatch.setattr(payfast, 'get_valid_ips', lambda: {'127.0.0.1'})

    data = _checkout(student_user, pending_booking, 'payfast')
    ref = data['transaction_reference']

    def itn(**overrides):
        fields = {
            'm_payment_id': ref, 'pf_payment_id': '1089250', 'payment_status': 'COMPLETE',
            'item_name': 'Lesson', 'amount_gross': '162.00', 'amount_fee': '-3.72', 'amount_net': '158.28',
            'custom_str1': str(pending_booking.id), 'merchant_id': MERCHANT,
        }
        tamper = overrides.pop('tamper_sig', False)
        remote = overrides.pop('remote_addr', '127.0.0.1')
        passphrase = overrides.pop('passphrase', PASSPHRASE)
        fields.update(overrides)
        fields = {k: v for k, v in fields.items() if v is not None}
        return APIClient().generic('POST', ITN, _signed_body(fields, passphrase, tamper),
                                   content_type='application/x-www-form-urlencoded', REMOTE_ADDR=remote)

    return itn, calls, ref


@pytest.mark.django_db
class TestPayFastITN:
    def test_valid_itn_confirms_booking(self, pf, pending_booking):
        itn, calls, ref = pf
        assert itn().status_code == 200
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.CONFIRMED
        tx = PaymentTransaction.objects.get(merchant_reference=ref)
        assert tx.status == 'success' and tx.gateway_reference == '1089250'
        assert tx.fx_rate_to_zar == Decimal('1.000000')
        assert tx.fx_source == 'transaction_currency'
        assert tx.provider_fee_amount == Decimal('3.72') and tx.provider_fee_currency == 'ZAR'
        assert LedgerEntry.objects.filter(
            payment_transaction=tx,
            account=LedgerAccount.EXPENSE_GATEWAY_FEES,
            amount=Decimal('3.72'),
        ).exists()
        assert PaymentTransaction.objects.count() == 1
        assert calls['postback'] == 1 and 'sandbox.payfast.co.za' in calls['url']

    def test_bad_signature_rejected(self, pf, pending_booking):
        itn, _, _ = pf
        assert itn(tamper_sig=True).status_code == 400
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.PENDING_PAYMENT

    def test_wrong_passphrase_rejected(self, pf):
        itn, _, _ = pf
        assert itn(passphrase='attacker-guess').status_code == 400

    def test_unsigned_forged_itn_rejected(self, pf, pending_booking):
        res = APIClient().generic('POST', ITN, urlencode({
            'm_payment_id': 'X', 'payment_status': 'COMPLETE', 'amount_gross': '0.01',
            'custom_str1': str(pending_booking.id)}), content_type='application/x-www-form-urlencoded')
        assert res.status_code == 400
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.PENDING_PAYMENT

    def test_wrong_source_ip_rejected(self, pf):
        itn, calls, _ = pf
        assert itn(remote_addr='203.0.113.9').status_code == 400
        assert calls['postback'] == 0

    def test_amount_mismatch_rejected(self, pf, pending_booking):
        itn, _, _ = pf
        assert itn(amount_gross='1.00').status_code == 400
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.PENDING_PAYMENT

    def test_merchant_mismatch_rejected(self, pf):
        itn, _, _ = pf
        assert itn(merchant_id='99999999').status_code == 400

    def test_unknown_reference_rejected(self, pf):
        itn, _, _ = pf
        assert itn(m_payment_id='TX-DOESNOTEXIST').status_code == 400

    def test_missing_pf_payment_id_rejected(self, pf):
        itn, _, _ = pf
        assert itn(pf_payment_id=None).status_code == 400

    def test_postback_not_valid_rejected(self, pf, pending_booking):
        itn, calls, _ = pf
        calls['answer'] = 'INVALID'
        assert itn().status_code == 400
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.PENDING_PAYMENT

    def test_duplicate_itn_is_idempotent(self, pf):
        itn, calls, _ = pf
        assert itn().status_code == 200
        assert itn().status_code == 200
        assert PaymentTransaction.objects.count() == 1
        assert calls['postback'] == 1

    def test_non_complete_status_acknowledged_without_confirming(self, pf, pending_booking):
        itn, _, _ = pf
        assert itn(payment_status='CANCELLED').status_code == 200
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.PENDING_PAYMENT

    def test_forwarded_ip_used_only_when_proxy_count_configured(self, pf, settings):
        itn, _, _ = pf
        settings.PAYFAST_TRUSTED_PROXY_COUNT = 0
        req = APIClient().generic('POST', ITN, '', REMOTE_ADDR='203.0.113.9', HTTP_X_FORWARDED_FOR='127.0.0.1')
        assert req.status_code == 400  # spoofed XFF ignored


def test_signature_matches_independent_md5():
    pairs = [('merchant_id', '10000100'), ('amount', '10.00'), ('item_name', 'Test Item')]
    expected = hashlib.md5(b"merchant_id=10000100&amount=10.00&item_name=Test+Item&passphrase=abc").hexdigest()
    sig_pairs = pairs + [('signature', expected)]
    assert payfast.verify_signature(sig_pairs, 'abc')
    assert not payfast.verify_signature(sig_pairs, 'abd')


# ---------- PayFast checkout URLs + documented signature order (Task 10.2 slice H) ----------

# PayFast signs the checkout form in the documented field order (NOT alphabetical).
PF_DOC_ORDER = ['merchant_id', 'merchant_key', 'return_url', 'cancel_url', 'notify_url', 'name_first', 'name_last',
                'email_address', 'm_payment_id', 'amount', 'item_name', 'custom_str1']


def _signed_pairs(fields):
    """Recompute the signature independently, walking the fields in PayFast's documented order."""
    ordered = sorted(((k, v) for k, v in fields.items() if k != 'signature'), key=lambda kv: PF_DOC_ORDER.index(kv[0]))
    qs = '&'.join(f"{k}={quote_plus(v.strip())}" for k, v in ordered) + f"&passphrase={quote_plus(PASSPHRASE)}"
    return hashlib.md5(qs.encode()).hexdigest()


@pytest.mark.django_db
class TestPayFastCheckoutUrls:
    def test_defaults_derive_from_frontend_base_url(self):
        from django.conf import settings
        assert settings.PAYFAST_RETURN_URL.endswith('/student/checkout/return')
        assert settings.PAYFAST_CANCEL_URL.endswith('/student/checkout/cancel')
        assert settings.PAYFAST_RETURN_URL.startswith(settings.FRONTEND_BASE_URL)

    def test_checkout_form_has_return_and_cancel_urls_with_opaque_reference(self, student_user, pending_booking, settings):
        settings.PAYFAST_RETURN_URL = 'https://sharonesl.com/student/checkout/return'
        settings.PAYFAST_CANCEL_URL = 'https://sharonesl.com/student/checkout/cancel'
        settings.PAYFAST_NOTIFY_URL = 'https://api.sharonesl.com/api/v1/payments/webhooks/payfast/'
        data = _checkout(student_user, pending_booking, 'payfast')
        f = data['fields']
        ref = data['transaction_reference']
        assert ref.startswith('TX-')
        assert f['return_url'] == f"https://sharonesl.com/student/checkout/return?ref={ref}"
        assert f['cancel_url'] == f"https://sharonesl.com/student/checkout/cancel?ref={ref}"
        assert str(pending_booking.id) not in f['return_url'] + f['cancel_url']
        assert f['signature'] == _signed_pairs(f)

    def test_field_order_is_payfast_documented_order(self):
        fields = payfast.build_checkout_fields(
            reference='TX-1', amount=Decimal('10.00'), item_name='Lesson', booking_id='b1',
            notify_url='https://x/n', return_url='https://x/r', cancel_url='https://x/c')
        keys = [k for k in fields if k != 'signature']
        assert keys == ['merchant_id', 'merchant_key', 'return_url', 'cancel_url', 'notify_url',
                        'm_payment_id', 'amount', 'item_name', 'custom_str1']
        assert fields['signature'] == _signed_pairs(fields)
        assert payfast.verify_signature(list(fields.items()), PASSPHRASE)

    def test_buyer_fields_sit_between_notify_url_and_m_payment_id(self):
        fields = payfast.build_checkout_fields(
            reference='TX-1', amount=Decimal('10.00'), item_name='Lesson', booking_id='b1',
            notify_url='https://x/n', return_url='https://x/r', cancel_url='https://x/c',
            name_first='Ann', email_address='a@b.co')
        keys = list(fields)
        assert keys.index('notify_url') < keys.index('name_first') < keys.index('email_address') < keys.index('m_payment_id')
        assert fields['signature'] == _signed_pairs(fields)

    def test_tampering_with_return_url_invalidates_signature(self):
        fields = payfast.build_checkout_fields(
            reference='TX-1', amount=Decimal('10.00'), item_name='Lesson', booking_id='b1',
            notify_url='https://x/n', return_url='https://x/r', cancel_url='https://x/c')
        assert payfast.verify_signature(list(fields.items()), PASSPHRASE)
        for field in ('return_url', 'cancel_url'):
            bad = dict(fields, **{field: 'https://evil.example/steal'})
            assert not payfast.verify_signature(list(bad.items()), PASSPHRASE)


# ---------- PayPal ----------

def _now_iso():
    return timezone.now().strftime('%Y-%m-%dT%H:%M:%SZ')


def _pp_headers(**overrides):
    headers = {
        'HTTP_PAYPAL_AUTH_ALGO': 'SHA256withRSA', 'HTTP_PAYPAL_CERT_URL': 'https://api.sandbox.paypal.com/cert',
        'HTTP_PAYPAL_TRANSMISSION_ID': 'tid', 'HTTP_PAYPAL_TRANSMISSION_SIG': 'sig',
        'HTTP_PAYPAL_TRANSMISSION_TIME': _now_iso(),
    }
    headers.update(overrides)
    return headers


@pytest.fixture
def pp(monkeypatch, student_user, pending_booking):
    state = {'verify': 'SUCCESS', 'capture': None, 'lookup_error': False, 'verify_calls': []}
    data = _checkout(student_user, pending_booking, 'paypal')
    ref = data['transaction_reference']
    state['capture'] = {'id': 'CAP-1', 'status': 'COMPLETED', 'custom_id': ref,
                        'amount': {'value': '9.00', 'currency_code': 'USD'}}

    class Resp:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            if state['lookup_error']:
                raise paypal.requests.RequestException('boom')

        def json(self):
            return self.payload

    state['verify_status_code'] = 200
    state['bodies'] = []

    def fake_token_post(url, **kw):
        return Resp({'access_token': 'tok', 'expires_in': 3600})

    def fake_request(method, url, **kw):
        if method == 'POST':
            state['bodies'].append(kw['data'])
            state['verify_calls'].append(json.loads(kw['data']))
            r = Resp({'verification_status': state['verify']})
            r.status_code = state['verify_status_code']
            return r
        return Resp(state['capture'])

    monkeypatch.setattr(paypal.requests, 'post', fake_token_post)
    monkeypatch.setattr(paypal.requests, 'request', fake_request)

    def hook(event_type='PAYMENT.CAPTURE.COMPLETED', headers=None, body=None):
        event = {'id': 'WH-EVT', 'event_type': event_type, 'resource': {'id': 'CAP-1', 'amount': {'value': '0.01', 'currency_code': 'USD'}}}
        raw = body if body is not None else json.dumps(event)
        return APIClient().generic('POST', PP, raw, content_type='application/json',
                                   **(headers if headers is not None else _pp_headers()))

    return hook, state, ref


@pytest.mark.django_db
class TestPayPalWebhook:
    def test_valid_capture_confirms_booking(self, pp, pending_booking):
        hook, state, ref = pp
        assert hook().status_code == 200
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.CONFIRMED
        tx = PaymentTransaction.objects.get(merchant_reference=ref)
        assert tx.gateway_reference == 'CAP-1' and tx.status == 'success'
        sent = state['verify_calls'][0]
        assert sent['webhook_id'] == 'WH-TEST' and sent['transmission_id'] == 'tid'

    def test_amount_comes_from_paypal_not_webhook_body(self, pp, pending_booking):
        # body claims 0.01 USD but PayPal's own record says 9.00 -> accepted using PayPal's value
        hook, _, ref = pp
        assert hook().status_code == 200
        assert PaymentTransaction.objects.get(merchant_reference=ref).amount == Decimal('9.00')

    def test_bad_signature_rejected(self, pp, pending_booking):
        hook, state, _ = pp
        state['verify'] = 'FAILURE'
        assert hook().status_code == 400
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.PENDING_PAYMENT

    def test_missing_signature_headers_rejected(self, pp):
        hook, _, _ = pp
        assert hook(headers={}).status_code == 400

    def test_underpaid_capture_rejected(self, pp, pending_booking):
        hook, state, _ = pp
        state['capture']['amount']['value'] = '1.00'
        assert hook().status_code == 400
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.PENDING_PAYMENT

    def test_currency_mismatch_rejected(self, pp):
        hook, state, _ = pp
        state['capture']['amount']['currency_code'] = 'JPY'
        assert hook().status_code == 400

    def test_unknown_custom_id_rejected(self, pp):
        hook, state, _ = pp
        state['capture']['custom_id'] = 'TX-NOPE'
        assert hook().status_code == 400

    def test_incomplete_capture_rejected(self, pp):
        hook, state, _ = pp
        state['capture']['status'] = 'PENDING'
        assert hook().status_code == 400

    def test_other_event_types_acknowledged_noop(self, pp, pending_booking):
        hook, _, _ = pp
        assert hook(event_type='CHECKOUT.ORDER.COMPLETED').status_code == 200
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.PENDING_PAYMENT

    def test_duplicate_delivery_idempotent(self, pp):
        hook, _, _ = pp
        assert hook().status_code == 200
        assert hook().status_code == 200
        assert PaymentTransaction.objects.count() == 1

    def test_paypal_outage_returns_503_so_paypal_retries(self, pp):
        hook, state, _ = pp
        state['lookup_error'] = True
        assert hook().status_code == 503
