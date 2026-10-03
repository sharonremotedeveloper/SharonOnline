"""Task 9.1: the booking state machine and its audit trail."""
import ast
import itertools
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.admin_api.models import DisputeCase
from apps.bookings.models import Booking, BookingStatusChange, LessonMemo
from apps.bookings.services.state_machine import (
    ALLOWED_TRANSITIONS, TERMINAL_STATUSES, InvalidTransition, can_transition, transition_booking,
)
from apps.payments.models import CreditBundle, RefundRequest, PaymentTransaction
from apps.payments.services.funding import ensure_gateway_funding
from apps.payments.services.webhook_handler import process_payment_webhook

S = Booking.Status
ALL = list(Booking.Status.values)


def make_booking(teacher, student, status=S.CONFIRMED, offset_hours=48, **kw):
    funded = kw.pop('funded', False)
    start = timezone.now() + timedelta(hours=offset_hours)
    booking = Booking.objects.create(teacher=teacher, student=student, start_time_utc=start,
                                     end_time_utc=start + timedelta(minutes=25), status=status, **kw)
    if funded:
        tx = PaymentTransaction.objects.create(
            booking=booking, gateway='paypal', gateway_reference=f'TEST-{booking.id}',
            amount=Decimal('9.00'), currency='USD', status='success')
        ensure_gateway_funding(tx, booking)
    return booking


