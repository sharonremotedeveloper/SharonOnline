"""Task 10.4 / 10.2 slice F: every gateway event the platform can receive, and the reconciliation of lost webhooks.

Rules under test: the signature gates EVERY event; PayPal is re-read for anything that matters (the webhook body is never
trusted for amounts or status); every handler is idempotent; a refund never posts twice; chargebacks create a durable
anomaly + DisputeCase and never move money by themselves; an unmatched payment is quarantined with a 200 (never a 500).
"""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.admin_api.models import DisputeCase
from apps.bookings.models import Booking
from apps.payments.gateways import paypal
from apps.payments.models import (GatewayAnomaly, LedgerAccount, LedgerEntry,
                                  PaymentTransaction, RefundRequest)
from apps.payments.services import grace, refunds
from apps.payments.services.reconciliation import reconcile_initialized_transaction
from apps.payments.tasks import reconcile_pending_transactions_task
from test_payment_verification import (  # noqa: F401  (fixtures + helpers shared with the gateway tests)
    ITN, PP, _checkout, _pp_headers, _signed_body, gateway_settings, pending_booking, pf, PASSPHRASE)
from test_settlement_paths import net

ACC = LedgerAccount
EV = LedgerEntry.EventType
CAP = 'CAP-1'


def capture_json(ref, status='COMPLETED', amount='9.00', currency='USD', cap_id=CAP, reason=None):
    c = {'id': cap_id, 'status': status, 'custom_id': ref, 'amount': {'value': amount, 'currency_code': currency}}
    if reason:
        c['status_details'] = {'reason': reason}
    return c


@pytest.fixture
def ev(monkeypatch, student_user, pending_booking):
    """A PayPal checkout (tx 9.00 USD) plus a scriptable PayPal. `state` holds what PayPal 'says' on a re-read."""
    state = {'verify': True, 'lookups': [], 'captures': {}, 'refunds': {}, 'disputes': {}, 'orders': {}, 'down': False}
    data = _checkout(student_user, pending_booking, 'paypal')
    ref = data['transaction_reference']
    state['captures'][CAP] = capture_json(ref)

    def lookup(kind, key, table):
        state['lookups'].append((kind, key))
        if state['down']:
            raise paypal.PayPalError('PayPal is down')
        if key not in state[table]:
            raise paypal.PayPalError(f'{kind} {key} not found')
        return json.loads(json.dumps(state[table][key]))

    monkeypatch.setattr(paypal, 'verify_webhook_signature', lambda meta, body: state['verify'])
    monkeypatch.setattr(paypal, 'get_capture', lambda i: lookup('capture', i, 'captures'))
    monkeypatch.setattr(paypal, 'get_refund', lambda i: lookup('refund', i, 'refunds'))
    monkeypatch.setattr(paypal, 'get_dispute', lambda i: lookup('dispute', i, 'disputes'))
    monkeypatch.setattr(paypal, 'get_order', lambda i: lookup('order', i, 'orders'))

    def hook(event_type='PAYMENT.CAPTURE.COMPLETED', resource=None, headers=None):
        # the webhook body deliberately lies about the amount: only the re-read may be believed
        body = {'id': 'WH-EVT', 'event_type': event_type,
                'resource': resource if resource is not None else {'id': CAP, 'amount': {'value': '0.01', 'currency_code': 'USD'}}}
        return APIClient().generic('POST', PP, json.dumps(body), content_type='application/json',
                                   **(headers if headers is not None else _pp_headers()))

    return hook, state, ref


def tx_of(ref):
    return PaymentTransaction.objects.get(merchant_reference=ref)


def settle(hook, ref):
    assert hook().status_code == 200
    tx = tx_of(ref)
    assert tx.status == PaymentTransaction.Status.SUCCESS
    return tx


def refund_json(cap_id=CAP, amount='9.00', currency='USD', status='COMPLETED', rid='REF-1'):
    return {'id': rid, 'status': status, 'amount': {'value': amount, 'currency_code': currency},
            'links': [{'rel': 'self', 'href': f'https://api.sandbox.paypal.com/v2/payments/refunds/{rid}'},
                      {'rel': 'up', 'href': f'https://api.sandbox.paypal.com/v2/payments/captures/{cap_id}'}]}


def dispute_json(dispute_id='PP-D-1', status='OPEN', outcome=None, cap_id=CAP):
    d = {'dispute_id': dispute_id, 'status': status, 'reason': 'MERCHANDISE_OR_SERVICE_NOT_RECEIVED',
         'disputed_transactions': [{'seller_transaction_id': cap_id}]}
    if outcome:
        d['dispute_outcome'] = {'outcome_code': outcome}
    return d


