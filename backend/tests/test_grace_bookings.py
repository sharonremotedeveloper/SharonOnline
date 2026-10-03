"""
Task 10.2 slice E + G: pending-payment grace bookings and the failure runbook.

Policy under test (docs/PHASE_10_2_PAYPAL_ORDERS_PLAN.md): P-1 grace confirms on a PENDING capture, P-2 one open grace per
account AND per PayPal payer, P-3 the platform pays the tutor if the payment fails after the lesson, P-4 admin alert +
e-mail + support ticket, P-5 reason allow-list, P-6 circuit breaker, P-7 never for packs, P-8 the endpoint confirms.
"""
import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APIClient

from apps.admin_api.models import DisputeCase
from apps.bookings.models import AttendanceAudit, Booking, BookingStatusChange
from apps.payments.gateways import paypal
from apps.payments.models import (
    BookingFunding, CreditBundle, CreditPack, FxRate, GatewayAnomaly, LedgerAccount, LedgerEntry, PaymentTransaction,
    RefundRequest, SettlementAnomaly)
from apps.payments.services import grace
from apps.payments.services.funding import PaymentNotCleared
from apps.payments.services.ledger_service import get_general_ledger_trial_balance, record_escrow_clearance_entry
from apps.payments.tasks import reconcile_pending_transactions_task, release_cleared_escrow_task
from apps.users.models import SupportInquiry

pytestmark = pytest.mark.django_db

S = Booking.Status
User = get_user_model()
RISK = 'PENDING_REVIEW'
MERCHANT = ['RECEIVING_PREFERENCE_MANDATES_MANUAL_ACTION', 'INTERNATIONAL_WITHDRAWAL']
AWAITING = 'TRANSACTION_APPROVED_AWAITING_FUNDING'          # buyer-side bank funding: RISK-based, not merchant-side
INIT, CAPTURE, WEBHOOK = '/api/v1/payments/checkout/init/', '/api/v1/payments/paypal/capture/', '/api/v1/payments/webhooks/paypal/'


# --------------------------------------------------------------------------------------------------------- fixtures
@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake(to, subject, html, text=''):
        sent.append({'to': to, 'subject': subject, 'html': html, 'text': text})
    monkeypatch.setattr('apps.payments.tasks.send_email', fake)
    monkeypatch.setattr('apps.users.tasks.send_email', fake)
    monkeypatch.setattr('apps.integrations.email.send_email', fake)          # send_cancellation_emails imports it at call time
    return sent


@pytest.fixture
def spy(monkeypatch):
    calls = {'dispatch': [], 'release': []}
    monkeypatch.setattr('apps.payments.services.webhook_handler.dispatch_fulfillment', lambda bid: calls['dispatch'].append(bid))
    real_release = __import__('apps.payments.services.webhook_handler', fromlist=['x']).release_slot_lock

    def release(*a, **k):
        calls['release'].append(a)
        return real_release(*a, **k)
    monkeypatch.setattr('apps.payments.services.webhook_handler.release_slot_lock', release)
    return calls


@pytest.fixture
def make(teacher_user, student_user):
    state = {'n': 0}

    class Maker:
        teacher, student = teacher_user, student_user

        def user(self, name):
            return User.objects.create_user(username=name, email=f'{name}@test.com', password='x', role='student')

        def booking(self, student=None, hours=48, status=S.PENDING_PAYMENT):
            state['n'] += 1
            start = timezone.now() + timedelta(hours=hours, minutes=state['n'] * 30)
            return Booking.objects.create(teacher=teacher_user, student=student or student_user, start_time_utc=start,
                                          end_time_utc=start + timedelta(minutes=25), status=status)

        def pending(self, booking=None, *, reason=RISK, payer_id='PAYER-A', payer_email='a@example.com', amount='9.00',
                    currency='USD', **kw):
            booking = booking or self.booking()
            state['n'] += 1
            ref = f"TX-{uuid.uuid4().hex[:12].upper()}"
            return PaymentTransaction.objects.create(
                booking=booking, gateway='paypal', gateway_reference=f'CAP-{state["n"]}-{ref}', merchant_reference=ref,
                amount=Decimal(amount), currency=currency, status=PaymentTransaction.Status.PENDING_CAPTURE,
                pending_reason=reason, payer_id=payer_id, payer_email=payer_email, **kw)

        def grace(self, **kw):
            """A confirmed grace booking (policy allowed) and its transaction."""
            tx = self.pending(**kw)
            decision = grace.confirm_grace_booking(tx)
            assert decision.allowed, decision.reason
            tx.refresh_from_db()
            return tx, Booking.objects.get(pk=tx.booking_id)
    return Maker()


def classify(reason):
    return paypal.classify_capture({'status': 'PENDING', 'status_details': {'reason': reason}} if reason is not None
                                   else {'status': 'PENDING'})


def decide(tx, reason=None):
    return grace.evaluate_grace(tx, classify(tx.pending_reason if reason is None else reason))


def net(booking, account, event=None):
    rows = LedgerEntry.objects.filter(booking=booking, account=account)
    if event:
        rows = rows.filter(event_type=event)
    cr = rows.filter(entry_type='credit').aggregate(t=Sum('amount'))['t'] or Decimal('0')
    dr = rows.filter(entry_type='debit').aggregate(t=Sum('amount'))['t'] or Decimal('0')
    return cr - dr


def finish_lesson(booking, *, status=S.COMPLETED, hours_ago=25, teacher_minutes=25):
    start = timezone.now() - timedelta(hours=hours_ago, minutes=25)
    Booking.objects.filter(pk=booking.pk).update(status=status, start_time_utc=start, end_time_utc=start + timedelta(minutes=25))
    booking.refresh_from_db()
    AttendanceAudit.objects.create(booking=booking, participant_email=booking.teacher.user.email, total_minutes=teacher_minutes)
    return booking


