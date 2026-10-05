"""
Slice T1b review conditions (Architect / QA, 2026-10-05):
M1 PayPal capture must refuse an unbookable tutor BEFORE money moves; M2 admin cancel must not release a hold whose payment is
in flight; m1 tutor row locked after the booking; m2 money edges of the admin cancel; m3 per-lesson failures and the batch cap;
nits (dead legacy create path, unreachable 403 branch).
"""
import threading
import time as pytime
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

import factories as f
from apps.bookings.models import Booking
from apps.payments.models import LedgerEntry, PaymentTransaction, RefundRequest
from apps.payments.services import refunds
from payment_helpers import captured
# fixtures / helpers of the existing PayPal and grace suites
from test_grace_bookings import make, outbox  # noqa: F401  (fixtures)
from test_paypal_orders import booking, capture, init, initialised, order_json, pp  # noqa: F401  (fixtures + helpers)

S = Booking.Status
H = 60
pytestmark = pytest.mark.django_db


def api(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def cancel_all(admin, tutor, **body):
    body.setdefault('reason', 'Tutor suspended')
    return api(admin).post(f'/api/v1/admin/teachers/{tutor.id}/cancel-future-lessons/', body, format='json')


def rows(res):
    return {r['booking_id']: r for r in res.json()['results']}


# ------------------------------------------------------------------ M1: capture refuses before PayPal is called
class TestCaptureRefusesUnbookableTutor:
    def test_a_suspension_between_checkout_and_approval_never_charges(self, student_user, teacher_user, booking, pp):
        data = initialised(student_user, booking)
        f.advance_teacher(teacher_user, 'suspended')
        pp['order'] = order_json(data['transaction_reference'])
        res = capture(student_user, data['order_id'])
        assert res.status_code == 409 and res.json()['code'] == 'tutor_not_bookable' and res.json()['outcome'] == 'failed'
        assert res.json()['retryable'] is False
        assert pp['calls'] == 0
        booking.refresh_from_db()
        assert booking.status == S.PENDING_PAYMENT
        assert not LedgerEntry.objects.exists()

    def test_the_training_gate_flipping_on_has_the_same_effect(self, student_user, booking, pp, settings):
        data = initialised(student_user, booking)
        settings.TUTOR_TRAINING_GATE_ENABLED = True
        res = capture(student_user, data['order_id'])
        assert res.status_code == 409 and res.json()['code'] == 'tutor_not_bookable' and pp['calls'] == 0

    def test_a_bookable_tutor_still_captures(self, student_user, booking, pp):
        data = initialised(student_user, booking)
        pp['order'] = order_json(data['transaction_reference'])
        assert capture(student_user, data['order_id']).json()['outcome'] == 'confirmed'

    def test_payfast_checkout_initiation_refuses_an_unbookable_tutor(self, student_user, teacher_user, booking):
        f.advance_teacher(teacher_user, 'suspended')
        res = api(student_user).post('/api/v1/payments/checkout/init/', {'booking_id': str(booking.id), 'gateway': 'payfast'},
                                     format='json')
        assert res.status_code == 409 and not PaymentTransaction.objects.exists()


# ------------------------------------------------------------------ M2: a payment in flight is never released
class TestPaymentInFlight:
    def _hold(self, tutor):
        return f.make_booking(teacher=tutor, student=f.make_student(), status=S.PENDING_PAYMENT, offset_hours=48)

    @pytest.mark.parametrize('tx_status', [PaymentTransaction.Status.INITIALIZED, PaymentTransaction.Status.PENDING_CAPTURE])
    def test_skipped_and_flagged(self, admin_user, teacher_user, tx_status, mail_outbox):
        hold = self._hold(teacher_user)
        f.make_payment_transaction(hold, status=tx_status, gateway='paypal', amount=Decimal('9.00'))
        f.advance_teacher(teacher_user, 'suspended')
        res = cancel_all(admin_user, teacher_user)
        assert res.status_code == 200
        assert rows(res)[str(hold.id)]['outcome'] == 'payment_in_flight'
        assert res.json()['payment_in_flight_ids'] == [str(hold.id)] and res.json()['cancelled_count'] == 0
        hold.refresh_from_db()
        assert hold.status == S.PENDING_PAYMENT and hold.cancelled_by is None
        assert not mail_outbox

    def test_an_abandoned_initialised_attempt_does_not_block(self, admin_user, teacher_user):
        from datetime import timedelta
        hold = self._hold(teacher_user)
        tx = f.make_payment_transaction(hold, status=PaymentTransaction.Status.INITIALIZED, gateway='paypal')
        PaymentTransaction.objects.filter(pk=tx.pk).update(created_at=timezone.now() - timedelta(hours=3))
        f.advance_teacher(teacher_user, 'suspended')
        assert rows(cancel_all(admin_user, teacher_user))[str(hold.id)]['outcome'] == 'released'

    def test_a_failed_attempt_does_not_block(self, admin_user, teacher_user):
        hold = self._hold(teacher_user)
        f.make_payment_transaction(hold, status=PaymentTransaction.Status.FAILED, gateway='paypal')
        f.advance_teacher(teacher_user, 'suspended')
        assert rows(cancel_all(admin_user, teacher_user))[str(hold.id)]['outcome'] == 'released'

    def test_the_flagged_hold_is_cancellable_once_the_payment_has_resolved(self, admin_user, teacher_user):
        hold = self._hold(teacher_user)
        tx = f.make_payment_transaction(hold, status=PaymentTransaction.Status.INITIALIZED, gateway='paypal')
        f.advance_teacher(teacher_user, 'suspended')
        assert rows(cancel_all(admin_user, teacher_user))[str(hold.id)]['outcome'] == 'payment_in_flight'
        PaymentTransaction.objects.filter(pk=tx.pk).update(status=PaymentTransaction.Status.FAILED)
        assert rows(cancel_all(admin_user, teacher_user))[str(hold.id)]['outcome'] == 'released'


@pytest.fixture
def mail_outbox(monkeypatch):
    from django.core import mail
    return mail.outbox


# ------------------------------------------------------------------ m1: the tutor row is locked too (booking -> tutor)
def test_admin_cancel_locks_booking_then_tutor(monkeypatch, admin_user, teacher_user, student_user):
    from django.db.models import QuerySet
    captured(teacher_user, student_user, 48 * H, ref='L1')
    f.advance_teacher(teacher_user, 'suspended')
    locked, original = [], QuerySet.select_for_update

    def spy(qs, *a, **k):
        locked.append(qs.model.__name__)
        return original(qs, *a, **k)
    monkeypatch.setattr(QuerySet, 'select_for_update', spy)
    cancel_all(admin_user, teacher_user)
    admin_part = [m for m in locked if m in ('Booking', 'TeacherProfile')]
    assert admin_part.index('Booking') < admin_part.index('TeacherProfile')


def test_a_reactivated_tutor_keeps_the_paid_lesson(admin_user, teacher_user, student_user):
    from apps.bookings.services.admin_cancellation import admin_cancel_booking
    paid = captured(teacher_user, student_user, 48 * H, ref='L2')
    f.advance_teacher(teacher_user, 'suspended', 'approved')
    out = admin_cancel_booking(paid.id, admin_user, teacher_id=teacher_user.id, reason='x')
    assert out.outcome == 'not_cancellable'
    paid.refresh_from_db()
    assert paid.status == S.CONFIRMED and not RefundRequest.objects.exists()


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_postgres_a_concurrent_reactivate_wins_over_the_admin_cancel(admin_user, teacher_user, student_user):
    if connection.vendor != 'postgresql':
        pytest.skip('PostgreSQL concurrency test (run in the Postgres CI job)')
    from django.db import transaction
    from apps.bookings.services.admin_cancellation import admin_cancel_booking
    from apps.teachers.models import TeacherProfile
    from apps.teachers.vetting import transition_teacher
    paid = captured(teacher_user, student_user, 48 * H, ref='L3')
    f.advance_teacher(teacher_user, 'suspended')
    holding, result = threading.Event(), {}

    def reactivator():
        try:
            with transaction.atomic():
                TeacherProfile.objects.select_for_update().get(pk=teacher_user.pk)
                holding.set()
                pytime.sleep(0.6)
                transition_teacher(TeacherProfile.objects.get(pk=teacher_user.pk), 'approved', actor=admin_user, reason='back')
        finally:
            connection.close()

    def canceller():
        try:
            holding.wait(5)
            result['outcome'] = admin_cancel_booking(paid.id, admin_user, teacher_id=teacher_user.id, reason='x').outcome
        finally:
            connection.close()

    threads = [threading.Thread(target=reactivator), threading.Thread(target=canceller)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    assert result['outcome'] == 'not_cancellable'
    paid.refresh_from_db()
    assert paid.status == S.CONFIRMED


# ------------------------------------------------------------------ m2: money edges of the admin cancel
class TestMoneyEdges:
    def test_a_grace_lesson_awaits_clearance_and_posts_nothing(self, admin_user, make, teacher_user, outbox):
        tx, lesson = make.grace()
        f.advance_teacher(teacher_user, 'suspended')
        res = cancel_all(admin_user, teacher_user)
        assert rows(res)[str(lesson.id)]['outcome'] == 'admin_refund'
        refund = RefundRequest.objects.get(booking=lesson)
        assert refund.status == RefundRequest.Status.AWAITING_CLEARANCE and refund.amount == Decimal('9.00')
        assert not LedgerEntry.objects.filter(booking=lesson).exists()
        lesson.refresh_from_db()
        assert lesson.status == S.CANCELLED_BY_TEACHER

    def test_an_already_settled_lesson_is_reported_and_left_alone(self, admin_user, teacher_user, student_user):
        from apps.payments.models import RefundRequest as RR
        paid = captured(teacher_user, student_user, 48 * H, ref='E1')
        refunds.request_refund(paid, RR.Reason.OUTAGE)                      # settled by another path (ledger event)
        f.advance_teacher(teacher_user, 'suspended')
        res = cancel_all(admin_user, teacher_user)
        assert rows(res)[str(paid.id)]['outcome'] == 'not_cancellable'
        paid.refresh_from_db()
        assert paid.status == S.CONFIRMED and RefundRequest.objects.filter(booking=paid).count() == 1

    @pytest.mark.parametrize('gateway,amount,currency', [('paypal', '9.00', 'USD'), ('payfast', '168.75', 'ZAR')])
    def test_the_refund_is_in_the_captured_currency(self, admin_user, teacher_user, student_user, gateway, amount, currency):
        paid = captured(teacher_user, student_user, 48 * H, gateway=gateway, amount=amount, currency=currency, ref='E2')
        f.advance_teacher(teacher_user, 'suspended')
        assert rows(cancel_all(admin_user, teacher_user))[str(paid.id)]['outcome'] == 'admin_refund'
        refund = RefundRequest.objects.get(booking=paid)
        assert (refund.amount, refund.currency, refund.payment_transaction.gateway) == (Decimal(amount), currency, gateway)

    def test_a_lesson_starting_in_minutes_is_still_refunded(self, admin_user, teacher_user, student_user):
        soon = captured(teacher_user, student_user, 5, ref='E3')
        f.advance_teacher(teacher_user, 'suspended')
        assert rows(cancel_all(admin_user, teacher_user))[str(soon.id)]['outcome'] == 'admin_refund'
        assert not __import__('apps.teachers.models', fromlist=['x']).TeacherStrike.objects.exists()


# ------------------------------------------------------------------ m3: one failure never aborts the rest; the batch is capped
class TestBatch:
    @pytest.mark.parametrize('error,outcome', [(refunds.MissingFunding('x'), 'funding_unavailable'),
                                               (refunds.RefundStateError('x'), 'not_cancellable')])
    def test_domain_errors_are_reported_per_lesson(self, monkeypatch, admin_user, teacher_user, student_user, error, outcome):
        first = captured(teacher_user, student_user, 48 * H, ref='B1')
        second = captured(teacher_user, f.make_student(), 72 * H, ref='B2')
        real = refunds.request_refund

        def flaky(booking, *a, **k):
            if booking.pk == first.pk:
                raise error
            return real(booking, *a, **k)
        monkeypatch.setattr(refunds, 'request_refund', flaky)
        f.advance_teacher(teacher_user, 'suspended')
        res = cancel_all(admin_user, teacher_user)
        assert res.status_code == 200
        assert rows(res)[str(first.id)]['outcome'] == outcome and rows(res)[str(second.id)]['outcome'] == 'admin_refund'
        first.refresh_from_db()
        assert first.status == S.CONFIRMED                                    # its transaction rolled back

    def test_the_default_batch_is_capped_and_says_so(self, monkeypatch, admin_user):
        from apps.bookings.services import admin_cancellation
        monkeypatch.setattr(admin_cancellation, 'BATCH_LIMIT', 3)
        tutor = f.make_teacher_profile(status='approved')
        for h in range(5):
            f.make_booking(teacher=tutor, student=f.make_student(), status=S.PENDING_PAYMENT, offset_hours=30 + h)
        f.advance_teacher(tutor, 'suspended')
        first = cancel_all(admin_user, tutor)
        assert len(first.json()['results']) == 3 and first.json()['remaining'] is True and first.json()['cancelled_count'] == 3
        second = cancel_all(admin_user, tutor)
        assert len(second.json()['results']) == 2 and second.json()['remaining'] is False

    def test_the_default_limit_is_fifty(self):
        from apps.bookings.services import admin_cancellation
        assert admin_cancellation.BATCH_LIMIT == 50

    def test_in_flight_holds_do_not_make_the_queue_loop_forever(self, monkeypatch, admin_user):
        """A flagged hold stays pending, so it must not count as 'remaining' work forever once everything else is done."""
        from apps.bookings.services import admin_cancellation
        monkeypatch.setattr(admin_cancellation, 'BATCH_LIMIT', 1)
        tutor = f.make_teacher_profile(status='approved')
        hold = f.make_booking(teacher=tutor, student=f.make_student(), status=S.PENDING_PAYMENT, offset_hours=30)
        f.make_payment_transaction(hold, status=PaymentTransaction.Status.INITIALIZED, gateway='paypal')
        f.advance_teacher(tutor, 'suspended')
        res = cancel_all(admin_user, tutor)
        assert res.json()['payment_in_flight_ids'] == [str(hold.id)] and res.json()['remaining'] is False


# ------------------------------------------------------------------ nits
def test_the_legacy_create_serializer_cannot_create_a_booking():
    from apps.bookings.serializers import BookingCreateSerializer
    with pytest.raises(NotImplementedError):
        BookingCreateSerializer().create({})
    assert not Booking.objects.exists()


def test_the_review_error_mapper_has_no_unreachable_branch():
    import inspect
    from apps.admin_api import teacher_review_views
    assert 'forbidden' not in inspect.getsource(teacher_review_views._error)
