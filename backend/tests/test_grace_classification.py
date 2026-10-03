"""
Task 10.2 follow-up: TRANSACTION_APPROVED_AWAITING_FUNDING is RISK-BASED (a buyer-side bank payment that can still fail),
plus the overall grace ceiling, reason-drift safety and payer-identity safety found by the logic review.
"""
from decimal import Decimal

import pytest

from apps.payments.gateways import paypal
from apps.payments.models import GatewayAnomaly, PaymentTransaction
from apps.payments.services import grace
from apps.payments.services.paypal_capture import record_pending_capture

pytestmark = pytest.mark.django_db

AWAITING = 'TRANSACTION_APPROVED_AWAITING_FUNDING'
MERCHANT_REASONS = ['RECEIVING_PREFERENCE_MANDATES_MANUAL_ACTION', 'INTERNATIONAL_WITHDRAWAL']


# The fixtures below mirror tests/test_grace_bookings.py (kept separate on purpose: no cross-test imports).
import uuid
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.bookings.models import Booking

S = Booking.Status
User = get_user_model()


@pytest.fixture
def make(teacher_user, student_user):
    state = {'n': 0}

    class Maker:
        def student(self, name):
            return User.objects.create_user(username=name, email=f'{name}@test.com', password='x', role='student')

        def pending(self, *, reason, payer_id=None, student=None, status=PaymentTransaction.Status.PENDING_CAPTURE):
            state['n'] += 1
            start = timezone.now() + timedelta(hours=48, minutes=state['n'] * 30)
            booking = Booking.objects.create(
                teacher=teacher_user, student=student or self.student(f'u{state["n"]}'), start_time_utc=start,
                end_time_utc=start + timedelta(minutes=25), status=S.PENDING_PAYMENT)
            ref = f"TX-{uuid.uuid4().hex[:12].upper()}"
            return PaymentTransaction.objects.create(
                booking=booking, gateway='paypal', gateway_reference=f'CAP-{state["n"]}-{ref}', merchant_reference=ref,
                amount=Decimal('9.00'), currency='USD', status=status, pending_reason=reason,
                payer_id=payer_id or f'PAYER-{state["n"]}', payer_email=f'p{state["n"]}@example.com')

        def grant(self, **kw):
            tx = self.pending(**kw)
            decision = grace.confirm_grace_booking(tx)
            assert decision.allowed, decision.reason
            return tx
    return Maker()


def outcome(reason):
    return paypal.classify_capture({'status': 'PENDING', 'status_details': {'reason': reason}})


# ---------- classification ----------

def test_awaiting_funding_is_risk_based_not_merchant_side():
    o = outcome(AWAITING)
    assert (o.merchant_side, o.risk_based) == (False, True)


@pytest.mark.parametrize('reason', MERCHANT_REASONS)
def test_the_two_account_setting_reasons_stay_merchant_side(reason):
    o = outcome(reason)
    assert (o.merchant_side, o.risk_based) == (True, False)


def test_pending_review_stays_risk_based():
    assert (outcome('PENDING_REVIEW').merchant_side, outcome('PENDING_REVIEW').risk_based) == (False, True)


@pytest.mark.parametrize('reason', ['pending_review', ' PENDING_REVIEW ', 'transaction_approved_awaiting_funding', None, '',
                                    'ECHECK', 'VERIFICATION_REQUIRED', 'OTHER', 'SOMETHING_NEW'])
def test_odd_or_unknown_reason_strings_never_get_grace(make, reason):
    tx = make.pending(reason=reason or '')
    o = paypal.classify_capture({'status': 'PENDING', 'status_details': {'reason': reason}} if reason is not None
                                else {'status': 'PENDING', 'status_details': {}})
    assert grace.evaluate_grace(tx, o).allowed is False


# ---------- AWAITING_FUNDING behaves as risk-based ----------

def test_awaiting_funding_gets_grace_and_counts_toward_the_breaker(make, settings):
    settings.GRACE_MAX_OPEN = 2
    make.grant(reason=AWAITING)
    make.grant(reason='PENDING_REVIEW')
    third = make.pending(reason=AWAITING)
    decision = grace.evaluate_grace(third, outcome(AWAITING))
    assert decision.allowed is False and decision.reason == 'circuit_breaker'


def test_awaiting_funding_does_not_raise_the_fix_your_paypal_account_alert(make):
    tx = make.pending(reason=AWAITING)
    grace.handle_pending_capture(tx, outcome(AWAITING))
    assert not GatewayAnomaly.objects.filter(reason='paypal_merchant_side_pending').exists()


def test_a_merchant_side_pending_still_alerts_the_admin_immediately(make):
    tx = make.pending(reason=MERCHANT_REASONS[0])
    grace.handle_pending_capture(tx, outcome(MERCHANT_REASONS[0]))
    assert GatewayAnomaly.objects.filter(reason='paypal_merchant_side_pending').exists()


# ---------- overall ceiling (merchant-side grace is no longer unbounded) ----------

def test_the_total_ceiling_blocks_merchant_side_grace_even_when_the_risk_breaker_is_clear(make, settings):
    settings.GRACE_MAX_OPEN = 5
    settings.GRACE_MAX_OPEN_TOTAL = 3
    for _ in range(3):
        make.grant(reason=MERCHANT_REASONS[0])
    nxt = make.pending(reason=MERCHANT_REASONS[1])
    decision = grace.evaluate_grace(nxt, outcome(MERCHANT_REASONS[1]))
    assert decision.allowed is False and decision.reason == 'total_ceiling'


