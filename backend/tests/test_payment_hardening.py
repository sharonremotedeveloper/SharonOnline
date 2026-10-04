"""Audit-driven payment hardening: surplus money, input validation, signature/IP/PayPal details."""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.admin_api.models import DisputeCase
from apps.bookings.models import Booking
from apps.payments.gateways import payfast, paypal
from apps.payments.models import CreditBundle, LessonPrice, GatewayAnomaly, LedgerEntry, PaymentTransaction

# Reuse the fixtures/helpers from the baseline verification suite (fixtures are registered by name).
from tests.test_payment_verification import (  # noqa: F401
    _checkout, _pp_headers, gateway_settings, pending_booking, pf, pp,
)


def _unallocated_held(gateway_reference):
    return LedgerEntry.objects.filter(
        payment_transaction__gateway_reference=gateway_reference,
        event_type=LedgerEntry.EventType.UNALLOCATED_PAYMENT,
        account='2030_liability_quarantine_deposit', entry_type='credit').exists()


# ---------- Surplus / duplicate money must never be silently dropped or corrupt a booking ----------

@pytest.mark.django_db
class TestSurplusPayments:
    def test_payfast_second_payment_on_settled_reference_is_held_not_dropped(self, pf, pending_booking):
        itn, _, ref = pf
        assert itn().status_code == 200
        assert itn(pf_payment_id='2222222').status_code == 200   # same signed form paid again
        dup = PaymentTransaction.objects.get(gateway_reference='2222222')
        assert dup.status == PaymentTransaction.Status.UNALLOCATED and dup.amount == Decimal('162.00')
        assert _unallocated_held('2222222')
        assert GatewayAnomaly.objects.filter(reason='duplicate_payment', reference='2222222', resolved=False).exists()
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.CONFIRMED
        # Redelivery of the surplus ITN is idempotent: no second ledger leg, no second row
        assert itn(pf_payment_id='2222222').status_code == 200
        assert PaymentTransaction.objects.filter(gateway_reference='2222222').count() == 1
        assert LedgerEntry.objects.filter(payment_transaction=dup).count() == 2

    def test_paypal_second_capture_on_settled_reference_is_held(self, pp, pending_booking):
        hook, state, ref = pp
        assert hook().status_code == 200
        state['capture'] = {**state['capture'], 'id': 'CAP-2'}
        body = json.dumps({'id': 'WH-2', 'event_type': 'PAYMENT.CAPTURE.COMPLETED', 'resource': {'id': 'CAP-2'}})
        assert hook(body=body).status_code == 200
        dup = PaymentTransaction.objects.get(gateway_reference='CAP-2')
        assert dup.status == PaymentTransaction.Status.UNALLOCATED
        assert _unallocated_held('CAP-2')
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.CONFIRMED

    def test_second_checkout_paid_after_booking_confirmed_is_held(self, pf, student_user, pending_booking):
        itn, _, _ = pf
        ref2 = _checkout(student_user, pending_booking, 'payfast')['transaction_reference']
        assert itn().status_code == 200
        assert itn(m_payment_id=ref2, pf_payment_id='3333333').status_code == 200
        assert PaymentTransaction.objects.get(merchant_reference=ref2).status == PaymentTransaction.Status.UNALLOCATED
        assert PaymentTransaction.objects.filter(status=PaymentTransaction.Status.SUCCESS).count() == 1
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.CONFIRMED

    @pytest.mark.parametrize('final_state', [Booking.Status.COMPLETED, Booking.Status.IN_PROGRESS,
                                             Booking.Status.COMPLETED_PENDING_MEMO, Booking.Status.DISPUTED])
    def test_late_second_payment_cannot_corrupt_a_finished_booking(self, pf, pending_booking, student_user, final_state):
        """A second INITIALIZED tx paid after the lesson must not flip the booking to DISPUTED / freeze payouts."""
        itn, _, ref = pf
        Booking.objects.filter(pk=pending_booking.pk).update(
            status=final_state, start_time_utc=timezone.now() - timedelta(hours=3),
            end_time_utc=timezone.now() - timedelta(hours=2, minutes=35))
        assert itn().status_code == 200
        pending_booking.refresh_from_db()
        assert pending_booking.status == final_state                  # untouched
        assert not DisputeCase.objects.filter(booking=pending_booking).exists()
        assert not CreditBundle.objects.filter(user=student_user).exists()
        tx = PaymentTransaction.objects.get(merchant_reference=ref)
        assert tx.status == PaymentTransaction.Status.UNALLOCATED and _unallocated_held(tx.gateway_reference)

    def test_unallocated_money_never_enters_escrow_selection(self, pf, pending_booking):
        itn, _, _ = pf
        itn()
        itn(pf_payment_id='4444444')
        success = PaymentTransaction.objects.filter(status=PaymentTransaction.Status.SUCCESS, escrow_cleared=False)
        assert success.count() == 1   # the escrow task selects SUCCESS rows only

    def test_authenticated_amount_mismatch_leaves_durable_anomaly(self, pf):
        itn, _, _ = pf
        assert itn(amount_gross='1.00').status_code == 400
        assert GatewayAnomaly.objects.filter(reason='amount_mismatch', resolved=False).count() == 1
        itn(amount_gross='1.00')  # gateway retry must not multiply rows
        assert GatewayAnomaly.objects.filter(reason='amount_mismatch').count() == 1

    def test_unauthenticated_junk_cannot_create_anomaly_rows(self, pf):
        itn, _, _ = pf
        itn(tamper_sig=True, amount_gross='1.00')
        itn(remote_addr='203.0.113.9', m_payment_id='TX-NOPE')
        assert GatewayAnomaly.objects.count() == 0

    def test_postback_not_made_inside_a_savepoint_we_opened(self, pf, monkeypatch):
        from django.db import connection
        itn, _, _ = pf
        depth = {}
        original = payfast.server_confirms

        def spy(pairs):
            depth['at_postback'] = len(connection.savepoint_ids)
            return original(pairs)

        monkeypatch.setattr(payfast, 'server_confirms', spy)
        assert itn().status_code == 200
        # The view's own atomic() (which holds the row lock) has not been entered yet when the postback runs.
        assert depth['at_postback'] == 0