ALL_NEW_EVENTS = [
    ('PAYMENT.CAPTURE.DENIED', {'id': CAP}), ('PAYMENT.CAPTURE.DECLINED', {'id': CAP}),
    ('PAYMENT.CAPTURE.PENDING', {'id': CAP}), ('PAYMENT.CAPTURE.REFUNDED', {'id': 'REF-1'}),
    ('PAYMENT.CAPTURE.REVERSED', {'id': CAP}), ('CUSTOMER.DISPUTE.CREATED', {'dispute_id': 'PP-D-1'}),
    ('CUSTOMER.DISPUTE.RESOLVED', {'dispute_id': 'PP-D-1'}),
]


# ======================================================================================= signature gates everything
@pytest.mark.django_db
class TestSignatureGatesEveryEvent:
    @pytest.mark.parametrize('event_type,resource', ALL_NEW_EVENTS + [('PAYMENT.CAPTURE.COMPLETED', {'id': CAP})])
    def test_bad_signature_rejected_with_no_lookup_and_no_effect(self, ev, pending_booking, event_type, resource):
        hook, state, ref = ev
        state['verify'] = False
        state['refunds']['REF-1'] = refund_json()
        state['disputes']['PP-D-1'] = dispute_json()
        before = (PaymentTransaction.objects.count(), GatewayAnomaly.objects.count(), LedgerEntry.objects.count(),
                  DisputeCase.objects.count())
        assert hook(event_type, resource).status_code == 400
        assert state['lookups'] == []
        assert before == (PaymentTransaction.objects.count(), GatewayAnomaly.objects.count(),
                          LedgerEntry.objects.count(), DisputeCase.objects.count())
        assert tx_of(ref).status == PaymentTransaction.Status.INITIALIZED

    @pytest.mark.parametrize('event_type,resource', ALL_NEW_EVENTS)
    def test_paypal_outage_during_reread_is_503_so_paypal_retries(self, ev, event_type, resource):
        hook, state, _ = ev
        state['down'] = True
        assert hook(event_type, resource).status_code == 503

    def test_unknown_event_type_is_acknowledged_and_ignored(self, ev):
        hook, state, ref = ev
        res = hook('BILLING.SUBSCRIPTION.CREATED')
        assert res.status_code == 200 and res.json() == {'status': 'ignored'}
        assert state['lookups'] == []
        assert tx_of(ref).status == PaymentTransaction.Status.INITIALIZED


# ======================================================================================= DENIED / DECLINED
@pytest.mark.django_db
class TestCaptureDenied:
    @pytest.mark.parametrize('event_type,status', [('PAYMENT.CAPTURE.DENIED', 'DECLINED'), ('PAYMENT.CAPTURE.DENIED', 'DENIED'),
                                                   ('PAYMENT.CAPTURE.DECLINED', 'DECLINED')])
    def test_initialized_transaction_is_failed_without_grace(self, ev, monkeypatch, event_type, status):
        hook, state, ref = ev
        calls = []
        monkeypatch.setattr(grace, 'on_failed', lambda tx: calls.append(tx.pk))
        state['captures'][CAP]['status'] = status
        assert hook(event_type).status_code == 200
        assert tx_of(ref).status == PaymentTransaction.Status.FAILED
        assert calls == []                                    # nothing was ever confirmed on grace: nothing to unwind

    def test_pending_capture_failure_calls_grace_exactly_once_even_on_redelivery(self, ev, monkeypatch):
        hook, state, ref = ev
        calls = []
        monkeypatch.setattr(grace, 'on_failed', lambda tx: calls.append(tx.pk))
        PaymentTransaction.objects.filter(merchant_reference=ref).update(status=PaymentTransaction.Status.PENDING_CAPTURE)
        state['captures'][CAP]['status'] = 'DECLINED'
        assert hook('PAYMENT.CAPTURE.DENIED').status_code == 200
        assert hook('PAYMENT.CAPTURE.DENIED').status_code == 200
        assert hook('PAYMENT.CAPTURE.DECLINED').status_code == 200
        assert tx_of(ref).status == PaymentTransaction.Status.FAILED
        assert calls == [tx_of(ref).pk]

    def test_a_settled_transaction_is_never_failed(self, ev, monkeypatch):
        hook, state, ref = ev
        monkeypatch.setattr(grace, 'on_failed', lambda tx: pytest.fail('grace must not run for a settled payment'))
        tx = settle(hook, ref)
        state['captures'][CAP]['status'] = 'DECLINED'
        assert hook('PAYMENT.CAPTURE.DENIED').status_code == 200
        tx.refresh_from_db()
        assert tx.status == PaymentTransaction.Status.SUCCESS

    def test_status_comes_from_paypal_not_the_event_name(self, ev, monkeypatch):
        hook, state, ref = ev
        monkeypatch.setattr(grace, 'on_failed', lambda tx: pytest.fail('not failed per PayPal'))
        state['captures'][CAP]['status'] = 'COMPLETED'        # PayPal says it is fine: a forged/stale event changes nothing
        assert hook('PAYMENT.CAPTURE.DENIED').status_code == 200
        assert tx_of(ref).status == PaymentTransaction.Status.INITIALIZED

    def test_unknown_capture_is_quarantined_not_an_error(self, ev):
        hook, state, ref = ev
        state['captures'][CAP]['custom_id'] = 'TX-NOPE'
        state['captures'][CAP]['status'] = 'DECLINED'
        assert hook('PAYMENT.CAPTURE.DENIED').status_code == 200
        assert GatewayAnomaly.objects.filter(reason='unknown_reference', reference=CAP).count() == 1
        assert tx_of(ref).status == PaymentTransaction.Status.INITIALIZED