def test_the_total_ceiling_counts_risk_based_rows_too(make, settings):
    settings.GRACE_MAX_OPEN = 5
    settings.GRACE_MAX_OPEN_TOTAL = 2
    make.grant(reason='PENDING_REVIEW')
    make.grant(reason=AWAITING)
    nxt = make.pending(reason=MERCHANT_REASONS[0])
    assert grace.evaluate_grace(nxt, outcome(MERCHANT_REASONS[0])).reason == 'total_ceiling'


def test_the_total_ceiling_allows_exactly_the_limit(make, settings):
    settings.GRACE_MAX_OPEN_TOTAL = 3
    make.grant(reason=MERCHANT_REASONS[0])
    make.grant(reason=MERCHANT_REASONS[0])
    assert grace.evaluate_grace(make.pending(reason=MERCHANT_REASONS[0]), outcome(MERCHANT_REASONS[0])).allowed is True


def test_the_total_ceiling_alerts_once_and_rearms(make, settings):
    settings.GRACE_MAX_OPEN_TOTAL = 1
    first = make.grant(reason=MERCHANT_REASONS[0])
    for _ in range(2):
        refused = make.pending(reason=MERCHANT_REASONS[0])
        assert grace.confirm_grace_booking(refused).reason == 'total_ceiling'
    assert GatewayAnomaly.objects.filter(reason='grace_total_ceiling_open', resolved=False).count() == 1
    grace.on_completed(first)                                    # capacity returns -> the alert is re-armed
    assert not GatewayAnomaly.objects.filter(reason='grace_total_ceiling_open', resolved=False).exists()


def test_total_ceiling_has_a_sane_default(settings):
    assert settings.GRACE_MAX_OPEN_TOTAL == 15 and settings.GRACE_MAX_OPEN == 5


# ---------- reason drift cannot hide exposure from the breaker ----------

def test_a_grace_row_whose_reason_drifts_to_an_unknown_one_still_counts(make, settings):
    settings.GRACE_MAX_OPEN = 1
    tx = make.grant(reason='PENDING_REVIEW')
    PaymentTransaction.objects.filter(pk=tx.pk).update(pending_reason='ECHECK')      # PayPal later says something else
    nxt = make.pending(reason='PENDING_REVIEW')
    assert grace.evaluate_grace(nxt, outcome('PENDING_REVIEW')).reason == 'circuit_breaker'


def test_reconcile_refreshes_a_changed_pending_reason(make, monkeypatch):
    from apps.payments.services.reconciliation import ReconciliationResult, reconcile_pending_capture
    tx = make.grant(reason='PENDING_REVIEW')
    capture = {'id': tx.gateway_reference, 'status': 'PENDING', 'status_details': {'reason': AWAITING},
               'custom_id': tx.merchant_reference, 'amount': {'value': '9.00', 'currency_code': 'USD'}}
    reconcile_pending_capture(tx, lookup=lambda t: ReconciliationResult('pending', 'still pending', capture))
    assert PaymentTransaction.objects.get(pk=tx.pk).pending_reason == AWAITING


# ---------- payer identity cannot be erased ----------

def test_a_pending_report_without_payer_data_never_blanks_the_payer_identity(make):
    tx = make.pending(reason='PENDING_REVIEW', payer_id='PAYER-KEEP')
    before_email = tx.payer_email
    record_pending_capture(tx.pk, {'id': tx.gateway_reference}, outcome('PENDING_REVIEW'), {})
    after = PaymentTransaction.objects.get(pk=tx.pk)
    assert after.payer_id == 'PAYER-KEEP' and after.payer_email == before_email


def test_a_pending_report_with_payer_data_updates_it(make):
    tx = make.pending(reason='PENDING_REVIEW', payer_id='OLD')
    record_pending_capture(tx.pk, {'id': tx.gateway_reference}, outcome('PENDING_REVIEW'),
                           {'payer': {'payer_id': 'NEW', 'email_address': 'new@example.com'}})
    after = PaymentTransaction.objects.get(pk=tx.pk)
    assert (after.payer_id, after.payer_email) == ('NEW', 'new@example.com')


# ---------- reconcile fairness and escalation ----------

def test_reconcile_polls_the_longest_unpolled_pending_first(make, monkeypatch):
    from apps.payments import tasks
    old = make.pending(reason='PENDING_REVIEW')
    fresh = make.pending(reason='PENDING_REVIEW')
    PaymentTransaction.objects.filter(pk=fresh.pk).update(last_reconciled_at=timezone.now())
    polled = []
    from apps.payments.services.reconciliation import ReconciliationResult
    monkeypatch.setattr(tasks, 'reconcile_pending_capture',
                        lambda t: polled.append(t.pk) or ReconciliationResult('pending', ''))
    tasks.reconcile_pending_transactions_task()
    assert polled[0] == old.pk


def test_a_payment_pending_for_35_days_raises_a_critical_alert(make, monkeypatch):
    from apps.payments import tasks
    from apps.payments.services.reconciliation import ReconciliationResult
    tx = make.pending(reason=MERCHANT_REASONS[0])
    PaymentTransaction.objects.filter(pk=tx.pk).update(created_at=timezone.now() - timedelta(days=36))
    monkeypatch.setattr(tasks, 'reconcile_pending_capture', lambda t: ReconciliationResult('pending', ''))
    tasks.reconcile_pending_transactions_task()
    assert GatewayAnomaly.objects.filter(reason='grace_pending_over_35_days').exists()
    assert GatewayAnomaly.objects.filter(reason='grace_pending_over_7_days').exists()
