from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.crm.models import StudentTutorDossier
from apps.payments.models import CreditBundle, PaymentTransaction
from apps.payments.services.funding import ensure_gateway_funding
from apps.teachers.models import TeacherProfile
from apps.users.models import User


def _client(user=None):
    c = APIClient()
    if user:
        c.force_authenticate(user)
    return c


@pytest.fixture
def booking(teacher_user, student_user):
    now = timezone.now() + timedelta(days=1)
    return Booking.objects.create(
        teacher=teacher_user, student=student_user, start_time_utc=now,
        end_time_utc=now + timedelta(minutes=25), status=Booking.Status.CONFIRMED)


@pytest.fixture
def other_student(db):
    return User.objects.create_user(username='other_s', email='os@test.com', password='x', role='student')


@pytest.fixture
def other_teacher(db):
    u = User.objects.create_user(username='other_t', email='ot@test.com', password='x', role='teacher')
    return TeacherProfile.objects.create(user=u, headline='x', price_per_25min_usd=9, is_verified=True, is_active=True)


@pytest.mark.django_db
class TestBookingIDOR:
    def test_other_student_cannot_view_booking(self, booking, other_student):
        assert _client(other_student).get(f'/api/v1/bookings/{booking.id}/').status_code in (403, 404)

    def test_other_student_cannot_report_outage(self, booking, other_student):
        assert _client(other_student).post(f'/api/v1/bookings/{booking.id}/report-outage/').status_code == 403
        booking.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED

    def test_outage_cannot_be_reported_twice(self, booking, student_user):
        booking.start_time_utc = timezone.now() + timedelta(minutes=5)  # inside the reporting window
        booking.end_time_utc = booking.start_time_utc + timedelta(minutes=25)
        booking.save()
        tx = PaymentTransaction.objects.create(
            booking=booking,
            gateway=PaymentTransaction.Gateway.PAYFAST,
            gateway_reference="tx-outage-idempotency",
            amount=9.00,
            currency="USD",
            status=PaymentTransaction.Status.SUCCESS,
        )
        ensure_gateway_funding(tx, booking)
        c = _client(student_user)
        assert c.post(f'/api/v1/bookings/{booking.id}/report-outage/').status_code == 200
        assert c.post(f'/api/v1/bookings/{booking.id}/report-outage/').status_code == 409
        assert sum(b.remaining_credits for b in CreditBundle.objects.filter(user=student_user)) == 1

    def test_outage_rejected_on_completed_booking(self, booking, student_user):
        booking.status = Booking.Status.COMPLETED
        booking.save()
        assert _client(student_user).post(f'/api/v1/bookings/{booking.id}/report-outage/').status_code == 409

    def test_other_teacher_cannot_submit_memo(self, booking, other_teacher):
        res = _client(other_teacher.user).post(f'/api/v1/bookings/{booking.id}/memo/', {'feedback_text': 'x'}, format='json')
        assert res.status_code == 403

    def test_student_cannot_submit_memo(self, booking, student_user):
        res = _client(student_user).post(f'/api/v1/bookings/{booking.id}/memo/', {'feedback_text': 'x'}, format='json')
        assert res.status_code == 403

    def test_memo_rejected_for_unpaid_booking(self, booking, teacher_user):
        booking.status = Booking.Status.PENDING_PAYMENT
        booking.save()
        res = _client(teacher_user.user).post(f'/api/v1/bookings/{booking.id}/memo/', {'feedback_text': 'x'}, format='json')
        assert res.status_code == 409

    def test_other_student_cannot_review(self, booking, other_student):
        res = _client(other_student).post(f'/api/v1/bookings/{booking.id}/review/', {'rating': 5}, format='json')
        assert res.status_code in (403, 404)


@pytest.mark.django_db
class TestCrmAuthorization:
    def test_teacher_without_relationship_cannot_patch_dossier(self, other_teacher, student_user):
        res = _client(other_teacher.user).patch(
            f'/api/v1/teacher/students/{student_user.id}/dossier/',
            {'private_pedagogical_notes': 'snoop'}, format='json')
        assert res.status_code == 403
        assert not StudentTutorDossier.objects.filter(student=student_user).exists()

    def test_teacher_with_booking_can_patch_dossier(self, booking, teacher_user, student_user):
        res = _client(teacher_user.user).patch(
            f'/api/v1/teacher/students/{student_user.id}/dossier/',
            {'private_pedagogical_notes': 'ok'}, format='json')
        assert res.status_code == 200

    def test_admin_must_name_a_teacher(self, admin_user, student_user):
        res = _client(admin_user).patch(
            f'/api/v1/teacher/students/{student_user.id}/dossier/',
            {'private_pedagogical_notes': 'x'}, format='json')
        assert res.status_code == 400

    def test_student_cannot_list_dossiers(self, student_user):
        assert _client(student_user).get('/api/v1/teacher/students/').status_code == 403


@pytest.mark.django_db
class TestTeacherVisibility:
    def test_unverified_teacher_detail_404(self, other_teacher):
        other_teacher.is_verified = False
        other_teacher.save()
        assert _client().get(f'/api/v1/teachers/{other_teacher.id}/').status_code == 404

    def test_tefl_url_has_no_hardcoded_default(self, other_teacher):
        assert other_teacher.resolved_tefl_certificate_url == ''

    def test_availability_create_without_profile_is_403_not_500(self, student_user):
        res = _client(student_user).post('/api/v1/teachers/availability/manage/', {}, format='json')
        assert res.status_code == 403


ADMIN_ROUTES = [
    ('get', '/api/v1/admin/telemetry/'), ('get', '/api/v1/admin/teachers/pending-vetting/'),
    ('get', '/api/v1/admin/attendance/live/'), ('get', '/api/v1/admin/disputes/'),
    ('get', '/api/v1/admin/finance/ledger/'), ('get', '/api/v1/admin/payouts/batch/'),
    ('post', '/api/v1/admin/payouts/execute-batch/'),
]


@pytest.mark.django_db
@pytest.mark.parametrize('method,url', ADMIN_ROUTES)
def test_admin_routes_forbidden_to_non_admins(method, url, student_user, teacher_user):
    for user in (student_user, teacher_user.user):
        assert getattr(_client(user), method)(url).status_code == 403
    assert getattr(_client(), method)(url).status_code == 401
