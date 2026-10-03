"""Task 9.6: cancelling a lesson - who, when, what the money does, and that it happens exactly once."""
from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking, BookingStatusChange
from apps.bookings.services.slot_generator import generate_teacher_slots
from apps.payments.models import CreditBundle, LedgerAccount, LedgerEntry, PaymentTransaction, RefundRequest
from apps.payments.services.funding import ensure_gateway_funding
from apps.payments.tasks import release_cleared_escrow_task
from apps.teachers.models import TeacherAvailability, TeacherProfile, TeacherStrike
from test_settlement_paths import captured, force, lesson, net

S = Booking.Status
ACC = LedgerAccount
User = get_user_model()
H = 60          # minutes per hour, for readability: captured(..., start_in_min=3 * H)


def call(user, method, booking, path, body=None):
    c = APIClient()
    if user:
        c.force_authenticate(user=user)
    url = f'/api/v1/bookings/{booking.id}/{path}/'
    return c.get(url) if method == 'get' else c.post(url, body or {}, format='json')


def cancel(user, booking, **body):
    return call(user, 'post', booking, 'cancel', body)


def reload(b):
    b.refresh_from_db()
    return b


@pytest.fixture
def tutor(teacher_user):
    TeacherAvailability.objects.all().delete()
    for dow in range(7):
        TeacherAvailability.objects.create(teacher=teacher_user, day_of_week=dow, start_time=time(8, 0), end_time=time(10, 0), is_active=True)
    return teacher_user


# ------------------------------------------------------------------ student, outside the free window
@pytest.mark.django_db
class TestStudentFreeCancel:
    def test_more_than_two_hours_out_is_fully_refunded_through_the_gateway(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 5 * H)
        res = cancel(student_user, b, reason='Change of plans')
        assert res.status_code == 200, res.json()
        assert res.json()['outcome'] == 'full_refund'
        b = reload(b)
        assert b.status == S.CANCELLED_BY_STUDENT
        assert (b.cancelled_by, b.cancel_reason) == (student_user, 'Change of plans') and b.cancelled_at
        r = RefundRequest.objects.get(booking=b)
        assert (r.amount, r.currency, r.status, r.reason) == (Decimal('168.75'), 'ZAR', 'pending_gateway', 'student_cancel')
        assert net(b, ACC.LIABILITY_STUDENT_ESCROW) == 0 and net(b, ACC.LIABILITY_TUTOR_PAYABLE) == 0
        assert net(b, ACC.LIABILITY_REFUNDS_PAYABLE) == Decimal('168.75')
        assert not CreditBundle.objects.exists()
        assert BookingStatusChange.objects.filter(booking=b, to_status=S.CANCELLED_BY_STUDENT, actor=f'user:{student_user.username}').exists()

    def test_the_slot_becomes_bookable_again(self, tutor, student_user):
        from datetime import datetime
        far = timezone.now() + timedelta(hours=4)       # outside the free-cancel window whatever time the suite runs
        slot = next(s for s in generate_teacher_slots(teacher=tutor, days_ahead=5)
                    if s['is_bookable'] and datetime.fromisoformat(s['start_time_utc']) > far)
        start = datetime.fromisoformat(slot['start_time_utc'])
        b = Booking.objects.create(teacher=tutor, student=student_user, start_time_utc=start, end_time_utc=start + timedelta(minutes=25), status=S.CONFIRMED)
        tx = PaymentTransaction.objects.create(booking=b, gateway='payfast', gateway_reference='SLOT-TX', merchant_reference='SLOT',
                                               amount='168.75', currency='ZAR', status=PaymentTransaction.Status.SUCCESS)
        ensure_gateway_funding(tx, b)
        assert next(s for s in generate_teacher_slots(teacher=tutor, days_ahead=5) if s['start_time_utc'] == slot['start_time_utc'])['is_bookable'] is False
        assert cancel(student_user, b).status_code == 200
        assert next(s for s in generate_teacher_slots(teacher=tutor, days_ahead=5) if s['start_time_utc'] == slot['start_time_utc'])['is_bookable'] is True

    def test_the_tutor_is_not_paid_after_a_refunded_cancellation(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 5 * H)
        cancel(student_user, b)
        Booking.objects.filter(pk=b.pk).update(end_time_utc=timezone.now() - timedelta(hours=30))
        release_cleared_escrow_task()
        assert net(b, ACC.LIABILITY_TUTOR_PAYABLE) == 0

    def test_a_second_cancel_is_refused_and_refunds_nothing_more(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 5 * H)
        assert cancel(student_user, b).status_code == 200
        again = cancel(student_user, b)
        assert again.status_code == 409 and again.json()['code'] == 'not_cancellable'
        assert RefundRequest.objects.count() == 1 and net(b, ACC.LIABILITY_REFUNDS_PAYABLE) == Decimal('168.75')

    def test_an_unpaid_booking_is_simply_released(self, teacher_user, student_user):
        b = lesson(teacher_user, student_user, 5 * H, status=S.PENDING_PAYMENT)
        res = cancel(student_user, b)
        assert res.status_code == 200 and res.json()['outcome'] == 'released'
        assert reload(b).status == S.CANCELLED and not RefundRequest.objects.exists() and not LedgerEntry.objects.exists()

    def test_the_reason_is_trimmed_and_bounded(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 5 * H)
        assert cancel(student_user, b, reason='x' * 1000).status_code == 200
        assert len(reload(b).cancel_reason) <= 255
        b2 = captured(teacher_user, student_user, 6 * H, ref='CAP-2')
        assert cancel(student_user, b2, reason=['not', 'a', 'string']).status_code in (200, 400)