# ------------------------------------------------------------------------------- PayPal fake (capture endpoint)
def order_json(ref, *, status='COMPLETED', value='9.00', currency='USD', reason=None, capture_id='CAP-1',
               payer_id='PAYER1', email='buyer@example.com'):
    capture = {'id': capture_id, 'status': status, 'custom_id': ref, 'amount': {'value': value, 'currency_code': currency}}
    if reason:
        capture['status_details'] = {'reason': reason}
    order = {'id': f'ORDER-{ref}', 'status': 'COMPLETED', 'purchase_units': [{'payments': {'captures': [capture]}}]}
    order['payer'] = {'payer_id': payer_id, 'email_address': email}
    return order


@pytest.fixture
def pp(monkeypatch):
    state = {'order': None}
    monkeypatch.setattr(paypal, 'capture_order', lambda order_id, *, request_id: state['order'])
    monkeypatch.setattr(paypal, 'verify_webhook_signature', lambda meta, body: True)
    monkeypatch.setattr(paypal, 'get_capture', lambda cid: state['order']['purchase_units'][0]['payments']['captures'][0])
    return state


def api(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def checkout(user, booking, **extra):
    res = api(user).post(INIT, {'gateway': 'paypal', 'booking_id': str(booking.id), **extra}, format='json')
    assert res.status_code == 200, res.json()
    return res.json()


def capture(user, order_id):
    return api(user).post(CAPTURE, {'order_id': order_id}, format='json')


def webhook(capture_id='CAP-1'):
    event = {'id': 'WH-1', 'event_type': 'PAYMENT.CAPTURE.COMPLETED', 'resource': {'id': capture_id}}
    return APIClient().generic('POST', WEBHOOK, json.dumps(event), content_type='application/json')


# ============================================================================================ 1. evaluate_grace
@pytest.mark.parametrize('reason', MERCHANT)
def test_merchant_side_reasons_are_eligible(make, reason):
    d = decide(make.pending(reason=reason))
    assert d.allowed and d.reason == 'merchant_side'


def test_pending_review_is_eligible(make):
    d = decide(make.pending(reason=RISK))
    assert d.allowed and d.reason == 'risk_based'


@pytest.mark.parametrize('reason', ['ECHECK', 'VERIFICATION_REQUIRED', 'OTHER', 'SHIPPING_ADDRESS', 'SOMETHING_PAYPAL_INVENTED', ''])
def test_every_other_pending_reason_never_gets_grace(make, reason):
    d = decide(make.pending(reason=reason), reason=reason)
    assert not d.allowed and d.reason.startswith('reason_not_eligible')


def test_a_pending_capture_with_no_status_details_never_gets_grace(make):
    tx = make.pending(reason='')
    d = grace.evaluate_grace(tx, classify(None))
    assert not d.allowed


@pytest.mark.parametrize('state', ['declined', 'failed', 'completed'])
def test_only_a_pending_capture_is_eligible(make, state):
    tx = make.pending()
    d = grace.evaluate_grace(tx, paypal.CaptureOutcome(state, RISK, False, True))
    assert not d.allowed and d.reason == 'not_pending'


def test_credit_pack_purchases_never_get_grace(student_user):
    pack = CreditPack.objects.create(code='p5', name='Five', credits=5, price_usd=Decimal('38'), price_zar=Decimal('700'),
                                     price_eur=Decimal('35.5'), price_jpy=Decimal('5700'))
    from apps.payments.models import CreditPurchase
    purchase = CreditPurchase.objects.create(user=student_user, pack=pack, amount=Decimal('38.00'), currency='USD',
                                             fx_rate_to_zar=Decimal('18'), fx_source='credit_catalog')
    tx = PaymentTransaction.objects.create(credit_purchase=purchase, gateway='paypal', gateway_reference='CAP-PACK',
                                           merchant_reference='TX-PACK', amount=Decimal('38.00'), currency='USD',
                                           status='pending_capture', pending_reason=RISK, payer_id='P', payer_email='p@e.com')
    d = grace.evaluate_grace(tx, classify(RISK))
    assert not d.allowed and d.reason == 'credit_pack'


def test_one_open_grace_booking_per_student_account(make):
    make.grace()
    second = make.pending(payer_id='PAYER-OTHER', payer_email='other@example.com')
    d = decide(second)
    assert not d.allowed and d.reason == 'account_cap'


def test_one_open_grace_booking_per_paypal_payer_across_accounts(make):
    make.grace(payer_id='SHARED', payer_email='x@example.com')
    other_student = make.user('second_student')
    second = make.pending(make.booking(student=other_student), payer_id='SHARED', payer_email='different@example.com')
    d = decide(second)
    assert not d.allowed and d.reason == 'payer_cap'


def test_payer_email_is_used_when_the_payer_id_is_empty(make):
    make.grace(payer_id='', payer_email='Buyer@Example.com')
    other_student = make.user('second_student')
    second = make.pending(make.booking(student=other_student), payer_id='', payer_email='buyer@example.com')
    d = decide(second)
    assert not d.allowed and d.reason == 'payer_cap'


def test_an_unidentifiable_payer_gets_no_grace(make):
    d = decide(make.pending(payer_id='', payer_email=''))
    assert not d.allowed and d.reason == 'payer_unknown'


def test_a_blocked_student_gets_no_grace(make, student_user):
    User.objects.filter(pk=student_user.pk).update(booking_blocked_reason='unpaid lesson')
    student_user.refresh_from_db()
    d = decide(make.pending())
    assert not d.allowed and d.reason == 'student_blocked'


def test_a_resolved_grace_booking_no_longer_counts(make):
    tx, _ = make.grace()
    assert decide(make.pending(payer_id='PAYER-B', payer_email='b@example.com')).reason == 'account_cap'
    grace.on_completed(tx)
    assert decide(make.pending(payer_id='PAYER-B', payer_email='b@example.com')).allowed


def test_a_cancelled_grace_booking_no_longer_counts(make):
    _, booking = make.grace()
    Booking.objects.filter(pk=booking.pk).update(status=S.CANCELLED_BY_STUDENT)
    assert decide(make.pending(payer_id='PAYER-B', payer_email='b@example.com')).allowed


# ================================================================================================ circuit breaker
def risk_grace(make, i):
    return make.grace(booking=make.booking(student=make.user(f's{i}')), payer_id=f'P{i}', payer_email=f'p{i}@e.com')


def test_circuit_breaker_stops_risk_based_grace_at_the_limit(make, settings):
    settings.GRACE_MAX_OPEN = 2
    risk_grace(make, 1), risk_grace(make, 2)
    third = make.pending(make.booking(student=make.user('s3')), payer_id='P3', payer_email='p3@e.com')
    d = decide(third)
    assert not d.allowed and d.reason == 'circuit_breaker'


def test_the_breaker_allows_exactly_the_limit_not_one_fewer(make, settings):
    settings.GRACE_MAX_OPEN = 3
    risk_grace(make, 1), risk_grace(make, 2)
    third = make.pending(make.booking(student=make.user('s3')), payer_id='P3', payer_email='p3@e.com')
    assert decide(third).allowed                       # 2 open < 3: the third is the 3rd, still within the limit


def test_the_limit_is_a_setting(make, settings):
    settings.GRACE_MAX_OPEN = 0
    d = decide(make.pending())
    assert not d.allowed and d.reason == 'circuit_breaker'


def test_merchant_side_pendings_do_not_count_toward_the_breaker(make, settings):
    settings.GRACE_MAX_OPEN = 1
    make.grace(booking=make.booking(student=make.user('m1')), reason=MERCHANT[0], payer_id='M1', payer_email='m1@e.com')
    make.grace(booking=make.booking(student=make.user('m2')), reason=MERCHANT[1], payer_id='M2', payer_email='m2@e.com')
    risky = make.pending(make.booking(student=make.user('r1')), payer_id='R1', payer_email='r1@e.com')
    assert decide(risky).allowed                       # two merchant-side open, limit 1, yet a risk-based one is fine


def test_merchant_side_grace_is_not_blocked_by_a_tripped_breaker(make, settings):
    settings.GRACE_MAX_OPEN = 1
    risk_grace(make, 1)
    merchant = make.pending(make.booking(student=make.user('m1')), reason=MERCHANT[1], payer_id='M1', payer_email='m1@e.com')
    assert decide(merchant).allowed


def test_the_breaker_alerts_the_admin_once_per_trip(make, settings, outbox, django_capture_on_commit_callbacks):
    settings.GRACE_MAX_OPEN = 1
    with django_capture_on_commit_callbacks(execute=True):
        risk_grace(make, 1)                            # this grant trips it
        for i in (2, 3):                               # further refused attempts do not re-alert
            grace.confirm_grace_booking(make.pending(make.booking(student=make.user(f's{i}')), payer_id=f'P{i}', payer_email=f'p{i}@e.com'))
    assert GatewayAnomaly.objects.filter(reason=grace.BREAKER_ALERT).count() == 1
    assert len([m for m in outbox if 'circuit breaker' in m['subject']]) == 1


def test_the_breaker_alert_rearms_after_it_clears(make, settings):
    settings.GRACE_MAX_OPEN = 1
    tx, _ = risk_grace(make, 1)
    assert GatewayAnomaly.objects.filter(reason=grace.BREAKER_ALERT, resolved=False).count() == 1
    grace.on_completed(tx)
    assert GatewayAnomaly.objects.filter(reason=grace.BREAKER_ALERT, resolved=False).count() == 0
    risk_grace(make, 2)
    assert GatewayAnomaly.objects.filter(reason=grace.BREAKER_ALERT).count() == 2


def test_a_merchant_side_pending_alerts_the_admin_immediately(make, outbox, django_capture_on_commit_callbacks):
    tx = make.pending(reason=MERCHANT[0])
    with django_capture_on_commit_callbacks(execute=True):
        grace.handle_pending_capture(tx, classify(MERCHANT[0]))
    assert GatewayAnomaly.objects.filter(reason='paypal_merchant_side_pending').count() == 1
    assert any('account settings' in m['subject'] for m in outbox)


def test_a_risk_based_pending_does_not_raise_the_account_alert(make):
    grace.handle_pending_capture(make.pending(reason=RISK), classify(RISK))
    assert not GatewayAnomaly.objects.filter(reason='paypal_merchant_side_pending').exists()


# ================================================================================ 2. confirm via capture endpoint
def test_pending_review_confirms_the_lesson_through_the_capture_endpoint(student_user, make, pp, spy, django_capture_on_commit_callbacks):
    booking = make.booking()
    data = checkout(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason=RISK)
    with django_capture_on_commit_callbacks(execute=True):
        res = capture(student_user, data['order_id'])
    assert res.status_code == 200 and res.json()['outcome'] == 'pending_confirmed'
    assert res.json()['booking_id'] == str(booking.id)
    booking.refresh_from_db()
    assert booking.status == S.CONFIRMED
    change = BookingStatusChange.objects.get(booking=booking, to_status=S.CONFIRMED)
    assert change.reason == 'grace_pending_capture'
    tx = PaymentTransaction.objects.get()
    assert tx.status == 'pending_capture'
    funding = BookingFunding.objects.get(booking=booking)
    assert (funding.source_type, funding.captured_amount, funding.currency) == ('gateway_pending', Decimal('9.00'), 'USD')
    assert funding.payment_transaction_id == tx.pk
    assert not LedgerEntry.objects.exists()                              # nothing posted while pending
    assert spy['dispatch'] == [str(booking.id)] and spy['release']       # fulfilment queued, slot hold released


def test_the_grace_funding_snapshots_the_fx_stamped_at_checkout(student_user, make, pp):
    FxRate.objects.create(currency='EUR', rate_to_zar=Decimal('20.500000'), valid_from=timezone.now() - timedelta(hours=1))
    data = checkout(student_user, make.booking(), currency='EUR')
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason=RISK, value=data['amount'], currency='EUR')
    assert capture(student_user, data['order_id']).json()['outcome'] == 'pending_confirmed'
    funding = BookingFunding.objects.get()
    assert (funding.currency, funding.fx_rate_to_zar) == ('EUR', Decimal('20.500000'))
    assert funding.captured_amount == Decimal(data['amount'])