# ======================================================================================= PENDING
@pytest.mark.django_db
class TestCapturePending:
    def test_records_pending_with_reason_and_never_touches_the_booking(self, ev, pending_booking):
        hook, state, ref = ev
        state['captures'][CAP] = capture_json(ref, status='PENDING', reason='PENDING_REVIEW')
        state['orders'][f'ORDER-{ref}'] = {'id': f'ORDER-{ref}', 'payer': {'payer_id': 'PAYER1', 'email_address': 'p@example.com'}}
        assert hook('PAYMENT.CAPTURE.PENDING').status_code == 200
        tx = tx_of(ref)
        assert tx.status == PaymentTransaction.Status.PENDING_CAPTURE and tx.pending_reason == 'PENDING_REVIEW'
        assert tx.payer_id == 'PAYER1' and tx.gateway_reference == CAP
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.PENDING_PAYMENT
        assert LedgerEntry.objects.count() == 0               # nothing is posted while the money is not guaranteed

    def test_redelivery_is_idempotent(self, ev):
        hook, state, ref = ev
        state['captures'][CAP] = capture_json(ref, status='PENDING', reason='PENDING_REVIEW')
        state['orders'][f'ORDER-{ref}'] = {'id': 'x', 'payer': {}}
        assert hook('PAYMENT.CAPTURE.PENDING').status_code == 200
        assert hook('PAYMENT.CAPTURE.PENDING').status_code == 200
        assert PaymentTransaction.objects.count() == 1
        assert tx_of(ref).status == PaymentTransaction.Status.PENDING_CAPTURE

    def test_does_not_resurrect_failed_or_settled_transactions(self, ev):
        hook, state, ref = ev
        state['captures'][CAP] = capture_json(ref, status='PENDING', reason='PENDING_REVIEW')
        state['orders'][f'ORDER-{ref}'] = {'id': 'x', 'payer': {}}
        PaymentTransaction.objects.filter(merchant_reference=ref).update(status=PaymentTransaction.Status.FAILED)
        assert hook('PAYMENT.CAPTURE.PENDING').status_code == 200
        assert tx_of(ref).status == PaymentTransaction.Status.FAILED

    def test_amount_is_verified_against_paypal_not_the_event(self, ev):
        hook, state, ref = ev
        state['captures'][CAP] = capture_json(ref, status='PENDING', amount='1.00', reason='PENDING_REVIEW')
        assert hook('PAYMENT.CAPTURE.PENDING').status_code == 400
        assert tx_of(ref).status == PaymentTransaction.Status.INITIALIZED
        assert GatewayAnomaly.objects.filter(reason='amount_mismatch').exists()

    def test_paypal_says_completed_means_the_completed_event_settles_it_not_this_one(self, ev):
        hook, state, ref = ev
        assert hook('PAYMENT.CAPTURE.PENDING').status_code == 200
        assert tx_of(ref).status == PaymentTransaction.Status.INITIALIZED