# ---------- Checkout input validation ----------

@pytest.mark.django_db
class TestCheckoutValidation:
    def _post(self, student, body):
        c = APIClient()
        c.force_authenticate(student)
        return c.post('/api/v1/payments/checkout/init/', body, format='json')

    def test_non_uuid_booking_id_is_400_not_500(self, student_user):
        assert self._post(student_user, {'booking_id': 'not-a-uuid'}).status_code == 400

    def test_non_object_body_is_400(self, student_user):
        assert self._post(student_user, ['x']).status_code == 400

    def test_unverified_teacher_not_payable(self, student_user, pending_booking):
        from factories import advance_teacher
        advance_teacher(pending_booking.teacher, 'in_review')
        assert self._post(student_user, {'booking_id': str(pending_booking.id)}).status_code == 409

    def test_inactive_teacher_not_payable(self, student_user, pending_booking):
        from factories import advance_teacher
        advance_teacher(pending_booking.teacher, 'suspended')
        assert self._post(student_user, {'booking_id': str(pending_booking.id)}).status_code == 409

    def test_started_slot_not_payable(self, student_user, pending_booking):
        Booking.objects.filter(pk=pending_booking.pk).update(start_time_utc=timezone.now() - timedelta(minutes=1))
        assert self._post(student_user, {'booking_id': str(pending_booking.id)}).status_code == 409

    def test_missing_catalog_price_not_payable(self, student_user, pending_booking):
        LessonPrice.objects.filter(currency__in=['USD', 'ZAR']).update(is_active=False)
        assert self._post(student_user, {'booking_id': str(pending_booking.id)}).status_code == 409


# ---------- PayFast signature / network details ----------

def test_signature_encodes_tilde_like_php_urlencode():
    # PayFast signs PHP urlencode() output: '~' -> %7E, space -> '+'. Python's quote_plus alone would emit '~'.
    assert payfast.build_param_string([('item_name', 'a~b c'), ('signature', 'x')], '') == 'item_name=a%7Eb+c'
    assert payfast.build_param_string([('a', '1')], 'pass~word') == 'a=1&passphrase=pass%7Eword'


@pytest.mark.django_db
def test_extra_allowed_cidr_accepts_published_range(pf, settings):
    itn, _, _ = pf
    assert itn(remote_addr='203.0.113.9').status_code == 400
    settings.PAYFAST_EXTRA_ALLOWED_CIDRS = ['203.0.113.0/24']
    assert itn(remote_addr='203.0.113.9').status_code == 200


