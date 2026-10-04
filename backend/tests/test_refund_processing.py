"""
Task 10.7 slice R-B: the refund service core (docs/TASK_10_7_REFUND_GATEWAYS_PLAN.md section 2b).

Every behaviour of the claim / call / apply protocol is pinned here with scripted fake gateways (no network): exactly-once
money movement, crash recovery with the same request id, stale-worker fencing, the webhook race, SUBMITTED handling,
backoff and exhaustion, the per-gateway circuit breaker, the guards, the cumulative cap, and the wallet-conversion race.
Time is a fixture (`refunds._now`), so backoff and windows are asserted exactly.
"""
import logging
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.test import APIClient

from apps.payments.models import (FxRate, GatewayAnomaly, LedgerAccount, LedgerEntry, LedgerImmutabilityError, PaymentTransaction,
                                  RefundAttempt, RefundRequest)
from apps.payments.services import paypal_events, refund_gateways, refunds
from apps.payments.services.refund_gateways import RefundResult
from payment_helpers import captured, net

ACC = LedgerAccount
EV = LedgerEntry.EventType
RS = RefundRequest.Status
MIN, HOUR, DAY = timedelta(minutes=1), timedelta(hours=1), timedelta(days=1)

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------------------------------------ scripted gateway
class ScriptedGateway:
    """Class-level state because the sweep builds a fresh backend object each run. `behavior(order)` / `lookup_behavior(order)`
    return a RefundResult or raise; `gateway`-specific scripts can branch on `order.gateway`."""
    calls: list = []
    lookups: list = []
    behavior = None
    lookup_behavior = None

    @classmethod
    def reset(cls):
        cls.calls, cls.lookups = [], []
        cls.behavior = lambda order: RefundResult('completed', reference=f'RF-{order.request_id}')
        cls.lookup_behavior = lambda order: RefundResult('completed', reference=order.provider_refund_id)

    def refund(self, order):
        type(self).calls.append(order)
        return type(self).behavior(order)

    def lookup(self, order):
        type(self).lookups.append(order)
        return type(self).lookup_behavior(order)


@pytest.fixture(autouse=True)
def gw(settings):
    ScriptedGateway.reset()
    settings.REFUND_GATEWAY_BACKEND = 'test_refund_processing.ScriptedGateway'
    settings.REFUND_FIRST_ATTEMPT_DELAY_MINUTES = 0
    return ScriptedGateway


class Clock:
    def __init__(self):
        self.now = timezone.now() + DAY          # a day ahead of the real clock: rows created by a test are already "old enough"

    def advance(self, delta):
        self.now += delta


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(refunds, '_now', lambda: c.now)
    return c


@pytest.fixture
def sent_mail(monkeypatch):
    out = []
    monkeypatch.setattr('apps.payments.tasks.send_email', lambda to, subject, html, text='': out.append((to, subject, html, text)))
    return out


_START = [600]


def new_refund(teacher_user, student_user, *, ref=None, gateway='paypal', amount='9.00', currency='USD'):
    _START[0] += 90                                    # a distinct slot per booking
    if currency in ('EUR', 'JPY'):
        FxRate.objects.get_or_create(currency=currency, defaults={'rate_to_zar': Decimal('0.125000'), 'source': 'manual',
                                                                  'valid_from': timezone.now() - 30 * DAY})
    ref = ref or f'CAP-{_START[0]}'
    booking = captured(teacher_user, student_user, _START[0], gateway=gateway, amount=amount, currency=currency, ref=ref)
    return refunds.request_refund(booking, RefundRequest.Reason.STUDENT_CANCEL).refund


def fresh(refund):
    return RefundRequest.objects.get(pk=refund.pk)


def journals(refund):
    return LedgerEntry.objects.filter(booking=refund.booking, event_type=EV.GATEWAY_REFUND_PAID).count()


def claim_one(**kw):
    return next(refunds.claim_due_refunds(limit=1, **kw), None)


def alerts(code, key=None):
    qs = GatewayAnomaly.objects.filter(reason=code)
    return qs.filter(reference=str(key)) if key is not None else qs


def set_row(refund, **fields):
    RefundRequest.objects.filter(pk=refund.pk).update(**fields)
    return fresh(refund)


def result_dict(**over):
    base = {'sent': 0, 'completed': 0, 'submitted': 0, 'rejected': 0, 'transient': 0, 'manual': 0, 'polled': 0, 'skipped_breaker': 0}
    base.update(over)
    return base


# ================================================================================================ settings and wiring
class TestSettingsAndWiring:
    def test_settings_have_the_exact_names_and_defaults(self, settings):
        assert settings.REFUND_MAX_ATTEMPTS == 8
        assert settings.REFUND_TRANSIENT_WINDOW_HOURS == 168
        assert settings.REFUND_ATTEMPT_LEASE_MINUTES == 10
        assert settings.REFUND_MANUAL_ALERT_AFTER_HOURS == 72
        assert settings.REFUND_REPLAY_WINDOW_DAYS == 30
        assert settings.REFUND_SWEEP_LIMIT == 25
        assert settings.REFUND_SWEEP_BUDGET_SECONDS == 600
        assert settings.REFUND_POLL_INTERVAL_MINUTES == 60

    def test_the_first_attempt_delay_defaults_to_an_hour(self):
        from importlib import import_module
        import os
        os.environ.pop('REFUND_FIRST_ATTEMPT_DELAY_MINUTES', None)
        base = import_module('config.settings.base')
        assert base.REFUND_FIRST_ATTEMPT_DELAY_MINUTES == 60

    def test_the_old_import_path_still_resolves_to_the_contract_class(self):
        assert refunds.ManualSandboxRefundGateway is refund_gateways.ManualSandboxRefundGateway

    def test_the_default_backend_is_the_manual_one(self):
        from importlib import import_module
        base = import_module('config.settings.base')
        assert base.REFUND_GATEWAY_BACKEND.endswith('ManualSandboxRefundGateway')

    def test_the_sweep_runs_every_15_minutes_on_the_financial_queue(self):
        from config.celery_schedule import CELERY_BEAT_SCHEDULE
        entry = next(v for v in CELERY_BEAT_SCHEDULE.values() if v['task'] == 'apps.payments.tasks.process_pending_refunds_task')
        assert entry['options']['queue'] == 'financial_escrow'

    def test_the_task_returns_the_sweep_dict(self, teacher_user, student_user):
        from apps.payments.tasks import process_pending_refunds_task
        new_refund(teacher_user, student_user)
        assert process_pending_refunds_task() == result_dict(sent=1, completed=1)