# ======================================================================================= REFUNDED
@pytest.mark.django_db
class TestCaptureRefunded:
    def _confirmed(self, hook, ref, pending_booking):
        tx = settle(hook, ref)
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.CONFIRMED
        return tx

    def test_a_refund_we_initiated_is_completed_exactly_once(self, ev, pending_booking):
        hook, state, ref = ev
        self._confirmed(hook, ref, pending_booking)
        outcome = refunds.request_refund(pending_booking, RefundRequest.Reason.STUDENT_CANCEL)
        state['refunds']['REF-1'] = refund_json()
        entries_before = LedgerEntry.objects.count()
        for _ in range(3):
            assert hook('PAYMENT.CAPTURE.REFUNDED', {'id': 'REF-1'}).status_code == 200
        rr = RefundRequest.objects.get(pk=outcome.refund.pk)
        assert rr.status == RefundRequest.Status.PROCESSED and rr.gateway_reference == 'REF-1'
        assert LedgerEntry.objects.filter(event_type=EV.GATEWAY_REFUND_PAID).count() == 2     # one balanced pair, once
        assert LedgerEntry.objects.count() == entries_before + 2
        assert net(pending_booking, ACC.LIABILITY_REFUNDS_PAYABLE) == Decimal('0')
        assert not GatewayAnomaly.objects.filter(reason='external_refund').exists()
        assert tx_of(ref).status == PaymentTransaction.Status.REFUNDED

    def test_refund_already_paid_by_our_own_flow_never_posts_again(self, ev, pending_booking):
        hook, state, ref = ev
        self._confirmed(hook, ref, pending_booking)
        outcome = refunds.request_refund(pending_booking, RefundRequest.Reason.STUDENT_CANCEL)
        refunds.mark_processed(outcome.refund.pk, 'OUR-REF')                 # our flow got there first, other reference
        entries = LedgerEntry.objects.count()
        state['refunds']['REF-1'] = refund_json()
        assert hook('PAYMENT.CAPTURE.REFUNDED', {'id': 'REF-1'}).status_code == 200
        assert LedgerEntry.objects.count() == entries
        assert RefundRequest.objects.count() == 1

    def test_dashboard_refund_with_no_request_is_an_anomaly_and_reverses_the_ledger_once(self, ev, pending_booking):
        hook, state, ref = ev
        self._confirmed(hook, ref, pending_booking)
        assert net(pending_booking, ACC.LIABILITY_STUDENT_ESCROW) == Decimal('9.00')
        state['refunds']['REF-1'] = refund_json()
        for _ in range(3):
            assert hook('PAYMENT.CAPTURE.REFUNDED', {'id': 'REF-1'}).status_code == 200
        anomaly = GatewayAnomaly.objects.get(reason='external_refund')
        assert anomaly.reference == 'REF-1' and anomaly.booking_id == pending_booking.id
        rr = RefundRequest.objects.get(booking=pending_booking)
        assert rr.status == RefundRequest.Status.PROCESSED and rr.gateway_reference == 'REF-1' and rr.amount == Decimal('9.00')
        assert net(pending_booking, ACC.LIABILITY_STUDENT_ESCROW) == Decimal('0')          # escrow released back
        assert net(pending_booking, ACC.LIABILITY_REFUNDS_PAYABLE) == Decimal('0')
        assert net(pending_booking, ACC.ASSET_GATEWAY_PAYPAL) == Decimal('0')              # the cash really left PayPal
        assert LedgerEntry.objects.filter(event_type=EV.GATEWAY_REFUND_PAID).count() == 2
        assert tx_of(ref).status == PaymentTransaction.Status.REFUNDED

    def test_partial_dashboard_refund_flags_a_human_and_posts_nothing(self, ev, pending_booking):
        hook, state, ref = ev
        self._confirmed(hook, ref, pending_booking)
        entries = LedgerEntry.objects.count()
        state['refunds']['REF-1'] = refund_json(amount='3.00')
        assert hook('PAYMENT.CAPTURE.REFUNDED', {'id': 'REF-1'}).status_code == 200
        assert LedgerEntry.objects.count() == entries and not RefundRequest.objects.exists()
        assert GatewayAnomaly.objects.filter(reason='external_refund').count() == 1
        assert tx_of(ref).status == PaymentTransaction.Status.SUCCESS

    def test_amount_is_read_from_paypal_not_the_webhook(self, ev, pending_booking):
        hook, state, ref = ev
        self._confirmed(hook, ref, pending_booking)
        state['refunds']['REF-1'] = refund_json(amount='3.00')   # webhook body claims 0.01, PayPal says a partial 3.00
        assert hook('PAYMENT.CAPTURE.REFUNDED', {'id': 'REF-1', 'amount': {'value': '9.00', 'currency_code': 'USD'}}).status_code == 200
        assert not RefundRequest.objects.exists()               # the lie about a full refund was not believed

    def test_refund_not_completed_yet_is_ignored(self, ev, pending_booking):
        hook, state, ref = ev
        self._confirmed(hook, ref, pending_booking)
        state['refunds']['REF-1'] = refund_json(status='PENDING')
        entries = LedgerEntry.objects.count()
        assert hook('PAYMENT.CAPTURE.REFUNDED', {'id': 'REF-1'}).status_code == 200
        assert LedgerEntry.objects.count() == entries and not GatewayAnomaly.objects.filter(reason='external_refund').exists()

    def test_refund_of_an_unknown_payment_is_quarantined(self, ev):
        hook, state, ref = ev
        state['captures'][CAP]['custom_id'] = 'TX-NOPE'
        state['refunds']['REF-1'] = refund_json()
        assert hook('PAYMENT.CAPTURE.REFUNDED', {'id': 'REF-1'}).status_code == 200
        assert GatewayAnomaly.objects.filter(reason='unknown_reference').count() == 1

    def test_dashboard_refund_when_escrow_was_already_returned_posts_nothing_more(self, ev, pending_booking):
        hook, state, ref = ev
        self._confirmed(hook, ref, pending_booking)
        outcome = refunds.request_refund(pending_booking, RefundRequest.Reason.TEACHER_CANCEL)   # escrow already settled
        RefundRequest.objects.filter(pk=outcome.refund.pk).update(status=RefundRequest.Status.CONVERTED)
        entries = LedgerEntry.objects.count()
        state['refunds']['REF-9'] = refund_json(rid='REF-9')
        assert hook('PAYMENT.CAPTURE.REFUNDED', {'id': 'REF-9'}).status_code == 200
        assert LedgerEntry.objects.count() == entries              # nothing further is posted
        assert GatewayAnomaly.objects.filter(reason='external_refund').count() == 1