def test_echeck_pending_stays_pending_and_does_not_confirm(student_user, make, pp):
    booking = make.booking()
    data = checkout(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason='ECHECK')
    res = capture(student_user, data['order_id'])
    assert res.json()['outcome'] == 'pending'
    booking.refresh_from_db()
    assert booking.status == S.PENDING_PAYMENT and not BookingFunding.objects.exists()


def test_replaying_the_capture_of_a_grace_booking_reports_pending_confirmed(student_user, make, pp):
    data = checkout(student_user, make.booking())
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason=RISK)
    capture(student_user, data['order_id'])
    again = capture(student_user, data['order_id'])
    assert again.json()['outcome'] == 'pending_confirmed' and BookingFunding.objects.count() == 1


def test_a_slot_taken_by_someone_else_denies_grace_and_nothing_is_posted(student_user, make, pp):
    booking = make.booking()
    data = checkout(student_user, booking)
    Booking.objects.create(teacher=make.teacher, student=make.user('rival'), start_time_utc=booking.start_time_utc,
                           end_time_utc=booking.end_time_utc, status=S.CONFIRMED)
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason=RISK)
    res = capture(student_user, data['order_id'])
    assert res.json()['outcome'] == 'pending'
    booking.refresh_from_db()
    assert booking.status == S.PENDING_PAYMENT and not BookingFunding.objects.exists() and not LedgerEntry.objects.exists()


