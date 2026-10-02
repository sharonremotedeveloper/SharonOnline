"""Task 9.4: the purge job must not cancel a booking whose payment is in flight; late payments settle safely."""
import uuid
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking, BookingStatusChange
from apps.bookings.services.holds import hold_expires_at, hold_is_live, live_hold_q
from apps.bookings.services.lock_service import acquire_slot_lock, extend_slot_lock, is_slot_locked
from apps.bookings.tasks import purge_expired_reservations_task
from apps.payments.models import PaymentTransaction
from apps.payments.services.webhook_handler import process_payment_webhook
from django.contrib.auth import get_user_model

S = Booking.Status
TX = PaymentTransaction.Status
User = get_user_model()
MIN = timedelta(minutes=1)


def hold(teacher, student, age_min, offset_hours=48, status=S.PENDING_PAYMENT):
    """A booking whose reservation was made `age_min` minutes ago."""
    start = timezone.now() + timedelta(hours=offset_hours)
    b = Booking.objects.create(teacher=teacher, student=student, start_time_utc=start,
                               end_time_utc=start + timedelta(minutes=25), status=status)
    Booking.objects.filter(pk=b.pk).update(created_at=timezone.now() - age_min * MIN)
    b.refresh_from_db()
    return b


def pay_attempt(booking, age_min=1, status=TX.INITIALIZED, ref=None):
    ref = ref or f"TX-{uuid.uuid4().hex[:8]}"
    tx = PaymentTransaction.objects.create(booking=booking, gateway='paypal', gateway_reference=f"INIT-{ref}",
                                           merchant_reference=ref, amount='9.00', currency='USD', status=status)
    PaymentTransaction.objects.filter(pk=tx.pk).update(created_at=timezone.now() - age_min * MIN)
    tx.refresh_from_db()
    return tx


def lock(booking):
    assert acquire_slot_lock(str(booking.teacher_id), booking.start_time_utc.isoformat(), str(booking.student_id))


# ------------------------------------------------------------------ the hold definition
@pytest.mark.django_db
class TestHoldDefinition:
    def test_plain_hold_lasts_ten_minutes(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=4)
        assert hold_expires_at(b) == b.created_at + 10 * MIN
        assert hold_is_live(b)
        assert not hold_is_live(hold(teacher_user, student_user, age_min=11, offset_hours=50))

    def test_fresh_payment_attempt_extends_the_hold_by_the_grace_period(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=9)
        tx = pay_attempt(b, age_min=0)
        assert hold_expires_at(b) == tx.created_at + 15 * MIN
        assert hold_expires_at(b) > b.created_at + 10 * MIN
        assert hold_is_live(b)

    def test_attempt_older_than_grace_or_not_initialized_extends_nothing(self, teacher_user, student_user):
        base_age = 12
        for n, (age, status) in enumerate([(16, TX.INITIALIZED), (2, TX.FAILED), (2, TX.SUCCESS), (2, TX.UNALLOCATED)]):
            b = hold(teacher_user, student_user, age_min=base_age, offset_hours=60 + n)
            pay_attempt(b, age_min=age, status=status)
            assert hold_expires_at(b) == b.created_at + 10 * MIN, (age, status)
            assert not hold_is_live(b)

    def test_hard_cap_stops_endless_payment_retries(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=29)
        pay_attempt(b, age_min=0)
        assert hold_expires_at(b) == b.created_at + 30 * MIN  # not tx+15
        b2 = hold(teacher_user, student_user, age_min=31, offset_hours=70)
        pay_attempt(b2, age_min=0)
        assert not hold_is_live(b2)

    def test_live_hold_q_matches_hold_is_live(self, teacher_user, student_user):
        cases = [hold(teacher_user, student_user, age_min=a, offset_hours=80 + i) for i, a in enumerate([2, 11, 12, 31])]
        pay_attempt(cases[2], age_min=1)
        pay_attempt(cases[3], age_min=1)
        live = set(Booking.objects.filter(live_hold_q(timezone.now())).values_list('pk', flat=True))
        assert live == {b.pk for b in cases if hold_is_live(b)} == {cases[0].pk, cases[2].pk}