# ======================================================================================= chargebacks
@pytest.mark.django_db
class TestChargebacks:
    def _assert_opened(self, ref, pending_booking, reference):
        anomaly = GatewayAnomaly.objects.get(reason='chargeback_opened')
        assert anomaly.reference == reference and anomaly.booking_id == pending_booking.id and not anomaly.resolved
        case = DisputeCase.objects.get(booking=pending_booking)
        assert case.status == DisputeCase.Status.OPEN
        return anomaly, case

    def test_reversed_capture_flags_the_booking_and_moves_no_money(self, ev, pending_booking):
        hook, state, ref = ev
        tx = settle(hook, ref)
        ledger = list(LedgerEntry.objects.values_list('pk', flat=True))
        state['captures'][CAP]['status'] = 'REFUNDED'
        for _ in range(2):
            assert hook('PAYMENT.CAPTURE.REVERSED').status_code == 200
        self._assert_opened(ref, pending_booking, CAP)
        assert list(LedgerEntry.objects.values_list('pk', flat=True)) == ledger
        assert DisputeCase.objects.count() == 1 and GatewayAnomaly.objects.filter(reason='chargeback_opened').count() == 1
        tx.refresh_from_db()
        assert tx.status == PaymentTransaction.Status.SUCCESS and tx.escrow_cleared is False
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.CONFIRMED

    def test_dispute_created_is_resolved_to_the_booking_through_the_disputed_capture(self, ev, pending_booking):
        hook, state, ref = ev
        settle(hook, ref)
        ledger = LedgerEntry.objects.count()
        state['disputes']['PP-D-1'] = dispute_json()
        for _ in range(2):
            assert hook('CUSTOMER.DISPUTE.CREATED', {'dispute_id': 'PP-D-1'}).status_code == 200
        self._assert_opened(ref, pending_booking, 'PP-D-1')
        assert ('dispute', 'PP-D-1') in state['lookups'] and ('capture', CAP) in state['lookups']
        assert LedgerEntry.objects.count() == ledger
        assert DisputeCase.objects.count() == 1

    def test_dispute_resolved_updates_the_trail_and_still_leaves_the_money_to_a_human(self, ev, pending_booking):
        hook, state, ref = ev
        settle(hook, ref)
        state['disputes']['PP-D-1'] = dispute_json()
        assert hook('CUSTOMER.DISPUTE.CREATED', {'dispute_id': 'PP-D-1'}).status_code == 200
        ledger = LedgerEntry.objects.count()
        state['disputes']['PP-D-1'] = dispute_json(status='RESOLVED', outcome='RESOLVED_BUYER_FAVOUR')
        for _ in range(2):
            assert hook('CUSTOMER.DISPUTE.RESOLVED', {'dispute_id': 'PP-D-1'}).status_code == 200
        resolved = GatewayAnomaly.objects.get(reason='chargeback_resolved')
        assert resolved.reference == 'PP-D-1' and 'RESOLVED_BUYER_FAVOUR' in resolved.detail and not resolved.resolved
        assert GatewayAnomaly.objects.filter(reason='chargeback_opened').count() == 1
        case = DisputeCase.objects.get(booking=pending_booking)
        assert case.status == DisputeCase.Status.OPEN and 'RESOLVED_BUYER_FAVOUR' in case.admin_notes
        assert LedgerEntry.objects.count() == ledger
        assert tx_of(ref).status == PaymentTransaction.Status.SUCCESS

    def test_resolved_without_a_prior_open_event_still_opens_the_review(self, ev, pending_booking):
        hook, state, ref = ev
        settle(hook, ref)
        state['disputes']['PP-D-1'] = dispute_json(status='RESOLVED', outcome='RESOLVED_SELLER_FAVOUR')
        assert hook('CUSTOMER.DISPUTE.RESOLVED', {'dispute_id': 'PP-D-1'}).status_code == 200
        assert GatewayAnomaly.objects.filter(reason='chargeback_resolved').count() == 1
        assert DisputeCase.objects.filter(booking=pending_booking).count() == 1

    def test_dispute_over_an_unknown_transaction_is_quarantined(self, ev):
        hook, state, ref = ev
        state['disputes']['PP-D-1'] = dispute_json(cap_id='CAP-OTHER')
        state['captures']['CAP-OTHER'] = capture_json('TX-NOPE', cap_id='CAP-OTHER')
        assert hook('CUSTOMER.DISPUTE.CREATED', {'dispute_id': 'PP-D-1'}).status_code == 200
        assert GatewayAnomaly.objects.filter(reason='unknown_reference').count() == 1
        assert not DisputeCase.objects.exists()

    def test_an_existing_dispute_case_is_extended_not_duplicated(self, ev, pending_booking):
        hook, state, ref = ev
        settle(hook, ref)
        DisputeCase.objects.create(booking=pending_booking, student=pending_booking.student,
                                   teacher=pending_booking.teacher, student_statement='earlier complaint')
        state['disputes']['PP-D-1'] = dispute_json()
        assert hook('CUSTOMER.DISPUTE.CREATED', {'dispute_id': 'PP-D-1'}).status_code == 200
        case = DisputeCase.objects.get(booking=pending_booking)
        assert case.student_statement == 'earlier complaint' and 'PP-D-1' in case.admin_notes


