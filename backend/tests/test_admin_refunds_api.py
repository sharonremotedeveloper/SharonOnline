"""
Task 10.7 slice R-C: the staff refund API (docs/TASK_10_7_REFUND_GATEWAYS_PLAN.md section 2b, "Security / audit / ops").

    GET  /api/v1/admin/refunds/             list + filters + bucket counts, oldest first
    POST /api/v1/admin/refunds/<id>/retry/  send a failed refund back to the gateway (audited, throttled, 409 unless failed)
"""
import json
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.payments.models import GatewayAnomaly, PaymentTransaction, RefundAttempt, RefundRequest
from apps.payments.services import refunds
from test_refund_processing import fresh, new_refund

RS = RefundRequest.Status
FK = RefundRequest.FailureKind
LIST = '/api/v1/admin/refunds/'
pytestmark = pytest.mark.django_db


def retry_url(refund):
    return f'{LIST}{refund.pk}/retry/'


@pytest.fixture
def admin(admin_user):
    c = APIClient()
    c.force_authenticate(user=admin_user)
    return c


@pytest.fixture
def mk(teacher_user, student_user):
    def make(**kw):
        return new_refund(teacher_user, student_user, **kw)
    return make


def failed(refund, kind=FK.REJECTED, detail='nope'):
    return refunds.mark_failed(refund.pk, detail, kind=kind)


# ------------------------------------------------------------------------------------------------ authorization
class TestAuthorization:
    def test_anonymous_is_401_on_both_endpoints(self, mk):
        r = mk()
        c = APIClient()
        assert c.get(LIST).status_code == 401
        assert c.post(retry_url(r), {}, format='json').status_code == 401

    def test_student_and_teacher_are_403_on_both_endpoints(self, mk, student_user, teacher_user):
        r = failed(mk())
        for user in (student_user, teacher_user.user):
            c = APIClient()
            c.force_authenticate(user=user)
            assert c.get(LIST).status_code == 403
            assert c.post(retry_url(r), {}, format='json').status_code == 403
        assert fresh(r).status == RS.FAILED                      # the forbidden retry changed nothing

    def test_admin_is_allowed(self, mk, admin):
        r = failed(mk())
        assert admin.get(LIST).status_code == 200
        assert admin.post(retry_url(r), {}, format='json').status_code == 200