def test_a_lesson_that_already_started_gets_no_grace(student_user, make, pp):
    booking = make.booking()
    data = checkout(student_user, booking)
    Booking.objects.filter(pk=booking.pk).update(start_time_utc=timezone.now() - timedelta(minutes=5))
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason=RISK)
    assert capture(student_user, data['order_id']).json()['outcome'] == 'pending'
    assert not BookingFunding.objects.exists()


def test_a_pack_purchase_pending_never_confirms_anything(student_user, pp):
    pack = CreditPack.objects.create(code='p5', name='Five', credits=5, price_usd=Decimal('38'), price_zar=Decimal('700'),
                                     price_eur=Decimal('35.5'), price_jpy=Decimal('5700'))
    data = api(student_user).post(INIT, {'gateway': 'paypal', 'credit_pack_id': pack.id}, format='json').json()
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason=RISK, value='38.00')
    res = capture(student_user, data['order_id'])
    assert res.json()['outcome'] == 'pending'
    assert not CreditBundle.objects.filter(user=student_user).exists()


def test_webhook_only_mode_never_grants_grace(student_user, make, pp, settings):
    settings.PAYPAL_CAPTURE_CONFIRMS = False
    booking = make.booking()
    data = checkout(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason=RISK)
    assert capture(student_user, data['order_id']).json()['outcome'] == 'pending'
    booking.refresh_from_db()
    assert booking.status == S.PENDING_PAYMENT


# ======================================================================================== 3. the capture clears
def test_completed_capture_after_grace_settles_the_money_without_touching_the_booking(student_user, make, pp):
    FxRate.objects.create(currency='EUR', rate_to_zar=Decimal('20.500000'), valid_from=timezone.now() - timedelta(hours=1))
    booking = make.booking()
    data = checkout(student_user, booking, currency='EUR')
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason=RISK, value=data['amount'], currency='EUR')
    capture(student_user, data['order_id'])
    FxRate.objects.create(currency='EUR', rate_to_zar=Decimal('25.000000'), valid_from=timezone.now())   # the market moved
    pp['order'] = order_json(data['transaction_reference'], value=data['amount'], currency='EUR')       # now COMPLETED
    assert webhook().status_code == 200

    booking.refresh_from_db()
    assert booking.status == S.CONFIRMED
    assert BookingStatusChange.objects.filter(booking=booking).count() == 1                  # no second transition
    tx = PaymentTransaction.objects.get()
    assert tx.status == 'success'
    funding = BookingFunding.objects.get(booking=booking)
    assert funding.source_type == 'gateway'
    amount = Decimal(data['amount'])
    assert net(booking, LedgerAccount.LIABILITY_STUDENT_ESCROW) == amount
    rows = LedgerEntry.objects.filter(payment_transaction=tx, event_type='payment_captured')
    assert {r.fx_rate_to_zar for r in rows} == {Decimal('20.500000')}                        # the checkout-stamped rate
    assert rows.filter(account=LedgerAccount.ASSET_GATEWAY_PAYPAL, entry_type='debit').get().amount == amount
    assert not GatewayAnomaly.objects.exists()                                               # never "surplus"
    assert not PaymentTransaction.objects.filter(status='unallocated').exists()
    assert get_general_ledger_trial_balance()['is_balanced']


def test_a_repeated_completed_webhook_does_not_post_twice(student_user, make, pp):
    data = checkout(student_user, make.booking())
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason=RISK)
    capture(student_user, data['order_id'])
    pp['order'] = order_json(data['transaction_reference'])
    webhook(), webhook()
    assert LedgerEntry.objects.count() == 2 and PaymentTransaction.objects.count() == 1


def test_the_reconcile_job_also_clears_a_grace_booking(student_user, make, pp, monkeypatch):
    booking = make.booking()
    data = checkout(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason=RISK)
    capture(student_user, data['order_id'])
    pp['order'] = order_json(data['transaction_reference'])
    result = reconcile_pending_transactions_task()
    assert result['pending_captures']['completed'] == 1
    assert BookingFunding.objects.get(booking=booking).source_type == 'gateway'
    assert PaymentTransaction.objects.get().status == 'success'
    assert net(booking, LedgerAccount.LIABILITY_STUDENT_ESCROW) == Decimal('9.00')


def test_a_non_grace_pending_capture_still_confirms_normally_when_it_clears(student_user, make, pp):
    booking = make.booking()
    data = checkout(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason='ECHECK')
    capture(student_user, data['order_id'])
    pp['order'] = order_json(data['transaction_reference'])
    assert webhook().status_code == 200
    booking.refresh_from_db()
    assert booking.status == S.CONFIRMED
    assert BookingFunding.objects.get(booking=booking).source_type == 'gateway'
    assert PaymentTransaction.objects.get().status == 'success'