# ======================================================================================= unknown reference quarantine
@pytest.mark.django_db
class TestUnmatchedPaymentsAreQuarantinedNot500:
    def test_paypal_completed_for_unknown_custom_id_is_anomaly_and_200(self, ev):
        hook, state, ref = ev
        state['captures'][CAP]['custom_id'] = 'TX-NOPE'
        res = hook()
        assert res.status_code == 200
        assert GatewayAnomaly.objects.filter(gateway='paypal', reason='unknown_reference', reference=CAP).count() == 1
        assert hook().status_code == 200
        assert GatewayAnomaly.objects.filter(reason='unknown_reference').count() == 1   # deduplicated on redelivery
        assert tx_of(ref).status == PaymentTransaction.Status.INITIALIZED

    @pytest.mark.parametrize('custom_id', [None, 12345, ['TX-1'], {'a': 1}, ''])
    def test_paypal_completed_with_malformed_custom_id_is_200_not_500(self, ev, custom_id):
        hook, state, ref = ev
        state['captures'][CAP]['custom_id'] = custom_id
        assert hook().status_code == 200
        assert GatewayAnomaly.objects.filter(reason='unknown_reference').count() == 1

    def test_paypal_oversized_capture_id_is_rejected_cleanly(self, ev):
        hook, state, ref = ev
        assert hook(resource={'id': 'X' * 300}).status_code == 400

    def test_paypal_capture_lookup_returning_junk_is_not_a_500(self, ev, monkeypatch):
        hook, state, ref = ev
        monkeypatch.setattr(paypal, 'get_capture', lambda i: ['not', 'a', 'dict'])
        assert hook().status_code in (400, 503)

    def test_payfast_complete_for_unknown_reference_is_anomaly_and_200(self, pf):
        itn, _, _ = pf
        assert itn(m_payment_id='TX-DOESNOTEXIST').status_code == 200
        assert GatewayAnomaly.objects.filter(gateway='payfast', reason='unknown_reference', reference='TX-DOESNOTEXIST').count() == 1

    def test_payfast_oversized_pf_payment_id_is_rejected_cleanly(self, pf):
        itn, _, _ = pf
        assert itn(pf_payment_id='9' * 300).status_code == 400