def test_dns_failure_is_negative_cached(monkeypatch):
    import socket
    calls = {'n': 0}

    def boom(host):
        calls['n'] += 1
        raise OSError('dns down')

    monkeypatch.setattr(socket, 'gethostbyname_ex', boom)
    monkeypatch.setitem(payfast._ip_cache, 'ips', set())
    monkeypatch.setitem(payfast._ip_cache, 'at', 0.0)
    monkeypatch.setitem(payfast._ip_cache, 'ttl', 0)
    payfast.get_valid_ips()
    first = calls['n']
    payfast.get_valid_ips()
    payfast.get_valid_ips()
    assert first == len(payfast.PAYFAST_HOSTS) and calls['n'] == first   # no re-resolving on every ITN


# ---------- PayPal verification details ----------

@pytest.mark.django_db
class TestPayPalVerificationDetails:
    def test_foreign_cert_url_rejected_without_outbound_call(self, pp):
        hook, state, _ = pp
        res = hook(headers=_pp_headers(HTTP_PAYPAL_CERT_URL='https://evil.example.com/cert'))
        assert res.status_code == 400 and state['bodies'] == []

    def test_lookalike_cert_host_rejected(self, pp):
        hook, state, _ = pp
        assert hook(headers=_pp_headers(HTTP_PAYPAL_CERT_URL='https://api.paypal.com.evil.io/c')).status_code == 400
        assert hook(headers=_pp_headers(HTTP_PAYPAL_CERT_URL='http://api.paypal.com/c')).status_code == 400
        assert state['bodies'] == []

    def test_unexpected_auth_algo_rejected(self, pp):
        hook, state, _ = pp
        assert hook(headers=_pp_headers(HTTP_PAYPAL_AUTH_ALGO='none')).status_code == 400
        assert state['bodies'] == []

    def test_ancient_or_garbage_transmission_time_rejected(self, pp):
        hook, state, _ = pp
        assert hook(headers=_pp_headers(HTTP_PAYPAL_TRANSMISSION_TIME='2020-01-01T00:00:00Z')).status_code == 400
        assert hook(headers=_pp_headers(HTTP_PAYPAL_TRANSMISSION_TIME='not-a-date')).status_code == 400
        assert state['bodies'] == []

    def test_retry_within_paypal_retry_window_still_verifies(self, pp):
        hook, _, _ = pp
        two_days = (timezone.now() - timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
        assert hook(headers=_pp_headers(HTTP_PAYPAL_TRANSMISSION_TIME=two_days)).status_code == 200

    def test_paypal_4xx_on_verify_is_invalid_not_outage(self, pp):
        hook, state, _ = pp
        state['verify_status_code'] = 400
        assert hook().status_code == 400   # PayPal said the signature is bad -> 400, not a 503 retry storm

    def test_raw_event_bytes_forwarded_verbatim_including_non_ascii(self, pp):
        hook, state, _ = pp
        raw = ('{"id": "WH-EVT",  "event_type": "PAYMENT.CAPTURE.COMPLETED", '
               '"resource": {"id": "CAP-1", "payer": "Zoë Müller \\u00e9", "n": 1.10}}')
        assert hook(body=raw).status_code == 200
        sent = state['bodies'][0].decode('utf-8')
        assert raw in sent                      # byte-for-byte, not re-serialised
        assert json.loads(sent)['webhook_event']['resource']['payer'].startswith('Zoë')

    def test_expired_token_is_refreshed_once_on_401(self, monkeypatch):
        from django.core.cache import cache
        cache.set(paypal.TOKEN_CACHE_KEY, 'stale')
        seen = []

        class R:
            def __init__(self, code):
                self.status_code = code

            def raise_for_status(self):
                pass

            def json(self):
                return {'access_token': 'fresh', 'expires_in': 3600}

        def fake_request(method, url, headers=None, **kw):
            seen.append(headers['Authorization'])
            return R(401 if headers['Authorization'].endswith('stale') else 200)

        monkeypatch.setattr(paypal.requests, 'request', fake_request)
        monkeypatch.setattr(paypal.requests, 'post', lambda *a, **k: R(200))
        resp = paypal._call('GET', 'https://x')
        assert resp.status_code == 200 and seen == ['Bearer stale', 'Bearer fresh']
