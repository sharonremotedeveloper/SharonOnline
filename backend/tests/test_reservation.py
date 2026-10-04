"""Task 9.2: reserve = validate + 10-min lock + PENDING_PAYMENT booking, returning a real booking_id."""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.bookings.services.lock_service import is_slot_locked
from apps.bookings.services.slot_generator import generate_teacher_slots
from apps.users.models import User

RESERVE = '/api/v1/bookings/reserve/'


def _client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def _open_slots(teacher, n=1):
    slots = [s for s in generate_teacher_slots(teacher=teacher, days_ahead=15) if s['is_bookable']]
    assert len(slots) >= n, "fixture teacher should expose several Monday slots within 15 days"
    return slots[:n]


@pytest.fixture
def other_student(db):
    return User.objects.create_user(username='other_student', email='o@test.com', password='x', role=User.Role.STUDENT)


@pytest.mark.django_db
class TestReserve:
    def test_creates_pending_booking_with_real_id_and_lock(self, teacher_user, student_user):
        slot = _open_slots(teacher_user)[0]
        res = _client(student_user).post(RESERVE, {'teacher_id': str(teacher_user.id),
                                                   'start_time_utc': slot['start_time_utc']}, format='json')
        assert res.status_code == 201, res.data
        booking = Booking.objects.get(id=uuid.UUID(res.data['booking_id']))
        assert booking.status == Booking.Status.PENDING_PAYMENT and booking.student == student_user
        assert res.data['status'] == 'pending_payment'
        assert 0 < res.data['lock_ttl_seconds'] <= 600
        assert res.data['lock_expires_at'] == (booking.created_at + timedelta(seconds=600)).isoformat()
        assert is_slot_locked(str(teacher_user.id), slot['start_time_utc'])

    def test_retry_returns_same_hold_not_a_duplicate(self, teacher_user, student_user):
        slot = _open_slots(teacher_user)[0]
        body = {'teacher_id': str(teacher_user.id), 'start_time_utc': slot['start_time_utc']}
        first = _client(student_user).post(RESERVE, body, format='json')
        second = _client(student_user).post(RESERVE, body, format='json')
        assert (first.status_code, second.status_code) == (201, 200)
        assert first.data['booking_id'] == second.data['booking_id']
        assert Booking.objects.count() == 1

    def test_second_student_cannot_take_a_held_slot(self, teacher_user, student_user, other_student):
        slot = _open_slots(teacher_user)[0]
        body = {'teacher_id': str(teacher_user.id), 'start_time_utc': slot['start_time_utc']}
        assert _client(student_user).post(RESERVE, body, format='json').status_code == 201
        res = _client(other_student).post(RESERVE, body, format='json')
        assert res.status_code == 409
        assert Booking.objects.count() == 1

    def test_time_that_is_not_an_open_slot_is_rejected(self, teacher_user, student_user):
        slot = _open_slots(teacher_user)[0]
        off_grid = (timezone.datetime.fromisoformat(slot['start_time_utc']) + timedelta(minutes=7)).isoformat()
        res = _client(student_user).post(RESERVE, {'teacher_id': str(teacher_user.id), 'start_time_utc': off_grid}, format='json')
        assert res.status_code == 409 and Booking.objects.count() == 0

    def test_past_time_is_rejected(self, teacher_user, student_user):
        past = (timezone.now() - timedelta(days=1)).isoformat()
        res = _client(student_user).post(RESERVE, {'teacher_id': str(teacher_user.id), 'start_time_utc': past}, format='json')
        assert res.status_code == 409 and Booking.objects.count() == 0

    def test_unverified_or_inactive_tutor_not_bookable(self, teacher_user, student_user):
        slot = _open_slots(teacher_user)[0]
        body = {'teacher_id': str(teacher_user.id), 'start_time_utc': slot['start_time_utc']}
        from factories import advance_teacher
        advance_teacher(teacher_user, 'in_review')              # re-vet: no longer verified
        assert _client(student_user).post(RESERVE, body, format='json').status_code == 404
        advance_teacher(teacher_user, 'approved', 'suspended')  # verified but inactive
        assert _client(student_user).post(RESERVE, body, format='json').status_code == 404

    def test_unknown_tutor_is_404_not_500(self, student_user):
        res = _client(student_user).post(RESERVE, {'teacher_id': str(uuid.uuid4()),
                                                   'start_time_utc': timezone.now().isoformat()}, format='json')
        assert res.status_code == 404

    def test_only_students_can_reserve(self, teacher_user):
        slot = _open_slots(teacher_user)[0]
        res = _client(teacher_user.user).post(RESERVE, {'teacher_id': str(teacher_user.id),
                                                        'start_time_utc': slot['start_time_utc']}, format='json')
        assert res.status_code == 403

    def test_anonymous_cannot_reserve(self, teacher_user):
        res = APIClient().post(RESERVE, {'teacher_id': str(teacher_user.id), 'start_time_utc': timezone.now().isoformat()},
                               format='json')
        assert res.status_code == 401

    def test_malformed_input_is_400(self, student_user):
        assert _client(student_user).post(RESERVE, {'teacher_id': 'nope', 'start_time_utc': 'nope'}, format='json').status_code == 400

    def test_student_cannot_hoard_more_than_three_unpaid_holds(self, teacher_user, student_user):
        slots = _open_slots(teacher_user, 4)
        codes = [_client(student_user).post(RESERVE, {'teacher_id': str(teacher_user.id),
                                                      'start_time_utc': s['start_time_utc']}, format='json').status_code
                 for s in slots]
        assert codes == [201, 201, 201, 409]

    def test_expired_hold_can_be_reserved_again(self, teacher_user, student_user, other_student):
        from django.core.cache import cache
        from apps.bookings.services.lock_service import build_slot_lock_key
        slot = _open_slots(teacher_user)[0]
        body = {'teacher_id': str(teacher_user.id), 'start_time_utc': slot['start_time_utc']}
        first = _client(student_user).post(RESERVE, body, format='json')
        # simulate the 10 minutes passing: lock expires and the booking is older than the hold window
        Booking.objects.filter(id=first.data['booking_id']).update(created_at=timezone.now() - timedelta(minutes=11))
        cache.delete(build_slot_lock_key(str(teacher_user.id), slot['start_time_utc']))
        res = _client(other_student).post(RESERVE, body, format='json')
        assert res.status_code == 201 and res.data['booking_id'] != first.data['booking_id']


