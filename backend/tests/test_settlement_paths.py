"""Task 9.7: where the money goes for outages, no-shows and arbitrated lessons - exactly once."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APIClient

from apps.admin_api.models import DisputeCase
from apps.bookings.models import AttendanceAudit, Booking
from apps.payments.models import CreditBundle, LedgerAccount, LedgerEntry, PaymentTransaction, RefundRequest
from apps.payments.services.credits import grant_credit
from apps.payments.services.webhook_handler import process_payment_webhook
from apps.payments.tasks import release_cleared_escrow_task
from apps.payments.services.funding import ensure_gateway_funding
from payment_helpers import captured, lesson, net  # noqa: F401  (re-exported: other test modules still import them from here)

S = Booking.Status
User = get_user_model()
MIN = timedelta(minutes=1)


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def force(booking, status, *, start_in_min=None):
    """Test-only: put a booking into a state the lifecycle would normally reach over time."""
    fields = {'status': status}
    if start_in_min is not None:
        start = timezone.now() + start_in_min * MIN
        fields.update(start_time_utc=start, end_time_utc=start + 25 * MIN)
    Booking.objects.filter(pk=booking.pk).update(**fields)
    booking.refresh_from_db()
    return booking


# ------------------------------------------------------------------ credits helper
@pytest.mark.django_db
class TestGrantCredit:
    def test_first_grant_creates_a_bundle_holding_exactly_the_credit(self, student_user):
        b = grant_credit(student_user, pack_name='x')
        assert (b.total_credits, b.remaining_credits) == (1, 1)

    def test_students_with_several_bundles_do_not_crash_and_stay_consistent(self, student_user):
        for _ in range(2):
            CreditBundle.objects.create(user=student_user, total_credits=5, remaining_credits=2, amount_paid=40)
        b = grant_credit(student_user, credits=2)
        assert CreditBundle.objects.filter(user=student_user).count() == 3
        assert (b.total_credits, b.remaining_credits) == (2, 2) and b.remaining_credits <= b.total_credits
        assert sum(x.remaining_credits for x in CreditBundle.objects.filter(user=student_user)) == 6

    def test_rejects_nonsense(self, student_user):
        with pytest.raises(ValueError):
            grant_credit(student_user, credits=0)


# ------------------------------------------------------------------ outage reports
@pytest.mark.django_db
class TestOutageReport:
    def report(self, user, booking, body=None):
        return _client(user).post(f'/api/v1/bookings/{booking.id}/report-outage/', body, format='json')

    @pytest.mark.parametrize('start_in_min,expected', [
        (60 * 48, 409),    # two days away: not a free cancellation
        (90, 409),         # more than 60 min before the start
        (30, 200),         # inside the pre-lesson window
        (-10, 200),        # lesson under way
        (-45, 200),        # ended 20 min ago (25-min lesson), still inside the 30-min tail
        (-70, 409),        # ended 45 min ago
    ])
    def test_reporting_window(self, teacher_user, student_user, start_in_min, expected):
        booking = lesson(teacher_user, student_user, start_in_min, status=S.CONFIRMED)
        res = self.report(teacher_user.user, booking)
        assert res.status_code == expected, res.json()
        booking.refresh_from_db()
        if expected == 409:
            assert booking.status == S.CONFIRMED
            assert not CreditBundle.objects.exists() and not LedgerEntry.objects.exists()
        else:
            assert booking.status == S.INTERRUPTED_POWER

    def test_who_may_report(self, teacher_user, student_user, admin_user):
        stranger = User.objects.create_user(username='nosy', email='n@x.com', password='x-pass-12345', role='student')
        other_tutor = User.objects.create_user(username='t2', email='t2@x.com', password='x-pass-12345', role='teacher')
        b1 = lesson(teacher_user, student_user, 10, status=S.CONFIRMED)
        for denied in (stranger, other_tutor):                            # not a party to the lesson
            res = self.report(denied, b1)
            assert res.status_code == 403 and res.json()['code'] == 'not_a_party'
        res = self.report(student_user, b1)                               # the student needs provider evidence of an outage
        assert res.status_code == 409 and res.json()['code'] == 'outage_unconfirmed'
        assert Booking.objects.get(pk=b1.pk).status == S.CONFIRMED
        assert self.report(teacher_user.user, b1).status_code == 200      # the tutor of the booking
        b2 = lesson(teacher_user, student_user, 40, status=S.CONFIRMED)
        assert self.report(admin_user, b2).status_code == 200             # staff

    def test_free_text_input_cannot_break_or_bloat_the_report(self, teacher_user, student_user):
        weird = [None, ['a', 'b'], {'reason': {'x': 1}}, {'reason': 'y' * 1000}]
        for n, body in enumerate(weird):
            booking = lesson(teacher_user, student_user, 10 + n, status=S.CONFIRMED)
            res = self.report(teacher_user.user, booking, body)
            assert res.status_code == 200, body
        from apps.bookings.models import BookingStatusChange
        assert max(len(r) for r in BookingStatusChange.objects.values_list('reason', flat=True)) <= 255

    def test_second_report_is_refused_and_settles_nothing_twice(self, teacher_user, student_user):
        booking = captured(teacher_user, student_user, 10)
        assert self.report(teacher_user.user, booking).status_code == 200
        assert self.report(teacher_user.user, booking).status_code == 409
        assert RefundRequest.objects.filter(booking=booking).count() == 1 and not CreditBundle.objects.exists()
        assert LedgerEntry.objects.filter(booking=booking, event_type=LedgerEntry.EventType.OUTAGE_REFUND).count() == 2

    def test_the_student_is_refunded_through_the_gateway_and_the_tutor_is_not_struck(self, teacher_user, student_user):
        booking = captured(teacher_user, student_user, 10)
        res = self.report(teacher_user.user, booking)
        assert res.status_code == 200
        refund = RefundRequest.objects.get(booking=booking)
        assert (refund.reason, refund.status, refund.amount, refund.currency) == ('outage', 'pending_gateway', Decimal('168.75'), 'ZAR')
        teacher_user.refresh_from_db()
        assert teacher_user.sla_strikes == 0
        assert net(booking, LedgerAccount.LIABILITY_REFUNDS_PAYABLE) == Decimal('168.75')

    def test_a_lesson_the_tutor_taught_is_delivered_not_an_outage(self, teacher_user, student_user):
        booking = force(captured(teacher_user, student_user, 10), S.CONFIRMED, start_in_min=-10)       # under way
        AttendanceAudit.objects.create(booking=booking, participant_email=teacher_user.user.email, total_minutes=20)
        res = self.report(teacher_user.user, booking)
        assert res.status_code == 409 and res.json()['code'] == 'lesson_delivered'
        booking.refresh_from_db()
        assert booking.status == S.CONFIRMED and not RefundRequest.objects.exists()
        AttendanceAudit.objects.filter(booking=booking).update(total_minutes=19)       # just under the line: an outage after all
        assert self.report(teacher_user.user, booking).status_code == 200

    def test_refund_drains_the_escrow_by_exactly_what_was_captured_in_its_currency(self, teacher_user, student_user):
        booking = captured(teacher_user, student_user, 10, amount='168.75', currency='ZAR')
        assert net(booking, LedgerAccount.LIABILITY_STUDENT_ESCROW) == Decimal('168.75')   # held
        assert self.report(teacher_user.user, booking).status_code == 200
        assert net(booking, LedgerAccount.LIABILITY_STUDENT_ESCROW) == 0                    # nothing left in limbo
        refund = LedgerEntry.objects.filter(booking=booking, event_type=LedgerEntry.EventType.OUTAGE_REFUND)
        assert {(e.amount, e.currency) for e in refund} == {(Decimal('168.75'), 'ZAR')}
        assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == 0                     # the tutor is not also paid

    def test_the_release_job_never_pays_for_an_interrupted_lesson(self, teacher_user, student_user):
        booking = captured(teacher_user, student_user, 10)
        assert self.report(teacher_user.user, booking).status_code == 200
        Booking.objects.filter(pk=booking.pk).update(end_time_utc=timezone.now() - timedelta(hours=30))
        AttendanceAudit.objects.create(booking=booking, participant_email=teacher_user.user.email, total_minutes=25)
        assert release_cleared_escrow_task()['cleared_count'] == 0
        assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == 0


# ------------------------------------------------------------------ student no-show -> tutor is paid
@pytest.mark.django_db
class TestStudentNoShowSettlement:
    def finished(self, teacher, student, hours_ago):
        booking = captured(teacher, student, 10)
        force(booking, S.STUDENT_NO_SHOW, start_in_min=-(hours_ago * 60 + 25))
        return booking

    def test_tutor_present_at_ten_minutes_earns_the_lesson_after_24h(self, teacher_user, student_user):
        booking = self.finished(teacher_user, student_user, hours_ago=25)
        AttendanceAudit.objects.create(booking=booking, participant_email=teacher_user.user.email, total_minutes=11)
        assert release_cleared_escrow_task()['cleared_count'] == 1
        booking.refresh_from_db()
        assert booking.status == S.STUDENT_NO_SHOW and booking.escrow_cleared_at is not None
        assert net(booking, LedgerAccount.LIABILITY_STUDENT_ESCROW) == 0
        assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == Decimal('135.00')            # 80% of R168.75
        assert net(booking, LedgerAccount.REVENUE_PLATFORM_COMMISSION) == Decimal('33.75')
        assert PaymentTransaction.objects.get(booking=booking, status='success').escrow_cleared is True

    def test_it_is_only_paid_once(self, teacher_user, student_user):
        booking = self.finished(teacher_user, student_user, hours_ago=25)
        AttendanceAudit.objects.create(booking=booking, participant_email=teacher_user.user.email, total_minutes=11)
        assert release_cleared_escrow_task()['cleared_count'] == 1
        assert release_cleared_escrow_task()['cleared_count'] == 0
        assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == Decimal('135.00')

    def test_not_before_the_24h_window(self, teacher_user, student_user):
        booking = self.finished(teacher_user, student_user, hours_ago=2)
        AttendanceAudit.objects.create(booking=booking, participant_email=teacher_user.user.email, total_minutes=11)
        assert release_cleared_escrow_task()['cleared_count'] == 0

    def test_not_without_proof_the_tutor_showed_up(self, teacher_user, student_user):
        booking = self.finished(teacher_user, student_user, hours_ago=25)
        assert release_cleared_escrow_task()['cleared_count'] == 0
        assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == 0

    def test_a_tutor_no_show_is_never_released_to_the_tutor(self, teacher_user, student_user):
        booking = captured(teacher_user, student_user, 10)
        force(booking, S.TEACHER_NO_SHOW, start_in_min=-(25 * 60 + 25))
        AttendanceAudit.objects.create(booking=booking, participant_email=teacher_user.user.email, total_minutes=30)
        assert release_cleared_escrow_task()['cleared_count'] == 0


@pytest.mark.django_db
def test_teacher_no_show_refund_drains_the_escrow_in_the_captured_currency(teacher_user, student_user):
    from apps.bookings.tasks import audit_attendance_and_noshows_task
    from unittest.mock import patch
    from apps.integrations.zoom import zoom_client
    booking = captured(teacher_user, student_user, 10)
    force(booking, S.CONFIRMED, start_in_min=-12)           # T+12m, nobody joined
    Booking.objects.filter(pk=booking.pk).update(zoom_meeting_id='98765432101')   # no room = disputed, not scored (F0)
    with patch.object(zoom_client, 'get_meeting_status', return_value={'status': 'waiting', 'participant_count': 0}):
        audit_attendance_and_noshows_task()
    booking.refresh_from_db()
    assert booking.status == S.TEACHER_NO_SHOW
    assert net(booking, LedgerAccount.LIABILITY_STUDENT_ESCROW) == 0
    assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == 0
    # D-6: the refund goes back through the gateway; the apology is 1 bonus credit (not a second refund)
    assert RefundRequest.objects.get(booking=booking).status == 'pending_gateway'
    bonus = CreditBundle.objects.get(user=student_user)
    assert (bonus.source, bonus.remaining_credits, bonus.currency, bonus.unit_amount) == ('bonus', 1, 'ZAR', Decimal('168.75'))
    teacher_user.refresh_from_db()
    assert teacher_user.sla_strikes == 1


# ------------------------------------------------------------------ arbitration + release job must not both pay
@pytest.mark.django_db
class TestNoDoubleSettlement:
    def resolve(self, admin, booking, resolution):
        d = DisputeCase.objects.create(booking=booking, student=booking.student, teacher=booking.teacher, student_statement='x')
        res = _client(admin).post(f'/api/v1/admin/disputes/{d.id}/resolve/', {'resolution': resolution}, format='json')
        assert res.status_code == 200, res.json()
        return d

    @pytest.mark.parametrize('resolution', ['release_tutor', 'split_50_50'])
    def test_tutor_paid_by_arbitration_is_not_paid_again_by_the_24h_job(self, admin_user, teacher_user, student_user, resolution):
        booking = captured(teacher_user, student_user, 10)
        force(booking, S.DISPUTED, start_in_min=-(30 * 60))
        AttendanceAudit.objects.create(booking=booking, participant_email=teacher_user.user.email, total_minutes=25)
        self.resolve(admin_user, booking, resolution)
        booking.refresh_from_db()
        paid_once = net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE)
        assert paid_once > 0 and booking.escrow_cleared_at is not None
        assert PaymentTransaction.objects.get(booking=booking, status='success').escrow_cleared is True

        assert release_cleared_escrow_task()['cleared_count'] == 0
        assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == paid_once
        assert net(booking, LedgerAccount.LIABILITY_STUDENT_ESCROW) >= 0   # never driven negative

    def test_the_ledger_alone_blocks_a_second_payment_even_if_the_cleared_marker_is_missing(self, admin_user, teacher_user, student_user):
        booking = captured(teacher_user, student_user, 10)
        force(booking, S.DISPUTED, start_in_min=-(30 * 60))
        AttendanceAudit.objects.create(booking=booking, participant_email=teacher_user.user.email, total_minutes=25)
        self.resolve(admin_user, booking, 'release_tutor')
        Booking.objects.filter(pk=booking.pk).update(escrow_cleared_at=None)    # e.g. a booking settled before this fix
        assert release_cleared_escrow_task()['cleared_count'] == 0

    def test_a_refunded_dispute_never_reaches_the_tutor(self, admin_user, teacher_user, student_user):
        booking = captured(teacher_user, student_user, 10)
        force(booking, S.DISPUTED, start_in_min=-(30 * 60))
        self.resolve(admin_user, booking, 'full_refund_student')
        assert release_cleared_escrow_task()['cleared_count'] == 0
        assert net(booking, LedgerAccount.LIABILITY_STUDENT_ESCROW) == 0
        assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == 0

    def test_completed_lessons_still_pay_the_tutor_exactly_once(self, teacher_user, student_user):
        booking = captured(teacher_user, student_user, 10)
        force(booking, S.COMPLETED_PENDING_MEMO, start_in_min=-(30 * 60))
        AttendanceAudit.objects.create(booking=booking, participant_email=teacher_user.user.email, total_minutes=24)
        assert release_cleared_escrow_task()['cleared_count'] == 1
        assert release_cleared_escrow_task()['cleared_count'] == 0
        assert net(booking, LedgerAccount.LIABILITY_TUTOR_PAYABLE) == Decimal('135.00')

    def test_completed_lesson_with_too_little_teacher_time_is_held(self, teacher_user, student_user):
        booking = captured(teacher_user, student_user, 10)
        force(booking, S.COMPLETED_PENDING_MEMO, start_in_min=-(30 * 60))
        AttendanceAudit.objects.create(booking=booking, participant_email=teacher_user.user.email, total_minutes=12)
        assert release_cleared_escrow_task()['cleared_count'] == 0


# ------------------------------------------------------------------ admin escrow view
@pytest.mark.django_db
def test_admin_escrow_view_shows_every_outcome_that_moves_money(admin_user, teacher_user, student_user):
    interrupted = captured(teacher_user, student_user, 10, ref='A')
    _client(teacher_user.user).post(f'/api/v1/bookings/{interrupted.id}/report-outage/')
    ns = captured(teacher_user, student_user, 600, ref='B')
    force(ns, S.STUDENT_NO_SHOW, start_in_min=-(30 * 60))
    AttendanceAudit.objects.create(booking=ns, participant_email=teacher_user.user.email, total_minutes=11)
    release_cleared_escrow_task()
    items = _client(admin_user).get('/api/v1/admin/finance/ledger/?view=items').json()
    by_ref = {i['booking_ref']: i['escrow_status'] for i in items}
    assert by_ref[f"BK-{str(interrupted.id)[:6].upper()}"] == 'refunded'
    assert by_ref[f"BK-{str(ns.id)[:6].upper()}"] == 'cleared'
