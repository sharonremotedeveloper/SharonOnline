"""The booking detail payload is the frontend's contract for checkout / confirmed / classroom pages."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.users.models import User


@pytest.fixture
def booking(teacher_user, student_user):
    start = timezone.now() + timedelta(days=2)
    return Booking.objects.create(
        teacher=teacher_user, student=student_user, start_time_utc=start, end_time_utc=start + timedelta(minutes=25),
        status=Booking.Status.CONFIRMED, zoom_meeting_id='123456789', zoom_password='pw',
        zoom_join_url='https://zoom.example/j/123', zoom_start_url='https://zoom.example/s/123?zak=HOSTTOKEN')


def _get(user, booking, query=''):
    c = APIClient()
    c.force_authenticate(user)
    return c.get(f'/api/v1/bookings/{booking.id}/{query}')


@pytest.mark.django_db
class TestBookingDetailContract:
    def test_student_gets_every_field_the_pages_use(self, booking, student_user):
        res = _get(student_user, booking)
        assert res.status_code == 200
        d = res.data
        for key in ('booking_reference', 'price_usd', 'price_zar', 'lock_expires_at', 'local_date', 'local_start_time',
                    'local_end_time', 'viewer_timezone', 'zoom_join_url', 'zoom_meeting_id', 'zoom_password',
                    'material_slug', 'material_title'):
            assert key in d, key
        assert d['booking_reference'].startswith('BK-')
        assert d['price_usd'] == 9.0 and d['price_zar'] == 162.0
        assert d['student']['full_name'] and d['teacher']['full_name']
        assert d['zoom_join_url'] == 'https://zoom.example/j/123'

    def test_host_start_link_is_never_sent_to_the_student(self, booking, student_user):
        d = _get(student_user, booking).data
        assert d['zoom_start_url'] == ''
        assert 'HOSTTOKEN' not in str(d)
        assert d['zoom_url'] == 'https://zoom.example/j/123'

    def test_tutor_gets_the_host_start_link(self, booking, teacher_user):
        d = _get(teacher_user.user, booking).data
        assert d['zoom_start_url'].endswith('HOSTTOKEN')
        assert d['zoom_url'].endswith('HOSTTOKEN')

    def test_student_contact_details_are_not_shared_with_the_tutor(self, booking, teacher_user, student_user):
        assert 'email' not in _get(teacher_user.user, booking).data['student']
        assert _get(student_user, booking).data['student']['email'] == student_user.email

    def test_lock_expiry_only_while_awaiting_payment(self, booking, student_user):
        assert _get(student_user, booking).data['lock_expires_at'] is None
        Booking.objects.filter(pk=booking.pk).update(status=Booking.Status.PENDING_PAYMENT)
        booking.refresh_from_db()
        expected = (booking.created_at + timedelta(seconds=600)).isoformat()
        assert _get(student_user, booking).data['lock_expires_at'] == expected

    def test_local_times_follow_the_requested_timezone(self, booking, student_user):
        tokyo = _get(student_user, booking, '?tz=Asia/Tokyo').data
        utc = _get(student_user, booking, '?tz=UTC').data
        assert tokyo['viewer_timezone'] == 'Asia/Tokyo' and utc['viewer_timezone'] == 'UTC'
        assert tokyo['local_start_time'] != utc['local_start_time']

    def test_bad_timezone_falls_back_instead_of_500(self, booking, student_user):
        res = _get(student_user, booking, '?tz=Not/AZone')
        assert res.status_code == 200
        assert res.data['viewer_timezone'] == 'UTC'

    def test_other_users_cannot_read_the_booking(self, booking):
        stranger = User.objects.create_user(username='stranger', email='s@x.co', password='x', role=User.Role.STUDENT)
        assert _get(stranger, booking).status_code == 404
