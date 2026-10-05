"""
Slice T1b: what happens to a suspended tutor's future lessons (plan §3.1 "suspension with future lessons").

* Staff cancel them with a separate action, one transaction per booking: full refund of what was captured, no strike, no bonus
  credit by default (ADMIN_CANCEL_BONUS_CREDITS = 0, provisional), the student gets the cancellation e-mail. Idempotent.
* An automatic strike suspension has no admin present: the tutor shows up in a staff work queue and an admin alert line is
  logged with ids only.
* Lock order: the review path locks booking -> tutor like every other path (it used to lock tutor -> booking).
"""
import logging
import threading
import time as pytime
from decimal import Decimal

import pytest
from django.core import mail
from django.db import connection
from rest_framework.test import APIClient

import factories as f
from apps.bookings.models import Booking, BookingStatusChange
from apps.payments.models import CreditBundle, RefundRequest
from apps.teachers.models import TeacherStrike
from apps.teachers.strikes import add_strike
from payment_helpers import captured

S = Booking.Status
H = 60


def api(user):
    c = APIClient()
    if user is not None:
        c.force_authenticate(user=user)
    return c


def cancel_all(admin, tutor, **body):
    body.setdefault('reason', 'Tutor suspended')
    return api(admin).post(f'/api/v1/admin/teachers/{tutor.id}/cancel-future-lessons/', body, format='json')


def by_id(res):
    return {r['booking_id']: r for r in res.json()['results']}