# ------------------------------------------------------------------ student, inside the window
@pytest.mark.django_db
class TestStudentLateCancel:
    def test_inside_two_hours_needs_an_explicit_acknowledgement(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 90)
        res = cancel(student_user, b)
        assert res.status_code == 400 and res.json()['code'] == 'acknowledgement_required'
        assert reload(b).status == S.CONFIRMED and not RefundRequest.objects.exists()

    def test_acknowledged_late_cancel_keeps_the_fee_and_refunds_nothing(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 90)
        res = cancel(student_user, b, acknowledge_forfeit=True)
        assert res.status_code == 200 and res.json()['outcome'] == 'fee_forfeited'
        assert reload(b).status == S.STUDENT_LATE_CANCELLED
        assert not RefundRequest.objects.exists() and net(b, ACC.LIABILITY_REFUNDS_PAYABLE) == 0
        assert net(b, ACC.LIABILITY_STUDENT_ESCROW) == Decimal('168.75')            # still held until the release job

    def test_the_tutor_is_paid_80_20_after_24_hours_exactly_once(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 90)
        cancel(student_user, b, acknowledge_forfeit=True)
        release_cleared_escrow_task()                                              # too early
        assert net(b, ACC.LIABILITY_TUTOR_PAYABLE) == 0
        Booking.objects.filter(pk=b.pk).update(end_time_utc=timezone.now() - timedelta(hours=25))
        release_cleared_escrow_task()
        release_cleared_escrow_task()
        assert net(b, ACC.LIABILITY_TUTOR_PAYABLE) == Decimal('135.00')            # 80 % of R168.75
        assert net(b, ACC.REVENUE_PLATFORM_COMMISSION) == Decimal('33.75')
        assert net(b, ACC.LIABILITY_STUDENT_ESCROW) == 0

    def test_the_slot_stays_blocked_for_new_bookings(self):
        from apps.bookings.services.slot_generator import FREE_STATUSES
        assert S.STUDENT_LATE_CANCELLED not in FREE_STATUSES and S.CANCELLED_BY_TEACHER not in FREE_STATUSES
        assert S.CANCELLED_BY_STUDENT in FREE_STATUSES          # only a refunded student cancel frees the slot


# ------------------------------------------------------------------ when cancelling is not possible
@pytest.mark.django_db
class TestNotCancellable:
    def test_after_the_start_time_nobody_can_cancel(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 5 * H)
        force(b, S.CONFIRMED, start_in_min=-3)
        for user in (student_user, teacher_user.user):
            res = cancel(user, b, acknowledge_forfeit=True)
            assert res.status_code == 409 and res.json()['code'] == 'cancel_window_closed'
        assert reload(b).status == S.CONFIRMED

    @pytest.mark.parametrize('status', [S.IN_PROGRESS, S.COMPLETED, S.COMPLETED_PENDING_MEMO, S.DISPUTED, S.INTERRUPTED_POWER,
                                        S.TEACHER_NO_SHOW, S.STUDENT_NO_SHOW, S.CANCELLED, S.CANCELLED_BY_TEACHER])
    def test_only_confirmed_lessons_can_be_cancelled(self, teacher_user, student_user, status):
        b = lesson(teacher_user, student_user, 5 * H, status=status)
        res = cancel(student_user, b, acknowledge_forfeit=True)
        assert res.status_code == 409 and res.json()['code'] == 'not_cancellable'
        assert reload(b).status == status

    def test_a_tutor_cannot_cancel_an_unpaid_booking(self, teacher_user, student_user):
        b = lesson(teacher_user, student_user, 5 * H, status=S.PENDING_PAYMENT)
        assert cancel(teacher_user.user, b).status_code == 409