def test_a_non_grace_pending_capture_is_also_cleared_by_the_reconcile_job(student_user, make, pp):
    booking = make.booking()
    data = checkout(student_user, booking)
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason='ECHECK')
    capture(student_user, data['order_id'])
    pp['order'] = order_json(data['transaction_reference'])
    reconcile_pending_transactions_task()
    booking.refresh_from_db()
    assert booking.status == S.CONFIRMED


# ====================================================================== cancelling a grace booking: no refund yet
def test_cancelling_a_grace_booking_issues_no_refund_and_posts_nothing(make, student_user):
    from apps.bookings.services import cancellation
    tx, booking = make.grace()
    cancellation.cancel_booking(booking.id, student_user)
    booking.refresh_from_db()
    assert booking.status == S.CANCELLED_BY_STUDENT
    refund = RefundRequest.objects.get(booking=booking)
    assert refund.status == RefundRequest.Status.AWAITING_CLEARANCE and refund.amount == Decimal('9.00')
    assert not LedgerEntry.objects.exists()


def test_the_cancel_preview_does_not_promise_a_refund_of_money_not_yet_received(make, student_user):
    from apps.bookings.services import cancellation
    _, booking = make.grace()
    body = cancellation.preview(booking, student_user)
    assert body['refund_amount'] is None and 'still verifying' in body['message']


def test_a_cancelled_grace_booking_whose_payment_clears_is_refunded_for_real(make, student_user):
    from apps.bookings.services import cancellation
    tx, booking = make.grace()
    cancellation.cancel_booking(booking.id, student_user)
    grace.on_completed(tx)
    booking.refresh_from_db()
    assert booking.status == S.CANCELLED_BY_STUDENT                                        # not resurrected
    refund = RefundRequest.objects.get(booking=booking)
    assert refund.status == RefundRequest.Status.PENDING_GATEWAY
    assert net(booking, LedgerAccount.LIABILITY_STUDENT_ESCROW) == 0                       # in and straight back out
    assert net(booking, LedgerAccount.LIABILITY_REFUNDS_PAYABLE) == Decimal('9.00')
    assert get_general_ledger_trial_balance()['is_balanced']


def test_a_cancelled_grace_booking_whose_payment_fails_voids_the_refund(make, student_user, outbox):
    from apps.bookings.services import cancellation
    tx, booking = make.grace()
    cancellation.cancel_booking(booking.id, student_user)
    assert grace.on_failed(tx) == 'already_cancelled'
    assert RefundRequest.objects.get(booking=booking).status == RefundRequest.Status.VOID
    assert not LedgerEntry.objects.exists()
    student_user.refresh_from_db()
    assert student_user.booking_blocked_reason == ''


# ================================================================================ 4. the settlement / payout gate
def test_the_escrow_release_job_refuses_a_grace_booking_whose_payment_is_still_pending(make):
    tx, booking = make.grace()
    finish_lesson(booking)
    assert release_cleared_escrow_task()['cleared_count'] == 0
    booking.refresh_from_db()
    assert booking.escrow_cleared_at is None
    assert not LedgerEntry.objects.exists()                                              # no release, so no tutor payable
    anomaly = SettlementAnomaly.objects.get(booking=booking, code='grace_payment_still_pending')
    assert not anomaly.resolved


def test_the_pending_anomaly_and_alert_are_raised_once_not_every_run(make, outbox, django_capture_on_commit_callbacks):
    tx, booking = make.grace()
    finish_lesson(booking)
    with django_capture_on_commit_callbacks(execute=True):
        release_cleared_escrow_task()
        release_cleared_escrow_task()
        release_cleared_escrow_task()
    assert SettlementAnomaly.objects.filter(booking=booking, code='grace_payment_still_pending').count() == 1
    assert GatewayAnomaly.objects.filter(reason='grace_payment_still_pending').count() == 1
    assert len([m for m in outbox if 'still waiting' in m['subject']]) == 1


def test_a_grace_booking_is_paid_normally_once_the_payment_clears(make):
    tx, booking = make.grace()
    finish_lesson(booking)
    release_cleared_escrow_task()
    grace.on_completed(tx)
    assert SettlementAnomaly.objects.get(booking=booking).resolved
    assert release_cleared_escrow_task()['cleared_count'] == 1
    assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == Decimal('7.20')
    assert net(booking, LedgerAccount.LIABILITY_STUDENT_ESCROW) == 0
    assert net(booking, LedgerAccount.REVENUE_PLATFORM_COMMISSION) == Decimal('1.80')


def test_the_ledger_itself_refuses_to_clear_escrow_for_pending_funding(make):
    _, booking = make.grace()
    with pytest.raises(PaymentNotCleared):
        record_escrow_clearance_entry(booking)
    assert not LedgerEntry.objects.exists()


def test_arbitration_cannot_release_a_pending_payment(make, admin_user):
    _, booking = make.grace()
    Booking.objects.filter(pk=booking.pk).update(status=S.DISPUTED)
    case = DisputeCase.objects.create(booking=booking, student=booking.student, teacher=booking.teacher, student_statement='x')
    for resolution in ('release_tutor', 'split_50_50'):
        res = api(admin_user).post(f'/api/v1/admin/disputes/{case.id}/resolve/', {'resolution': resolution}, format='json')
        assert res.status_code == 409 and res.json()['code'] == 'payment_not_cleared'
    assert not LedgerEntry.objects.exists()


def test_a_student_refund_after_arbitration_of_a_pending_grace_booking_is_deferred(make, admin_user):
    _, booking = make.grace()
    Booking.objects.filter(pk=booking.pk).update(status=S.DISPUTED)
    case = DisputeCase.objects.create(booking=booking, student=booking.student, teacher=booking.teacher, student_statement='x')
    res = api(admin_user).post(f'/api/v1/admin/disputes/{case.id}/resolve/', {'resolution': 'full_refund_student'}, format='json')
    assert res.status_code == 200
    assert RefundRequest.objects.get(booking=booking).status == RefundRequest.Status.AWAITING_CLEARANCE
    assert not LedgerEntry.objects.exists()