# ------------------------------------------------------------------ the map itself
class TestTransitionMap:
    def test_every_status_has_an_entry_and_targets_are_real_statuses(self):
        assert set(ALLOWED_TRANSITIONS) == set(ALL)
        for src, targets in ALLOWED_TRANSITIONS.items():
            assert targets <= set(ALL), src
            assert src not in targets, f"{src} must not list itself (same-status requests are no-ops)"

    def test_every_status_is_reachable_from_a_new_booking(self):
        seen, frontier = {S.PENDING_PAYMENT}, [S.PENDING_PAYMENT]
        while frontier:
            for nxt in ALLOWED_TRANSITIONS[frontier.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
        assert seen == set(ALL)

    def test_only_an_outage_and_the_three_cancellations_are_terminal(self):
        assert TERMINAL_STATUSES == {S.INTERRUPTED_POWER, S.CANCELLED_BY_STUDENT, S.STUDENT_LATE_CANCELLED, S.CANCELLED_BY_TEACHER}

    def test_a_late_payment_can_never_resurrect_a_cancelled_paid_lesson(self):
        # CANCELLED may be re-confirmed by a late payment; the paid-and-refunded outcomes must not be
        for dead in (S.CANCELLED_BY_STUDENT, S.STUDENT_LATE_CANCELLED, S.CANCELLED_BY_TEACHER):
            assert not can_transition(dead, S.CONFIRMED) and not can_transition(dead, S.DISPUTED)
        for source in (S.PENDING_PAYMENT, S.IN_PROGRESS, S.COMPLETED):
            assert not can_transition(source, S.CANCELLED_BY_STUDENT)
        assert all(can_transition(S.CONFIRMED, t) for t in (S.CANCELLED_BY_STUDENT, S.STUDENT_LATE_CANCELLED, S.CANCELLED_BY_TEACHER))

    def test_cannot_pay_for_a_lesson_twice_or_resurrect_a_finished_one(self):
        assert not can_transition(S.CONFIRMED, S.PENDING_PAYMENT)
        assert not can_transition(S.COMPLETED, S.CONFIRMED)
        assert not can_transition(S.COMPLETED, S.CANCELLED)
        assert not can_transition(S.INTERRUPTED_POWER, S.COMPLETED)
        assert not can_transition(S.PENDING_PAYMENT, S.COMPLETED)  # an unpaid hold can never be 'completed'


@pytest.mark.django_db
@pytest.mark.parametrize('src,dst', list(itertools.product(ALL, ALL)))
def test_every_pair_behaves_as_the_map_says(teacher_user, student_user, src, dst):
    booking = make_booking(teacher_user, student_user, status=src)
    if src == dst:
        result = transition_booking(booking, dst, actor='system:test')
        assert (result.changed, booking.status) == (False, src)
        assert BookingStatusChange.objects.count() == 0
    elif dst in ALLOWED_TRANSITIONS[src]:
        result = transition_booking(booking, dst, actor='system:test', reason='because')
        assert (result.changed, result.from_status, result.to_status) == (True, src, dst)
        booking.refresh_from_db()
        assert booking.status == dst
        change = BookingStatusChange.objects.get()
        assert (change.from_status, change.to_status, change.actor, change.reason) == (src, dst, 'system:test', 'because')
    else:
        with pytest.raises(InvalidTransition) as exc:
            transition_booking(booking, dst, actor='system:test')
        assert (exc.value.from_status, exc.value.to_status) == (src, dst)
        booking.refresh_from_db()
        assert booking.status == src
        assert BookingStatusChange.objects.count() == 0


# ------------------------------------------------------------------ function contract
@pytest.mark.django_db
class TestTransitionBooking:
    def test_decides_on_the_database_not_on_a_stale_instance(self, teacher_user, student_user):
        booking = make_booking(teacher_user, student_user, status=S.CONFIRMED)
        stale = Booking.objects.get(pk=booking.pk)
        Booking.objects.filter(pk=booking.pk).update(status=S.COMPLETED)  # someone else moved it on
        with pytest.raises(InvalidTransition):
            transition_booking(stale, S.IN_PROGRESS, actor='system:test')
        assert Booking.objects.get(pk=booking.pk).status == S.COMPLETED

    def test_a_replayed_request_is_a_noop_so_side_effects_run_once(self, teacher_user, student_user):
        booking = make_booking(teacher_user, student_user, status=S.CONFIRMED)
        first = transition_booking(booking, S.IN_PROGRESS, actor='system:test')
        replay = transition_booking(Booking.objects.get(pk=booking.pk), S.IN_PROGRESS, actor='system:test')
        assert (first.changed, replay.changed) == (True, False)
        assert BookingStatusChange.objects.count() == 1

    def test_user_actor_is_recorded_with_name_and_fk(self, teacher_user, student_user, admin_user):
        booking = make_booking(teacher_user, student_user, status=S.DISPUTED)
        transition_booking(booking, S.COMPLETED, actor=admin_user, reason='x' * 400)
        change = BookingStatusChange.objects.get()
        assert change.actor == 'user:test_admin' and change.actor_user == admin_user
        assert len(change.reason) == 255

    def test_requires_an_actor_and_a_real_status(self, teacher_user, student_user):
        booking = make_booking(teacher_user, student_user, status=S.CONFIRMED)
        with pytest.raises(ValueError):
            transition_booking(booking, S.IN_PROGRESS, actor=None)
        with pytest.raises(ValueError):
            transition_booking(booking, 'teleported', actor='system:test')

    def test_failed_save_leaves_instance_and_audit_untouched(self, teacher_user, student_user):
        """The partial unique index on active slots rejects a second CONFIRMED booking for one teacher+time."""
        first = make_booking(teacher_user, student_user, status=S.CONFIRMED, offset_hours=72)
        rival = Booking.objects.create(teacher=teacher_user, student=student_user, start_time_utc=first.start_time_utc,
                                       end_time_utc=first.end_time_utc, status=S.PENDING_PAYMENT)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                transition_booking(rival, S.CONFIRMED, actor='system:test')
        assert rival.status == S.PENDING_PAYMENT
        assert BookingStatusChange.objects.count() == 0

    def test_extra_columns_are_saved_in_the_same_write(self, teacher_user, student_user):
        booking = make_booking(teacher_user, student_user, status=S.CONFIRMED)
        booking.zoom_meeting_id = '123'
        transition_booking(booking, S.IN_PROGRESS, actor='system:test', update_fields=['zoom_meeting_id'])
        assert Booking.objects.get(pk=booking.pk).zoom_meeting_id == '123'


# ------------------------------------------------------------------ the call sites
def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.mark.django_db
class TestMemo:
    def url(self, booking):
        return f'/api/v1/bookings/{booking.id}/memo/'

    @pytest.mark.parametrize('status', [S.PENDING_PAYMENT, S.CANCELLED, S.CONFIRMED, S.IN_PROGRESS, S.DISPUTED, S.INTERRUPTED_POWER,
                                        S.TEACHER_NO_SHOW, S.STUDENT_NO_SHOW])
    def test_memo_rejected_unless_the_lesson_actually_happened(self, teacher_user, student_user, status):
        booking = make_booking(teacher_user, student_user, status=status)
        res = _client(teacher_user.user).post(self.url(booking), {'feedback_text': 'x'}, format='json')
        assert res.status_code == 409
        assert LessonMemo.objects.count() == 0 and Booking.objects.get(pk=booking.pk).status == status

    @pytest.mark.parametrize('status', [S.COMPLETED_PENDING_MEMO, S.COMPLETED_MEMO_FORFEITED, S.COMPLETED])
    def test_memo_completes_the_booking_and_is_audited(self, teacher_user, student_user, status):
        booking = make_booking(teacher_user, student_user, status=status, offset_hours=-3)
        res = _client(teacher_user.user).post(self.url(booking), {'feedback_text': 'good'}, format='json')
        assert res.status_code == 200
        assert Booking.objects.get(pk=booking.pk).status == S.COMPLETED
        assert LessonMemo.objects.filter(booking=booking).exists()
        expected = 0 if status == S.COMPLETED else 1
        assert BookingStatusChange.objects.filter(booking=booking, actor='user:test_tutor').count() == expected


@pytest.mark.django_db
class TestOutage:
    def test_outage_is_audited_and_credits_once(self, teacher_user, student_user):
        booking = make_booking(teacher_user, student_user, status=S.CONFIRMED, offset_hours=0.1, funded=True)  # starts in 6 min
        c = _client(teacher_user.user)
        assert c.post(f'/api/v1/bookings/{booking.id}/report-outage/').status_code == 200
        assert c.post(f'/api/v1/bookings/{booking.id}/report-outage/').status_code == 409
        assert RefundRequest.objects.filter(booking=booking, reason='outage').count() == 1       # one gateway refund, not two
        assert not CreditBundle.objects.filter(user=student_user).exists()
        change = BookingStatusChange.objects.get(booking=booking)
        assert (change.from_status, change.to_status, change.actor) == (S.CONFIRMED, S.INTERRUPTED_POWER, 'user:test_tutor')


@pytest.mark.django_db
class TestDisputeResolution:
    def _dispute(self, teacher_user, student_user, status=S.DISPUTED):
        booking = make_booking(teacher_user, student_user, status=status, offset_hours=-3, funded=True)
        return DisputeCase.objects.create(booking=booking, student=student_user, teacher=teacher_user, student_statement='x')

    def resolve(self, admin, dispute, resolution='full_refund_student'):
        return _client(admin).post(f'/api/v1/admin/disputes/{dispute.id}/resolve/', {'resolution': resolution}, format='json')

    @pytest.mark.parametrize('resolution,expected', [('full_refund_student', S.CANCELLED), ('release_tutor', S.COMPLETED),
                                                    ('split_50_50', S.COMPLETED)])
    def test_resolution_moves_the_booking_and_is_audited(self, admin_user, teacher_user, student_user, resolution, expected):
        d = self._dispute(teacher_user, student_user)
        assert self.resolve(admin_user, d, resolution).status_code == 200
        d.booking.refresh_from_db()
        assert d.booking.status == expected
        change = BookingStatusChange.objects.get(booking=d.booking)
        assert (change.from_status, change.to_status, change.actor) == (S.DISPUTED, expected, 'user:test_admin')

    def test_a_dispute_cannot_be_resolved_twice(self, admin_user, teacher_user, student_user):
        d = self._dispute(teacher_user, student_user)
        assert self.resolve(admin_user, d).status_code == 200
        second = self.resolve(admin_user, d, 'release_tutor')
        assert second.status_code == 409
        d.refresh_from_db(); d.booking.refresh_from_db()
        assert (d.resolution, d.booking.status) == ('full_refund_student', S.CANCELLED)
        assert RefundRequest.objects.filter(booking=d.booking, reason='dispute').count() == 1  # refunded once, not twice

    def test_an_already_resolved_dispute_is_refused_even_if_its_booking_is_disputed_again(self, admin_user, teacher_user, student_user):
        d = self._dispute(teacher_user, student_user)
        DisputeCase.objects.filter(pk=d.pk).update(status=DisputeCase.Status.RESOLVED, resolution='release_tutor')
        res = self.resolve(admin_user, d)
        assert res.status_code == 409 and 'already been resolved' in res.json()['error']
        assert Booking.objects.get(pk=d.booking.pk).status == S.DISPUTED and not CreditBundle.objects.exists()

    def test_booking_must_actually_be_awaiting_arbitration(self, admin_user, teacher_user, student_user):
        d = self._dispute(teacher_user, student_user, status=S.COMPLETED)
        assert self.resolve(admin_user, d).status_code == 409
        d.refresh_from_db()
        assert d.status == DisputeCase.Status.OPEN and not CreditBundle.objects.exists()

    def test_unknown_dispute_is_404(self, admin_user):
        import uuid
        assert _client(admin_user).post(f'/api/v1/admin/disputes/{uuid.uuid4()}/resolve/', {'resolution': 'release_tutor'},
                                        format='json').status_code == 404


@pytest.mark.django_db
class TestBackgroundJobs:
    def test_purge_cancels_only_expired_unpaid_holds_and_audits_it(self, teacher_user, student_user):
        from apps.bookings.tasks import purge_expired_reservations_task
        stale = make_booking(teacher_user, student_user, status=S.PENDING_PAYMENT, offset_hours=30)
        paid = make_booking(teacher_user, student_user, status=S.CONFIRMED, offset_hours=31)
        fresh = make_booking(teacher_user, student_user, status=S.PENDING_PAYMENT, offset_hours=32)
        old = timezone.now() - timedelta(minutes=11)
        Booking.objects.filter(pk__in=[stale.pk, paid.pk]).update(created_at=old)
        assert purge_expired_reservations_task()['purged_count'] == 1
        assert Booking.objects.get(pk=stale.pk).status == S.CANCELLED
        assert Booking.objects.get(pk=paid.pk).status == S.CONFIRMED
        assert Booking.objects.get(pk=fresh.pk).status == S.PENDING_PAYMENT
        change = BookingStatusChange.objects.get()
        assert change.actor == 'system:purge_expired_reservations' and change.booking_id == stale.pk

    def test_memo_sla_forfeits_unmemoed_lessons_but_not_memoed_ones(self, teacher_user, student_user):
        from apps.bookings.tasks import enforce_memo_sla_task
        late = make_booking(teacher_user, student_user, status=S.COMPLETED_PENDING_MEMO, offset_hours=-30, funded=True)
        done = make_booking(teacher_user, student_user, status=S.COMPLETED_PENDING_MEMO, offset_hours=-31)
        LessonMemo.objects.create(booking=done, teacher=teacher_user, student=student_user, feedback_text='ok')
        assert enforce_memo_sla_task()['memos_forfeited'] == 1
        assert Booking.objects.get(pk=late.pk).status == S.COMPLETED_MEMO_FORFEITED
        assert Booking.objects.get(pk=done.pk).status == S.COMPLETED_PENDING_MEMO
        assert BookingStatusChange.objects.get().actor == 'system:memo_sla'

    def test_memo_sla_skips_a_booking_whose_memo_arrived_after_the_query(self, teacher_user, student_user, monkeypatch):
        """Race: the candidate list was built, then the teacher submitted the memo before the job reached the row."""
        from apps.bookings import tasks
        late = make_booking(teacher_user, student_user, status=S.COMPLETED_PENDING_MEMO, offset_hours=-30)
        real_filter = tasks.LessonMemo.objects.filter
        LessonMemo.objects.create(booking=late, teacher=teacher_user, student=student_user, feedback_text='just in time')
        # The candidate query filters memo__isnull=True, so force the row through to hit the in-lock re-check.
        monkeypatch.setattr(tasks.Booking.objects, 'filter', lambda *a, **k: Booking.objects.all().filter(pk=late.pk), raising=False)
        tasks.enforce_memo_sla_task()
        assert Booking.objects.get(pk=late.pk).status == S.COMPLETED_PENDING_MEMO

    def test_escrow_release_completes_pending_memo_lessons_with_audit(self, teacher_user, student_user):
        from apps.bookings.models import AttendanceAudit
        from apps.payments.tasks import release_cleared_escrow_task
        booking = make_booking(teacher_user, student_user, status=S.COMPLETED_PENDING_MEMO, offset_hours=-30, funded=True)
        AttendanceAudit.objects.create(booking=booking, participant_email=teacher_user.user.email, total_minutes=24)
        assert release_cleared_escrow_task()['cleared_count'] == 1
        assert Booking.objects.get(pk=booking.pk).status == S.COMPLETED
        assert BookingStatusChange.objects.get().actor == 'system:escrow_release'


@pytest.mark.django_db
class TestPaymentWebhook:
    def pay(self, booking, ref='TX-1'):
        return process_payment_webhook(booking_id=str(booking.id), gateway='paypal', transaction_id=ref, amount=9.00,
                                       currency='USD', status='success', raw_payload={})

    def test_payment_confirms_and_is_audited(self, teacher_user, student_user, django_capture_on_commit_callbacks):
        booking = make_booking(teacher_user, student_user, status=S.PENDING_PAYMENT)
        with django_capture_on_commit_callbacks(execute=False):
            self.pay(booking)
        change = BookingStatusChange.objects.get()
        assert (change.from_status, change.to_status, change.actor) == (S.PENDING_PAYMENT, S.CONFIRMED, 'system:paypal_webhook')

    def test_late_payment_on_a_rebooked_slot_is_quarantined_and_audited(self, teacher_user, student_user):
        mine = make_booking(teacher_user, student_user, status=S.CANCELLED, offset_hours=50)
        Booking.objects.create(teacher=teacher_user, student=student_user, start_time_utc=mine.start_time_utc,
                               end_time_utc=mine.end_time_utc, status=S.CONFIRMED)
        self.pay(mine, 'TX-LATE')
        assert Booking.objects.get(pk=mine.pk).status == S.DISPUTED
        change = BookingStatusChange.objects.get(booking=mine)
        assert (change.from_status, change.to_status) == (S.CANCELLED, S.DISPUTED) and 'DEF-501' in change.reason

    def test_payment_for_a_finished_booking_never_touches_it(self, teacher_user, student_user):
        booking = make_booking(teacher_user, student_user, status=S.COMPLETED, offset_hours=-5)
        self.pay(booking, 'TX-SURPLUS')
        assert Booking.objects.get(pk=booking.pk).status == S.COMPLETED
        assert BookingStatusChange.objects.count() == 0


# ------------------------------------------------------------------ enforcement
APPS = Path(__file__).resolve().parents[1] / 'apps'
ALLOWED_WRITERS = {APPS / 'bookings' / 'services' / 'state_machine.py'}


def _status_writes(path):
    """Assignments like `x.status = Booking.Status.Y` / `x.status = S.Y` and `.update(status=Booking.Status...)`."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == 'status' and 'Booking.Status' in ast.unparse(node.value):
                    hits.append((node.lineno, ast.unparse(node)))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {'update', 'bulk_update'}:
            for kw in node.keywords:
                if kw.arg == 'status' and 'Booking.Status' in ast.unparse(kw.value):
                    hits.append((node.lineno, ast.unparse(node)))
    return hits


class TestNoDirectStatusWrites:
    def test_only_the_state_machine_writes_booking_status(self):
        offenders = []
        for path in APPS.rglob('*.py'):
            if 'migrations' in path.parts or path in ALLOWED_WRITERS:
                continue
            offenders += [f"{path.relative_to(APPS)}:{line}: {code}" for line, code in _status_writes(path)]
        assert not offenders, "Route these through transition_booking():\n" + "\n".join(offenders)

    def test_the_detector_actually_detects(self, tmp_path):
        bad = tmp_path / 'bad.py'
        bad.write_text("b.status = Booking.Status.COMPLETED\nBooking.objects.filter().update(status=Booking.Status.CANCELLED)\n"
                       "tx.status = PaymentTransaction.Status.SUCCESS\n")
        assert len(_status_writes(bad)) == 2