@pytest.mark.django_db
class TestAdminCancel:
    def test_paid_lessons_are_refunded_without_strike_or_bonus_and_holds_released(self, admin_user, teacher_user, student_user,
                                                                                   django_capture_on_commit_callbacks):
        paid = captured(teacher_user, student_user, 48 * H, ref='ADM-1')
        hold = f.make_booking(teacher=teacher_user, student=f.make_student(), status=S.PENDING_PAYMENT, offset_hours=72)
        f.advance_teacher(teacher_user, 'suspended')
        with django_capture_on_commit_callbacks(execute=True):
            res = cancel_all(admin_user, teacher_user)
        assert res.status_code == 200, res.json()
        rows = by_id(res)
        assert rows[str(paid.id)]['outcome'] == 'admin_refund' and rows[str(paid.id)]['status'] == S.CANCELLED_BY_TEACHER
        assert rows[str(hold.id)]['outcome'] == 'released' and rows[str(hold.id)]['status'] == S.CANCELLED
        assert res.json()['cancelled_count'] == 2
        paid.refresh_from_db()
        assert (paid.cancelled_by, paid.cancel_reason) == (admin_user, 'Tutor suspended')
        refund = RefundRequest.objects.get(booking=paid)
        assert (refund.amount, refund.currency) == (Decimal('168.75'), 'ZAR')
        assert not TeacherStrike.objects.exists()
        assert not CreditBundle.objects.exists()
        assert BookingStatusChange.objects.filter(booking=paid, actor=f'user:{admin_user.username}').exists()
        assert any(student_user.email in m.to for m in mail.outbox)
        assert all('your tutor had to cancel' not in m.body.lower() for m in mail.outbox)

    def test_the_admin_cancel_does_not_count_as_the_tutors_own_cancel(self, admin_user, teacher_user, student_user):
        from django.utils import timezone
        from apps.bookings.services.cancellation import recent_early_cancels
        captured(teacher_user, student_user, 48 * H, ref='ADM-2')
        f.advance_teacher(teacher_user, 'suspended')
        cancel_all(admin_user, teacher_user)
        assert recent_early_cancels(teacher_user, timezone.now()) == 0

    def test_bonus_credits_follow_the_provisional_setting(self, admin_user, teacher_user, student_user, settings):
        settings.ADMIN_CANCEL_BONUS_CREDITS = 1
        captured(teacher_user, student_user, 48 * H, ref='ADM-3')
        f.advance_teacher(teacher_user, 'suspended')
        cancel_all(admin_user, teacher_user)
        bundle = CreditBundle.objects.get(user=student_user, source=CreditBundle.Source.BONUS)
        assert bundle.remaining_credits == 1

    def test_default_is_zero_bonus(self):
        from django.conf import settings
        assert settings.ADMIN_CANCEL_BONUS_CREDITS == 0

    def test_a_credit_funded_lesson_gets_its_credit_back(self, admin_user, teacher_user, student_user):
        from apps.payments.services.credits import grant_credit, redeem_booking_credit
        grant_credit(student_user, source=CreditBundle.Source.PURCHASE, pack_name='p', unit_amount=Decimal('9.00'), currency='USD',
                     fx_rate_to_zar=Decimal('18.750000'), fx_source='test', idempotency_key='adm-credit')
        hold = f.make_booking(teacher=teacher_user, student=student_user, status=S.PENDING_PAYMENT, offset_hours=48)
        redeem_booking_credit(booking=hold, student=student_user)
        f.advance_teacher(teacher_user, 'suspended')
        assert by_id(cancel_all(admin_user, teacher_user))[str(hold.id)]['outcome'] == 'admin_refund'
        assert CreditBundle.objects.filter(user=student_user, source=CreditBundle.Source.REFUND).exists()

    def test_it_is_idempotent(self, admin_user, teacher_user, student_user):
        paid = captured(teacher_user, student_user, 48 * H, ref='ADM-4')
        f.advance_teacher(teacher_user, 'suspended')
        cancel_all(admin_user, teacher_user, booking_ids=[str(paid.id)])
        again = cancel_all(admin_user, teacher_user, booking_ids=[str(paid.id)])
        assert again.status_code == 200 and by_id(again)[str(paid.id)]['outcome'] == 'already_cancelled'
        assert again.json()['cancelled_count'] == 0
        assert RefundRequest.objects.filter(booking=paid).count() == 1

    def test_the_default_list_is_the_future_lessons_only(self, admin_user, teacher_user, student_user):
        future = captured(teacher_user, student_user, 48 * H, ref='ADM-5')
        started = f.make_booking(teacher=teacher_user, status=S.CONFIRMED, offset_hours=-1, funded=True)
        f.advance_teacher(teacher_user, 'suspended')
        rows = by_id(cancel_all(admin_user, teacher_user))
        assert set(rows) == {str(future.id)}
        started.refresh_from_db()
        assert started.status == S.CONFIRMED

    def test_explicit_ids_are_checked_one_by_one(self, admin_user, teacher_user, student_user):
        started = f.make_booking(teacher=teacher_user, status=S.CONFIRMED, offset_hours=-1, funded=True)
        foreign = f.make_booking(status=S.CONFIRMED, offset_hours=48, funded=True)
        f.advance_teacher(teacher_user, 'suspended')
        rows = by_id(cancel_all(admin_user, teacher_user, booking_ids=[str(started.id), str(foreign.id)]))
        assert rows[str(started.id)]['outcome'] == 'not_cancellable'
        assert rows[str(foreign.id)]['outcome'] == 'not_found'
        foreign.refresh_from_db()
        assert foreign.status == S.CONFIRMED

    def test_one_failure_does_not_undo_the_others(self, admin_user, teacher_user, student_user):
        paid = captured(teacher_user, student_user, 48 * H, ref='ADM-6')
        unfunded = f.make_booking(teacher=teacher_user, status=S.CONFIRMED, offset_hours=72)      # no funding record
        f.advance_teacher(teacher_user, 'suspended')
        rows = by_id(cancel_all(admin_user, teacher_user))
        assert rows[str(unfunded.id)]['outcome'] == 'funding_unavailable'
        assert rows[str(paid.id)]['outcome'] == 'admin_refund'
        unfunded.refresh_from_db()
        assert unfunded.status == S.CONFIRMED

    @pytest.mark.parametrize('status', ['approved', 'in_review'])
    def test_only_for_suspended_or_removed_tutors(self, admin_user, status):
        tutor = f.make_teacher_profile(status=status)
        booking = f.make_booking(teacher=tutor, status=S.CONFIRMED, offset_hours=48, funded=True)
        res = cancel_all(admin_user, tutor)
        assert res.status_code == 409 and res.json()['code'] == 'tutor_not_suspended'
        booking.refresh_from_db()
        assert booking.status == S.CONFIRMED

    def test_works_after_suspended_to_rejected(self, admin_user, teacher_user, student_user):
        paid = captured(teacher_user, student_user, 48 * H, ref='ADM-7')
        f.advance_teacher(teacher_user, 'suspended', 'rejected')
        assert by_id(cancel_all(admin_user, teacher_user))[str(paid.id)]['outcome'] == 'admin_refund'

    def test_a_reason_is_required(self, admin_user, teacher_user):
        f.advance_teacher(teacher_user, 'suspended')
        assert cancel_all(admin_user, teacher_user, reason='').status_code == 400

    def test_staff_only_and_404(self, admin_user, teacher_user, student_user):
        import uuid
        f.advance_teacher(teacher_user, 'suspended')
        assert cancel_all(None, teacher_user).status_code == 401
        assert cancel_all(student_user, teacher_user).status_code == 403
        assert cancel_all(teacher_user.user, teacher_user).status_code == 403
        assert api(admin_user).post(f'/api/v1/admin/teachers/{uuid.uuid4()}/cancel-future-lessons/',
                                    {'reason': 'x'}, format='json').status_code == 404