# ------------------------------------------------------------------ purge job
@pytest.mark.django_db
class TestPurge:
    def test_cancels_expired_unpaid_holds(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=11)
        lock(b)
        assert purge_expired_reservations_task()['purged_count'] == 1
        assert Booking.objects.get(pk=b.pk).status == S.CANCELLED
        assert not is_slot_locked(str(b.teacher_id), b.start_time_utc.isoformat())

    def test_spares_a_booking_with_a_payment_in_flight(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=11)
        pay_attempt(b, age_min=3)
        lock(b)
        assert purge_expired_reservations_task()['purged_count'] == 0
        assert Booking.objects.get(pk=b.pk).status == S.PENDING_PAYMENT
        assert is_slot_locked(str(b.teacher_id), b.start_time_utc.isoformat())
        assert BookingStatusChange.objects.count() == 0

    @pytest.mark.parametrize('age,status', [(16, TX.INITIALIZED), (3, TX.FAILED)])
    def test_cancels_once_the_attempt_is_stale_or_has_failed(self, teacher_user, student_user, age, status):
        b = hold(teacher_user, student_user, age_min=20)
        pay_attempt(b, age_min=age, status=status)
        assert purge_expired_reservations_task()['purged_count'] == 1

    def test_hard_cap_wins_over_a_fresh_attempt(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=31)
        pay_attempt(b, age_min=0)
        assert purge_expired_reservations_task()['purged_count'] == 1

    def test_only_the_abandoned_one_is_purged(self, teacher_user, student_user):
        paying = hold(teacher_user, student_user, age_min=12, offset_hours=40)
        pay_attempt(paying, age_min=2)
        abandoned = hold(teacher_user, student_user, age_min=12, offset_hours=41)
        fresh = hold(teacher_user, student_user, age_min=1, offset_hours=42)
        assert purge_expired_reservations_task()['purged_count'] == 1
        assert Booking.objects.get(pk=abandoned.pk).status == S.CANCELLED
        assert Booking.objects.get(pk=paying.pk).status == S.PENDING_PAYMENT
        assert Booking.objects.get(pk=fresh.pk).status == S.PENDING_PAYMENT


# ------------------------------------------------------------------ slot lock extension
@pytest.mark.django_db
class TestExtendSlotLock:
    def test_owner_extends_lapsed_free_lock_is_retaken_stranger_is_refused(self):
        t, ts = 'teacher-1', '2026-12-01T10:00:00+00:00'
        assert extend_slot_lock(t, ts, 'alice', 900)            # nothing there: re-take
        assert is_slot_locked(t, ts)
        assert extend_slot_lock(t, ts, 'alice', 900)            # own lock: extend
        assert not extend_slot_lock(t, ts, 'bob', 900)          # someone else's: untouched
        assert cache.get(f"lock:slot:{t}:{ts}") == 'alice'


# ------------------------------------------------------------------ checkout
def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.mark.django_db
class TestCheckoutGuards:
    def checkout(self, user, booking):
        return _client(user).post('/api/v1/payments/checkout/init/', {'booking_id': str(booking.id), 'gateway': 'paypal'}, format='json')

    def test_live_hold_starts_payment_and_keeps_the_lock(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=9)
        lock(b)
        res = self.checkout(student_user, b)
        assert res.status_code == 200 and PaymentTransaction.objects.filter(booking=b).count() == 1
        assert is_slot_locked(str(b.teacher_id), b.start_time_utc.isoformat())
        assert hold_expires_at(b) > b.created_at + 10 * MIN  # now extended by the in-flight attempt
        from datetime import datetime
        assert datetime.fromisoformat(res.json()['hold_expires_at']) == hold_expires_at(b)  # the UI timer follows this

    def test_expired_reservation_cannot_start_a_payment(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=11)
        res = self.checkout(student_user, b)
        assert res.status_code == 409 and 'expired' in res.json()['error']
        assert not PaymentTransaction.objects.exists()

    def test_a_retry_inside_the_grace_window_is_allowed(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=12)
        pay_attempt(b, age_min=4)  # an earlier attempt keeps the hold alive
        lock(b)
        assert self.checkout(student_user, b).status_code == 200

    def test_slot_already_booked_by_someone_else_is_refused_before_any_money_moves(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=2)
        other = User.objects.create_user(username='other', email='o@x.com', password='x-pass-12345')
        Booking.objects.create(teacher=teacher_user, student=other, start_time_utc=b.start_time_utc,
                               end_time_utc=b.end_time_utc, status=S.CONFIRMED)
        res = self.checkout(student_user, b)
        assert res.status_code == 409 and 'booked by someone else' in res.json()['error']
        assert not PaymentTransaction.objects.exists()

    def test_lock_lost_to_another_student_is_refused(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=2)
        assert acquire_slot_lock(str(b.teacher_id), b.start_time_utc.isoformat(), 'someone-else')
        res = self.checkout(student_user, b)
        assert res.status_code == 409 and 'just been taken' in res.json()['error']
        assert not PaymentTransaction.objects.exists()