@pytest.mark.django_db
class TestWhoMayCancel:
    def test_only_the_two_people_in_the_lesson(self, teacher_user, student_user, admin_user):
        stranger = User.objects.create_user(username='nosy', email='n@x.com', password='x-pass-12345', role='student')
        other_tutor = User.objects.create_user(username='t2', email='t2@x.com', password='x-pass-12345', role='teacher')
        TeacherProfile.objects.create(user=other_tutor, headline='x', price_per_25min_usd=9, is_verified=True, is_active=True)
        b = captured(teacher_user, student_user, 5 * H)
        assert cancel(None, b).status_code == 401
        assert cancel(stranger, b).status_code == 404            # it does not exist for them
        assert cancel(other_tutor, b).status_code == 404
        assert cancel(admin_user, b).status_code == 403          # staff resolve things through disputes, not this endpoint
        assert reload(b).status == S.CONFIRMED and not RefundRequest.objects.exists()


# ------------------------------------------------------------------ tutor cancels
@pytest.mark.django_db
class TestTutorCancel:
    def test_a_day_or_more_ahead_is_a_refund_with_no_penalty(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 30 * H)
        res = cancel(teacher_user.user, b, reason='Family emergency')
        assert res.status_code == 200 and res.json()['outcome'] == 'tutor_refund'
        b = reload(b); teacher_user.refresh_from_db()
        assert b.status == S.CANCELLED_BY_TEACHER and b.cancelled_by == teacher_user.user
        assert RefundRequest.objects.get(booking=b).status == 'pending_gateway'
        assert not CreditBundle.objects.exists() and not TeacherStrike.objects.exists()
        assert teacher_user.sla_strikes == 0 and teacher_user.is_active

    def test_less_than_a_day_ahead_adds_a_bonus_credit_and_a_strike(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 5 * H)
        res = cancel(teacher_user.user, b)
        assert res.status_code == 200 and res.json()['outcome'] == 'tutor_refund_with_penalty'
        teacher_user.refresh_from_db()
        assert TeacherStrike.objects.get(booking=b).kind == 'late_cancel' and teacher_user.sla_strikes == 1
        bonus = CreditBundle.objects.get(user=student_user)
        assert (bonus.source, bonus.total_credits, bonus.currency, bonus.unit_amount) == ('bonus', 1, 'ZAR', Decimal('168.75'))
        assert abs((bonus.expires_at - (timezone.now() + timedelta(days=30))).total_seconds()) < 5
        assert net(b, ACC.LIABILITY_STUDENT_WALLET) == Decimal('168.75')            # the bonus, funded by...
        assert net(b, ACC.EXPENSE_STUDENT_COMPENSATION) == Decimal('-168.75')       # ...a platform expense
        assert RefundRequest.objects.filter(booking=b).count() == 1                 # and the refund itself is separate

    def test_the_third_strike_inside_the_window_deactivates_the_tutor(self, teacher_user, student_user):
        for n in range(3):
            cancel(teacher_user.user, captured(teacher_user, student_user, 5 * H + n, ref=f'C{n}'))
        teacher_user.refresh_from_db()
        assert teacher_user.sla_strikes == 3 and teacher_user.is_active is False

    def test_a_fourth_early_cancellation_in_30_days_is_a_strike(self, teacher_user, student_user):
        for n in range(3):
            assert cancel(teacher_user.user, captured(teacher_user, student_user, 30 * H + n, ref=f'E{n}')).status_code == 200
        teacher_user.refresh_from_db()
        assert teacher_user.sla_strikes == 0
        fourth = captured(teacher_user, student_user, 31 * H, ref='E4')
        res = cancel(teacher_user.user, fourth)
        assert res.status_code == 200
        teacher_user.refresh_from_db()
        assert teacher_user.sla_strikes == 1 and TeacherStrike.objects.get(booking=fourth).kind == 'serial_cancel'
        assert not CreditBundle.objects.exists()                                    # a strike, but no bonus: they gave notice

    def test_the_slot_stays_blocked_and_the_tutor_is_not_paid(self, teacher_user, student_user):
        b = captured(teacher_user, student_user, 5 * H)
        cancel(teacher_user.user, b)
        Booking.objects.filter(pk=b.pk).update(end_time_utc=timezone.now() - timedelta(hours=30))
        release_cleared_escrow_task()
        assert net(b, ACC.LIABILITY_TUTOR_PAYABLE) == 0

    def test_a_deactivated_tutors_other_lessons_are_not_touched(self, teacher_user, student_user):
        keep = captured(teacher_user, student_user, 60 * H, ref='KEEP')
        for n in range(3):
            cancel(teacher_user.user, captured(teacher_user, student_user, 5 * H + n, ref=f'D{n}'))
        assert reload(keep).status == S.CONFIRMED          # an admin routine deals with these (documented follow-up)


