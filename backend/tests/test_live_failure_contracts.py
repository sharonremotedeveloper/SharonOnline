from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.utils import timezone

from apps.admin_api.serializers import LiveSessionRadarSerializer
from apps.bookings.models import Booking
from apps.integrations.services.attendance import credited_attendance_minutes
from apps.materials.models import Material
from apps.materials.serializers import MaterialDetailSerializer, MaterialListSerializer
from apps.srs.serializers import StudentLessonItemSerializer

import factories as f


pytestmark = pytest.mark.django_db


class TestMaterialsContract:
    def test_list_and_detail_expose_frontend_contract_fields(self):
        material = Material.objects.create(
            title='Remote work', slug='remote-work', category=Material.Category.DAILY_NEWS,
            cefr_level=Material.CEFRLevel.B2, description='A short summary.', content_html='<p>Lesson body</p>',
        )

        listed = MaterialListSerializer(material).data
        detail = MaterialDetailSerializer(material).data

        for payload in (listed, detail):
            assert payload['summary'] == 'A short summary.'
            assert payload['estimated_minutes'] == 25
            assert payload['vocabulary'] == []
            assert payload['discussion_questions'] == []

    def test_list_search_is_server_side(self, client):
        Material.objects.create(title='Remote work', slug='remote-work', category='daily_news', cefr_level='B2', description='distributed teams')
        Material.objects.create(title='Interview skills', slug='interview-skills', category='test_prep', cefr_level='C1', description='STAR answers')

        response = client.get('/api/v1/materials/?search=distributed')

        assert response.status_code == 200
        assert [item['slug'] for item in response.json()['results']] == ['remote-work']


class TestStudentLessonContract:
    def test_unlinked_booking_does_not_emit_a_broken_placeholder_material_slug(self):
        tutor = f.make_teacher_profile()
        student = f.make_student()
        booking = f.make_booking(teacher=tutor, student=student, status=Booking.Status.CONFIRMED)
        booking.material = None
        booking.save(update_fields=['material'])

        payload = StudentLessonItemSerializer(booking).data

        assert payload['material_title'] is None
        assert payload['material_cefr'] is None
        assert payload['material_slug'] is None

    def test_local_times_use_the_student_timezone(self):
        tutor = f.make_teacher_profile()
        student = f.make_student(timezone='Asia/Tokyo')
        start = datetime(2026, 1, 5, 23, 30, tzinfo=dt_timezone.utc)
        booking = f.make_booking(teacher=tutor, student=student, start=start, status=Booking.Status.CONFIRMED)

        payload = StudentLessonItemSerializer(booking).data

        assert payload['local_date'] == 'Jan 06, 2026'
        assert payload['local_start_time'] == '08:30'
        assert payload['local_end_time'] == '08:55'


class TestAttendanceBounds:
    def test_credited_attendance_caps_legacy_minutes_to_the_lesson_window(self):
        tutor = f.make_teacher_profile()
        student = f.make_student()
        start = timezone.now() - timedelta(hours=2)
        booking = f.make_booking(teacher=tutor, student=student, start=start, status=Booking.Status.CONFIRMED)
        from apps.bookings.models import AttendanceAudit
        AttendanceAudit.objects.create(
            booking=booking, participant_email=tutor.user.email, classification='teacher',
            identity='legacy', total_minutes=1136,
        )

        assert credited_attendance_minutes(booking, 'teacher', through=booking.end_time_utc) == 25


class TestLiveRadarBounds:
    def test_elapsed_minutes_is_clamped_to_lesson_window(self):
        tutor = f.make_teacher_profile()
        student = f.make_student()
        start = timezone.now() - timedelta(hours=19)
        booking = f.make_booking(teacher=tutor, student=student, start=start, status=Booking.Status.IN_PROGRESS)

        payload = LiveSessionRadarSerializer(booking).data

        assert payload['elapsed_minutes'] == 25