@pytest.mark.django_db
class TestCreateEndpointCannotBypassTheHold:
    def test_post_bookings_goes_through_the_same_lock(self, teacher_user, student_user, other_student):
        slot = _open_slots(teacher_user)[0]
        body = {'teacher_id': str(teacher_user.id), 'start_time_utc': slot['start_time_utc']}
        res = _client(student_user).post('/api/v1/bookings/', body, format='json')
        assert res.status_code == 201 and is_slot_locked(str(teacher_user.id), slot['start_time_utc'])
        assert _client(other_student).post('/api/v1/bookings/', body, format='json').status_code == 409

    def test_post_bookings_rejects_arbitrary_times_and_unknown_tutors(self, teacher_user, student_user):
        c = _client(student_user)
        assert c.post('/api/v1/bookings/', {'teacher_id': str(teacher_user.id),
                                            'start_time_utc': (timezone.now() + timedelta(days=1)).isoformat()},
                      format='json').status_code == 409
        assert c.post('/api/v1/bookings/', {'teacher_id': str(uuid.uuid4()),
                                            'start_time_utc': timezone.now().isoformat()}, format='json').status_code == 404


@pytest.mark.django_db
def test_reserved_booking_is_payable_end_to_end(teacher_user, student_user):
    slot = _open_slots(teacher_user)[0]
    c = _client(student_user)
    booking_id = c.post(RESERVE, {'teacher_id': str(teacher_user.id), 'start_time_utc': slot['start_time_utc']},
                        format='json').data['booking_id']
    res = c.post('/api/v1/payments/checkout/init/', {'booking_id': booking_id, 'gateway': 'paypal'}, format='json')
    assert res.status_code == 200 and res.data['amount'] == '9.00'


@pytest.mark.django_db
def test_reserve_endpoint_is_throttled(teacher_user, student_user, monkeypatch):
    from rest_framework.throttling import ScopedRateThrottle
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, 'reserve', '2/min')
    c = _client(student_user)
    codes = [c.post(RESERVE, {'teacher_id': 'x', 'start_time_utc': 'x'}, format='json').status_code for _ in range(3)]
    assert codes == [400, 400, 429]