# ------------------------------------------------------------------ preview
@pytest.mark.django_db
class TestPreview:
    @pytest.mark.parametrize('user_kind,start,outcome', [
        ('student', 5 * H, 'full_refund'), ('student', 90, 'fee_forfeited'),
        ('teacher', 30 * H, 'tutor_refund'), ('teacher', 5 * H, 'tutor_refund_with_penalty')])
    def test_tells_each_party_what_would_happen_without_doing_it(self, teacher_user, student_user, user_kind, start, outcome):
        b = captured(teacher_user, student_user, start)
        user = student_user if user_kind == 'student' else teacher_user.user
        res = call(user, 'get', b, 'cancel-preview')
        assert res.status_code == 200
        body = res.json()
        assert body['outcome'] == outcome and body['can_cancel'] is True
        assert reload(b).status == S.CONFIRMED and not RefundRequest.objects.exists() and not TeacherStrike.objects.exists()
        if outcome in ('full_refund', 'tutor_refund', 'tutor_refund_with_penalty'):
            assert (Decimal(body['refund_amount']), body['refund_currency']) == (Decimal('168.75'), 'ZAR')

    def test_says_when_cancelling_is_not_possible(self, teacher_user, student_user):
        b = lesson(teacher_user, student_user, 5 * H, status=S.COMPLETED)
        body = call(student_user, 'get', b, 'cancel-preview').json()
        assert body['can_cancel'] is False and body['outcome'] == 'not_cancellable'

    def test_strangers_get_nothing(self, teacher_user, student_user):
        stranger = User.objects.create_user(username='nosy', email='n@x.com', password='x-pass-12345', role='student')
        b = captured(teacher_user, student_user, 5 * H)
        assert call(stranger, 'get', b, 'cancel-preview').status_code == 404
        assert call(None, 'get', b, 'cancel-preview').status_code == 401


@pytest.mark.django_db
class TestNoFundingRecord:
    """A confirmed lesson with no payment and no credit behind it (a data fault) must not be refunded from the list price."""

    def unfunded(self, teacher_user, student_user):
        start = timezone.now() + timedelta(hours=5)
        return Booking.objects.create(teacher=teacher_user, student=student_user, start_time_utc=start,
                                      end_time_utc=start + timedelta(minutes=25), status=S.CONFIRMED)

    def test_cancelling_is_refused_changes_nothing_and_alerts_finance(self, teacher_user, student_user):
        from apps.payments.models import SettlementAnomaly
        b = self.unfunded(teacher_user, student_user)
        res = cancel(student_user, b)
        assert res.status_code == 409 and res.json()['code'] == 'funding_unavailable'
        assert reload(b).status == S.CONFIRMED and b.cancelled_at is None
        assert not RefundRequest.objects.exists() and not CreditBundle.objects.exists() and not LedgerEntry.objects.exists()
        assert SettlementAnomaly.objects.filter(booking=b, code='missing_booking_funding', resolved=False).exists()

    def test_a_tutor_cannot_cancel_it_either_and_gets_no_strike(self, teacher_user, student_user):
        b = self.unfunded(teacher_user, student_user)
        assert cancel(teacher_user.user, b).status_code == 409
        assert reload(b).status == S.CONFIRMED and not TeacherStrike.objects.exists()

    def test_a_late_student_cancel_needs_no_refund_so_it_still_works(self, teacher_user, student_user):
        start = timezone.now() + timedelta(minutes=45)
        b = Booking.objects.create(teacher=teacher_user, student=student_user, start_time_utc=start,
                                   end_time_utc=start + timedelta(minutes=25), status=S.CONFIRMED)
        assert cancel(student_user, b, acknowledge_forfeit=True).status_code == 200
        assert reload(b).status == S.STUDENT_LATE_CANCELLED


@pytest.mark.django_db
def test_cancelled_lessons_show_up_in_the_admin_escrow_view(admin_user, teacher_user, student_user):
    """The finance view must list every outcome that moves money, including the three cancellation statuses."""
    refunded = captured(teacher_user, student_user, 5 * H, ref='ADM-1')
    kept = captured(teacher_user, student_user, 90, ref='ADM-2')
    by_tutor = captured(teacher_user, student_user, 30 * H, ref='ADM-3')
    assert cancel(student_user, refunded).status_code == 200
    assert cancel(student_user, kept, acknowledge_forfeit=True).status_code == 200
    assert cancel(teacher_user.user, by_tutor).status_code == 200
    c = APIClient(); c.force_authenticate(user=admin_user)
    items = {i['booking_ref']: i['escrow_status'] for i in c.get('/api/v1/admin/finance/ledger/?view=items').json()}
    ref = lambda b: f"BK-{str(b.id)[:6].upper()}"
    assert items[ref(refunded)] == 'refunded' and items[ref(by_tutor)] == 'refunded'
    assert items[ref(kept)] == 'holding'            # released to the tutor by the 24h job, not yet