def test_the_payout_batch_cannot_see_money_for_a_pending_grace_lesson(make, admin_user):
    tx, booking = make.grace()
    finish_lesson(booking)
    release_cleared_escrow_task()
    assert not LedgerEntry.objects.filter(account=LedgerAccount.LIABILITY_TUTOR_PAYABLE).exists()


# ============================================================================== 5. failure BEFORE the lesson
def test_failure_before_the_lesson_cancels_it_frees_the_slot_and_refunds_nothing(make, student_user):
    tx, booking = make.grace()
    assert grace.on_failed(tx) == 'cancelled'
    booking.refresh_from_db()
    tx.refresh_from_db()
    assert booking.status == S.CANCELLED and tx.status == 'failed'
    assert BookingStatusChange.objects.filter(booking=booking, to_status=S.CANCELLED, reason='grace_payment_failed').exists()
    assert not LedgerEntry.objects.exists() and not RefundRequest.objects.exists()           # money never received, nothing returned
    student_user.refresh_from_db()
    assert student_user.booking_blocked_reason == ''                                         # nothing was lost
    # the slot is free again: another student can now confirm the same time
    Booking.objects.create(teacher=make.teacher, student=make.user('next'), start_time_utc=booking.start_time_utc,
                           end_time_utc=booking.end_time_utc, status=S.CONFIRMED)


def test_failure_of_a_grace_payment_lifts_the_grace_cap(make):
    tx, _ = make.grace()
    grace.on_failed(tx)
    assert decide(make.pending(payer_id='PAYER-B', payer_email='b@example.com')).allowed


def test_failure_before_the_lesson_tells_the_tutor_and_cleans_up(make, outbox, django_capture_on_commit_callbacks):
    tx, booking = make.grace()
    with django_capture_on_commit_callbacks(execute=True):
        grace.on_failed(tx)
    assert any(m['to'] == 'tutor@test.com' and 'payment did not go through' in m['text'] for m in outbox)


def test_failure_of_a_non_grace_pending_payment_leaves_the_held_booking_alone(make, student_user, outbox):
    booking = make.booking()
    tx = make.pending(booking, reason='ECHECK')
    assert grace.on_failed(tx) == 'unconfirmed'
    booking.refresh_from_db()
    assert booking.status == S.PENDING_PAYMENT and PaymentTransaction.objects.get().status == 'failed'
    assert SupportInquiry.objects.filter(category='payment_failure').count() == 1


# ============================================================================== 5. failure AFTER the lesson (P-3)
def test_failure_after_the_lesson_still_pays_the_tutor_from_platform_funds(make, student_user):
    tx, booking = make.grace()
    finish_lesson(booking)
    assert grace.on_failed(tx) == 'absorbed'
    assert BookingFunding.objects.get(booking=booking).source_type == 'platform_absorbed'
    assert PaymentTransaction.objects.get().status == 'failed'
    assert release_cleared_escrow_task()['cleared_count'] == 1

    rows = LedgerEntry.objects.filter(booking=booking)
    assert {r.event_type for r in rows} == {'payment_failure_absorbed'}
    assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == Decimal('7.20')            # 80 % of 9.00, as normal
    assert net(booking, LedgerAccount.EXPENSE_ABSORBED_PAYMENT_FAILURE) == Decimal('-7.20')  # platform expense (debit)
    assert net(booking, LedgerAccount.LIABILITY_STUDENT_ESCROW) == 0                         # escrow never touched
    assert not rows.filter(account=LedgerAccount.REVENUE_PLATFORM_COMMISSION).exists()       # nothing collected, no commission
    assert get_general_ledger_trial_balance()['is_balanced']
    assert release_cleared_escrow_task()['cleared_count'] == 0                               # and only once
    assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == Decimal('7.20')


def test_the_platform_funded_payment_counts_as_a_settlement_so_no_other_path_can_pay_the_lesson_again(make):
    tx, booking = make.grace()
    finish_lesson(booking)
    grace.on_failed(tx)
    release_cleared_escrow_task()
    Booking.objects.filter(pk=booking.pk).update(escrow_cleared_at=None)       # even if the release flag were lost, the ledger knows
    assert release_cleared_escrow_task()['cleared_count'] == 0
    assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == Decimal('7.20')


def test_the_tutor_wallet_shows_the_platform_funded_payment_as_cleared(make, teacher_user):
    from apps.payments.services.tutor_wallet import tutor_wallet_payload
    tx, booking = make.grace()
    finish_lesson(booking)
    grace.on_failed(tx)
    release_cleared_escrow_task()
    payload = tutor_wallet_payload(teacher_user.user)
    assert payload['cleared_balance_zar'] > 0


def test_failure_after_the_lesson_blocks_new_bookings_until_staff_clear_it(make, student_user):
    tx, booking = make.grace()
    finish_lesson(booking)
    grace.on_failed(tx)
    student_user.refresh_from_db()
    assert 'did not go through' in student_user.booking_blocked_reason
    res = api(student_user).post('/api/v1/bookings/reserve/', {'teacher_id': str(make.teacher.id),
                                 'start_time_utc': (timezone.now() + timedelta(days=3)).isoformat()}, format='json')
    assert res.status_code == 409 and 'paused' in res.json()['error'] and 'did not go through' in res.json()['error']
    User.objects.filter(pk=student_user.pk).update(booking_blocked_reason='')                # staff clear it
    student_user.refresh_from_db()
    res = api(student_user).post('/api/v1/bookings/reserve/', {'teacher_id': str(make.teacher.id),
                                 'start_time_utc': (timezone.now() + timedelta(days=3)).isoformat()}, format='json')
    assert res.status_code != 409 or 'paused' not in res.json().get('error', '')


def test_a_blocked_student_cannot_start_checkout_or_redeem_credit(make, student_user):
    booking = make.booking()
    User.objects.filter(pk=student_user.pk).update(booking_blocked_reason='Unpaid lesson.')
    res = api(student_user).post(INIT, {'gateway': 'paypal', 'booking_id': str(booking.id)}, format='json')
    assert res.status_code == 409 and res.json()['code'] == 'booking_blocked' and 'Unpaid lesson.' in res.json()['error']
    res = api(student_user).post(f'/api/v1/bookings/{booking.id}/redeem-credit/')
    assert res.status_code == 409