# ------------------------------------------------------------------ reservation guard
@pytest.mark.django_db
def test_second_student_cannot_reserve_a_slot_whose_payment_is_in_flight(teacher_user, student_user):
    """Redis lock lapsed at minute 10, but student A is still paying: the database says the slot is held."""
    from apps.bookings.services.reservation import ReservationError, reserve_slot
    b = hold(teacher_user, student_user, age_min=12)
    pay_attempt(b, age_min=2)
    other = User.objects.create_user(username='b2', email='b2@x.com', password='x-pass-12345', role='student')
    assert not is_slot_locked(str(b.teacher_id), b.start_time_utc.isoformat())  # nothing holds the Redis key
    # The generator does not know this slot yet (not in the tutor's availability), so exercise the DB guard directly:
    import apps.bookings.services.reservation as r
    r_slot = {'start_time_utc': b.start_time_utc.isoformat(), 'is_bookable': True}
    from unittest import mock
    with mock.patch.object(r, 'generate_teacher_slots', return_value=[r_slot]):
        with pytest.raises(ReservationError) as exc:
            reserve_slot(student=other, teacher_id=teacher_user.id, start_time_utc=b.start_time_utc)
    assert exc.value.status_code == 409
    assert Booking.objects.filter(student=other).count() == 0


# ------------------------------------------------------------------ late payments after the hold lapsed
@pytest.mark.django_db
class TestLatePayment:
    def pay(self, booking, ref):
        return process_payment_webhook(booking_id=str(booking.id), gateway='paypal', transaction_id=ref, amount=9.00,
                                       currency='USD', status='success', raw_payload={})

    def test_payment_landing_while_in_flight_confirms_normally(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=11)
        pay_attempt(b, age_min=2, ref='TX-OK')
        purge_expired_reservations_task()                      # spared
        self.pay(b, 'CAPTURE-1')
        assert Booking.objects.get(pk=b.pk).status == S.CONFIRMED

    def test_payment_after_purge_reconfirms_when_the_slot_is_still_free(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=25)
        pay_attempt(b, age_min=20, ref='TX-STALE')             # stale attempt: no protection left
        purge_expired_reservations_task()
        assert Booking.objects.get(pk=b.pk).status == S.CANCELLED
        result = self.pay(b, 'CAPTURE-LATE')
        assert Booking.objects.get(pk=b.pk).status == S.CONFIRMED and result.get('status') != 'collision_quarantined'
        changes = list(BookingStatusChange.objects.filter(booking=b).values_list('from_status', 'to_status'))
        assert changes == [(S.PENDING_PAYMENT, S.CANCELLED), (S.CANCELLED, S.CONFIRMED)]

    def test_payment_after_purge_is_quarantined_when_someone_else_took_the_slot(self, teacher_user, student_user):
        b = hold(teacher_user, student_user, age_min=25)
        purge_expired_reservations_task()
        other = User.objects.create_user(username='b3', email='b3@x.com', password='x-pass-12345')
        Booking.objects.create(teacher=teacher_user, student=other, start_time_utc=b.start_time_utc,
                               end_time_utc=b.end_time_utc, status=S.CONFIRMED)
        result = self.pay(b, 'CAPTURE-LATE2')
        assert result['status'] == 'collision_quarantined'
        assert Booking.objects.get(pk=b.pk).status == S.DISPUTED
        from apps.payments.models import CreditBundle
        assert CreditBundle.objects.get(user=student_user).remaining_credits == 1  # made whole