# ------------------------------------------------------------------------------------------------ list
class TestList:
    def test_oldest_first_and_row_shape(self, mk, admin):
        a, b, c = mk(), mk(), mk()
        RefundRequest.objects.filter(pk=a.pk).update(created_at=timezone.now() - timedelta(hours=50))
        RefundRequest.objects.filter(pk=b.pk).update(created_at=timezone.now() - timedelta(hours=70))
        body = admin.get(LIST).json()
        assert [row['id'] for row in body['results']] == [str(b.pk), str(a.pk), str(c.pk)]
        row = body['results'][0]
        assert set(row) == {'id', 'booking_id', 'student', 'amount', 'currency', 'reason', 'status', 'failure_kind', 'failure_detail',
                            'attempts', 'next_attempt_at', 'last_http_status', 'last_error_code', 'gateway', 'created_at', 'age_hours',
                            'recent_attempts'}
        assert row['student'] == 'test_student' and row['gateway'] == 'paypal'
        assert row['booking_id'] == str(b.booking_id)
        assert 69.9 <= row['age_hours'] <= 70.2

    def test_amounts_are_exact_strings_in_the_row_currency(self, mk, admin):
        mk(amount='9.00', currency='USD')
        mk(amount='1350', currency='JPY')
        rows = {r['currency']: r for r in admin.get(LIST).json()['results']}
        assert rows['USD']['amount'] == '9.00'
        assert rows['JPY']['amount'] == '1350'
        assert all(isinstance(r['amount'], str) for r in rows.values())

    def test_filters(self, mk, admin):
        pending = mk()
        rej = failed(mk(), FK.REJECTED)
        exh = failed(mk(gateway='payfast', amount='168.75', currency='ZAR'), FK.EXHAUSTED)

        def ids(qs):
            return {r['id'] for r in admin.get(LIST + qs).json()['results']}
        assert ids('?status=failed') == {str(rej.pk), str(exh.pk)}
        assert ids('?status=pending_gateway') == {str(pending.pk)}
        assert ids('?failure_kind=exhausted') == {str(exh.pk)}
        assert ids('?gateway=payfast') == {str(exh.pk)}
        assert ids('?gateway=paypal&status=failed') == {str(rej.pk)}
        assert ids('?status=nonsense') == set()

    def test_in_flight_filter_uses_a_live_lease(self, mk, admin):
        live, stale, never = mk(), mk(), mk()
        now = timezone.now()
        RefundRequest.objects.filter(pk=live.pk).update(claimed_until=now + timedelta(minutes=5), claim_token='t' * 32)
        RefundRequest.objects.filter(pk=stale.pk).update(claimed_until=now - timedelta(minutes=5), claim_token='u' * 32)
        body = admin.get(LIST + '?in_flight=true').json()
        assert [r['id'] for r in body['results']] == [str(live.pk)]
        assert body['buckets']['in_flight'] == 1
        assert len(admin.get(LIST + '?in_flight=false').json()['results']) == 2

    def test_waiting_manual_filter(self, mk, admin, settings):
        settings.REFUND_GATEWAY_BACKEND = 'apps.payments.services.refund_gateways.ManualSandboxRefundGateway'
        settings.REFUND_FIRST_ATTEMPT_DELAY_MINUTES = 0
        manual, plain = mk(), mk()
        refunds.process_pending_refunds()                       # the manual backend answers 'manual' for both
        # `plain` is a pending refund whose latest answer was not manual (attempts are append-only: add a later one)
        refunds._write_attempt(plain, 'send', 'transient')
        body = admin.get(LIST + '?waiting_manual=true').json()
        assert {r['id'] for r in body['results']} == {str(manual.pk)}
        assert body['buckets']['waiting_manual'] == 1
        assert admin.get(LIST).json()['buckets']['waiting_manual'] == 1

    def test_waiting_manual_means_pending_only(self, mk, admin):
        r = mk()
        refunds._write_attempt(r, 'send', 'manual')
        refunds.mark_failed(r.pk, 'a person gave up', kind=FK.GUARD)       # latest answer is still 'manual', but it is not pending now
        body = admin.get(LIST + '?waiting_manual=true').json()
        assert body['results'] == [] and body['buckets']['waiting_manual'] == 0

    def test_buckets_count_everything_regardless_of_filters(self, mk, admin):
        mk()
        failed(mk(), FK.REJECTED)
        failed(mk(), FK.REJECTED)
        failed(mk(), FK.GUARD)
        body = admin.get(LIST + '?status=failed&failure_kind=guard').json()
        assert len(body['results']) == 1
        buckets = body['buckets']
        assert buckets['status'] == {'pending_gateway': 1, 'failed': 3}
        assert buckets['failure_kind'] == {'rejected': 2, 'guard': 1}
        assert buckets['in_flight'] == 0 and buckets['waiting_manual'] == 0

    def test_paginated(self, mk, admin, settings):
        for _ in range(3):
            mk()
        body = admin.get(LIST + '?page_size=2').json()
        assert body['count'] == 3 and len(body['results']) == 2 and body['next']
        assert 'buckets' in body

    def test_recent_attempts_are_the_last_five_newest_first_with_actor(self, mk, admin, admin_user):
        r = failed(mk())
        for i in range(7):
            refunds._write_attempt(r, 'send', 'transient', http_status=500 + i, error_code=f'E{i}', request_id='rid')
        refunds._write_attempt(r, 'admin_retry', 'retry', actor=admin_user, request_id='rid')
        attempts = admin.get(LIST).json()['results'][0]['recent_attempts']
        assert len(attempts) == 5
        assert [a['seq'] for a in attempts] == [8, 7, 6, 5, 4]
        assert set(attempts[0]) == {'seq', 'kind', 'result_state', 'http_status', 'error_code', 'created_at', 'actor'}
        assert attempts[0]['actor'] == 'test_admin' and attempts[0]['kind'] == 'admin_retry'
        assert attempts[1]['actor'] is None and attempts[1]['http_status'] == 506

    def test_never_exposes_secrets_or_internals(self, mk, admin):
        r = mk()
        RefundRequest.objects.filter(pk=r.pk).update(claim_token='SECRETTOKEN' + 'x' * 21, gateway_request_id='refund-INTERNAL-REQ',
                                                     gateway_reference='PROVIDER-REF-1')
        refunds._write_attempt(r, 'send', 'transient', request_id='refund-INTERNAL-REQ')
        text = json.dumps(admin.get(LIST).json())
        for forbidden in ('SECRETTOKEN', 'claim_token', 'gateway_request_id', 'refund-INTERNAL-REQ', 'request_id'):
            assert forbidden not in text

    def test_failure_detail_is_stripped_and_truncated(self, mk, admin):
        failed(mk(), FK.REJECTED, detail='   ' + 'A' * 500 + '   ')
        detail = admin.get(LIST).json()['results'][0]['failure_detail']
        assert detail == 'A' * 200