@pytest.mark.django_db
class TestWorkQueue:
    URL = '/api/v1/admin/teachers/suspended-with-lessons/'

    def test_lists_unbookable_tutors_that_still_have_future_lessons(self, admin_user):
        suspended = f.make_teacher_profile(status='suspended')
        rejected = f.make_teacher_profile(status='rejected')
        idle = f.make_teacher_profile(status='suspended')
        live = f.make_teacher_profile(status='approved')
        b1 = f.make_booking(teacher=suspended, status=S.CONFIRMED, offset_hours=24)
        f.make_booking(teacher=suspended, status=S.PENDING_PAYMENT, offset_hours=48)
        f.make_booking(teacher=rejected, status=S.CONFIRMED, offset_hours=30)
        f.make_booking(teacher=idle, status=S.CONFIRMED, offset_hours=-3)
        f.make_booking(teacher=live, status=S.CONFIRMED, offset_hours=24)
        body = api(admin_user).get(self.URL).json()
        assert body['count'] == 2
        rows = {r['teacher_id']: r for r in body['results']}
        assert set(rows) == {str(suspended.id), str(rejected.id)}
        assert rows[str(suspended.id)]['future_lesson_count'] == 2
        assert rows[str(suspended.id)]['status'] == 'suspended'
        assert rows[str(suspended.id)]['next_lesson_start_utc'].startswith(b1.start_time_utc.isoformat()[:16])

    def test_staff_only(self, student_user):
        assert api(student_user).get(self.URL).status_code == 403
        assert api(None).get(self.URL).status_code == 401

    def test_a_strike_suspension_alerts_the_admin_with_ids_only(self, settings, caplog, django_capture_on_commit_callbacks):
        settings.STRIKE_LIMIT = 1
        tutor = f.make_teacher_profile(status='approved')
        booking = f.make_booking(teacher=tutor, status=S.CONFIRMED, offset_hours=24)
        with caplog.at_level(logging.WARNING, logger='apps.teachers.strikes'):
            with django_capture_on_commit_callbacks(execute=True):
                add_strike(tutor, TeacherStrike.Kind.NO_SHOW)
        alerts = [r.getMessage() for r in caplog.records if 'ADMIN ALERT' in r.getMessage()]
        assert len(alerts) == 1 and str(tutor.id) in alerts[0] and str(booking.id) in alerts[0]
        assert tutor.user.email not in alerts[0]

    def test_no_alert_without_future_lessons(self, settings, caplog, django_capture_on_commit_callbacks):
        settings.STRIKE_LIMIT = 1
        tutor = f.make_teacher_profile(status='approved')
        with caplog.at_level(logging.WARNING, logger='apps.teachers.strikes'):
            with django_capture_on_commit_callbacks(execute=True):
                add_strike(tutor, TeacherStrike.Kind.NO_SHOW)
        assert not [r for r in caplog.records if 'ADMIN ALERT' in r.getMessage()]


# ------------------------------------------------------------------ lock order: booking -> tutor in the review path
@pytest.mark.django_db
def test_review_locks_the_booking_before_the_tutor(monkeypatch, teacher_user, student_user):
    from django.db.models import QuerySet
    from apps.bookings.services.reviews import submit_review
    from test_review_endpoint import lesson
    locked = []
    original = QuerySet.select_for_update

    def spy(qs, *args, **kwargs):
        locked.append(qs.model.__name__)
        return original(qs, *args, **kwargs)
    monkeypatch.setattr(QuerySet, 'select_for_update', spy)
    booking = lesson(teacher_user, student_user)
    submit_review(booking_id=booking.id, student=student_user, rating=4, tags=[], notes='')
    assert locked.index('Booking') < locked.index('TeacherProfile')


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_postgres_review_and_strike_on_the_same_lesson_do_not_deadlock(teacher_user, student_user):
    """Thread B holds the booking row (as cancel / memo / no-show do) and then strikes the tutor; thread A reviews the same
    lesson meanwhile. With tutor -> booking in the review path this deadlocked; with booking -> tutor A simply waits."""
    if connection.vendor != 'postgresql':
        pytest.skip('PostgreSQL concurrency test (run in the Postgres CI job)')
    from django.db import transaction
    from apps.bookings.services.reviews import submit_review
    from test_review_endpoint import lesson
    booking = lesson(teacher_user, student_user)
    held, errors = threading.Event(), []

    def striker():
        try:
            with transaction.atomic():
                row = Booking.objects.select_for_update(of=('self',)).select_related('teacher').get(pk=booking.pk)
                held.set()
                pytime.sleep(0.5)
                add_strike(row.teacher, TeacherStrike.Kind.MEMO_SLA, booking=row)
        except Exception as exc:          # recorded, asserted below
            errors.append(type(exc).__name__)
        finally:
            connection.close()

    def reviewer():
        try:
            held.wait(5)
            submit_review(booking_id=booking.id, student=student_user, rating=5, tags=[], notes='')
        except Exception as exc:
            errors.append(type(exc).__name__)
        finally:
            connection.close()

    threads = [threading.Thread(target=striker), threading.Thread(target=reviewer)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    assert errors == []
    booking.refresh_from_db()
    assert booking.student_rating == 5 and TeacherStrike.objects.filter(booking=booking).count() == 1