def test_a_lesson_in_progress_when_the_payment_fails_is_absorbed_not_cancelled(make):
    tx, booking = make.grace()
    Booking.objects.filter(pk=booking.pk).update(status=S.IN_PROGRESS, start_time_utc=timezone.now() - timedelta(minutes=10))
    assert grace.on_failed(tx) == 'absorbed'
    booking.refresh_from_db()
    assert booking.status == S.IN_PROGRESS


def test_a_tutor_no_show_on_an_absorbed_lesson_owes_the_student_no_refund(make):
    from apps.payments.services.refunds import request_refund
    tx, booking = make.grace()
    Booking.objects.filter(pk=booking.pk).update(status=S.IN_PROGRESS, start_time_utc=timezone.now() - timedelta(minutes=10))
    assert grace.on_failed(tx) == 'absorbed'
    Booking.objects.filter(pk=booking.pk).update(status=S.TEACHER_NO_SHOW)         # adjudicated afterwards
    booking.refresh_from_db()
    outcome = request_refund(booking, RefundRequest.Reason.TEACHER_NO_SHOW)
    assert outcome.refund is None and outcome.credit_lot is None and not LedgerEntry.objects.exists()


def test_a_refund_requested_after_the_payment_already_failed_is_not_left_waiting_forever(make):
    from apps.payments.services.refunds import request_refund
    tx, booking = make.grace()
    Booking.objects.filter(pk=booking.pk).update(status=S.TEACHER_NO_SHOW)
    booking.refresh_from_db()
    grace.on_failed(tx)
    assert request_refund(booking, RefundRequest.Reason.TEACHER_NO_SHOW).refund is None
    assert not RefundRequest.objects.filter(status=RefundRequest.Status.AWAITING_CLEARANCE).exists()


def absorbed_dispute(make):
    tx, booking = make.grace()
    finish_lesson(booking, hours_ago=1)
    grace.on_failed(tx)
    Booking.objects.filter(pk=booking.pk).update(status=S.DISPUTED)
    case = DisputeCase.objects.create(booking=booking, student=booking.student, teacher=booking.teacher, student_statement='x')
    return booking, case


def test_arbitration_release_for_an_absorbed_lesson_pays_the_tutor_from_the_platform(make, admin_user):
    booking, case = absorbed_dispute(make)
    res = api(admin_user).post(f'/api/v1/admin/disputes/{case.id}/resolve/', {'resolution': 'release_tutor'}, format='json')
    assert res.status_code == 200
    assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == Decimal('7.20')
    assert net(booking, LedgerAccount.EXPENSE_ABSORBED_PAYMENT_FAILURE) == Decimal('-7.20')
    assert net(booking, LedgerAccount.LIABILITY_STUDENT_ESCROW) == 0
    assert release_cleared_escrow_task()['cleared_count'] == 0                      # never paid a second time
    assert get_general_ledger_trial_balance()['is_balanced']


def test_a_split_on_a_payment_that_never_arrived_is_refused(make, admin_user):
    booking, case = absorbed_dispute(make)
    res = api(admin_user).post(f'/api/v1/admin/disputes/{case.id}/resolve/', {'resolution': 'split_50_50'}, format='json')
    assert res.status_code == 409 and res.json()['code'] == 'payment_not_collected'
    assert not LedgerEntry.objects.exists() and not CreditBundle.objects.exists()


def test_a_different_payment_for_a_booking_whose_grace_payment_failed_cannot_resurrect_it(make):
    from apps.payments.services.webhook_handler import process_payment_webhook
    tx, booking = make.grace()
    grace.on_failed(tx)
    PaymentTransaction.objects.create(booking=booking, gateway='paypal', gateway_reference='INIT-OTHER', merchant_reference='TX-OTHER',
                                      amount=Decimal('9.00'), currency='USD')
    result = process_payment_webhook(booking_id=str(booking.id), gateway='paypal', transaction_id='INIT-OTHER', amount=Decimal('9.00'),
                                     currency='USD', status='success', raw_payload={})
    assert result['status'] == 'unallocated'
    booking.refresh_from_db()
    assert booking.status == S.CANCELLED
    assert BookingFunding.objects.get(booking=booking).source_type == 'gateway_pending'


# ==================================================================================== 5. runbook side effects
def test_failure_opens_one_ticket_emails_the_student_and_alerts_the_admin(make, student_user, outbox, django_capture_on_commit_callbacks):
    tx, booking = make.grace()
    with django_capture_on_commit_callbacks(execute=True):
        grace.on_failed(tx)
    ticket = SupportInquiry.objects.get(category='payment_failure')
    assert ticket.student_id == student_user.id and ticket.related_booking_id == booking.id
    assert ticket.related_transaction_ref == tx.merchant_reference
    assert ticket.sender_email == student_user.email and ticket.sender_type == 'student'
    mails = [m for m in outbox if m['to'] == student_user.email]
    assert len(mails) == 1
    assert 'cancelled' in mails[0]['text'] and 'not collected any money' in mails[0]['text']
    assert ticket.id.hex[:8] in mails[0]['text'].replace('-', '')                            # points at the ticket
    assert GatewayAnomaly.objects.filter(reason='pending_payment_failed').count() == 1
    assert any(m['to'] == 'support@sharonesl.com' and 'payment failed' in m['subject'] for m in outbox)


def test_the_student_email_after_a_delivered_lesson_says_what_happens_next(make, student_user, outbox, django_capture_on_commit_callbacks):
    tx, booking = make.grace()
    finish_lesson(booking)
    with django_capture_on_commit_callbacks(execute=True):
        grace.on_failed(tx)
    text = next(m['text'] for m in outbox if m['to'] == student_user.email)
    assert 'took place' in text and 'paused new bookings' in text and 'contact' in text.lower()