# ------------------------------------------------------------------------------------------------ retry
class TestRetry:
    def test_retry_requeues_a_rejected_refund_and_audits_the_admin(self, mk, admin, admin_user):
        r = failed(mk(), FK.REJECTED)
        res = admin.post(retry_url(r), {}, format='json')
        assert res.status_code == 200
        assert res.json()['status'] == 'pending_gateway' and res.json()['failure_kind'] == ''
        assert fresh(r).status == RS.PENDING_GATEWAY
        log = RefundAttempt.objects.filter(refund=r, kind='admin_retry')
        assert log.count() == 1 and log.get().actor == admin_user

    def test_unknown_refund_is_404(self, admin):
        res = admin.post(f'{LIST}{uuid.uuid4()}/retry/', {}, format='json')
        assert res.status_code == 404

    def test_not_failed_is_409_not_failed_and_second_retry_is_idempotent(self, mk, admin):
        pending = mk()
        res = admin.post(retry_url(pending), {}, format='json')
        assert res.status_code == 409 and res.json()['code'] == 'not_failed'
        r = failed(mk(), FK.REJECTED)
        assert admin.post(retry_url(r), {}, format='json').status_code == 200
        again = admin.post(retry_url(r), {}, format='json')
        assert again.status_code == 409 and again.json()['code'] == 'not_failed'
        assert RefundAttempt.objects.filter(refund=r, kind='admin_retry').count() == 1

    @pytest.mark.parametrize('kind', [FK.EXHAUSTED, FK.REPLAY_WINDOW, FK.ALREADY_REFUNDED])
    def test_ambiguous_failures_need_the_confirm_flag(self, mk, admin, kind):
        r = failed(mk(), kind)
        for body in ({}, {'confirm_not_refunded_in_gateway': False}):
            res = admin.post(retry_url(r), body, format='json')
            assert res.status_code == 409 and res.json()['code'] == 'confirmation_required'
            assert fresh(r).status == RS.FAILED
        assert not RefundAttempt.objects.filter(refund=r, kind='admin_retry').exists()
        res = admin.post(retry_url(r), {'confirm_not_refunded_in_gateway': True}, format='json')
        assert res.status_code == 200 and fresh(r).status == RS.PENDING_GATEWAY

    def test_confirm_flag_is_not_needed_for_certain_failures(self, mk, admin):
        for kind in (FK.REJECTED, FK.PROVIDER_FAILED, FK.GUARD):
            r = failed(mk(), kind)
            assert admin.post(retry_url(r), {}, format='json').status_code == 200, kind

    def test_guard_still_failing_is_409_guard_failed(self, mk, admin):
        r = failed(mk(), FK.GUARD)
        GatewayAnomaly.objects.create(gateway='paypal', reference='ext', reason='external_refund', payment_transaction=r.payment_transaction)
        res = admin.post(retry_url(r), {}, format='json')
        assert res.status_code == 409 and res.json()['code'] == 'guard_failed'
        assert 'external refund' in res.json()['error']
        assert fresh(r).status == RS.FAILED

    def test_confirmation_is_checked_before_the_guard(self, mk, admin):
        r = failed(mk(), FK.EXHAUSTED)
        PaymentTransaction.objects.filter(pk=r.payment_transaction_id).update(status=PaymentTransaction.Status.REFUNDED)
        res = admin.post(retry_url(r), {'confirm_not_refunded_in_gateway': True}, format='json')
        assert res.status_code == 409 and res.json()['code'] == 'guard_failed'

    def test_malformed_body_is_400(self, mk, admin):
        r = failed(mk(), FK.EXHAUSTED)
        res = admin.post(retry_url(r), {'confirm_not_refunded_in_gateway': 'maybe'}, format='json')
        assert res.status_code == 400
        assert fresh(r).status == RS.FAILED

    def test_retry_is_throttled(self, mk, admin, monkeypatch):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'admin_refund_retry', '2/hour')
        r = mk()                                                # pending: every call is a 409, but still counts
        codes = [admin.post(retry_url(r), {}, format='json').status_code for _ in range(3)]
        assert codes == [409, 409, 429]

    def test_the_list_is_not_subject_to_the_retry_throttle(self, mk, admin, monkeypatch):
        monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'admin_refund_retry', '1/hour')
        assert all(admin.get(LIST).status_code == 200 for _ in range(3))