# ================================================================================================ models
class TestModels:
    def test_new_refund_fields_default_to_a_free_unattempted_row(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        assert (r.attempts, r.claim_token, r.gateway_request_id, r.request_epoch, r.failure_kind, r.last_error_code) == (0, '', '', 0, '', '')
        assert (r.submitted_at, r.next_attempt_at, r.last_attempt_at, r.first_attempt_at, r.claimed_until, r.last_http_status) == (None,) * 6

    def test_submitted_is_a_status(self):
        assert RefundRequest.Status.SUBMITTED == 'submitted'

    def test_the_status_next_attempt_index_exists(self):
        names = [tuple(i.fields) for i in RefundRequest._meta.indexes]
        assert ('status', 'next_attempt_at') in names

    def test_refund_attempts_are_immutable(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        refunds.mark_paid_manually(r.pk, actor=None, reference='MANUAL-1')
        row = RefundAttempt.objects.get()
        row.error_code = 'x'
        with pytest.raises(LedgerImmutabilityError):
            row.save()
        with pytest.raises(LedgerImmutabilityError):
            row.delete()
        with pytest.raises(LedgerImmutabilityError):
            RefundAttempt.objects.all().update(error_code='y')
        with pytest.raises(LedgerImmutabilityError):
            RefundAttempt.objects.all().delete()

    def test_attempt_sequence_numbers_are_unique_per_refund(self, teacher_user, student_user):
        from django.db import IntegrityError, transaction
        r = new_refund(teacher_user, student_user)
        RefundAttempt.objects.create(refund=r, seq=1, kind='send', request_id='x', result_state='transient')
        with pytest.raises(IntegrityError), transaction.atomic():
            RefundAttempt.objects.create(refund=r, seq=1, kind='send', request_id='x', result_state='transient')


# ================================================================================================ happy path and replay
class TestHappyPath:
    def test_completed_posts_one_journal_and_records_one_attempt(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        assert refunds.process_pending_refunds() == result_dict(sent=1, completed=1)
        r = fresh(r)
        assert r.status == RS.PROCESSED and r.gateway_reference == f'RF-refund-{r.pk}' and r.processed_at
        assert r.claim_token == '' and r.claimed_until is None
        assert r.payment_transaction.status == PaymentTransaction.Status.REFUNDED
        assert journals(r) == 2 and net(r.booking, ACC.LIABILITY_REFUNDS_PAYABLE) == 0
        row = RefundAttempt.objects.get()
        assert (row.refund_id, row.seq, row.kind, row.actor, row.request_id, row.result_state) == (r.pk, 1, 'send', None, f'refund-{r.pk}', 'completed')

    def test_the_order_handed_to_the_gateway_is_exact(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        order = gw.calls[0]
        assert (order.refund_id, order.request_id, order.gateway, order.amount, order.currency, order.invoice_id) == \
               (str(r.pk), f'refund-{r.pk}', 'paypal', Decimal('9.00'), 'USD', str(r.pk))
        assert order.capture_ref == r.payment_transaction.gateway_reference and order.provider_refund_id == ''
        assert order.note == 'Refund from Sharon Online'

    def test_the_note_comes_from_the_setting_when_it_exists(self, teacher_user, student_user, gw, settings):
        settings.PAYPAL_REFUND_NOTE = 'Thanks for learning with us'
        new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        assert gw.calls[0].note == 'Thanks for learning with us'

    def test_a_second_sweep_never_calls_again_nor_posts_again(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        assert refunds.process_pending_refunds() == result_dict()
        assert len(gw.calls) == 1 and journals(r) == 2 and RefundAttempt.objects.count() == 1

    def test_replaying_the_same_apply_is_a_noop(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        claim = claim_one()
        res = RefundResult('completed', reference='RF-1')
        assert refunds.apply_result(claim.refund_id, claim.token, res, kind='send') == 'processed'
        assert refunds.apply_result(claim.refund_id, claim.token, res, kind='send') == 'noop'
        assert journals(r) == 2 and RefundAttempt.objects.count() == 1

    def test_cash_account_follows_the_gateway_not_the_currency(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user, gateway='paypal', amount='168.75', currency='ZAR')       # PayPal ZAR
        refunds.process_pending_refunds()
        assert LedgerEntry.objects.filter(booking=r.booking, account=ACC.ASSET_GATEWAY_PAYPAL, event_type=EV.GATEWAY_REFUND_PAID).count() == 1

    def test_payfast_cash_account_is_1010(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user, gateway='payfast', amount='168.75', currency='ZAR')
        refunds.process_pending_refunds()
        assert LedgerEntry.objects.filter(booking=r.booking, account=ACC.ASSET_GATEWAY_PAYFAST, event_type=EV.GATEWAY_REFUND_PAID).count() == 1

    def test_a_completed_result_without_a_reference_uses_the_request_id(self, teacher_user, student_user, gw):
        gw.behavior = lambda order: RefundResult('completed')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        assert fresh(r).gateway_reference == f'refund-{r.pk}'

    def test_the_student_is_emailed_once_in_plain_words(self, teacher_user, student_user, sent_mail, django_capture_on_commit_callbacks):
        r = new_refund(teacher_user, student_user)
        with django_capture_on_commit_callbacks(execute=True):
            refunds.process_pending_refunds()
            refunds.process_pending_refunds()
        mails = [m for m in sent_mail if m[0] == student_user.email]
        assert len(mails) == 1
        to, subject, html, text = mails[0]
        assert '9.00 USD' in text and 'business days' in text and 'RF-' not in text and 'RF-' not in html and str(r.pk) not in text

    def test_no_email_for_a_refund_that_is_not_processed(self, teacher_user, student_user, sent_mail, django_capture_on_commit_callbacks):
        from apps.payments.tasks import send_refund_processed_email_task
        r = new_refund(teacher_user, student_user)
        send_refund_processed_email_task(str(r.pk))
        assert sent_mail == []

    def test_the_email_task_is_idempotent_per_refund(self, teacher_user, student_user, sent_mail, django_capture_on_commit_callbacks):
        from apps.payments.tasks import send_refund_processed_email_task
        r = new_refund(teacher_user, student_user)
        with django_capture_on_commit_callbacks(execute=True):
            refunds.process_pending_refunds()
        send_refund_processed_email_task(str(r.pk))
        assert len([m for m in sent_mail if m[0] == student_user.email]) == 1


# ================================================================================================ crash safety / races
class TestCrashAndConcurrency:
    def test_a_crash_after_the_gateway_call_replays_the_same_request_id_after_the_lease(self, teacher_user, student_user, gw, clock):
        r = new_refund(teacher_user, student_user)
        claim = claim_one()                                   # claimed, gateway called by the "crashed" worker, nothing applied
        gw.calls.append(claim.order)
        assert fresh(r).attempts == 1 and fresh(r).claim_token == claim.token
        clock.advance(9 * MIN)
        assert refunds.process_pending_refunds() == result_dict()          # still inside the lease: untouched
        clock.advance(2 * MIN)
        assert refunds.process_pending_refunds() == result_dict(sent=1, completed=1)
        assert [o.request_id for o in gw.calls] == [claim.order.request_id, claim.order.request_id]
        r = fresh(r)
        assert r.status == RS.PROCESSED and r.attempts == 2 and journals(r) == 2

    def test_the_lease_length_is_the_setting(self, teacher_user, student_user, clock, settings):
        settings.REFUND_ATTEMPT_LEASE_MINUTES = 3
        r = new_refund(teacher_user, student_user)
        claim_one()
        assert fresh(r).claimed_until == clock.now + 3 * MIN

    def test_the_claim_stamps_everything_in_one_step(self, teacher_user, student_user, clock):
        r = new_refund(teacher_user, student_user)
        claim = claim_one()
        r = fresh(r)
        assert claim.kind == 'send' and claim.refund_id == str(r.pk)
        assert (r.attempts, r.last_attempt_at, r.first_attempt_at) == (1, clock.now, clock.now)
        assert r.claim_token == claim.token and len(claim.token) == 32 and r.claimed_until == clock.now + 10 * MIN
        assert r.gateway_request_id == f'refund-{r.pk}' == claim.order.request_id and r.status == RS.PENDING_GATEWAY

    def test_the_first_attempt_time_is_kept_by_later_claims(self, teacher_user, student_user, clock, gw):
        gw.behavior = lambda order: RefundResult('transient')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        first = fresh(r).first_attempt_at
        clock.advance(2 * HOUR)
        refunds.process_pending_refunds()
        r = fresh(r)
        assert r.attempts == 2 and r.first_attempt_at == first and r.last_attempt_at == clock.now

    def test_two_overlapping_sweeps_only_one_wins(self, teacher_user, student_user, gw):
        new_refund(teacher_user, student_user)
        g1, g2 = refunds.claim_due_refunds(limit=5), refunds.claim_due_refunds(limit=5)
        first, second = next(g1, None), next(g2, None)
        assert first is not None and second is None

    def test_the_compare_and_swap_alone_stops_a_second_claim(self, teacher_user, student_user, monkeypatch, gw):
        r = new_refund(teacher_user, student_user)
        monkeypatch.setattr(refunds, '_is_due', lambda refund, now: True)     # pretend the python-side check was stale
        cands = list(refunds._due_candidates(refunds._now()))
        assert refunds._try_claim(*cands[0][:2], refunds._now) is not None
        assert refunds._try_claim(*cands[0][:2], refunds._now) is None
        assert fresh(r).attempts == 1

    @pytest.mark.parametrize('field,value', [
        ('status', RS.FAILED), ('status', RS.SUBMITTED), ('status', RS.PROCESSED), ('status', RS.CONVERTED),
        ('next_attempt_at', 'future'), ('claimed_until', 'future'), ('request_epoch', 1),
    ])
    def test_each_cas_condition_blocks_the_claim(self, teacher_user, student_user, clock, field, value):
        r = new_refund(teacher_user, student_user)
        if value == 'future':
            value = clock.now + HOUR
        set_row(r, **{field: value})
        assert refunds._cas_claim(r.pk, now=clock.now, lease=10 * MIN, token='t' * 32, request_id='refund-x', epoch=0,
                                  kind='send', delay=timedelta(0)) is False
        assert fresh(r).attempts == 0 and fresh(r).claim_token == ''

    def test_the_cas_claims_a_clean_row_and_reports_it(self, teacher_user, student_user, clock):
        r = new_refund(teacher_user, student_user)
        assert refunds._cas_claim(r.pk, now=clock.now, lease=10 * MIN, token='t' * 32, request_id='refund-x', epoch=0,
                                  kind='send', delay=timedelta(0)) is True
        assert fresh(r).attempts == 1

    def test_the_cas_respects_an_expired_lease_and_a_due_backoff(self, teacher_user, student_user, clock):
        r = new_refund(teacher_user, student_user)
        set_row(r, claimed_until=clock.now - MIN, next_attempt_at=clock.now - MIN, claim_token='old', attempts=1)
        assert refunds._cas_claim(r.pk, now=clock.now, lease=10 * MIN, token='n' * 32, request_id='refund-x', epoch=0,
                                  kind='send', delay=timedelta(0)) is True
        r = fresh(r)
        assert r.claim_token == 'n' * 32 and r.attempts == 2

    def test_the_cas_keeps_a_stored_request_id(self, teacher_user, student_user, clock):
        r = new_refund(teacher_user, student_user)
        set_row(r, gateway_request_id='refund-original', attempts=1)
        refunds._cas_claim(r.pk, now=clock.now, lease=10 * MIN, token='t' * 32, request_id='refund-other', epoch=0, kind='send', delay=timedelta(0))
        assert fresh(r).gateway_request_id == 'refund-original'

    def test_the_first_attempt_delay_is_part_of_the_cas(self, teacher_user, student_user, clock):
        r = new_refund(teacher_user, student_user)
        assert refunds._cas_claim(r.pk, now=clock.now, lease=10 * MIN, token='t' * 32, request_id='x', epoch=0, kind='send', delay=2 * DAY) is False
        set_row(r, attempts=1)
        assert refunds._cas_claim(r.pk, now=clock.now, lease=10 * MIN, token='t' * 32, request_id='x', epoch=0, kind='send', delay=2 * DAY) is True

    def test_a_stale_token_apply_is_a_noop(self, teacher_user, student_user, clock):
        r = new_refund(teacher_user, student_user)
        old = claim_one()
        clock.advance(11 * MIN)
        new = claim_one()
        assert old.token != new.token
        assert refunds.apply_result(r.pk, old.token, RefundResult('completed', reference='LATE'), kind='send') == 'noop'
        assert fresh(r).status == RS.PENDING_GATEWAY and journals(r) == 0 and RefundAttempt.objects.count() == 0
        assert refunds.apply_result(r.pk, new.token, RefundResult('completed', reference='NEW'), kind='send') == 'processed'
        assert fresh(r).gateway_reference == 'NEW'

    def test_an_empty_or_unknown_token_never_applies(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        claim_one()
        assert refunds.apply_result(r.pk, '', RefundResult('completed', reference='X'), kind='send') == 'noop'
        assert refunds.apply_result(r.pk, 'nope', RefundResult('completed', reference='X'), kind='send') == 'noop'
        assert fresh(r).status == RS.PENDING_GATEWAY

    def test_a_row_that_was_never_claimed_cannot_be_applied(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        assert refunds.apply_result(r.pk, '', RefundResult('completed', reference='X'), kind='send') == 'noop'

    def test_a_poll_result_cannot_be_applied_to_a_send_claim(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        claim = claim_one()
        assert refunds.apply_result(r.pk, claim.token, RefundResult('completed', reference='X'), kind='poll') == 'noop'

    def test_a_webhook_before_the_apply_wins_and_the_apply_is_a_noop(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        claim = claim_one()
        refunds.mark_processed(r.pk, 'WH-REF')
        assert refunds.apply_result(r.pk, claim.token, RefundResult('completed', reference='RF'), kind='send') == 'noop'
        r = fresh(r)
        assert r.gateway_reference == 'WH-REF' and journals(r) == 2 and r.claim_token == ''

    def test_a_webhook_after_the_apply_is_a_duplicate(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        r = fresh(r)
        tx = r.payment_transaction
        assert paypal_events.apply_refund(tx.pk, r.gateway_reference, Decimal('9.00'), 'USD', {}) == 'duplicate'
        assert journals(r) == 2

    def test_an_unrelated_dashboard_refund_id_for_a_processed_request_posts_nothing(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        before = LedgerEntry.objects.count()
        paypal_events.apply_refund(r.payment_transaction_id, 'OTHER-REF', Decimal('9.00'), 'USD', {})
        assert LedgerEntry.objects.filter(event_type=EV.GATEWAY_REFUND_PAID).count() == 2
        assert LedgerEntry.objects.count() == before

    def test_the_bad_row_never_stops_the_sweep(self, teacher_user, student_user, gw):
        a = new_refund(teacher_user, student_user)
        b = new_refund(teacher_user, student_user)

        def behavior(order):
            if order.refund_id == str(a.pk):
                raise RuntimeError('provider exploded with a secret-token')
            return RefundResult('completed', reference='OK')
        gw.behavior = behavior
        out = refunds.process_pending_refunds()
        assert out == result_dict(sent=2, completed=1, transient=1)
        assert fresh(a).status == RS.PENDING_GATEWAY and fresh(b).status == RS.PROCESSED

    def test_an_exception_in_apply_never_stops_the_sweep_and_the_row_replays(self, teacher_user, student_user, gw, clock, monkeypatch):
        a = new_refund(teacher_user, student_user)
        b = new_refund(teacher_user, student_user)
        real = refunds.apply_result
        boom = {'on': True}

        def flaky(refund_id, token, result, *, kind):
            if boom['on'] and str(refund_id) == str(a.pk):
                raise RuntimeError('db hiccup')
            return real(refund_id, token, result, kind=kind)
        monkeypatch.setattr(refunds, 'apply_result', flaky)
        out = refunds.process_pending_refunds()
        assert fresh(b).status == RS.PROCESSED and fresh(a).status == RS.PENDING_GATEWAY and out['sent'] == 2
        boom['on'] = False
        clock.advance(11 * MIN)
        refunds.process_pending_refunds()
        assert fresh(a).status == RS.PROCESSED
        assert len({o.request_id for o in gw.calls if o.refund_id == str(a.pk)}) == 1      # same request id on the replay

    def test_the_sweep_limit_bounds_one_run(self, teacher_user, student_user, settings, gw):
        settings.REFUND_SWEEP_LIMIT = 2
        for _ in range(3):
            new_refund(teacher_user, student_user)
        assert refunds.process_pending_refunds()['sent'] == 2
        assert refunds.process_pending_refunds()['sent'] == 1

    def test_the_sweep_budget_stops_the_run_before_the_next_claim(self, teacher_user, student_user, settings, monkeypatch):
        settings.REFUND_SWEEP_BUDGET_SECONDS = 600
        times = iter([0, 0, 700, 700, 700, 700, 700, 700])
        monkeypatch.setattr(refunds, '_monotonic', lambda: next(times))
        rows = [new_refund(teacher_user, student_user) for _ in range(3)]
        out = refunds.process_pending_refunds()
        assert out['sent'] == 1
        assert sorted(fresh(r).attempts for r in rows) == [0, 0, 1]        # the others were never claimed, so burn nothing

    def test_the_budget_boundary_is_inclusive(self, teacher_user, student_user, settings, monkeypatch):
        settings.REFUND_SWEEP_BUDGET_SECONDS = 600
        times = iter([0, 600, 600, 600])
        monkeypatch.setattr(refunds, '_monotonic', lambda: next(times))
        new_refund(teacher_user, student_user)
        assert refunds.process_pending_refunds()['sent'] == 0

    def test_old_refunds_go_first(self, teacher_user, student_user, gw, settings):
        settings.REFUND_SWEEP_LIMIT = 1
        a = new_refund(teacher_user, student_user)
        b = new_refund(teacher_user, student_user)
        set_row(a, created_at=timezone.now() - 2 * DAY)
        set_row(b, created_at=timezone.now() - 3 * DAY)
        refunds.process_pending_refunds()
        assert fresh(b).status == RS.PROCESSED and fresh(a).status == RS.PENDING_GATEWAY


# ================================================================================================ first attempt delay and convert
class TestFirstAttemptDelayAndConvert:
    def test_the_first_attempt_waits_for_the_delay_then_goes(self, teacher_user, student_user, settings, clock, gw):
        settings.REFUND_FIRST_ATTEMPT_DELAY_MINUTES = 60
        r = new_refund(teacher_user, student_user)
        clock.now = r.created_at + 59 * MIN
        assert refunds.process_pending_refunds() == result_dict()
        assert gw.calls == []
        clock.now = r.created_at + 61 * MIN
        assert refunds.process_pending_refunds() == result_dict(sent=1, completed=1)

    def test_the_student_can_convert_inside_the_delay_and_the_gateway_is_never_called(self, teacher_user, student_user, settings, clock, gw):
        settings.REFUND_FIRST_ATTEMPT_DELAY_MINUTES = 60
        r = new_refund(teacher_user, student_user)
        lot = refunds.convert_to_wallet(r.pk)
        assert lot.remaining_credits == 1 and fresh(r).status == RS.CONVERTED
        clock.now = r.created_at + 3 * HOUR
        assert refunds.process_pending_refunds() == result_dict()
        assert gw.calls == []

    def test_convert_before_the_first_attempt_wins_even_against_a_stale_candidate_list(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        stale = list(refunds._due_candidates(refunds._now()))
        refunds.convert_to_wallet(r.pk)
        assert refunds._try_claim(*stale[0][:2], refunds._now) is None
        assert gw.calls == [] and fresh(r).attempts == 0 and fresh(r).status == RS.CONVERTED

    def test_convert_after_the_claim_is_refused_as_in_progress(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        claim_one()
        with pytest.raises(refunds.RefundInProgress):
            refunds.convert_to_wallet(r.pk)
        assert fresh(r).status == RS.PENDING_GATEWAY

    def test_in_progress_is_a_state_error(self):
        assert issubclass(refunds.RefundInProgress, refunds.RefundStateError)

    def test_convert_stays_refused_after_the_lease_expires(self, teacher_user, student_user, clock):
        r = new_refund(teacher_user, student_user)
        claim_one()
        clock.advance(HOUR)
        with pytest.raises(refunds.RefundInProgress):
            refunds.convert_to_wallet(r.pk)

    def test_convert_is_refused_after_a_transient_attempt(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        gw.behavior = lambda order: RefundResult('transient')
        refunds.process_pending_refunds()
        with pytest.raises(refunds.RefundInProgress):
            refunds.convert_to_wallet(r.pk)

    @pytest.mark.parametrize('field,value', [('attempts', 1), ('last_attempt_at', 'now'), ('claim_token', 'x' * 32), ('claimed_until', 'future')])
    def test_each_in_progress_signal_blocks_the_convert(self, teacher_user, student_user, field, value):
        r = new_refund(teacher_user, student_user)
        if value == 'now':
            value = timezone.now() - DAY
        elif value == 'future':
            value = timezone.now() + HOUR
        set_row(r, **{field: value})
        with pytest.raises(refunds.RefundInProgress):
            refunds.convert_to_wallet(r.pk)

    def test_an_expired_claim_marker_alone_does_not_block_a_never_attempted_row(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        set_row(r, claimed_until=timezone.now() - HOUR)
        assert refunds.convert_to_wallet(r.pk).remaining_credits == 1

    def test_a_manual_row_stays_convertible_because_nothing_was_attempted(self, teacher_user, student_user, gw):
        gw.behavior = lambda order: RefundResult('manual')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        assert refunds.convert_to_wallet(r.pk).remaining_credits == 1

    def test_a_submitted_refund_cannot_be_converted(self, teacher_user, student_user, gw):
        gw.behavior = lambda order: RefundResult('submitted', reference='RF-S')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        with pytest.raises(refunds.RefundInProgress):
            refunds.convert_to_wallet(r.pk)

    @pytest.mark.parametrize('status', [RS.PROCESSED, RS.CONVERTED, RS.FAILED, RS.VOID, RS.AWAITING_CLEARANCE])
    def test_only_a_pending_refund_converts(self, teacher_user, student_user, status):
        r = new_refund(teacher_user, student_user)
        set_row(r, status=status)
        with pytest.raises(refunds.RefundStateError):
            refunds.convert_to_wallet(r.pk)

    def test_the_api_maps_in_progress_to_409_refund_in_progress(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        claim_one()
        c = APIClient()
        c.force_authenticate(user=student_user)
        res = c.post(f'/api/v1/refunds/{r.pk}/convert-to-wallet/')
        assert res.status_code == 409 and res.json()['code'] == 'refund_in_progress'

    def test_the_api_keeps_already_processed_for_the_other_states(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        c = APIClient()
        c.force_authenticate(user=student_user)
        res = c.post(f'/api/v1/refunds/{r.pk}/convert-to-wallet/')
        assert res.status_code == 409 and res.json()['code'] == 'already_processed'

    def test_the_student_list_shows_the_submitted_status(self, teacher_user, student_user, gw):
        gw.behavior = lambda order: RefundResult('submitted', reference='RF-S')
        new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        c = APIClient()
        c.force_authenticate(user=student_user)
        assert c.get('/api/v1/refunds/').json()['results'][0]['status'] == 'submitted'


# ================================================================================================ SUBMITTED
class TestSubmitted:
    @pytest.fixture
    def submitted(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: RefundResult('submitted', reference='RF-S', http_status=201)
        r = new_refund(teacher_user, student_user)
        assert refunds.process_pending_refunds() == result_dict(sent=1, submitted=1)
        return fresh(r)

    def test_send_pending_becomes_submitted_with_the_provider_id(self, submitted, clock):
        assert submitted.status == RS.SUBMITTED and submitted.gateway_reference == 'RF-S'
        assert submitted.submitted_at == clock.now and submitted.next_attempt_at == clock.now + 60 * MIN
        assert submitted.claim_token == '' and submitted.claimed_until is None and submitted.attempts == 1
        assert journals(submitted) == 0 and submitted.payment_transaction.status == PaymentTransaction.Status.SUCCESS

    def test_poll_interval_is_the_setting(self, teacher_user, student_user, gw, clock, settings):
        settings.REFUND_POLL_INTERVAL_MINUTES = 5
        gw.behavior = lambda order: RefundResult('submitted', reference='RF-S')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        assert fresh(r).next_attempt_at == clock.now + 5 * MIN

    def test_a_submitted_refund_is_not_polled_before_its_time_and_never_resent(self, submitted, gw, clock):
        clock.advance(59 * MIN)
        assert refunds.process_pending_refunds() == result_dict()
        assert len(gw.calls) == 1 and gw.lookups == []

    def test_the_poll_completes_it_exactly_once(self, submitted, gw, clock):
        clock.advance(61 * MIN)
        assert refunds.process_pending_refunds() == result_dict(polled=1, completed=1)
        r = fresh(submitted)
        assert r.status == RS.PROCESSED and r.gateway_reference == 'RF-S' and journals(r) == 2
        assert gw.lookups[0].provider_refund_id == 'RF-S' and len(gw.calls) == 1
        assert [a.kind for a in RefundAttempt.objects.order_by('seq')] == ['send', 'poll']
        assert refunds.process_pending_refunds() == result_dict() and journals(r) == 2

    def test_the_poll_keeps_waiting_while_the_provider_is_pending(self, submitted, gw, clock):
        gw.lookup_behavior = lambda order: RefundResult('submitted', reference='RF-S')
        clock.advance(61 * MIN)
        assert refunds.process_pending_refunds() == result_dict(polled=1)
        r = fresh(submitted)
        assert r.status == RS.SUBMITTED and r.next_attempt_at == clock.now + 60 * MIN and r.submitted_at == submitted.submitted_at
        assert r.attempts == 1                                                  # a poll is not a send attempt

    def test_a_poll_that_cannot_tell_keeps_the_row_submitted(self, submitted, gw, clock):
        gw.lookup_behavior = lambda order: RefundResult('transient')
        clock.advance(61 * MIN)
        assert refunds.process_pending_refunds() == result_dict(polled=1, transient=1)
        assert fresh(submitted).status == RS.SUBMITTED and fresh(submitted).next_attempt_at == clock.now + 60 * MIN

    def test_a_manual_poll_result_keeps_the_row_submitted(self, submitted, gw, clock):
        gw.lookup_behavior = lambda order: RefundResult('manual')
        clock.advance(61 * MIN)
        refunds.process_pending_refunds()
        assert fresh(submitted).status == RS.SUBMITTED

    def test_an_exception_while_polling_keeps_the_row_submitted(self, submitted, gw, clock):
        def boom(order):
            raise RuntimeError('x')
        gw.lookup_behavior = boom
        clock.advance(61 * MIN)
        assert refunds.process_pending_refunds()['transient'] == 1
        assert fresh(submitted).status == RS.SUBMITTED

    def test_a_provider_failure_after_submission_is_a_failure_for_a_human(self, submitted, gw, clock):
        gw.lookup_behavior = lambda order: RefundResult('rejected', detail='refund cancelled', code='CANCELLED')
        clock.advance(61 * MIN)
        assert refunds.process_pending_refunds() == result_dict(polled=1, rejected=1)
        r = fresh(submitted)
        assert r.status == RS.FAILED and r.failure_kind == 'provider_failed' and journals(r) == 0
        assert alerts('refund_failed_provider_failed', r.pk).count() == 1

    def test_the_stale_alert_fires_only_after_14_days(self, submitted, gw, clock):
        gw.lookup_behavior = lambda order: RefundResult('submitted', reference='RF-S')
        clock.advance(13 * DAY + 23 * HOUR)
        refunds.process_pending_refunds()
        assert alerts('refund_submitted_stale').count() == 0
        clock.advance(2 * HOUR)
        refunds.process_pending_refunds()
        assert alerts('refund_submitted_stale', submitted.pk).count() == 1
        clock.advance(2 * HOUR)
        refunds.process_pending_refunds()
        assert alerts('refund_submitted_stale').count() == 1                     # once while open

    def test_the_webhook_completes_a_submitted_refund_by_its_provider_id(self, submitted):
        tx = submitted.payment_transaction
        assert paypal_events.apply_refund(tx.pk, 'RF-S', Decimal('9.00'), 'USD', {}) == 'refund_completed'
        r = fresh(submitted)
        assert r.status == RS.PROCESSED and journals(r) == 2
        assert paypal_events.apply_refund(tx.pk, 'RF-S', Decimal('9.00'), 'USD', {}) == 'duplicate'
        assert journals(r) == 2

    def test_a_duplicate_webhook_for_a_still_submitted_ref_that_is_not_ours_to_finish_is_not_possible(self, submitted):
        # the matched-by-reference submitted row is finished; a *different* reference with the same amount also finishes it (ours lookup)
        tx = submitted.payment_transaction
        assert paypal_events.apply_refund(tx.pk, 'RF-OTHER', Decimal('9.00'), 'USD', {}) == 'refund_completed'
        assert fresh(submitted).status == RS.PROCESSED and fresh(submitted).gateway_reference == 'RF-OTHER'

    def test_the_webhook_then_the_poll_posts_once(self, submitted, gw, clock):
        refunds.mark_processed(submitted.pk, 'RF-S')
        clock.advance(61 * MIN)
        assert refunds.process_pending_refunds() == result_dict()
        assert journals(submitted) == 2

    def test_a_poll_in_flight_when_the_webhook_lands_is_a_noop(self, submitted, clock):
        clock.advance(61 * MIN)
        claim = claim_one()
        assert claim.kind == 'poll' and claim.order.provider_refund_id == 'RF-S'
        refunds.mark_processed(submitted.pk, 'RF-S')
        assert refunds.apply_result(submitted.pk, claim.token, RefundResult('completed', reference='RF-S'), kind='poll') == 'noop'
        assert journals(submitted) == 2

    def test_a_submitted_send_result_without_a_provider_id_is_treated_as_transient(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: RefundResult('submitted')
        r = new_refund(teacher_user, student_user)
        assert refunds.process_pending_refunds() == result_dict(sent=1, transient=1)
        assert fresh(r).status == RS.PENDING_GATEWAY

    def test_mark_submitted_requires_the_claim_token(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        claim = claim_one()
        with pytest.raises(refunds.RefundStateError):
            refunds.mark_submitted(r.pk, 'RF-1', token='wrong')
        refunds.mark_submitted(r.pk, 'RF-1', token=claim.token)
        assert fresh(r).status == RS.SUBMITTED and fresh(r).gateway_reference == 'RF-1'

    def test_submitted_cannot_be_paid_by_hand(self, submitted):
        with pytest.raises(refunds.RefundStateError):
            refunds.mark_paid_manually(submitted.pk, actor=None, reference='MANUAL-1')


# ================================================================================================ transient, backoff, exhaustion
class TestTransient:
    def test_backoff_is_15m_1h_4h_12h_then_24h(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: RefundResult('transient', http_status=503)
        r = new_refund(teacher_user, student_user)
        for delay in (15 * MIN, HOUR, 4 * HOUR, 12 * HOUR, DAY, DAY, DAY):
            assert refunds.process_pending_refunds() == result_dict(sent=1, transient=1)
            row = fresh(r)
            assert row.status == RS.PENDING_GATEWAY and row.next_attempt_at == clock.now + delay and row.claim_token == ''
            clock.advance(delay - MIN)
            assert refunds.process_pending_refunds() == result_dict()           # not due one minute early
            clock.advance(MIN)
        assert fresh(r).attempts == 7

    def test_the_http_status_and_error_code_are_kept(self, teacher_user, student_user, gw):
        gw.behavior = lambda order: RefundResult('transient', http_status=503, code='SERVICE_UNAVAILABLE', detail='try later')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        r = fresh(r)
        assert (r.last_http_status, r.last_error_code) == (503, 'SERVICE_UNAVAILABLE')
        row = RefundAttempt.objects.get()
        assert (row.http_status, row.error_code, row.result_state) == (503, 'SERVICE_UNAVAILABLE', 'transient')

    def test_retry_after_is_honoured_but_capped_at_a_day(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: RefundResult('transient', retry_after_s=7200)
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        assert fresh(r).next_attempt_at == clock.now + 2 * HOUR
        clock.advance(3 * HOUR)
        gw.behavior = lambda order: RefundResult('transient', retry_after_s=10 * 86400)
        refunds.process_pending_refunds()
        assert fresh(r).next_attempt_at == clock.now + DAY

    def test_a_small_retry_after_never_shortens_the_backoff(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: RefundResult('transient', retry_after_s=5)
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        assert fresh(r).next_attempt_at == clock.now + 15 * MIN

    def test_an_unexpected_exception_is_transient_and_only_its_type_is_logged(self, teacher_user, student_user, gw, caplog):
        def boom(order):
            raise ValueError('Bearer super-secret-token-123')
        gw.behavior = boom
        r = new_refund(teacher_user, student_user)
        with caplog.at_level(logging.DEBUG):
            assert refunds.process_pending_refunds() == result_dict(sent=1, transient=1)
        assert fresh(r).status == RS.PENDING_GATEWAY
        assert 'ValueError' in caplog.text and 'super-secret-token-123' not in caplog.text
        assert 'super-secret-token-123' not in fresh(r).failure_detail

    def test_never_failed_within_the_window_even_after_many_attempts(self, teacher_user, student_user, gw, clock, settings):
        settings.REFUND_MAX_ATTEMPTS = 2
        gw.behavior = lambda order: RefundResult('transient')
        r = new_refund(teacher_user, student_user)
        for _ in range(5):
            clock.advance(DAY)
            refunds.process_pending_refunds()
        r = fresh(r)
        assert r.attempts == 5 and r.status == RS.PENDING_GATEWAY

    def test_never_failed_after_the_window_while_attempts_remain(self, teacher_user, student_user, gw, clock, settings):
        settings.REFUND_MAX_ATTEMPTS = 8
        gw.behavior = lambda order: RefundResult('transient')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        clock.advance(169 * HOUR)
        refunds.process_pending_refunds()
        assert fresh(r).attempts == 2 and fresh(r).status == RS.PENDING_GATEWAY

    def _exhaust(self, r, clock, *, attempts_before, age):
        set_row(r, attempts=attempts_before, first_attempt_at=clock.now - age, last_attempt_at=clock.now - age)
        return claim_one()

    def test_exhaustion_needs_both_conditions_at_the_boundary(self, teacher_user, student_user, clock, settings):
        settings.REFUND_MAX_ATTEMPTS, settings.REFUND_TRANSIENT_WINDOW_HOURS = 3, 168
        r = new_refund(teacher_user, student_user)
        claim = self._exhaust(r, clock, attempts_before=2, age=168 * HOUR)                  # attempts becomes 3 == MAX, age == window
        assert refunds.apply_result(r.pk, claim.token, RefundResult('transient', detail='503'), kind='send') == 'failed'
        r = fresh(r)
        assert r.status == RS.FAILED and r.failure_kind == 'exhausted'
        assert alerts('refund_failed_exhausted', r.pk).count() == 1

    def test_one_attempt_short_does_not_exhaust(self, teacher_user, student_user, clock, settings):
        settings.REFUND_MAX_ATTEMPTS, settings.REFUND_TRANSIENT_WINDOW_HOURS = 3, 168
        r = new_refund(teacher_user, student_user)
        claim = self._exhaust(r, clock, attempts_before=1, age=200 * HOUR)                  # attempts becomes 2 < 3
        assert refunds.apply_result(r.pk, claim.token, RefundResult('transient'), kind='send') == 'retry'
        assert fresh(r).status == RS.PENDING_GATEWAY

    def test_one_second_short_of_the_window_does_not_exhaust(self, teacher_user, student_user, clock, settings):
        settings.REFUND_MAX_ATTEMPTS, settings.REFUND_TRANSIENT_WINDOW_HOURS = 3, 168
        r = new_refund(teacher_user, student_user)
        claim = self._exhaust(r, clock, attempts_before=5, age=168 * HOUR - timedelta(seconds=1))
        assert refunds.apply_result(r.pk, claim.token, RefundResult('transient'), kind='send') == 'retry'

    def test_more_attempts_than_the_cap_also_exhaust_once_the_window_passes(self, teacher_user, student_user, clock, settings):
        settings.REFUND_MAX_ATTEMPTS, settings.REFUND_TRANSIENT_WINDOW_HOURS = 3, 168
        r = new_refund(teacher_user, student_user)
        claim = self._exhaust(r, clock, attempts_before=6, age=170 * HOUR)
        assert refunds.apply_result(r.pk, claim.token, RefundResult('transient'), kind='send') == 'failed'

    def test_a_provider_level_error_never_exhausts_a_row(self, teacher_user, student_user, clock, settings):
        settings.REFUND_MAX_ATTEMPTS, settings.REFUND_TRANSIENT_WINDOW_HOURS = 3, 168
        r = new_refund(teacher_user, student_user)
        claim = self._exhaust(r, clock, attempts_before=9, age=400 * HOUR)
        assert refunds.apply_result(r.pk, claim.token, RefundResult('transient', provider_level=True, http_status=401), kind='send') == 'retry'
        assert fresh(r).status == RS.PENDING_GATEWAY


# ================================================================================================ manual
class TestManual:
    def test_manual_does_not_burn_an_attempt_and_waits_six_hours(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: RefundResult('manual', detail='manual refund backend')
        r = new_refund(teacher_user, student_user)
        assert refunds.process_pending_refunds() == result_dict(sent=1, manual=1)
        row = fresh(r)
        assert (row.attempts, row.last_attempt_at, row.first_attempt_at) == (0, None, None)
        assert row.next_attempt_at == clock.now + 6 * HOUR and row.status == RS.PENDING_GATEWAY and row.claim_token == ''
        assert RefundAttempt.objects.get().result_state == 'manual'

    def test_many_manual_rounds_never_exhaust_or_fail(self, teacher_user, student_user, gw, clock, settings):
        settings.REFUND_MAX_ATTEMPTS = 1
        gw.behavior = lambda order: RefundResult('manual')
        r = new_refund(teacher_user, student_user)
        for _ in range(6):
            refunds.process_pending_refunds()
            clock.advance(10 * DAY)
        row = fresh(r)
        assert row.attempts == 0 and row.status == RS.PENDING_GATEWAY

    def test_manual_after_a_real_attempt_only_gives_back_the_manual_attempt(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: RefundResult('transient')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        clock.advance(HOUR)
        gw.behavior = lambda order: RefundResult('manual')
        refunds.process_pending_refunds()
        row = fresh(r)
        assert row.attempts == 1 and row.last_attempt_at is not None and row.first_attempt_at is not None

    def test_the_waiting_alert_comes_after_72_hours_only(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: RefundResult('manual')
        r = new_refund(teacher_user, student_user)
        set_row(r, created_at=clock.now - 71 * HOUR)
        refunds.process_pending_refunds()
        assert alerts('refund_manual_waiting').count() == 0
        clock.advance(2 * HOUR)
        set_row(r, next_attempt_at=None)
        refunds.process_pending_refunds()
        assert alerts('refund_manual_waiting', r.pk).count() == 1
        set_row(r, next_attempt_at=None)
        clock.advance(7 * HOUR)
        refunds.process_pending_refunds()
        assert alerts('refund_manual_waiting').count() == 1                  # once while open

    def test_the_waiting_threshold_is_the_setting(self, teacher_user, student_user, gw, clock, settings):
        settings.REFUND_MANUAL_ALERT_AFTER_HOURS = 1
        gw.behavior = lambda order: RefundResult('manual')
        r = new_refund(teacher_user, student_user)
        set_row(r, created_at=clock.now - 2 * HOUR)
        refunds.process_pending_refunds()
        assert alerts('refund_manual_waiting', r.pk).count() == 1

    def test_the_default_manual_backend_leaves_requests_waiting(self, teacher_user, student_user, settings):
        settings.REFUND_GATEWAY_BACKEND = 'apps.payments.services.refunds.ManualSandboxRefundGateway'
        r = new_refund(teacher_user, student_user)
        assert refunds.process_pending_refunds() == result_dict(sent=1, manual=1)
        assert fresh(r).status == RS.PENDING_GATEWAY and fresh(r).attempts == 0


# ================================================================================================ rejected / replay window
class TestRejectedAndReplayWindow:
    def test_rejected_is_failed_with_an_alert_and_an_audit_row(self, teacher_user, student_user, gw):
        gw.behavior = lambda order: RefundResult('rejected', detail='instrument declined', code='INSTRUMENT_DECLINED', http_status=422)
        r = new_refund(teacher_user, student_user)
        assert refunds.process_pending_refunds() == result_dict(sent=1, rejected=1)
        r = fresh(r)
        assert r.status == RS.FAILED and r.failure_kind == 'rejected' and 'instrument declined' in r.failure_detail
        assert (r.last_error_code, r.last_http_status) == ('INSTRUMENT_DECLINED', 422) and r.claim_token == ''
        assert alerts('refund_failed_rejected', r.pk).count() == 1 and journals(r) == 0
        assert RefundAttempt.objects.get().result_state == 'rejected'
        assert net(r.booking, ACC.LIABILITY_REFUNDS_PAYABLE) == Decimal('9.00')    # still owed: a human decides

    def test_capture_fully_refunded_is_already_refunded(self, teacher_user, student_user, gw):
        gw.behavior = lambda order: RefundResult('rejected', code='CAPTURE_FULLY_REFUNDED', http_status=422)
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        r = fresh(r)
        assert r.failure_kind == 'already_refunded' and alerts('refund_failed_already_refunded', r.pk).count() == 1

    def test_a_failed_refund_is_not_resent_by_the_sweep(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: RefundResult('rejected')
        new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        clock.advance(10 * DAY)
        assert refunds.process_pending_refunds() == result_dict() and len(gw.calls) == 1

    def test_the_detail_is_capped(self, teacher_user, student_user, gw):
        gw.behavior = lambda order: RefundResult('rejected', detail='x' * 5000)
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        assert len(fresh(r).failure_detail) <= 2000

    def test_beyond_the_replay_window_a_blind_replay_is_refused(self, teacher_user, student_user, gw, clock):
        r = new_refund(teacher_user, student_user)
        set_row(r, attempts=1, first_attempt_at=clock.now - 30 * DAY - MIN, last_attempt_at=clock.now - 30 * DAY,
                gateway_request_id=f'refund-{r.pk}', claimed_until=clock.now - DAY)
        assert refunds.process_pending_refunds() == result_dict()
        r = fresh(r)
        assert r.status == RS.FAILED and r.failure_kind == 'replay_window' and gw.calls == []
        assert alerts('refund_failed_replay_window', r.pk).count() == 1

    def test_inside_the_replay_window_it_is_replayed(self, teacher_user, student_user, gw, clock):
        r = new_refund(teacher_user, student_user)
        set_row(r, attempts=1, first_attempt_at=clock.now - 30 * DAY + MIN, last_attempt_at=clock.now - 30 * DAY,
                gateway_request_id=f'refund-{r.pk}', claimed_until=clock.now - DAY)
        assert refunds.process_pending_refunds()['sent'] == 1

    def test_the_replay_window_is_the_setting(self, teacher_user, student_user, gw, clock, settings):
        settings.REFUND_REPLAY_WINDOW_DAYS = 2
        r = new_refund(teacher_user, student_user)
        set_row(r, attempts=1, first_attempt_at=clock.now - 3 * DAY, last_attempt_at=clock.now - 3 * DAY, claimed_until=clock.now - DAY)
        refunds.process_pending_refunds()
        assert fresh(r).failure_kind == 'replay_window'

    def test_a_fresh_row_is_never_blocked_by_the_replay_window(self, teacher_user, student_user, gw, clock):
        r = new_refund(teacher_user, student_user)
        set_row(r, created_at=clock.now - 100 * DAY)                   # old row, but never attempted
        assert refunds.process_pending_refunds()['sent'] == 1


# ================================================================================================ circuit breaker
class TestCircuitBreaker:
    def _setup(self, teacher_user, student_user, gw, n_paypal=4, n_payfast=1):
        paypal = [new_refund(teacher_user, student_user) for _ in range(n_paypal)]
        payfast = [new_refund(teacher_user, student_user, gateway='payfast', amount='168.75', currency='ZAR') for _ in range(n_payfast)]
        gw.behavior = lambda order: RefundResult('transient', http_status=503) if order.gateway == 'paypal' else RefundResult('completed', reference='PF-OK')
        return paypal, payfast

    def test_three_consecutive_transients_stop_that_gateway_for_the_sweep(self, teacher_user, student_user, gw):
        paypal, payfast = self._setup(teacher_user, student_user, gw)
        out = refunds.process_pending_refunds()
        assert out == result_dict(sent=4, transient=3, completed=1, skipped_breaker=1)
        assert [fresh(r).attempts for r in paypal] == [1, 1, 1, 0]
        skipped = fresh(paypal[3])
        assert (skipped.next_attempt_at, skipped.claim_token, skipped.last_attempt_at) == (None, '', None)
        assert fresh(payfast[0]).status == RS.PROCESSED
        assert alerts('refund_provider_outage', 'paypal').count() == 1

    def test_provider_level_results_count_toward_the_breaker(self, teacher_user, student_user, gw):
        paypal, _ = self._setup(teacher_user, student_user, gw, n_payfast=0)
        gw.behavior = lambda order: RefundResult('transient', provider_level=True, http_status=401)
        assert refunds.process_pending_refunds() == result_dict(sent=3, transient=3, skipped_breaker=1)

    def test_a_success_between_failures_resets_the_count(self, teacher_user, student_user, gw):
        rows = [new_refund(teacher_user, student_user) for _ in range(5)]
        script = iter(['transient', 'transient', 'ok', 'transient', 'transient'])
        gw.behavior = lambda order: RefundResult('transient') if next(script) == 'transient' else RefundResult('completed', reference='OK')
        out = refunds.process_pending_refunds()
        assert out == result_dict(sent=5, transient=4, completed=1) and alerts('refund_provider_outage').count() == 0

    def test_a_rejection_counts_as_the_provider_answering(self, teacher_user, student_user, gw):
        [new_refund(teacher_user, student_user) for _ in range(5)]
        script = iter(['transient', 'transient', 'rejected', 'transient', 'transient'])
        gw.behavior = lambda order: RefundResult('transient') if next(script) == 'transient' else RefundResult('rejected')
        out = refunds.process_pending_refunds()
        assert out['skipped_breaker'] == 0 and out['sent'] == 5

    def test_a_manual_result_neither_trips_nor_resets_the_breaker(self, teacher_user, student_user, gw):
        [new_refund(teacher_user, student_user) for _ in range(5)]
        script = iter(['transient', 'manual', 'transient', 'transient'])
        gw.behavior = lambda order: RefundResult(next(script))
        out = refunds.process_pending_refunds()
        # transient, (manual: neutral), transient, transient = three in a row: the fifth refund is left alone
        assert out['skipped_breaker'] == 1 and out['sent'] == 4 and out['manual'] == 1

    def test_a_provider_level_result_is_never_a_per_row_failure_and_counts_toward_the_breaker(self, teacher_user, student_user, gw):
        rows = [new_refund(teacher_user, student_user) for _ in range(4)]
        gw.behavior = lambda order: RefundResult('rejected', provider_level=True, http_status=403, code='NOT_AUTHORIZED')
        out = refunds.process_pending_refunds()
        assert out == result_dict(sent=3, transient=3, skipped_breaker=1)
        assert all(fresh(r).status == RS.PENDING_GATEWAY for r in rows)

    def test_a_gateway_that_does_not_return_a_refund_result_is_transient_and_gets_no_shim(self, teacher_user, student_user, gw, caplog):
        gw.behavior = lambda order: f'FAKE-{order.refund_id}'                  # the old "returns a reference string" contract
        r = new_refund(teacher_user, student_user)
        with caplog.at_level(logging.DEBUG):
            assert refunds.process_pending_refunds() == result_dict(sent=1, transient=1)
        assert fresh(r).status == RS.PENDING_GATEWAY and journals(r) == 0
        assert RefundAttempt.objects.get().result_state == 'transient' and 'TypeError' in caplog.text

    def test_the_alert_resolves_on_the_next_success_and_fires_again_on_a_new_trip(self, teacher_user, student_user, gw, clock):
        self._setup(teacher_user, student_user, gw, n_payfast=0)
        refunds.process_pending_refunds()
        assert alerts('refund_provider_outage', 'paypal').filter(resolved=False).count() == 1
        gw.behavior = lambda order: RefundResult('completed', reference='OK')
        clock.advance(20 * MIN)
        refunds.process_pending_refunds()
        assert alerts('refund_provider_outage', 'paypal').filter(resolved=False).count() == 0
        assert alerts('refund_provider_outage', 'paypal').filter(resolved=True).count() == 1
        for _ in range(3):
            new_refund(teacher_user, student_user)
        gw.behavior = lambda order: RefundResult('transient')
        clock.advance(HOUR)
        refunds.process_pending_refunds()
        assert alerts('refund_provider_outage', 'paypal').count() == 2

    def test_the_alert_is_raised_once_per_trip_not_once_per_row(self, teacher_user, student_user, gw, clock):
        self._setup(teacher_user, student_user, gw, n_payfast=0)
        refunds.process_pending_refunds()
        clock.advance(20 * MIN)
        refunds.process_pending_refunds()
        assert alerts('refund_provider_outage', 'paypal').count() == 1

    def test_the_breaker_is_per_sweep(self, teacher_user, student_user, gw, clock):
        paypal, _ = self._setup(teacher_user, student_user, gw, n_payfast=0)
        refunds.process_pending_refunds()
        gw.behavior = lambda order: RefundResult('completed', reference='OK')
        clock.advance(20 * MIN)
        out = refunds.process_pending_refunds()
        assert out['skipped_breaker'] == 0 and out['completed'] >= 1

    def test_polls_of_a_tripped_gateway_are_skipped_too(self, teacher_user, student_user, gw, clock):
        [new_refund(teacher_user, student_user) for _ in range(2)]
        gw.behavior = lambda order: RefundResult('submitted', reference=f'S-{order.refund_id[:6]}')
        refunds.process_pending_refunds()
        [new_refund(teacher_user, student_user) for _ in range(3)]
        gw.behavior = lambda order: RefundResult('transient')
        gw.lookup_behavior = lambda order: RefundResult('transient')
        clock.advance(2 * HOUR)
        # two older submitted refunds are polled first (transient, transient), then the first new send makes three in a row:
        # the gateway is stopped, so the other two new refunds are left untouched
        assert refunds.process_pending_refunds() == result_dict(sent=1, polled=2, transient=3, skipped_breaker=2)


# ================================================================================================ guards
class TestGuards:
    def _guard_failed(self, refund, gw, *, fragment=None):
        out = refunds.process_pending_refunds()
        r = fresh(refund)
        assert r.status == RS.FAILED and r.failure_kind == 'guard', (r.status, r.failure_kind, r.failure_detail)
        assert gw.calls == [] and r.attempts == 0 and r.claim_token == '' and RefundAttempt.objects.count() == 0
        assert alerts('refund_failed_guard', r.pk).count() == 1 and journals(r) == 0
        assert out['sent'] == 0
        if fragment:
            assert fragment in r.failure_detail
        return r

    @pytest.mark.parametrize('status', [PaymentTransaction.Status.REFUNDED, PaymentTransaction.Status.FAILED,
                                        PaymentTransaction.Status.INITIALIZED, PaymentTransaction.Status.UNALLOCATED,
                                        PaymentTransaction.Status.PENDING_CAPTURE])
    def test_the_payment_must_be_a_success(self, teacher_user, student_user, gw, status):
        r = new_refund(teacher_user, student_user)
        PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(status=status)
        self._guard_failed(r, gw, fragment=status)

    @pytest.mark.parametrize('ref', ['INIT-abc123', 'init-abc123', 'abcd', 'a b c d e', 'abc/def', 'x' * 65, 'cap;rm', 'café-123'])
    def test_the_capture_reference_must_be_real(self, teacher_user, student_user, gw, ref):
        r = new_refund(teacher_user, student_user)
        PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(gateway_reference=ref)
        self._guard_failed(r, gw)

    @pytest.mark.parametrize('ref', ['A' * 5, 'a-b_c9', 'X' * 64, '5LP12345AB6789012'])
    def test_valid_capture_references_pass(self, teacher_user, student_user, gw, ref):
        r = new_refund(teacher_user, student_user)
        PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(gateway_reference=ref)
        assert refunds.process_pending_refunds()['sent'] == 1 and gw.calls[0].capture_ref == ref

    def test_the_refund_currency_must_equal_the_payment_currency(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        set_row(r, currency='EUR')
        self._guard_failed(r, gw, fragment='currency')

    def test_the_payment_currency_must_equal_the_refund_currency(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(currency='EUR')
        self._guard_failed(r, gw, fragment='currency')

    def test_the_funding_currency_must_match_too(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        with connection.cursor() as cur:
            cur.execute("UPDATE payments_bookingfunding SET currency = 'EUR' WHERE booking_id = %s", [str(r.booking_id).replace('-', '')])
        self._guard_failed(r, gw, fragment='currency')

    def test_a_missing_funding_record_is_a_guard_failure(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        with connection.cursor() as cur:
            cur.execute("DELETE FROM payments_bookingfunding WHERE booking_id = %s", [str(r.booking_id).replace('-', '')])
        self._guard_failed(r, gw, fragment='funding')

    def test_jpy_must_be_whole_yen_and_is_never_rounded(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user, amount='1350', currency='JPY')
        set_row(r, amount=Decimal('1350.50'))
        self._guard_failed(r, gw, fragment='minor unit')

    def test_a_whole_yen_refund_passes(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user, amount='1350', currency='JPY')
        assert refunds.process_pending_refunds()['sent'] == 1
        assert gw.calls[0].amount == Decimal('1350') and gw.calls[0].currency == 'JPY'

    @pytest.mark.parametrize('amount', [Decimal('0.00'), Decimal('-1.00')])
    def test_the_amount_must_be_positive(self, teacher_user, student_user, gw, amount):
        r = new_refund(teacher_user, student_user)
        set_row(r, amount=amount)
        self._guard_failed(r, gw, fragment='amount')

    def test_an_unsupported_currency_fails_the_guard_instead_of_crashing(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(currency='XYZ')
        set_row(r, currency='XYZ')
        with connection.cursor() as cur:
            cur.execute("UPDATE payments_bookingfunding SET currency = 'XYZ' WHERE booking_id = %s", [str(r.booking_id).replace('-', '')])
        self._guard_failed(r, gw)

    def test_an_unresolved_external_refund_anomaly_blocks_the_send(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        GatewayAnomaly.objects.create(gateway='paypal', reference='EXT-1', reason='external_refund', payment_transaction=r.payment_transaction)
        self._guard_failed(r, gw, fragment='external')

    def test_a_resolved_or_unrelated_anomaly_does_not_block(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        other = new_refund(teacher_user, student_user)
        GatewayAnomaly.objects.create(gateway='paypal', reference='EXT-1', reason='external_refund', payment_transaction=r.payment_transaction, resolved=True)
        GatewayAnomaly.objects.create(gateway='paypal', reference='EXT-2', reason='external_refund', payment_transaction=other.payment_transaction)
        GatewayAnomaly.objects.create(gateway='paypal', reference='X-3', reason='unknown_reference', payment_transaction=r.payment_transaction)
        refunds.process_pending_refunds()
        assert fresh(r).status == RS.PROCESSED and fresh(other).status == RS.FAILED

    def _sibling(self, refund, *, status, attempts=0, amount=None, reason=RefundRequest.Reason.OUTAGE):
        return RefundRequest.objects.create(
            booking=refund.booking, payment_transaction=refund.payment_transaction, user=refund.user,
            amount=amount or refund.amount, currency=refund.currency, reason=reason, status=status, attempts=attempts,
            gateway_reference='SIB-1' if status in (RS.SUBMITTED, RS.PROCESSED) else '',
            next_attempt_at=timezone.now() + 30 * DAY)                          # not due: only the refund under test is swept

    @pytest.mark.parametrize('status,attempts,blocks', [
        (RS.PROCESSED, 1, True), (RS.SUBMITTED, 1, True), (RS.PENDING_GATEWAY, 1, True), (RS.FAILED, 2, True),
        (RS.PENDING_GATEWAY, 0, False), (RS.FAILED, 0, False), (RS.CONVERTED, 0, False), (RS.VOID, 0, False),
        (RS.AWAITING_CLEARANCE, 0, False),
    ])
    def test_the_cumulative_cap_counts_only_money_that_may_have_moved(self, teacher_user, student_user, gw, status, attempts, blocks):
        r = new_refund(teacher_user, student_user)
        set_row(r, created_at=timezone.now() - DAY)                                 # the sibling is newer, so r is claimed first
        self._sibling(r, status=status, attempts=attempts)
        if status == RS.PROCESSED:
            PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(status=PaymentTransaction.Status.SUCCESS)
        if blocks:
            self._guard_failed(r, gw, fragment='exceed')
        else:
            refunds.process_pending_refunds()
            assert fresh(r).status == RS.PROCESSED and len(gw.calls) == 1

    def test_the_cap_allows_a_total_exactly_equal_to_the_payment(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(amount=Decimal('18.00'))
        self._sibling(r, status=RS.SUBMITTED, attempts=1, amount=Decimal('9.00'))
        assert refunds.process_pending_refunds()['sent'] == 1 and fresh(r).status == RS.PROCESSED

    def test_the_cap_stops_a_total_one_cent_over(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(amount=Decimal('17.99'))
        self._sibling(r, status=RS.SUBMITTED, attempts=1, amount=Decimal('9.00'))
        self._guard_failed(r, gw, fragment='exceed')

    def test_a_refund_larger_than_the_payment_is_refused(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(amount=Decimal('8.99'))
        self._guard_failed(r, gw, fragment='exceed')

    def test_two_pending_siblings_cannot_both_be_sent(self, teacher_user, student_user, gw):
        r = new_refund(teacher_user, student_user)
        PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(amount=Decimal('9.00'))
        set_row(r, created_at=timezone.now() - DAY)
        other = set_row(self._sibling(r, status=RS.PENDING_GATEWAY, attempts=0), next_attempt_at=None)       # due too
        gw.behavior = lambda order: RefundResult('submitted', reference=f'S-{order.refund_id}')
        refunds.process_pending_refunds()
        assert fresh(r).status == RS.SUBMITTED
        assert fresh(other).status == RS.FAILED and fresh(other).failure_kind == 'guard' and len(gw.calls) == 1

    def test_a_guard_failure_does_not_stop_the_other_rows(self, teacher_user, student_user, gw):
        bad = new_refund(teacher_user, student_user)
        good = new_refund(teacher_user, student_user)
        PaymentTransaction.objects.filter(pk=bad.payment_transaction_id).update(status=PaymentTransaction.Status.FAILED)
        refunds.process_pending_refunds()
        assert fresh(bad).status == RS.FAILED and fresh(good).status == RS.PROCESSED

    def test_a_row_that_is_not_due_is_not_guarded(self, teacher_user, student_user, gw, clock):
        r = new_refund(teacher_user, student_user)
        PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(status=PaymentTransaction.Status.FAILED)
        set_row(r, next_attempt_at=clock.now + HOUR)
        refunds.process_pending_refunds()
        assert fresh(r).status == RS.PENDING_GATEWAY                                  # guards run when it is due, not before

    def test_a_poll_of_a_submitted_row_does_not_run_the_send_guards(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: RefundResult('submitted', reference='RF-S')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        GatewayAnomaly.objects.create(gateway='paypal', reference='EXT-1', reason='external_refund', payment_transaction=r.payment_transaction)
        clock.advance(2 * HOUR)
        out = refunds.process_pending_refunds()
        assert out['polled'] == 1 and fresh(r).status == RS.PROCESSED

    def test_awaiting_clearance_is_never_claimed(self, teacher_user, student_user, gw, clock):
        r = new_refund(teacher_user, student_user)
        set_row(r, status=RS.AWAITING_CLEARANCE)
        assert refunds.process_pending_refunds() == result_dict()
        assert claim_one() is None and gw.calls == [] and fresh(r).attempts == 0

    def test_void_converted_processed_and_failed_rows_are_never_claimed(self, teacher_user, student_user, gw):
        for status in (RS.VOID, RS.CONVERTED, RS.PROCESSED, RS.FAILED):
            r = new_refund(teacher_user, student_user)
            set_row(r, status=status)
        assert refunds.process_pending_refunds() == result_dict() and gw.calls == []

    def test_a_pending_payment_refund_is_deferred_and_never_sent(self, teacher_user, student_user, gw):
        b = captured(teacher_user, student_user, 1500, gateway='paypal', amount='9.00', currency='USD', ref='CAP-GRACE')
        with connection.cursor() as cur:
            cur.execute("UPDATE payments_bookingfunding SET source_type = 'gateway_pending' WHERE booking_id = %s", [str(b.pk).replace('-', '')])
        out = refunds.request_refund(b, RefundRequest.Reason.STUDENT_CANCEL)
        assert out.refund.status == RS.AWAITING_CLEARANCE
        assert refunds.process_pending_refunds() == result_dict() and gw.calls == []

    def test_a_platform_absorbed_booking_has_nothing_to_refund(self, teacher_user, student_user, gw):
        b = captured(teacher_user, student_user, 1600, gateway='paypal', amount='9.00', currency='USD', ref='CAP-ABS')
        with connection.cursor() as cur:
            cur.execute("UPDATE payments_bookingfunding SET source_type = 'platform_absorbed' WHERE booking_id = %s", [str(b.pk).replace('-', '')])
        out = refunds.request_refund(b, RefundRequest.Reason.STUDENT_CANCEL)
        assert out.refund is None and refunds.process_pending_refunds() == result_dict() and gw.calls == []


# ================================================================================================ mark_failed / mark_processed / mark_paid_manually
class TestStateTransitions:
    def test_mark_failed_from_pending_and_submitted(self, teacher_user, student_user):
        a = new_refund(teacher_user, student_user)
        refunds.mark_failed(a.pk, 'bad', kind='guard')
        assert fresh(a).status == RS.FAILED and fresh(a).failure_kind == 'guard' and alerts('refund_failed_guard', a.pk).count() == 1
        b = new_refund(teacher_user, student_user)
        set_row(b, status=RS.SUBMITTED)
        refunds.mark_failed(b.pk, 'bad', kind='provider_failed')
        assert fresh(b).status == RS.FAILED

    @pytest.mark.parametrize('status', [RS.PROCESSED, RS.CONVERTED, RS.FAILED, RS.VOID, RS.AWAITING_CLEARANCE])
    def test_mark_failed_refuses_every_other_state(self, teacher_user, student_user, status):
        r = new_refund(teacher_user, student_user)
        set_row(r, status=status)
        with pytest.raises(refunds.RefundStateError):
            refunds.mark_failed(r.pk, 'x', kind='guard')

    def test_mark_failed_with_a_token_fences_a_stale_worker(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        claim = claim_one()
        with pytest.raises(refunds.RefundStateError):
            refunds.mark_failed(r.pk, 'x', kind='rejected', token='nope')
        refunds.mark_failed(r.pk, 'x', kind='rejected', token=claim.token)
        assert fresh(r).status == RS.FAILED and fresh(r).claim_token == ''

    def test_mark_processed_accepts_pending_submitted_and_failed(self, teacher_user, student_user):
        for status in (RS.PENDING_GATEWAY, RS.SUBMITTED, RS.FAILED):
            r = new_refund(teacher_user, student_user)
            set_row(r, status=status)
            refunds.mark_processed(r.pk, f'REF-{status}')
            r = fresh(r)
            assert r.status == RS.PROCESSED and journals(r) == 2

    @pytest.mark.parametrize('status', [RS.CONVERTED, RS.VOID, RS.AWAITING_CLEARANCE])
    def test_mark_processed_refuses_the_rest(self, teacher_user, student_user, status):
        r = new_refund(teacher_user, student_user)
        set_row(r, status=status)
        with pytest.raises(refunds.RefundStateError):
            refunds.mark_processed(r.pk, 'X')

    def test_mark_processed_resolves_the_refund_alerts_and_clears_the_claim(self, teacher_user, student_user, gw):
        gw.behavior = lambda order: RefundResult('rejected', code='X')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        assert alerts('refund_failed_rejected', r.pk).filter(resolved=False).count() == 1
        refunds.mark_processed(r.pk, 'HUMAN-1')
        assert alerts('refund_failed_rejected', r.pk).filter(resolved=False).count() == 0
        r = fresh(r)
        assert r.failure_kind == '' and r.failure_detail == '' and r.claim_token == '' and r.next_attempt_at is None

    def test_mark_processed_is_idempotent(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        refunds.mark_processed(r.pk, 'A')
        refunds.mark_processed(r.pk, 'B')
        assert fresh(r).gateway_reference == 'A' and journals(r) == 2

    def test_mark_paid_manually_writes_an_audit_row_with_the_actor(self, teacher_user, student_user, admin_user):
        r = new_refund(teacher_user, student_user)
        out = refunds.mark_paid_manually(r.pk, actor=admin_user, reference='MANUAL-7')
        assert out.status == RS.PROCESSED and out.gateway_reference == 'MANUAL-7' and journals(r) == 2
        row = RefundAttempt.objects.get()
        assert (row.kind, row.actor_id, row.result_state) == ('admin_mark_paid', admin_user.pk, 'completed')
        refunds.mark_paid_manually(r.pk, actor=admin_user, reference='MANUAL-8')               # repeat: nothing new
        assert RefundAttempt.objects.count() == 1 and journals(r) == 2 and fresh(r).gateway_reference == 'MANUAL-7'

    def test_mark_paid_manually_works_from_failed_and_rejects_the_rest(self, teacher_user, student_user, admin_user):
        a = new_refund(teacher_user, student_user)
        set_row(a, status=RS.FAILED, failure_kind='rejected')
        assert refunds.mark_paid_manually(a.pk, actor=admin_user, reference='M-1').status == RS.PROCESSED
        for status in (RS.CONVERTED, RS.VOID, RS.AWAITING_CLEARANCE, RS.SUBMITTED):
            r = new_refund(teacher_user, student_user)
            set_row(r, status=status)
            with pytest.raises(refunds.RefundStateError):
                refunds.mark_paid_manually(r.pk, actor=admin_user, reference='M-2')

    def test_mark_paid_manually_needs_a_reference(self, teacher_user, student_user, admin_user):
        r = new_refund(teacher_user, student_user)
        with pytest.raises(ValueError):
            refunds.mark_paid_manually(r.pk, actor=admin_user, reference='  ')

    def test_the_django_admin_action_goes_through_the_service_and_keeps_its_label(self, teacher_user, student_user, admin_user, rf):
        from django.contrib.admin.sites import AdminSite
        from apps.payments.admin import RefundRequestAdmin
        ma = RefundRequestAdmin(RefundRequest, AdminSite())
        messages = []
        ma.message_user = lambda request, msg, *a, **k: messages.append(msg)
        a, b = new_refund(teacher_user, student_user), new_refund(teacher_user, student_user)
        set_row(b, status=RS.SUBMITTED)
        request = rf.post('/')
        request.user = admin_user
        ma.mark_paid_in_gateway(request, RefundRequest.objects.filter(pk__in=[a.pk, b.pk]))
        assert fresh(a).status == RS.PROCESSED and fresh(a).gateway_reference == f'MANUAL-{a.pk}' and fresh(b).status == RS.SUBMITTED
        row = RefundAttempt.objects.get()
        assert row.kind == 'admin_mark_paid' and row.actor_id == admin_user.pk and row.refund_id == a.pk
        assert messages == ['1 refund(s) marked as paid.']
        assert ma.mark_paid_in_gateway.short_description == 'Mark as paid in the gateway (posts the cash movement)'


# ================================================================================================ retry_failed
class TestRetryFailed:
    def _failed(self, teacher_user, student_user, kind, *, epoch=0, request_id=''):
        r = new_refund(teacher_user, student_user)
        return set_row(r, status=RS.FAILED, failure_kind=kind, failure_detail='boom', request_epoch=epoch,
                       gateway_request_id=request_id, attempts=2, last_attempt_at=timezone.now() - DAY,
                       first_attempt_at=timezone.now() - DAY)

    def test_a_rejected_retry_bumps_the_epoch_and_uses_a_new_request_id(self, teacher_user, student_user, admin_user, gw):
        r = self._failed(teacher_user, student_user, 'rejected', request_id='placeholder')
        r = set_row(r, gateway_request_id=f'refund-{r.pk}')
        refunds.retry_failed(r.pk, actor=admin_user)
        r = fresh(r)
        assert r.status == RS.PENDING_GATEWAY and r.request_epoch == 1 and r.gateway_request_id == '' and r.failure_kind == ''
        assert r.next_attempt_at is None and r.claim_token == ''
        refunds.process_pending_refunds()
        assert gw.calls[0].request_id == f'refund-{r.pk}-r1' and fresh(r).gateway_request_id == f'refund-{r.pk}-r1'

    def test_a_second_rejected_retry_bumps_again(self, teacher_user, student_user, admin_user, gw):
        r = self._failed(teacher_user, student_user, 'rejected', epoch=1)
        refunds.retry_failed(r.pk, actor=admin_user)
        refunds.process_pending_refunds()
        assert gw.calls[0].request_id == f'refund-{r.pk}-r2'

    def test_a_provider_failed_retry_also_gets_a_new_request_id_and_forgets_the_old_provider_refund(self, teacher_user, student_user, admin_user):
        r = self._failed(teacher_user, student_user, 'provider_failed')
        set_row(r, gateway_reference='OLD-RF')
        refunds.retry_failed(r.pk, actor=admin_user)
        r = fresh(r)
        assert r.request_epoch == 1 and r.gateway_reference == ''

    def test_a_guard_retry_keeps_the_request_id(self, teacher_user, student_user, admin_user):
        r = self._failed(teacher_user, student_user, 'guard', request_id='refund-keep')
        refunds.retry_failed(r.pk, actor=admin_user)
        r = fresh(r)
        assert r.request_epoch == 0 and r.gateway_request_id == 'refund-keep' and r.status == RS.PENDING_GATEWAY

    @pytest.mark.parametrize('kind', ['exhausted', 'replay_window', 'already_refunded'])
    def test_ambiguous_failures_need_the_confirmation(self, teacher_user, student_user, admin_user, kind):
        r = self._failed(teacher_user, student_user, kind, request_id='refund-keep')
        with pytest.raises(refunds.RefundConfirmationRequired):
            refunds.retry_failed(r.pk, actor=admin_user)
        with pytest.raises(refunds.RefundConfirmationRequired):
            refunds.retry_failed(r.pk, actor=admin_user, confirm_not_refunded=False)
        assert fresh(r).status == RS.FAILED and RefundAttempt.objects.count() == 0
        refunds.retry_failed(r.pk, actor=admin_user, confirm_not_refunded=True)
        r = fresh(r)
        assert r.status == RS.PENDING_GATEWAY and r.request_epoch == 0 and r.gateway_request_id == 'refund-keep'

    def test_confirmation_is_not_needed_for_certain_failures(self, teacher_user, student_user, admin_user):
        for kind in ('guard', 'rejected', 'provider_failed'):
            r = self._failed(teacher_user, student_user, kind)
            refunds.retry_failed(r.pk, actor=admin_user, confirm_not_refunded=False)
            assert fresh(r).status == RS.PENDING_GATEWAY

    def test_a_replay_window_retry_restarts_the_clock_so_it_is_not_refused_again(self, teacher_user, student_user, admin_user, gw, clock):
        r = self._failed(teacher_user, student_user, 'replay_window', request_id='refund-keep')
        set_row(r, first_attempt_at=clock.now - 40 * DAY, last_attempt_at=clock.now - 40 * DAY)
        refunds.retry_failed(r.pk, actor=admin_user, confirm_not_refunded=True)
        refunds.process_pending_refunds()
        assert fresh(r).status == RS.PROCESSED and gw.calls[0].request_id == 'refund-keep'

    def test_a_retry_keeps_the_in_progress_marks_so_the_student_cannot_convert(self, teacher_user, student_user, admin_user):
        r = self._failed(teacher_user, student_user, 'rejected')
        refunds.retry_failed(r.pk, actor=admin_user)
        with pytest.raises(refunds.RefundInProgress):
            refunds.convert_to_wallet(r.pk)

    def test_the_guards_are_rerun_and_a_failing_one_keeps_it_failed(self, teacher_user, student_user, admin_user):
        r = self._failed(teacher_user, student_user, 'guard')
        PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(status=PaymentTransaction.Status.FAILED)
        with pytest.raises(refunds.RefundGuardFailed) as exc:
            refunds.retry_failed(r.pk, actor=admin_user)
        assert 'failed' in str(exc.value) and isinstance(exc.value, refunds.RefundStateError)
        assert fresh(r).status == RS.FAILED

    @pytest.mark.parametrize('status', [RS.PENDING_GATEWAY, RS.SUBMITTED, RS.PROCESSED, RS.CONVERTED, RS.VOID, RS.AWAITING_CLEARANCE])
    def test_only_a_failed_refund_can_be_retried(self, teacher_user, student_user, admin_user, status):
        r = new_refund(teacher_user, student_user)
        set_row(r, status=status)
        with pytest.raises(refunds.RefundStateError) as exc:
            refunds.retry_failed(r.pk, actor=admin_user, confirm_not_refunded=True)          # the confirmation cannot mask the state check
        assert not isinstance(exc.value, refunds.RefundConfirmationRequired)
        assert fresh(r).status == status and RefundAttempt.objects.count() == 0

    def test_a_failure_with_no_recorded_kind_needs_the_confirmation(self, teacher_user, student_user, admin_user):
        r = self._failed(teacher_user, student_user, '')               # a refund that failed before failure kinds existed
        with pytest.raises(refunds.RefundConfirmationRequired):
            refunds.retry_failed(r.pk, actor=admin_user)
        refunds.retry_failed(r.pk, actor=admin_user, confirm_not_refunded=True)
        assert fresh(r).status == RS.PENDING_GATEWAY

    def test_a_retry_makes_the_refund_due_again_immediately(self, teacher_user, student_user, admin_user, clock):
        r = self._failed(teacher_user, student_user, 'guard')
        set_row(r, next_attempt_at=clock.now + 30 * DAY)
        refunds.retry_failed(r.pk, actor=admin_user)
        assert fresh(r).next_attempt_at is None
        assert claim_one() is not None

    def test_a_certain_failure_retry_starts_a_fresh_round_and_a_fresh_staleness_clock(self, teacher_user, student_user, admin_user, gw, clock):
        gw.behavior = lambda order: RefundResult('submitted', reference='RF-1')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        gw.lookup_behavior = lambda order: RefundResult('rejected', code='CANCELLED')
        clock.advance(2 * HOUR)
        refunds.process_pending_refunds()
        failed = fresh(r)
        assert failed.status == RS.FAILED and failed.submitted_at is not None and failed.attempts == 1
        clock.advance(20 * DAY)
        refunds.retry_failed(r.pk, actor=admin_user)
        row = fresh(r)
        assert (row.attempts, row.first_attempt_at, row.submitted_at) == (0, None, None)
        gw.behavior = lambda order: RefundResult('submitted', reference='RF-2')
        gw.lookup_behavior = lambda order: RefundResult('submitted', reference='RF-2')
        refunds.process_pending_refunds()
        assert fresh(r).submitted_at == clock.now and alerts('refund_submitted_stale').count() == 0
        clock.advance(2 * HOUR)
        refunds.process_pending_refunds()
        assert alerts('refund_submitted_stale').count() == 0                # two hours after the NEW submission, not 20 days

    def test_a_retry_is_audited_and_resolves_the_alert(self, teacher_user, student_user, admin_user, gw):
        gw.behavior = lambda order: RefundResult('rejected', code='INSTRUMENT_DECLINED')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        assert alerts('refund_failed_rejected', r.pk).filter(resolved=False).count() == 1
        refunds.retry_failed(r.pk, actor=admin_user)
        assert alerts('refund_failed_rejected', r.pk).filter(resolved=False).count() == 0
        row = RefundAttempt.objects.order_by('seq').last()
        assert (row.kind, row.actor_id, row.seq) == ('admin_retry', admin_user.pk, 2)
        assert row.request_id == f'refund-{r.pk}-r1'

    def test_the_retried_refund_completes_through_the_sweeper(self, teacher_user, student_user, admin_user, gw):
        gw.behavior = lambda order: RefundResult('rejected', code='X')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        gw.behavior = lambda order: RefundResult('completed', reference='RF-OK')
        refunds.retry_failed(r.pk, actor=admin_user)
        refunds.process_pending_refunds()
        assert fresh(r).status == RS.PROCESSED and journals(r) == 2

    def test_a_failed_refund_finished_by_the_webhook_with_the_matching_amount(self, teacher_user, student_user, gw):
        gw.behavior = lambda order: RefundResult('rejected', code='X')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        assert paypal_events.apply_refund(r.payment_transaction_id, 'DASH-1', Decimal('9.00'), 'USD', {}) == 'refund_completed'
        assert fresh(r).status == RS.PROCESSED


# ================================================================================================ webhook edge: refund after convert
class TestRefundAfterConvert:
    @pytest.mark.parametrize('status', [RS.CONVERTED, RS.VOID])
    def test_a_refund_for_a_converted_or_void_request_is_a_critical_anomaly(self, teacher_user, student_user, status):
        r = new_refund(teacher_user, student_user)
        set_row(r, status=status)
        out = paypal_events.apply_refund(r.payment_transaction_id, 'LATE-1', Decimal('9.00'), 'USD', {'event_type': 'x'})
        assert out in ('refund_after_convert', 'external_refund')
        a = alerts('refund_after_convert', r.pk)
        assert a.count() == 1 and 'LATE-1' in a.first().detail
        assert LedgerEntry.objects.filter(event_type=EV.GATEWAY_REFUND_PAID).count() == 0

    def test_the_critical_alert_is_a_distinct_code_once_per_request(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        set_row(r, status=RS.CONVERTED)
        paypal_events.apply_refund(r.payment_transaction_id, 'LATE-1', Decimal('9.00'), 'USD', {})
        paypal_events.apply_refund(r.payment_transaction_id, 'LATE-2', Decimal('9.00'), 'USD', {})
        assert alerts('refund_after_convert', r.pk).count() == 1

    def test_the_state_error_is_caught_and_filed_as_the_anomaly(self, teacher_user, student_user, monkeypatch):
        r = new_refund(teacher_user, student_user)

        def boom(refund_id, ref):
            set_row(r, status=RS.CONVERTED)
            raise refunds.RefundStateError('converted')
        monkeypatch.setattr(refunds, 'mark_processed', boom)
        out = paypal_events.apply_refund(r.payment_transaction_id, 'LATE-9', Decimal('9.00'), 'USD', {})
        assert out == 'refund_after_convert' and alerts('refund_after_convert', r.pk).count() == 1

    def test_a_state_error_for_any_other_status_is_not_swallowed(self, teacher_user, student_user, monkeypatch):
        r = new_refund(teacher_user, student_user)

        def boom(refund_id, ref):
            raise refunds.RefundStateError('weird')
        monkeypatch.setattr(refunds, 'mark_processed', boom)
        with pytest.raises(refunds.RefundStateError):
            paypal_events.apply_refund(r.payment_transaction_id, 'LATE-9', Decimal('9.00'), 'USD', {})

    def test_a_pending_refund_is_matched_before_any_anomaly(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        assert paypal_events.apply_refund(r.payment_transaction_id, 'DASH', Decimal('9.00'), 'USD', {}) == 'refund_completed'
        assert alerts('refund_after_convert').count() == 0


# ================================================================================================ audit rows
class TestAttemptRows:
    @pytest.mark.parametrize('result,outcome', [
        (RefundResult('completed', reference='R'), 'processed'), (RefundResult('submitted', reference='R'), 'submitted'),
        (RefundResult('transient'), 'retry'), (RefundResult('rejected', code='X'), 'failed'), (RefundResult('manual'), 'manual'),
    ])
    def test_exactly_one_row_per_apply(self, teacher_user, student_user, result, outcome):
        r = new_refund(teacher_user, student_user)
        claim = claim_one()
        assert refunds.apply_result(r.pk, claim.token, result, kind='send') == outcome
        assert RefundAttempt.objects.filter(refund=r).count() == 1
        assert RefundAttempt.objects.get().result_state == result.state

    def test_a_noop_writes_nothing_and_seq_increments(self, teacher_user, student_user, clock, gw):
        gw.behavior = lambda order: RefundResult('transient')
        r = new_refund(teacher_user, student_user)
        for expected_seq in (1, 2, 3):
            refunds.process_pending_refunds()
            clock.advance(DAY)
            assert RefundAttempt.objects.filter(refund=r).count() == expected_seq
        assert [a.seq for a in RefundAttempt.objects.order_by('seq')] == [1, 2, 3]


# ================================================================================================ lock order
class TestLockOrder:
    @pytest.fixture
    def locks(self, monkeypatch):
        seen = []
        real = QuerySet.select_for_update

        def spy(self, *a, **k):
            seen.append(self.model.__name__)
            return real(self, *a, **k)
        monkeypatch.setattr(QuerySet, 'select_for_update', spy)
        return seen

    def _tx_first(self, seen):
        first_refund = seen.index('RefundRequest') if 'RefundRequest' in seen else None
        first_tx = seen.index('PaymentTransaction') if 'PaymentTransaction' in seen else None
        assert first_tx is not None and (first_refund is None or first_tx < first_refund), seen

    def test_the_claim_locks_the_payment_before_the_refund(self, teacher_user, student_user, locks):
        new_refund(teacher_user, student_user)
        locks.clear()
        claim_one()
        self._tx_first(locks)

    def test_apply_locks_the_payment_before_the_refund(self, teacher_user, student_user, locks):
        r = new_refund(teacher_user, student_user)
        claim = claim_one()
        locks.clear()
        refunds.apply_result(r.pk, claim.token, RefundResult('completed', reference='R'), kind='send')
        self._tx_first(locks)

    def test_mark_processed_failed_submitted_convert_retry_and_paid_lock_in_the_same_order(self, teacher_user, student_user, admin_user, locks):
        e, a, b, c, d = (new_refund(teacher_user, student_user) for _ in range(5))      # e is the oldest, so it is the one claimed
        locks.clear()
        refunds.mark_processed(a.pk, 'X'); self._tx_first(locks); locks.clear()
        refunds.mark_failed(b.pk, 'x', kind='guard'); self._tx_first(locks); locks.clear()
        refunds.retry_failed(b.pk, actor=admin_user); self._tx_first(locks); locks.clear()
        refunds.convert_to_wallet(c.pk); self._tx_first(locks); locks.clear()
        refunds.mark_paid_manually(d.pk, actor=admin_user, reference='M'); self._tx_first(locks); locks.clear()
        claim = claim_one()
        refunds.mark_submitted(e.pk, 'S', token=claim.token); self._tx_first(locks)

    def test_the_webhook_path_locks_the_payment_first(self, teacher_user, student_user, locks):
        r = new_refund(teacher_user, student_user)
        locks.clear()
        paypal_events.apply_refund(r.payment_transaction_id, 'DASH', Decimal('9.00'), 'USD', {})
        self._tx_first(locks)


# ================================================================================================ the three rewritten legacy contracts
class TestRewrittenLegacyContracts:
    def test_the_default_gateway_leaves_requests_pending_and_a_real_one_settles_them(self, teacher_user, student_user, settings):
        settings.REFUND_GATEWAY_BACKEND = 'apps.payments.services.refunds.ManualSandboxRefundGateway'
        r = new_refund(teacher_user, student_user)
        assert refunds.process_pending_refunds() == result_dict(sent=1, manual=1)
        assert fresh(r).status == RS.PENDING_GATEWAY
        settings.REFUND_GATEWAY_BACKEND = 'test_refund_processing.ScriptedGateway'
        set_row(r, next_attempt_at=None)
        assert refunds.process_pending_refunds() == result_dict(sent=1, completed=1)
        assert fresh(r).status == RS.PROCESSED


# ================================================================================================ defence in depth
class TestEachClaimLayerStandsOnItsOwn:
    """The python-side checks (under the row lock) and the claim UPDATE both guard the same conditions; each is pinned alone."""

    def _broken(self, refund):
        PaymentTransaction.objects.filter(pk=refund.payment_transaction_id).update(status=PaymentTransaction.Status.FAILED)

    @pytest.mark.parametrize('field', ['next_attempt_at', 'claimed_until'])
    def test_a_row_that_is_not_due_is_neither_guarded_nor_claimed(self, teacher_user, student_user, clock, field):
        r = new_refund(teacher_user, student_user)
        self._broken(r)                                         # a guard WOULD fail if the row were looked at
        set_row(r, **{field: clock.now + HOUR})
        assert refunds._try_claim(r.pk, RS.PENDING_GATEWAY, lambda: clock.now) is None
        r = fresh(r)
        assert r.status == RS.PENDING_GATEWAY and r.attempts == 0 and alerts('refund_failed_guard').count() == 0

    def test_a_row_inside_the_first_attempt_delay_is_neither_guarded_nor_claimed(self, teacher_user, student_user, settings):
        settings.REFUND_FIRST_ATTEMPT_DELAY_MINUTES = 60
        r = new_refund(teacher_user, student_user)
        self._broken(r)
        assert refunds._try_claim(r.pk, RS.PENDING_GATEWAY, lambda: r.created_at + 10 * MIN) is None
        assert fresh(r).status == RS.PENDING_GATEWAY and alerts('refund_failed_guard').count() == 0
        assert refunds._try_claim(r.pk, RS.PENDING_GATEWAY, lambda: r.created_at + 61 * MIN) is None      # due now: guarded, so failed
        assert fresh(r).status == RS.FAILED

    def test_a_status_change_after_the_candidate_list_is_seen_even_if_the_update_would_match(self, teacher_user, student_user, monkeypatch):
        r = new_refund(teacher_user, student_user)
        stale = list(refunds._due_candidates(refunds._now()))
        refunds.convert_to_wallet(r.pk)
        monkeypatch.setattr(refunds, '_cas_claim', lambda *a, **k: True)
        assert refunds._try_claim(*stale[0][:2], refunds._now) is None

    def test_candidates_hide_rows_inside_the_first_attempt_delay(self, teacher_user, student_user, settings):
        settings.REFUND_FIRST_ATTEMPT_DELAY_MINUTES = 60
        r = new_refund(teacher_user, student_user)
        assert refunds._due_candidates(r.created_at + 10 * MIN) == []
        assert [c[0] for c in refunds._due_candidates(r.created_at + 61 * MIN)] == [r.pk]

    def test_candidates_are_oldest_first_and_carry_the_gateway(self, teacher_user, student_user):
        a = new_refund(teacher_user, student_user)
        b = new_refund(teacher_user, student_user, gateway='payfast', amount='168.75', currency='ZAR')
        set_row(a, created_at=timezone.now() - 3 * DAY)
        set_row(b, created_at=timezone.now() - 5 * DAY)
        assert [(c[0], c[2]) for c in refunds._due_candidates(timezone.now())] == [(b.pk, 'payfast'), (a.pk, 'paypal')]

    def test_the_candidates_skip_awaiting_clearance_rows(self, teacher_user, student_user):
        r = new_refund(teacher_user, student_user)
        set_row(r, status=RS.AWAITING_CLEARANCE)
        assert refunds._due_candidates(timezone.now() + DAY) == []

    def test_an_expired_lease_makes_a_submitted_row_pollable_again(self, teacher_user, student_user, clock, gw):
        gw.behavior = lambda order: RefundResult('submitted', reference='RF-S')
        new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        clock.advance(2 * HOUR)
        poll = claim_one()
        assert poll.kind == 'poll' and claim_one() is None            # leased: nobody else gets it
        clock.advance(11 * MIN)
        assert claim_one().kind == 'poll'

    def test_a_row_that_became_submitted_after_the_candidate_list_is_not_sent_even_if_the_update_would_match(self, teacher_user, student_user, monkeypatch):
        r = new_refund(teacher_user, student_user)
        stale = list(refunds._due_candidates(refunds._now()))                      # seen as pending_gateway ...
        set_row(r, status=RS.SUBMITTED, gateway_reference='RF-S', attempts=1)       # ... but a webhook-less poll already moved it on
        monkeypatch.setattr(refunds, '_cas_claim', lambda *a, **k: True)
        assert stale[0][1] == RS.PENDING_GATEWAY
        assert refunds._try_claim(*stale[0][:2], refunds._now) is None

    def test_a_guard_failure_never_reaches_the_claim_update(self, teacher_user, student_user, monkeypatch):
        r = new_refund(teacher_user, student_user)
        PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(status=PaymentTransaction.Status.FAILED)
        calls = []
        monkeypatch.setattr(refunds, '_cas_claim', lambda *a, **k: calls.append(1) or True)
        assert refunds._try_claim(r.pk, RS.PENDING_GATEWAY, refunds._now) is None
        assert calls == [] and fresh(r).status == RS.FAILED

    def test_a_replay_window_failure_never_reaches_the_claim_update(self, teacher_user, student_user, monkeypatch, clock):
        r = new_refund(teacher_user, student_user)
        set_row(r, attempts=1, first_attempt_at=clock.now - 31 * DAY, last_attempt_at=clock.now - 31 * DAY, claimed_until=clock.now - DAY)
        calls = []
        monkeypatch.setattr(refunds, '_cas_claim', lambda *a, **k: calls.append(1) or True)
        assert refunds._try_claim(r.pk, RS.PENDING_GATEWAY, lambda: clock.now) is None
        assert calls == [] and fresh(r).failure_kind == 'replay_window'


# ================================================================================================ boundaries found by mutation checks
class TestBoundaries:
    def test_exactly_at_the_replay_window_it_is_still_replayed(self, teacher_user, student_user, gw, clock):
        r = new_refund(teacher_user, student_user)
        set_row(r, attempts=1, first_attempt_at=clock.now - 30 * DAY, last_attempt_at=clock.now - 30 * DAY, claimed_until=clock.now - DAY)
        assert refunds.process_pending_refunds()['sent'] == 1 and gw.calls

    def test_a_never_attempted_row_is_not_a_replay_whatever_its_stamps_say(self, teacher_user, student_user, gw, clock):
        r = new_refund(teacher_user, student_user)
        set_row(r, attempts=0, first_attempt_at=clock.now - 90 * DAY)
        assert refunds.process_pending_refunds()['sent'] == 1 and fresh(r).status == RS.PROCESSED

    def test_a_row_with_a_known_provider_refund_id_is_replayed_not_refused(self, teacher_user, student_user, gw, clock):
        r = new_refund(teacher_user, student_user)
        set_row(r, attempts=1, first_attempt_at=clock.now - 90 * DAY, last_attempt_at=clock.now - 90 * DAY,
                claimed_until=clock.now - DAY, gateway_reference='RF-KNOWN')
        assert refunds.process_pending_refunds()['sent'] == 1 and gw.calls[0].provider_refund_id == 'RF-KNOWN'

    def test_exactly_at_the_manual_alert_threshold_it_alerts(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: RefundResult('manual')
        r = new_refund(teacher_user, student_user)
        set_row(r, created_at=clock.now - 72 * HOUR)
        refunds.process_pending_refunds()
        assert alerts('refund_manual_waiting', r.pk).count() == 1

    def test_an_external_refund_request_does_not_email_the_student(self, teacher_user, student_user, sent_mail, django_capture_on_commit_callbacks):
        r = new_refund(teacher_user, student_user)
        set_row(r, reason='external_refund')
        with django_capture_on_commit_callbacks(execute=True):
            refunds.mark_processed(r.pk, 'DASH-1')
        assert [m for m in sent_mail if m[0] == student_user.email] == []

    def test_a_failed_refund_that_the_provider_later_reports_complete_is_finished_by_its_reference(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: RefundResult('submitted', reference='RF-S')
        gw.lookup_behavior = lambda order: RefundResult('rejected', code='CANCELLED')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        clock.advance(2 * HOUR)
        refunds.process_pending_refunds()
        assert fresh(r).status == RS.FAILED and fresh(r).gateway_reference == 'RF-S'
        assert paypal_events.apply_refund(r.payment_transaction_id, 'RF-S', Decimal('9.00'), 'USD', {}) == 'refund_completed'
        assert fresh(r).status == RS.PROCESSED and journals(r) == 2

    def test_the_poll_interval_setting_governs_a_poll_that_cannot_tell(self, teacher_user, student_user, gw, clock, settings):
        settings.REFUND_POLL_INTERVAL_MINUTES = 5
        gw.behavior = lambda order: RefundResult('submitted', reference='RF-S')
        gw.lookup_behavior = lambda order: RefundResult('transient')
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        clock.advance(6 * MIN)
        refunds.process_pending_refunds()
        assert fresh(r).next_attempt_at == clock.now + 5 * MIN


# ================================================================================================ QA fixes (2026-10-04)
class TestCaptureSideCashAccountFollowsTheGateway:
    """H1: the capture and the refund must hit the SAME cash account, which follows the gateway and never the currency."""

    @pytest.mark.parametrize('gateway, currency, amount, account', [
        ('paypal', 'ZAR', '168.75', ACC.ASSET_GATEWAY_PAYPAL),
        ('payfast', 'ZAR', '168.75', ACC.ASSET_GATEWAY_PAYFAST),
        ('paypal', 'USD', '9.00', ACC.ASSET_GATEWAY_PAYPAL),
        ('paypal', 'EUR', '8.00', ACC.ASSET_GATEWAY_PAYPAL),
        ('paypal', 'JPY', '1400', ACC.ASSET_GATEWAY_PAYPAL),
    ])
    def test_capture_then_refund_nets_both_cash_accounts_to_zero(self, teacher_user, student_user, gateway, currency, amount, account):
        r = new_refund(teacher_user, student_user, gateway=gateway, amount=amount, currency=currency)
        capture = LedgerEntry.objects.get(booking=r.booking, event_type=EV.PAYMENT_CAPTURED, account=account)
        assert capture.entry_type == LedgerEntry.EntryType.DEBIT and capture.amount == Decimal(amount)
        assert refunds.process_pending_refunds() == result_dict(sent=1, completed=1)
        for cash in (ACC.ASSET_GATEWAY_PAYFAST, ACC.ASSET_GATEWAY_PAYPAL):
            assert net(r.booking, cash) == 0, f'{cash} did not net to zero for {gateway} {currency}'
        other = ACC.ASSET_GATEWAY_PAYFAST if account == ACC.ASSET_GATEWAY_PAYPAL else ACC.ASSET_GATEWAY_PAYPAL
        assert not LedgerEntry.objects.filter(booking=r.booking, account=other).exists()

    def _tx(self, teacher_user, student_user, gateway, currency='ZAR', ref='H1-X'):
        from payment_helpers import lesson
        _START[0] += 90
        return PaymentTransaction.objects.create(booking=lesson(teacher_user, student_user, _START[0]), gateway=gateway, gateway_reference=ref,
                                                 amount=Decimal('168.75'), currency=currency, status='success',
                                                 fx_rate_to_zar=Decimal('1.000000'), fx_source='test')

    @pytest.mark.parametrize('gateway, account', [('paypal', ACC.ASSET_GATEWAY_PAYPAL), ('payfast', ACC.ASSET_GATEWAY_PAYFAST)])
    def test_the_def501_quarantine_and_unallocated_postings_use_the_same_rule(self, teacher_user, student_user, gateway, account):
        from apps.payments.services import ledger_service
        ledger_service.record_def501_quarantine_entry(self._tx(teacher_user, student_user, gateway, ref=f'H1-A-{gateway}'), user=student_user)
        ledger_service.record_unallocated_payment_entry(self._tx(teacher_user, student_user, gateway, ref=f'H1-B-{gateway}'), user=student_user)
        cash = LedgerEntry.objects.filter(account__in=(ACC.ASSET_GATEWAY_PAYFAST, ACC.ASSET_GATEWAY_PAYPAL))
        assert cash.count() == 2 and set(cash.values_list('account', flat=True)) == {account}

    @pytest.mark.parametrize('gateway, account', [('paypal', ACC.ASSET_GATEWAY_PAYPAL), ('payfast', ACC.ASSET_GATEWAY_PAYFAST)])
    def test_a_credit_pack_capture_uses_the_same_rule(self, teacher_user, student_user, gateway, account):
        from types import SimpleNamespace
        from apps.payments.services import ledger_service
        purchase = SimpleNamespace(pack=SimpleNamespace(name='Pack'), user=student_user, fx_rate_to_zar=Decimal('1.000000'), fx_source='test')
        ledger_service.record_credit_purchase_capture_entry(self._tx(teacher_user, student_user, gateway, ref=f'H1-C-{gateway}'), purchase)
        cash = LedgerEntry.objects.filter(account__in=(ACC.ASSET_GATEWAY_PAYFAST, ACC.ASSET_GATEWAY_PAYPAL))
        assert cash.count() == 1 and cash.get().account == account

    def test_one_helper_serves_the_refund_side_too(self):
        from apps.payments.services import ledger_service
        paypal_zar = PaymentTransaction(gateway='paypal', currency='ZAR')
        assert ledger_service.gateway_cash_account(paypal_zar) == ACC.ASSET_GATEWAY_PAYPAL == refunds._gateway_cash_account(paypal_zar)
        payfast_usd = PaymentTransaction(gateway='payfast', currency='USD')
        assert ledger_service.gateway_cash_account(payfast_usd) == ACC.ASSET_GATEWAY_PAYFAST == refunds._gateway_cash_account(payfast_usd)


NOT_FOUND = RefundResult('transient', detail='PayPal does not know this id', code='INVALID_RESOURCE_ID', http_status=404)


class TestCaptureNotFound404:
    """M1: a 404 on the send path is a per-row transient; a person is told about THAT refund after 3 straight 404s."""

    def _sweep_n(self, n, clock):
        for _ in range(n):
            refunds.process_pending_refunds()
            clock.advance(25 * HOUR)

    def test_a_404_burns_the_rows_own_attempt_and_backs_off(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: NOT_FOUND
        r = new_refund(teacher_user, student_user)
        assert refunds.process_pending_refunds() == result_dict(sent=1, transient=1)
        r = fresh(r)
        assert (r.status, r.attempts, r.last_http_status, r.last_error_code) == (RS.PENDING_GATEWAY, 1, 404, 'INVALID_RESOURCE_ID')
        assert r.next_attempt_at == clock.now + 15 * MIN
        assert not alerts('refund_capture_not_found').exists()

    def test_the_alert_comes_after_three_attempts_that_all_ended_in_404(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: NOT_FOUND
        r = new_refund(teacher_user, student_user)
        self._sweep_n(2, clock)
        assert not alerts('refund_capture_not_found').exists()
        self._sweep_n(1, clock)
        found = alerts('refund_capture_not_found', r.pk)
        assert found.count() == 1 and fresh(r).attempts == 3
        self._sweep_n(2, clock)
        assert alerts('refund_capture_not_found', r.pk).count() == 1          # one alert per refund, not one per attempt

    def test_a_different_answer_in_between_means_it_is_not_a_straight_404_run(self, teacher_user, student_user, gw, clock):
        answers = iter([NOT_FOUND, RefundResult('transient', http_status=503), NOT_FOUND])
        gw.behavior = lambda order: next(answers)
        new_refund(teacher_user, student_user)
        self._sweep_n(3, clock)
        assert not alerts('refund_capture_not_found').exists()

    def test_only_the_current_request_ids_attempts_count(self, teacher_user, student_user, gw, clock, admin_user):
        gw.behavior = lambda order: NOT_FOUND
        r = new_refund(teacher_user, student_user)
        self._sweep_n(2, clock)
        refunds.mark_failed(r.pk, 'x', kind='rejected')
        refunds.retry_failed(r.pk, actor=admin_user, confirm_not_refunded=True)      # epoch bump: a new request id, a new round
        self._sweep_n(2, clock)
        assert not alerts('refund_capture_not_found').exists()

    def test_the_alert_is_resolved_when_the_refund_is_finally_paid(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: NOT_FOUND
        r = new_refund(teacher_user, student_user)
        self._sweep_n(3, clock)
        assert alerts('refund_capture_not_found', r.pk).filter(resolved=False).count() == 1
        refunds.mark_processed(r.pk, 'RF-LATE')
        assert not alerts('refund_capture_not_found', r.pk).filter(resolved=False).exists()

    def test_three_404s_from_three_refunds_in_one_sweep_trip_the_gateway_breaker(self, teacher_user, student_user, gw):
        gw.behavior = lambda order: NOT_FOUND
        for _ in range(4):
            new_refund(teacher_user, student_user)
        done = refunds.process_pending_refunds()
        assert done['sent'] == 3 and done['transient'] == 3 and done['skipped_breaker'] == 1
        assert alerts('refund_provider_outage', 'paypal').count() == 1

    def test_a_row_that_only_ever_got_404s_ends_exhausted_never_as_replay_window(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: NOT_FOUND
        r = new_refund(teacher_user, student_user)
        self._sweep_n(14, clock)                                           # a bit over two weeks of daily attempts
        r = fresh(r)
        assert r.status == RS.FAILED and r.failure_kind == FK_EXHAUSTED
        assert r.attempts >= 8 and r.last_http_status == 404
        assert alerts('refund_failed_exhausted', r.pk).count() == 1 and not alerts('refund_failed_replay_window').exists()

    def test_a_provider_level_404_from_the_lookup_still_never_fails_a_submitted_row(self, teacher_user, student_user, gw, clock):
        gw.behavior = lambda order: RefundResult('submitted', reference='RF-S')
        gw.lookup_behavior = lambda order: RefundResult('transient', code='INVALID_RESOURCE_ID', http_status=404, provider_level=True)
        r = new_refund(teacher_user, student_user)
        refunds.process_pending_refunds()
        for _ in range(5):
            clock.advance(2 * HOUR)
            refunds.process_pending_refunds()
        assert fresh(r).status == RS.SUBMITTED


FK_EXHAUSTED = RefundRequest.FailureKind.EXHAUSTED