# ======================================================================================= PayFast CANCELLED / FAILED
@pytest.mark.django_db
class TestPayFastNonCompleteStatuses:
    @pytest.mark.parametrize('payment_status', ['CANCELLED', 'FAILED'])
    def test_initialized_transaction_is_failed(self, pf, pending_booking, payment_status):
        itn, calls, ref = pf
        assert itn(payment_status=payment_status).status_code == 200
        assert PaymentTransaction.objects.get(merchant_reference=ref).status == PaymentTransaction.Status.FAILED
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.PENDING_PAYMENT
        assert LedgerEntry.objects.count() == 0

    def test_redelivery_is_idempotent(self, pf):
        itn, _, ref = pf
        assert itn(payment_status='CANCELLED').status_code == 200
        assert itn(payment_status='CANCELLED').status_code == 200
        assert PaymentTransaction.objects.count() == 1

    def test_a_settled_transaction_is_never_failed_by_a_late_cancel(self, pf):
        itn, _, ref = pf
        assert itn().status_code == 200
        before = PaymentTransaction.objects.get(merchant_reference=ref)
        assert before.status == PaymentTransaction.Status.SUCCESS
        assert itn(payment_status='CANCELLED').status_code == 200
        assert itn(payment_status='FAILED').status_code == 200
        assert PaymentTransaction.objects.get(merchant_reference=ref).status == PaymentTransaction.Status.SUCCESS

    def test_the_same_form_paid_after_a_cancel_still_settles(self, pf, pending_booking):
        itn, _, ref = pf
        assert itn(payment_status='CANCELLED').status_code == 200
        assert itn().status_code == 200
        assert PaymentTransaction.objects.get(merchant_reference=ref).status == PaymentTransaction.Status.SUCCESS
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.CONFIRMED

    def test_cancel_with_a_bad_signature_changes_nothing(self, pf):
        itn, _, ref = pf
        assert itn(payment_status='CANCELLED', tamper_sig=True).status_code == 400
        assert PaymentTransaction.objects.get(merchant_reference=ref).status == PaymentTransaction.Status.INITIALIZED

    def test_unknown_status_is_ignored_but_logged(self, pf, caplog):
        itn, _, ref = pf
        with caplog.at_level('WARNING'):
            assert itn(payment_status='SOMETHING_NEW').status_code == 200
        assert PaymentTransaction.objects.get(merchant_reference=ref).status == PaymentTransaction.Status.INITIALIZED
        assert any('SOMETHING_NEW' in r.getMessage() for r in caplog.records)

    def test_pending_status_is_acknowledged_without_failing(self, pf):
        itn, _, ref = pf
        assert itn(payment_status='PENDING').status_code == 200
        assert PaymentTransaction.objects.get(merchant_reference=ref).status == PaymentTransaction.Status.INITIALIZED


# ======================================================================================= reconciliation of lost webhooks
def age(ref, hours=3):
    old = timezone.now() - timedelta(hours=hours)
    tx = PaymentTransaction.objects.get(merchant_reference=ref)
    PaymentTransaction.objects.filter(pk=tx.pk).update(created_at=old)
    if tx.booking_id:
        Booking.objects.filter(pk=tx.booking_id).update(created_at=old)
    return PaymentTransaction.objects.get(pk=tx.pk)


def order_json(ref, status='APPROVED', capture=None):
    unit = {'custom_id': ref}
    if capture:
        unit['payments'] = {'captures': [capture]}
    return {'id': f'ORDER-{ref}', 'status': status, 'purchase_units': [unit], 'payer': {'payer_id': 'PAYER1'}}


