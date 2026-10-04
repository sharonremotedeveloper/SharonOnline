"""Task 9.3: the slot grid must show a slot as taken whenever the booking system treats it as taken."""
from datetime import time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.bookings.services.slot_generator import generate_teacher_slots
from apps.payments.models import PaymentTransaction
from apps.teachers.models import TeacherAvailability

S = Booking.Status
User = get_user_model()
MIN = timedelta(minutes=1)


@pytest.fixture
def tutor(teacher_user):
    """Open every day 08:00-10:00 SAST so there are always future slots."""
    TeacherAvailability.objects.all().delete()
    for dow in range(7):
        TeacherAvailability.objects.create(teacher=teacher_user, day_of_week=dow, start_time=time(8, 0),
                                           end_time=time(10, 0), is_active=True)
    return teacher_user


def slots(teacher, days=3):
    return generate_teacher_slots(teacher=teacher, days_ahead=days)


def first_open(teacher):
    return next(s for s in slots(teacher) if s['is_bookable'])


def book(teacher, student, slot, status, *, age_min=0, shift=timedelta(0)):
    from datetime import datetime
    start = datetime.fromisoformat(slot['start_time_utc']) + shift
    b = Booking.objects.create(teacher=teacher, student=student, start_time_utc=start,
                               end_time_utc=start + 25 * MIN, status=status)
    if age_min:
        Booking.objects.filter(pk=b.pk).update(created_at=timezone.now() - age_min * MIN)
    return b


def state(teacher, slot):
    return next(s for s in slots(teacher) if s['start_time_utc'] == slot['start_time_utc'])


# ------------------------------------------------------------------ which statuses make a slot busy
@pytest.mark.django_db
class TestBusyStatuses:
    @pytest.mark.parametrize('status', [S.CONFIRMED, S.IN_PROGRESS, S.COMPLETED, S.COMPLETED_PENDING_MEMO,
                                        S.COMPLETED_MEMO_FORFEITED, S.INTERRUPTED_POWER, S.DISPUTED,
                                        S.TEACHER_NO_SHOW, S.STUDENT_NO_SHOW])
    def test_slot_is_booked_for_every_status_that_consumed_it(self, tutor, student_user, status):
        slot = first_open(tutor)
        book(tutor, student_user, slot, status)
        s = state(tutor, slot)
        assert (s['status'], s['is_bookable']) == ('booked', False)

    def test_cancelled_booking_frees_the_slot(self, tutor, student_user):
        slot = first_open(tutor)
        book(tutor, student_user, slot, S.CANCELLED)
        assert state(tutor, slot)['is_bookable'] is True

    def test_other_tutors_bookings_do_not_block(self, tutor, student_user):
        other_user = User.objects.create_user(username='t2', email='t2@x.com', password='x-pass-12345', role='teacher')
        from apps.teachers.models import TeacherProfile
        other = TeacherProfile.objects.create(user=other_user, headline='x', price_per_25min_usd=9, status='approved')
        slot = first_open(tutor)
        book(other, student_user, slot, S.CONFIRMED)
        assert state(tutor, slot)['is_bookable'] is True


# ------------------------------------------------------------------ unpaid holds seen through the database
@pytest.mark.django_db
class TestLiveHolds:
    def test_a_live_unpaid_hold_reserves_the_slot_even_if_the_redis_key_is_gone(self, tutor, student_user):
        slot = first_open(tutor)
        book(tutor, student_user, slot, S.PENDING_PAYMENT, age_min=2)
        cache.clear()                                   # no Redis lock at all
        s = state(tutor, slot)
        assert (s['status'], s['is_bookable']) == ('reserved', False)

    def test_an_expired_unpaid_hold_does_not(self, tutor, student_user):
        slot = first_open(tutor)
        book(tutor, student_user, slot, S.PENDING_PAYMENT, age_min=11)
        assert state(tutor, slot)['is_bookable'] is True

    def test_a_hold_kept_alive_by_an_in_flight_payment_still_reserves_it(self, tutor, student_user):
        slot = first_open(tutor)
        b = book(tutor, student_user, slot, S.PENDING_PAYMENT, age_min=12)
        PaymentTransaction.objects.create(booking=b, gateway='paypal', gateway_reference='INIT-X', merchant_reference='X',
                                          amount='9.00', currency='USD')
        assert state(tutor, slot)['status'] == 'reserved'