def test_failure_side_effects_are_idempotent_under_retries(make, student_user, outbox, django_capture_on_commit_callbacks):
    tx, booking = make.grace()
    with django_capture_on_commit_callbacks(execute=True):
        for _ in range(3):
            grace.on_failed(tx)
    assert SupportInquiry.objects.filter(category='payment_failure').count() == 1
    assert GatewayAnomaly.objects.filter(reason='pending_payment_failed').count() == 1
    assert len([m for m in outbox if m['to'] == student_user.email]) == 1
    assert BookingStatusChange.objects.filter(booking=booking, to_status=S.CANCELLED).count() == 1


def test_absorbing_twice_posts_one_journal_and_one_block(make, student_user):
    tx, booking = make.grace()
    finish_lesson(booking)
    grace.on_failed(tx), grace.on_failed(tx)
    release_cleared_escrow_task(), release_cleared_escrow_task()
    assert LedgerEntry.objects.filter(event_type='payment_failure_absorbed').count() == 2     # one DR + one CR
    student_user.refresh_from_db()
    assert student_user.booking_blocked_reason.count('did not go through') == 1


def test_a_failed_pack_payment_marks_the_purchase_failed_and_tells_the_student(student_user, pp, outbox, django_capture_on_commit_callbacks):
    pack = CreditPack.objects.create(code='p5', name='Five', credits=5, price_usd=Decimal('38'), price_zar=Decimal('700'),
                                     price_eur=Decimal('35.5'), price_jpy=Decimal('5700'))
    data = api(student_user).post(INIT, {'gateway': 'paypal', 'credit_pack_id': pack.id}, format='json').json()
    pp['order'] = order_json(data['transaction_reference'], status='PENDING', reason='ECHECK', value='38.00')
    capture(student_user, data['order_id'])
    tx = PaymentTransaction.objects.get()
    with django_capture_on_commit_callbacks(execute=True):
        assert grace.on_failed(tx) == 'pack'
    from apps.payments.models import CreditPurchase
    assert CreditPurchase.objects.get().status == 'failed' and not CreditBundle.objects.exists()
    text = next(m['text'] for m in outbox if m['to'] == student_user.email)
    assert 'No credits were added' in text


def test_a_payment_that_clears_after_it_was_written_off_is_held_for_refund_not_dropped(make):
    tx, booking = make.grace()
    grace.on_failed(tx)
    assert grace.on_completed(tx) is True
    tx.refresh_from_db()
    assert tx.status == 'unallocated'
    assert GatewayAnomaly.objects.filter(reason='payment_completed_after_failure').exists()
    assert net(booking, LedgerAccount.LIABILITY_QUARANTINE_DEPOSIT) == Decimal('9.00')


# =============================================================================================== 6. reconciliation
def lookup_returning(state, payload=None):
    return lambda t: __import__('apps.payments.services.reconciliation', fromlist=['x']).ReconciliationResult(state, '', payload)


def test_reconcile_failed_runs_the_failure_runbook(make):
    from apps.payments.services.reconciliation import reconcile_pending_capture
    tx, booking = make.grace()
    reconcile_pending_capture(tx, lookup=lookup_returning('failed'))
    booking.refresh_from_db()
    tx.refresh_from_db()
    assert tx.status == 'failed' and booking.status == S.CANCELLED


def test_reconcile_job_polls_pending_captures_by_capture_id(make, monkeypatch):
    tx, booking = make.grace()
    seen = []
    monkeypatch.setattr(paypal, 'get_capture', lambda cid: seen.append(cid) or {'status': 'DENIED' if False else 'FAILED'})
    result = reconcile_pending_transactions_task()
    assert seen == [tx.gateway_reference] and result['pending_captures']['failed'] == 1
    tx.refresh_from_db()
    assert tx.status == 'failed'


def test_reconcile_leaves_a_still_pending_capture_alone_and_survives_paypal_outages(make, monkeypatch):
    tx, booking = make.grace()
    monkeypatch.setattr(paypal, 'get_capture', lambda cid: {'status': 'PENDING'})
    assert reconcile_pending_transactions_task()['pending_captures']['pending'] == 1
    monkeypatch.setattr(paypal, 'get_capture', lambda cid: (_ for _ in ()).throw(paypal.PayPalError('down')))
    assert reconcile_pending_transactions_task()['pending_captures']['unresolved'] == 1
    tx.refresh_from_db()
    assert tx.status == 'pending_capture'
    booking.refresh_from_db()
    assert booking.status == S.CONFIRMED


def test_a_capture_pending_for_more_than_seven_days_alerts_the_admin_once(make, monkeypatch, outbox, django_capture_on_commit_callbacks):
    tx, _ = make.grace()
    monkeypatch.setattr(paypal, 'get_capture', lambda cid: {'status': 'PENDING'})
    with django_capture_on_commit_callbacks(execute=True):
        reconcile_pending_transactions_task()
    assert not GatewayAnomaly.objects.filter(reason='grace_pending_over_7_days').exists()       # young: no alert
    PaymentTransaction.objects.filter(pk=tx.pk).update(created_at=timezone.now() - timedelta(days=8))
    with django_capture_on_commit_callbacks(execute=True):
        reconcile_pending_transactions_task()
        reconcile_pending_transactions_task()
    assert GatewayAnomaly.objects.filter(reason='grace_pending_over_7_days').count() == 1
    assert len([m for m in outbox if '7 days' in m['subject']]) == 1


def test_reconcile_with_a_mismatching_amount_applies_nothing(make, monkeypatch):
    tx, booking = make.grace()
    monkeypatch.setattr(paypal, 'get_capture', lambda cid: {
        'status': 'COMPLETED', 'amount': {'value': '1.00', 'currency_code': 'USD'}})
    reconcile_pending_transactions_task()
    tx.refresh_from_db()
    assert tx.status == 'pending_capture' and not LedgerEntry.objects.exists()
    assert GatewayAnomaly.objects.filter(reason='amount_mismatch').exists()


# ============================================================================================== admin escrow view
def test_the_admin_escrow_view_marks_a_pending_grace_lesson(make, admin_user):
    make.grace()
    res = api(admin_user).get('/api/v1/admin/finance/ledger/?view=items')
    assert res.status_code == 200
    item = res.json()[0]
    assert item['payment_pending'] is True and item['escrow_status'] == 'holding'
