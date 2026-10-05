"""
Slice T2 QA fixes: a tutor's timezone change cannot silently strand lessons (MAJOR-2), concurrent deletes are 404s not 500s
(MINOR-3), legacy rows can be deactivated (MINOR-6).
"""
from datetime import time
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import NotFound

import factories as f
from apps.bookings.models import Booking
from apps.teachers.models import TeacherAvailability
from apps.teachers.services import availability as svc
from t2_helpers import BASE, client, lesson, monday_row, next_weekday_utc

pytestmark = pytest.mark.django_db
User = get_user_model()
ME = '/api/v1/auth/me/'


@pytest.fixture
def tutor(teacher_user):
    return teacher_user


# ------------------------------------------------------------------ MAJOR-2: timezone change
class TestTimezoneChange:
    def test_a_change_that_strands_a_confirmed_lesson_needs_acknowledgement(self, tutor, student_user):
        booking = lesson(tutor, student_user, next_weekday_utc(0, 10))          # Monday 10:00 SAST
        res = client(tutor.user).patch(ME, {'timezone': 'Asia/Tokyo'}, format='json')
        assert res.status_code == 409 and res.json()['code'] == 'availability_conflicts'
        assert [c['booking_id'] for c in res.json()['conflicts']] == [str(booking.id)]
        tutor.user.refresh_from_db()
        assert tutor.user.timezone == 'Africa/Johannesburg'

    def test_acknowledged_it_applies_and_the_lesson_stays_confirmed(self, tutor, student_user):
        booking = lesson(tutor, student_user, next_weekday_utc(0, 10))
        res = client(tutor.user).patch(ME, {'timezone': 'Asia/Tokyo', 'acknowledge_conflicts': True}, format='json')
        assert res.status_code == 200 and res.json()['timezone'] == 'Asia/Tokyo' and 'acknowledge_conflicts' not in res.json()
        tutor.user.refresh_from_db()
        booking.refresh_from_db()
        assert tutor.user.timezone == 'Asia/Tokyo' and booking.status == Booking.Status.CONFIRMED

    def test_a_tutor_without_future_lessons_is_unaffected(self, tutor):
        assert client(tutor.user).patch(ME, {'timezone': 'Asia/Tokyo'}, format='json').status_code == 200

    def test_a_zone_with_the_same_offset_keeps_every_lesson_covered(self, tutor, student_user):
        lesson(tutor, student_user, next_weekday_utc(0, 10))
        assert client(tutor.user).patch(ME, {'timezone': 'Africa/Harare'}, format='json').status_code == 200

    def test_resending_the_same_timezone_is_not_a_change(self, tutor, student_user):
        lesson(tutor, student_user, next_weekday_utc(0, 10))
        assert client(tutor.user).patch(ME, {'timezone': 'Africa/Johannesburg'}, format='json').status_code == 200

    def test_other_profile_fields_are_never_blocked(self, tutor, student_user):
        lesson(tutor, student_user, next_weekday_utc(0, 10))
        assert client(tutor.user).patch(ME, {'first_name': 'Naledi'}, format='json').status_code == 200

    def test_students_are_unaffected_even_with_lessons(self, tutor, student_user):
        lesson(tutor, student_user, next_weekday_utc(0, 10))
        assert client(student_user).patch(ME, {'timezone': 'Europe/London'}, format='json').status_code == 200

    def test_a_tutor_without_a_profile_is_unaffected(self):
        bare = f.make_user('teacher')
        assert client(bare).patch(ME, {'timezone': 'Asia/Tokyo'}, format='json').status_code == 200

    def test_the_tutor_row_is_locked_for_the_check(self, tutor, student_user):
        from django.db.models import QuerySet
        calls = []
        original = QuerySet.select_for_update

        def spy(self, *args, **kwargs):
            calls.append((self.model.__name__, kwargs))
            return original(self, *args, **kwargs)
        with mock.patch.object(QuerySet, 'select_for_update', spy):
            client(tutor.user).patch(ME, {'timezone': 'Africa/Harare'}, format='json')
        assert ('TeacherProfile', {'of': ('self',)}) in calls


# ------------------------------------------------------------------ MINOR-3: races under the lock are 404s
class TestRacesAre404:
    def test_services_raise_not_found_for_rows_that_vanished(self, tutor):
        gone = '00000000-0000-0000-0000-000000000001'
        for call in (lambda: svc.delete_row(tutor, gone, acknowledged=True), lambda: svc.delete_time_off(tutor, gone),
                     lambda: svc.delete_override(tutor, gone, acknowledged=True)):
            with pytest.raises(NotFound):
                call()

    def test_a_row_deleted_between_the_lookup_and_the_lock_is_a_404_for_patch(self, tutor):
        stale = monday_row(tutor)
        TeacherAvailability.objects.filter(pk=stale.pk).delete()
        from apps.teachers.serializers import AvailabilityUpdateSerializer
        serializer = AvailabilityUpdateSerializer(stale, data={'end_time': '11:00'}, partial=True, context={'teacher': tutor})
        with pytest.raises(NotFound):
            svc.update_row(tutor, stale, serializer)

    def test_a_vanished_tutor_is_a_404_at_the_lock(self, tutor):
        from django.db import transaction
        ghost = mock.Mock(pk='00000000-0000-0000-0000-000000000002')
        with transaction.atomic(), pytest.raises(NotFound):
            svc.lock_teacher(ghost)

    def test_the_view_maps_a_lost_race_to_404(self, tutor, monkeypatch):
        r = monday_row(tutor)
        monkeypatch.setattr('apps.teachers.views.get_object_or_404', lambda *a, **k: None)     # the pre-check passed ...
        TeacherAvailability.objects.filter(pk=r.pk).delete()                                    # ... then another request deleted it
        assert client(tutor.user).delete(f'{BASE}/manage/{r.id}/').status_code == 404


# ------------------------------------------------------------------ MINOR-6: legacy rows can be deactivated
class TestLegacyRows:
    def test_an_invalid_legacy_window_can_be_deactivated(self, tutor):
        legacy = TeacherAvailability.objects.create(teacher=tutor, day_of_week=2, start_time=time(12, 0), end_time=time(9, 0))
        res = client(tutor.user).patch(f'{BASE}/manage/{legacy.id}/', {'is_active': False}, format='json')
        assert res.status_code == 200
        legacy.refresh_from_db()
        assert legacy.is_active is False

    def test_a_window_in_the_payload_is_still_validated(self, tutor):
        legacy = TeacherAvailability.objects.create(teacher=tutor, day_of_week=2, start_time=time(12, 0), end_time=time(9, 0))
        res = client(tutor.user).patch(f'{BASE}/manage/{legacy.id}/', {'end_time': '09:00'}, format='json')
        assert res.status_code == 400 and 'end_time' in res.json()

    def test_a_valid_edit_of_a_legacy_row_still_works(self, tutor):
        legacy = TeacherAvailability.objects.create(teacher=tutor, day_of_week=2, start_time=time(12, 0), end_time=time(9, 0))
        res = client(tutor.user).patch(f'{BASE}/manage/{legacy.id}/', {'start_time': '09:00', 'end_time': '12:00'}, format='json')
        assert res.status_code == 200