# ------------------------------------------------------------------ overlap, not exact-start matching
@pytest.mark.django_db
class TestOverlap:
    def test_an_off_grid_booking_blocks_every_slot_it_overlaps(self, tutor, student_user):
        slot = first_open(tutor)
        book(tutor, student_user, slot, S.CONFIRMED, shift=10 * MIN)      # runs :10-:35 inside the :00 slot
        assert state(tutor, slot)['is_bookable'] is False

    def test_a_booking_that_ends_exactly_when_the_slot_starts_does_not_block_it(self, tutor, student_user):
        slot = first_open(tutor)
        book(tutor, student_user, slot, S.CONFIRMED, shift=-25 * MIN)     # ends at slot start
        assert state(tutor, slot)['is_bookable'] is True


@pytest.mark.django_db
def test_overlapping_availability_rows_do_not_produce_duplicate_slots(tutor):
    TeacherAvailability.objects.create(teacher=tutor, day_of_week=0, start_time=time(8, 0), end_time=time(9, 0), is_active=True)
    starts = [s['start_time_utc'] for s in slots(tutor, days=7)]
    assert len(starts) == len(set(starts))


# ------------------------------------------------------------------ the HTTP endpoint
@pytest.mark.django_db
class TestSlotsEndpoint:
    def get(self, teacher, query=''):
        return APIClient().get(f'/api/v1/bookings/slots/{teacher.id}/{query}')

    def test_defaults_work(self, tutor):
        res = self.get(tutor)
        assert res.status_code == 200 and res.json()['slot_count'] == len(res.json()['slots']) > 0

    @pytest.mark.parametrize('days', ['abc', '', '0', '-3', '2.5', '1e3'])
    def test_bad_days_is_a_400_not_a_500(self, tutor, days):
        res = self.get(tutor, f'?days={days}')
        assert res.status_code == 400 and 'days' in res.json()

    def test_too_many_days_is_clamped_and_says_so(self, tutor):
        res = self.get(tutor, '?days=99')
        assert res.status_code == 200 and res.json()['days'] == 14

    @pytest.mark.parametrize('tz', ['Not/AZone', 'Mars', '../etc/passwd', 'x' * 200])
    def test_unknown_timezone_is_a_400_not_a_silent_utc(self, tutor, tz):
        res = self.get(tutor, f'?tz={tz}')
        assert res.status_code == 400 and 'tz' in res.json()

    def test_valid_timezone_localises_the_slots(self, tutor):
        body = self.get(tutor, '?tz=Asia/Tokyo&days=2').json()
        assert body['viewer_timezone'] == 'Asia/Tokyo' and all(s['viewer_timezone'] == 'Asia/Tokyo' for s in body['slots'])

    def test_unverified_or_inactive_tutors_have_no_public_slots(self, tutor):
        from factories import advance_teacher
        advance_teacher(tutor, 'in_review')                     # re-vet: no longer verified
        assert self.get(tutor).status_code == 404
        advance_teacher(tutor, 'approved', 'suspended')         # verified but inactive
        assert self.get(tutor).status_code == 404

    def test_the_endpoint_reports_taken_slots_consistently_with_reserve(self, tutor, student_user):
        from apps.bookings.services.reservation import ReservationError, reserve_slot
        from datetime import datetime
        slot = first_open(tutor)
        book(tutor, User.objects.create_user(username='rival', email='r@x.com', password='x-pass-12345', role='student'),
             slot, S.PENDING_PAYMENT, age_min=1)
        cache.clear()
        shown = next(s for s in self.get(tutor).json()['slots'] if s['start_time_utc'] == slot['start_time_utc'])
        assert shown['is_bookable'] is False
        with pytest.raises(ReservationError):
            reserve_slot(student=student_user, teacher_id=tutor.id, start_time_utc=datetime.fromisoformat(slot['start_time_utc']))
