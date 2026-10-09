"""The one function that builds a lesson's join link (Phase 11/12 seam 1): the in-browser classroom page."""
import pytest

import factories as f
from apps.bookings.services.classroom_links import classroom_path, classroom_url


@pytest.mark.django_db
class TestClassroomLinks:
    def test_student_and_tutor_get_their_own_classroom_route(self, settings):
        settings.FRONTEND_BASE_URL = 'https://app.example.com/'
        booking = f.make_booking()
        assert classroom_path(booking, 'student') == f'/student/classroom/{booking.id}'
        assert classroom_path(booking, 'teacher') == f'/teacher/classroom/{booking.id}'
        assert classroom_url(booking, 'student') == f'https://app.example.com/student/classroom/{booking.id}'
        assert classroom_url(booking, 'teacher') == f'https://app.example.com/teacher/classroom/{booking.id}'

    def test_link_is_built_from_the_frontend_base_url_only(self, settings):
        settings.FRONTEND_BASE_URL = 'https://app.example.com'
        booking = f.make_booking()
        for role in ('student', 'teacher'):
            assert classroom_url(booking, role).startswith('https://app.example.com/')

    def test_unknown_role_is_refused(self):
        with pytest.raises(ValueError):
            classroom_path(f.make_booking(), 'admin')