@pytest.mark.django_db
class TestReconcilePayPalOrders:
    def test_captured_order_whose_webhook_was_lost_is_settled(self, ev, pending_booking):
        _, state, ref = ev
        tx = age(ref)
        state['orders'][tx.gateway_order_id] = order_json(ref, 'COMPLETED', capture_json(ref))
        result = reconcile_initialized_transaction(tx)
        assert result.state == 'completed'
        tx.refresh_from_db()
        assert tx.status == PaymentTransaction.Status.SUCCESS and tx.gateway_reference == CAP
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.CONFIRMED
        assert net(pending_booking, ACC.LIABILITY_STUDENT_ESCROW) == Decimal('9.00')

    def test_settled_exactly_once_when_the_late_webhook_also_arrives(self, ev, pending_booking):
        hook, state, ref = ev
        tx = age(ref)
        state['orders'][tx.gateway_order_id] = order_json(ref, 'COMPLETED', capture_json(ref))
        reconcile_initialized_transaction(tx)
        entries = LedgerEntry.objects.count()
        assert hook().status_code == 200
        reconcile_initialized_transaction(PaymentTransaction.objects.get(pk=tx.pk))
        assert LedgerEntry.objects.count() == entries
        assert PaymentTransaction.objects.count() == 1

    def test_amount_is_verified_against_what_we_asked_for(self, ev, pending_booking):
        _, state, ref = ev
        tx = age(ref)
        state['orders'][tx.gateway_order_id] = order_json(ref, 'COMPLETED', capture_json(ref, amount='1.00'))
        result = reconcile_initialized_transaction(tx)
        tx.refresh_from_db()
        assert result.state == 'unresolved' and tx.status == PaymentTransaction.Status.INITIALIZED
        assert GatewayAnomaly.objects.filter(reason='amount_mismatch').exists()
        assert LedgerEntry.objects.count() == 0

    def test_capture_belonging_to_another_checkout_is_not_applied(self, ev):
        _, state, ref = ev
        tx = age(ref)
        state['orders'][tx.gateway_order_id] = order_json(ref, 'COMPLETED', capture_json('TX-OTHER'))
        result = reconcile_initialized_transaction(tx)
        tx.refresh_from_db()
        assert result.state == 'unresolved' and tx.status == PaymentTransaction.Status.INITIALIZED
        assert GatewayAnomaly.objects.filter(reason='capture_reference_mismatch').exists()

    def test_declined_capture_in_the_order_fails_the_transaction(self, ev):
        _, state, ref = ev
        tx = age(ref)
        state['orders'][tx.gateway_order_id] = order_json(ref, 'COMPLETED', capture_json(ref, status='DECLINED'))
        assert reconcile_initialized_transaction(tx).state == 'failed'
        tx.refresh_from_db()
        assert tx.status == PaymentTransaction.Status.FAILED

    def test_pending_capture_in_the_order_is_recorded_without_confirming(self, ev, pending_booking):
        _, state, ref = ev
        tx = age(ref)
        state['orders'][tx.gateway_order_id] = order_json(ref, 'COMPLETED', capture_json(ref, status='PENDING', reason='PENDING_REVIEW'))
        assert reconcile_initialized_transaction(tx).state == 'pending'
        tx.refresh_from_db()
        assert tx.status == PaymentTransaction.Status.PENDING_CAPTURE and tx.payer_id == 'PAYER1'
        pending_booking.refresh_from_db()
        assert pending_booking.status == Booking.Status.PENDING_PAYMENT

    @pytest.mark.parametrize('order_status', ['CREATED', 'APPROVED'])
    def test_unpaid_order_past_the_hold_is_failed(self, ev, order_status):
        _, state, ref = ev
        tx = age(ref)
        state['orders'][tx.gateway_order_id] = order_json(ref, order_status)
        assert reconcile_initialized_transaction(tx).state == 'failed'
        tx.refresh_from_db()
        assert tx.status == PaymentTransaction.Status.FAILED

    def test_unpaid_order_still_inside_the_hold_is_left_alone(self, ev):
        _, state, ref = ev
        tx = tx_of(ref)                                        # fresh: the booking's hold is live
        state['orders'][tx.gateway_order_id] = order_json(ref, 'APPROVED')
        assert reconcile_initialized_transaction(tx).state == 'pending'
        tx.refresh_from_db()
        assert tx.status == PaymentTransaction.Status.INITIALIZED

    def test_voided_order_is_authoritatively_failed(self, ev):
        _, state, ref = ev
        tx = tx_of(ref)
        state['orders'][tx.gateway_order_id] = order_json(ref, 'VOIDED')
        assert reconcile_initialized_transaction(tx).state == 'failed'

    def test_paypal_unavailable_never_fails_the_transaction(self, ev):
        _, state, ref = ev
        tx = age(ref)
        state['down'] = True
        result = reconcile_initialized_transaction(tx)
        tx.refresh_from_db()
        assert result.state == 'unresolved' and tx.status == PaymentTransaction.Status.INITIALIZED
        assert GatewayAnomaly.objects.filter(payment_transaction=tx, reason='reconciliation_unresolved', resolved=False).exists()

    def test_order_with_no_capture_object_that_claims_completed_is_not_trusted(self, ev):
        _, state, ref = ev
        tx = age(ref)
        state['orders'][tx.gateway_order_id] = order_json(ref, 'COMPLETED')
        assert reconcile_initialized_transaction(tx).state == 'unresolved'
        tx.refresh_from_db()
        assert tx.status == PaymentTransaction.Status.INITIALIZED

    def test_the_hourly_task_settles_lost_webhooks_and_survives_a_bad_row(self, ev, pending_booking, teacher_user, student_user):
        _, state, ref = ev
        tx = age(ref)
        state['orders'][tx.gateway_order_id] = order_json(ref, 'COMPLETED', capture_json(ref))
        # a poisoned row that raises must not stop the rest of the batch
        start = timezone.now() + timedelta(days=3)
        other = Booking.objects.create(teacher=teacher_user, student=student_user, start_time_utc=start,
                                       end_time_utc=start + timedelta(minutes=25), status=Booking.Status.PENDING_PAYMENT)
        bad = PaymentTransaction.objects.create(booking=other, gateway='paypal', gateway_reference='INIT-BAD',
                                                merchant_reference='TX-BAD', gateway_order_id='ORDER-BAD',
                                                amount=Decimal('9.00'), currency='USD')
        PaymentTransaction.objects.filter(pk=bad.pk).update(created_at=timezone.now() - timedelta(hours=3))
        state['orders']['ORDER-BAD'] = object()          # the lookup helper blows up with a TypeError
        out = reconcile_pending_transactions_task()
        assert out['reconciled_count'] == 2
        assert tx_of(ref).status == PaymentTransaction.Status.SUCCESS
        assert PaymentTransaction.objects.get(pk=bad.pk).status == PaymentTransaction.Status.INITIALIZED
