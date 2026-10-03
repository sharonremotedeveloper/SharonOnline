"""Task 9.6 building blocks: credit lots with expiry, the refund service (gateway refund / convert to wallet), windowed strikes."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.payments.models import CreditBundle, LedgerAccount, LedgerEntry, PaymentTransaction, RefundRequest
from apps.payments.services import refunds
from apps.payments.services.refund_gateways import RefundResult
from apps.payments.services.credits import (InsufficientCredits, available_credits, expire_credits, grant_credit,
                                            spend_credit)
from apps.teachers.models import TeacherStrike
from apps.teachers.strikes import add_strike
from test_settlement_paths import captured, lesson, net

S = Booking.Status
EV = LedgerEntry.EventType
ACC = LedgerAccount
DAY = timedelta(days=1)


def balance(account, **filters):
    rows = LedgerEntry.objects.filter(account=account, **filters)
    cr = sum((r.amount for r in rows if r.entry_type == 'credit'), Decimal('0'))
    dr = sum((r.amount for r in rows if r.entry_type == 'debit'), Decimal('0'))
    return cr - dr


# ------------------------------------------------------------------ credit lots
@pytest.mark.django_db
class TestCreditLots:
    def test_every_grant_is_its_own_lot_with_a_30_day_expiry(self, student_user):
        a = grant_credit(student_user, source=CreditBundle.Source.REFUND, unit_amount=Decimal('9.00'))
        b = grant_credit(student_user, credits=2, source=CreditBundle.Source.BONUS)
        assert a.pk != b.pk and CreditBundle.objects.filter(user=student_user).count() == 2
        assert (b.total_credits, b.remaining_credits) == (2, 2)
        for lot in (a, b):
            assert abs((lot.expires_at - (timezone.now() + 30 * DAY)).total_seconds()) < 5
        assert a.unit_amount == Decimal('9.00')

    def test_expiry_days_can_be_overridden_per_grant(self, student_user):
        lot = grant_credit(student_user, expires_in_days=7)
        assert abs((lot.expires_at - (timezone.now() + 7 * DAY)).total_seconds()) < 5

    def test_rejects_nonsense(self, student_user):
        with pytest.raises(ValueError):
            grant_credit(student_user, credits=0)

    def test_expired_lots_are_not_spendable_even_before_the_job_runs(self, student_user):
        live = grant_credit(student_user, credits=2)
        dead = grant_credit(student_user, credits=3)
        CreditBundle.objects.filter(pk=dead.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        assert available_credits(student_user) == 2
        assert live.pk in CreditBundle.objects.active().values_list('pk', flat=True)

    def test_legacy_lots_without_a_date_never_expire(self, student_user):
        CreditBundle.objects.create(user=student_user, total_credits=4, remaining_credits=4, amount_paid=0)
        assert available_credits(student_user) == 4

    def test_spending_takes_the_soonest_to_expire_first(self, student_user):
        later = grant_credit(student_user, credits=2, expires_in_days=29)
        sooner = grant_credit(student_user, credits=1, expires_in_days=3)
        used = spend_credit(student_user, credits=2)
        sooner.refresh_from_db(); later.refresh_from_db()
        assert (sooner.remaining_credits, later.remaining_credits) == (0, 1)
        assert sum(n for _, n in used) == 2

    def test_cannot_spend_more_than_is_unexpired(self, student_user):
        grant_credit(student_user, credits=1)
        dead = grant_credit(student_user, credits=5)
        CreditBundle.objects.filter(pk=dead.pk).update(expires_at=timezone.now() - timedelta(days=1))
        with pytest.raises(InsufficientCredits):
            spend_credit(student_user, credits=2)
        assert available_credits(student_user) == 1                 # nothing was half-spent

    def test_the_expiry_job_posts_breakage_exactly_once(self, student_user):
        lot = grant_credit(student_user, credits=3, source=CreditBundle.Source.REFUND, unit_amount=Decimal('9.00'))
        # the 2040 liability was credited when the lot was granted (as the callers do)
        LedgerEntry.objects.create(journal_batch_id='00000000-0000-0000-0000-000000000001', account=ACC.EXPENSE_STUDENT_COMPENSATION,
                                   entry_type='debit', amount=Decimal('27.00'), fx_rate_to_zar=Decimal('18.75'), fx_source='test_seed', amount_zar=Decimal('506.25'), event_type=EV.COMPENSATION_AWARDED, description='seed')
        LedgerEntry.objects.create(journal_batch_id='00000000-0000-0000-0000-000000000001', account=ACC.LIABILITY_STUDENT_WALLET,
                                   entry_type='credit', amount=Decimal('27.00'), fx_rate_to_zar=Decimal('18.75'), fx_source='test_seed', amount_zar=Decimal('506.25'), event_type=EV.COMPENSATION_AWARDED, description='seed')
        CreditBundle.objects.filter(pk=lot.pk).update(expires_at=timezone.now() - timedelta(hours=1))
        CreditBundle.objects.filter(pk=lot.pk).update(remaining_credits=2)                 # one credit was spent
        first = expire_credits()
        second = expire_credits()
        lot.refresh_from_db()
        assert (lot.remaining_credits, lot.expired_credits) == (0, 2) and lot.expired_at is not None
        assert first['lots'] == 1 and second['lots'] == 0
        assert balance(ACC.REVENUE_CREDIT_BREAKAGE) == Decimal('18.00')                    # 2 credits * 9.00
        assert balance(ACC.LIABILITY_STUDENT_WALLET) == Decimal('27.00') - Decimal('18.00')
        assert LedgerEntry.objects.filter(event_type=EV.CREDIT_EXPIRED).count() == 2

    def test_unexpired_and_valueless_lots_are_handled(self, student_user):
        fresh = grant_credit(student_user, unit_amount=Decimal('5.00'))
        free = grant_credit(student_user, credits=2)                                       # unit_amount 0: nothing on the ledger
        CreditBundle.objects.filter(pk=free.pk).update(expires_at=timezone.now() - timedelta(hours=1))
        assert expire_credits()['lots'] == 1
        free.refresh_from_db(); fresh.refresh_from_db()
        assert free.remaining_credits == 0 and fresh.remaining_credits == 1
        assert not LedgerEntry.objects.exists()

    def test_the_job_is_scheduled_daily_on_the_financial_queue(self):
        from config.celery_schedule import CELERY_BEAT_SCHEDULE
        entry = next(v for v in CELERY_BEAT_SCHEDULE.values() if v['task'] == 'apps.payments.tasks.expire_credits_task')
        assert entry['options']['queue'] == 'financial_escrow'


# ------------------------------------------------------------------ refunds
@pytest.mark.django_db
class TestRefundService:
    def test_a_paid_booking_gets_a_pending_gateway_refund_for_the_exact_capture(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 600)                  # R168.75 through PayFast
        out = refunds.request_refund(b, RefundRequest.Reason.STUDENT_CANCEL)
        r = out.refund
        assert (r.amount, r.currency, r.status, r.user) == (Decimal('168.75'), 'ZAR', 'pending_gateway', student_user)
        assert r.payment_transaction.gateway == 'payfast'
        assert net(b, ACC.LIABILITY_STUDENT_ESCROW) == 0                       # escrow drained by exactly what was captured
        assert net(b, ACC.LIABILITY_REFUNDS_PAYABLE) == Decimal('168.75')
        assert out.credit_lot is None and not CreditBundle.objects.exists()

    def test_asking_twice_is_one_refund(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 600)
        refunds.request_refund(b, RefundRequest.Reason.STUDENT_CANCEL)
        refunds.request_refund(b, RefundRequest.Reason.STUDENT_CANCEL)
        assert RefundRequest.objects.count() == 1
        assert net(b, ACC.LIABILITY_REFUNDS_PAYABLE) == Decimal('168.75')

    def test_the_event_type_is_the_callers(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 600)
        refunds.request_refund(b, RefundRequest.Reason.OUTAGE, event_type=EV.OUTAGE_REFUND)
        assert LedgerEntry.objects.filter(booking=b, event_type=EV.OUTAGE_REFUND).count() == 2

    def test_processing_pays_the_original_gateway_once(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 600)
        r = refunds.request_refund(b, RefundRequest.Reason.STUDENT_CANCEL).refund
        refunds.mark_processed(r.pk, 'PF-REF-1')
        refunds.mark_processed(r.pk, 'PF-REF-1')                                # a retry changes nothing
        r.refresh_from_db(); r.payment_transaction.refresh_from_db()
        assert (r.status, r.gateway_reference) == ('processed', 'PF-REF-1') and r.processed_at
        assert r.payment_transaction.status == PaymentTransaction.Status.REFUNDED
        assert net(b, ACC.LIABILITY_REFUNDS_PAYABLE) == 0
        assert net(b, ACC.ASSET_GATEWAY_PAYFAST) == Decimal('0')                # captured in, refunded out
        assert LedgerEntry.objects.filter(event_type=EV.GATEWAY_REFUND_PAID).count() == 2

    def test_a_pending_refund_can_become_wallet_credit(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 600)
        r = refunds.request_refund(b, RefundRequest.Reason.STUDENT_CANCEL).refund
        lot = refunds.convert_to_wallet(r.pk)
        r.refresh_from_db()
        assert r.status == 'converted'
        assert (lot.source, lot.unit_amount, lot.currency, lot.remaining_credits) == ('refund', Decimal('168.75'), 'ZAR', 1)
        assert abs((lot.expires_at - (timezone.now() + 30 * DAY)).total_seconds()) < 5
        assert net(b, ACC.LIABILITY_REFUNDS_PAYABLE) == 0 and net(b, ACC.LIABILITY_STUDENT_WALLET) == Decimal('168.75')

    def test_a_processed_or_converted_refund_cannot_be_changed_again(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 600)
        r = refunds.request_refund(b, RefundRequest.Reason.STUDENT_CANCEL).refund
        refunds.mark_processed(r.pk, 'X')
        with pytest.raises(refunds.RefundStateError):
            refunds.convert_to_wallet(r.pk)
        b2 = captured(teacher_user, student_user, 700, ref='CAP-2')
        r2 = refunds.request_refund(b2, RefundRequest.Reason.STUDENT_CANCEL).refund
        refunds.convert_to_wallet(r2.pk)
        with pytest.raises(refunds.RefundStateError):
            refunds.mark_processed(r2.pk, 'Y')

    def test_a_booking_with_no_funding_record_is_never_refunded_from_the_list_price(self, teacher_user, student_user):
        from apps.payments.models import SettlementAnomaly
        b = lesson(teacher_user, student_user, 600)                              # nothing was paid and no credit was spent
        with pytest.raises(refunds.MissingFunding):
            refunds.request_refund(b, RefundRequest.Reason.TEACHER_CANCEL)
        assert not RefundRequest.objects.exists() and not CreditBundle.objects.exists() and not LedgerEntry.objects.exists()
        assert SettlementAnomaly.objects.filter(booking=b, code='missing_booking_funding', resolved=False).exists()

    def test_a_credit_funded_lesson_gets_its_credit_back_not_a_gateway_refund(self, teacher_user, student_user):
        from apps.payments.services.credits import redeem_booking_credit
        grant_credit(student_user, source=CreditBundle.Source.PURCHASE, unit_amount=Decimal('9.00'), currency='USD', pack_name='Pack')
        b = lesson(teacher_user, student_user, 600)                              # unpaid hold, still live
        redeem_booking_credit(booking=b, student=student_user)
        assert available_credits(student_user) == 0
        assert net(b, ACC.LIABILITY_STUDENT_ESCROW) == Decimal('9.00')           # the credit funded the escrow
        out = refunds.request_refund(b, RefundRequest.Reason.TEACHER_CANCEL)
        assert out.refund is None and out.credit_lot.remaining_credits == 1
        assert (out.credit_lot.unit_amount, out.credit_lot.currency, out.credit_lot.source) == (Decimal('9.00'), 'USD', 'refund')
        assert available_credits(student_user) == 1 and not RefundRequest.objects.exists()
        assert net(b, ACC.LIABILITY_STUDENT_ESCROW) == 0                          # escrow drained again

    def test_the_default_gateway_leaves_requests_pending_and_a_real_one_settles_them(self, teacher_user, student_user, settings):
        settings.REFUND_FIRST_ATTEMPT_DELAY_MINUTES = 0
        b = captured(teacher_user, student_user, 600)
        r = refunds.request_refund(b, RefundRequest.Reason.STUDENT_CANCEL).refund
        manual = {'sent': 1, 'completed': 0, 'submitted': 0, 'rejected': 0, 'transient': 0, 'manual': 1, 'polled': 0, 'skipped_breaker': 0}
        assert refunds.process_pending_refunds() == manual
        r.refresh_from_db()
        assert r.status == 'pending_gateway' and r.attempts == 0                 # a manual backend burns no attempt
        settings.REFUND_GATEWAY_BACKEND = 'test_refunds_credits_strikes.FakeGateway'
        RefundRequest.objects.filter(pk=r.pk).update(next_attempt_at=None)       # skip the 6 h wait of a manual row
        assert refunds.process_pending_refunds() == {**manual, 'completed': 1, 'manual': 0}
        r.refresh_from_db()
        assert r.status == 'processed' and r.gateway_reference == f'FAKE-{r.pk}'

    def test_a_gateway_error_is_retried_not_dead_ended_and_never_hidden(self, teacher_user, student_user, settings, caplog):
        settings.REFUND_FIRST_ATTEMPT_DELAY_MINUTES = 0
        b = captured(teacher_user, student_user, 600)
        r = refunds.request_refund(b, RefundRequest.Reason.STUDENT_CANCEL).refund
        settings.REFUND_GATEWAY_BACKEND = 'test_refunds_credits_strikes.BrokenGateway'
        out = refunds.process_pending_refunds()
        assert out['transient'] == 1 and out['rejected'] == 0 and out['completed'] == 0
        r.refresh_from_db()
        assert r.status == 'pending_gateway' and r.attempts == 1 and r.next_attempt_at is not None   # waits for a retry, not failed
        assert 'RuntimeError' in caplog.text                                       # the type is logged ...
        assert 'gateway is down' not in caplog.text                                # ... never the provider's text


class FakeGateway:
    def refund(self, order):
        return RefundResult('completed', reference=f'FAKE-{order.refund_id}')

    def lookup(self, order):
        return RefundResult('completed', reference=order.provider_refund_id)


class BrokenGateway:
    def refund(self, order):
        raise RuntimeError('gateway is down')

    def lookup(self, order):
        raise RuntimeError('gateway is down')


@pytest.mark.django_db
class TestRefundEndpoints:
    def client(self, user):
        c = APIClient(); c.force_authenticate(user=user); return c

    def test_the_student_can_list_and_convert_their_own_refund(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 600)
        r = refunds.request_refund(b, RefundRequest.Reason.STUDENT_CANCEL).refund
        rows = self.client(student_user).get('/api/v1/refunds/').json()
        assert [x['id'] for x in rows['results']] == [str(r.pk)] and rows['results'][0]['status'] == 'pending_gateway'
        res = self.client(student_user).post(f'/api/v1/refunds/{r.pk}/convert-to-wallet/')
        assert res.status_code == 200 and res.json()['status'] == 'converted'
        assert available_credits(student_user) == 1
        assert self.client(student_user).post(f'/api/v1/refunds/{r.pk}/convert-to-wallet/').status_code == 409

    def test_nobody_else_can_see_or_convert_it(self, teacher_user, student_user, admin_user):
        from django.contrib.auth import get_user_model
        other = get_user_model().objects.create_user(username='o', email='o@x.com', password='x-pass-12345', role='student')
        b = captured(teacher_user, student_user, 600)
        r = refunds.request_refund(b, RefundRequest.Reason.STUDENT_CANCEL).refund
        assert self.client(other).get('/api/v1/refunds/').json()['results'] == []
        assert self.client(other).post(f'/api/v1/refunds/{r.pk}/convert-to-wallet/').status_code == 404
        assert self.client(teacher_user.user).post(f'/api/v1/refunds/{r.pk}/convert-to-wallet/').status_code in (403, 404)
        assert APIClient().post(f'/api/v1/refunds/{r.pk}/convert-to-wallet/').status_code == 401
        r.refresh_from_db()
        assert r.status == 'pending_gateway'


# ------------------------------------------------------------------ strikes
@pytest.mark.django_db
class TestStrikes:
    def test_a_strike_is_recorded_and_counted(self, teacher_user):
        assert add_strike(teacher_user, TeacherStrike.Kind.NO_SHOW) == 1
        teacher_user.refresh_from_db()
        assert teacher_user.sla_strikes == 1 and teacher_user.is_active

    def test_three_inside_the_window_deactivate_the_tutor(self, teacher_user):
        for kind in (TeacherStrike.Kind.NO_SHOW, TeacherStrike.Kind.LATE_CANCEL, TeacherStrike.Kind.MEMO_SLA):
            add_strike(teacher_user, kind)
        teacher_user.refresh_from_db()
        assert teacher_user.sla_strikes == 3 and teacher_user.is_active is False

    def test_old_strikes_stop_counting(self, teacher_user):
        for kind in (TeacherStrike.Kind.NO_SHOW, TeacherStrike.Kind.LATE_CANCEL):
            add_strike(teacher_user, kind)
        TeacherStrike.objects.all().update(created_at=timezone.now() - timedelta(days=91))
        assert add_strike(teacher_user, TeacherStrike.Kind.MEMO_SLA) == 1
        teacher_user.refresh_from_db()
        assert teacher_user.sla_strikes == 1 and teacher_user.is_active

    def test_the_same_booking_cannot_earn_the_same_strike_twice(self, teacher_user, student_user):
        b = lesson(teacher_user, student_user, 600, status=S.CONFIRMED)
        add_strike(teacher_user, TeacherStrike.Kind.LATE_CANCEL, booking=b)
        assert add_strike(teacher_user, TeacherStrike.Kind.LATE_CANCEL, booking=b) == 1
        assert TeacherStrike.objects.count() == 1

    def test_a_strike_never_reactivates_a_deactivated_tutor(self, teacher_user):
        teacher_user.is_active = False
        teacher_user.save(update_fields=['is_active'])
        add_strike(teacher_user, TeacherStrike.Kind.NO_SHOW)
        teacher_user.refresh_from_db()
        assert teacher_user.is_active is False


# ------------------------------------------------------------------ a refunded lesson that is later disputed
@pytest.mark.django_db
class TestDisputeAfterRefund:
    """A tutor no-show is refunded; the tutor's late Zoom event then flips it to DISPUTED. The money has already left escrow."""

    def setup_dispute(self, teacher_user, student_user):
        from apps.admin_api.models import DisputeCase
        b = captured(teacher_user, student_user, 600)
        refunds.request_refund(b, RefundRequest.Reason.TEACHER_NO_SHOW)
        Booking.objects.filter(pk=b.pk).update(status=S.DISPUTED)
        d = DisputeCase.objects.create(booking=b, student=student_user, teacher=teacher_user, student_statement='x')
        return b, d

    def resolve(self, admin, d, resolution):
        c = APIClient(); c.force_authenticate(user=admin)
        return c.post(f'/api/v1/admin/disputes/{d.id}/resolve/', {'resolution': resolution}, format='json')

    @pytest.mark.parametrize('resolution', ['release_tutor', 'split_50_50'])
    def test_cannot_be_paid_to_the_tutor_as_well(self, admin_user, teacher_user, student_user, resolution):
        b, d = self.setup_dispute(teacher_user, student_user)
        res = self.resolve(admin_user, d, resolution)
        assert res.status_code == 409 and res.json()['code'] == 'already_settled'
        d.refresh_from_db(); b.refresh_from_db()
        assert d.status == 'open' and b.status == S.DISPUTED
        assert net(b, ACC.LIABILITY_TUTOR_PAYABLE) == 0 and net(b, ACC.LIABILITY_STUDENT_ESCROW) == 0

    def test_a_full_refund_decision_just_closes_it_without_paying_again(self, admin_user, teacher_user, student_user):
        b, d = self.setup_dispute(teacher_user, student_user)
        res = self.resolve(admin_user, d, 'full_refund_student')
        assert res.status_code == 200
        b.refresh_from_db()
        assert b.status == S.CANCELLED
        assert RefundRequest.objects.filter(booking=b).count() == 1
        assert net(b, ACC.LIABILITY_REFUNDS_PAYABLE) == Decimal('168.75')            # still one refund, not two

    def test_an_ordinary_dispute_full_refund_goes_through_the_gateway(self, admin_user, teacher_user, student_user):
        from apps.admin_api.models import DisputeCase
        b = captured(teacher_user, student_user, 600)
        Booking.objects.filter(pk=b.pk).update(status=S.DISPUTED)
        d = DisputeCase.objects.create(booking=b, student=student_user, teacher=teacher_user, student_statement='x')
        assert self.resolve(admin_user, d, 'full_refund_student').status_code == 200
        r = RefundRequest.objects.get(booking=b)
        assert (r.reason, r.status, r.amount, r.currency) == ('dispute', 'pending_gateway', Decimal('168.75'), 'ZAR')
        assert LedgerEntry.objects.filter(booking=b, event_type=EV.DISPUTE_RESOLVED).count() == 2
        assert not CreditBundle.objects.exists()
