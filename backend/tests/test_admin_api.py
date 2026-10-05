import pytest
from rest_framework.test import APIClient
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from apps.users.models import User
from apps.teachers.models import TeacherProfile
from apps.bookings.models import Booking
from apps.admin_api.models import DisputeCase, PayoutBatch
from apps.payments.models import CreditBundle, PaymentTransaction
from apps.payments.services.funding import ensure_gateway_funding


def _fund(booking):
    tx = PaymentTransaction.objects.create(
        booking=booking, gateway='paypal', gateway_reference=f'TEST-{booking.id}',
        amount=Decimal('9.00'), currency='USD', status='success')
    ensure_gateway_funding(tx, booking)

@pytest.mark.django_db
def test_admin_telemetry_access_control(admin_user, student_user):
    # Non-admin user gets 403 Forbidden
    client = APIClient()
    client.force_authenticate(user=student_user)
    res = client.get('/api/v1/admin/telemetry/')
    assert res.status_code == 403

    # Admin user gets 200 OK with all required telemetry fields
    client.force_authenticate(user=admin_user)
    res = client.get('/api/v1/admin/telemetry/')
    assert res.status_code == 200
    data = res.json()
    assert 'gmv_today_usd' in data
    assert 'gmv_month_usd' in data
    assert 'active_zoom_sessions_count' in data
    assert 'open_disputes_count' in data
    assert 'pending_vetting_count' in data
    assert 'escrow_liability_usd' in data
    assert 'escrow_liability_zar' in data
    assert 'total_students_count' in data
    assert 'total_teachers_count' in data


@pytest.mark.django_db
def test_pending_teachers_and_verification(admin_user):
    applicant_user = User.objects.create_user(
        username="applicant_tutor",
        email="applicant@test.com",
        password="password123",
        role=User.Role.TEACHER,
        country="ZA"
    )
    profile = TeacherProfile.objects.create(
        user=applicant_user,
        headline="Applicant Tutor",
        price_per_25min_usd=9.00,
        status=TeacherProfile.Status.SUBMITTED,
    )

    client = APIClient()
    client.force_authenticate(user=admin_user)

    # 1. Check pending vetting list
    res = client.get('/api/v1/admin/teachers/pending-vetting/')
    assert res.status_code == 200
    pending_list = res.json()
    assert any(item['id'] == str(profile.id) for item in pending_list)

    # 2. Verify / approve tutor
    verify_res = client.patch(
        f'/api/v1/admin/teachers/{profile.id}/verify/',
        {"is_verified": True, "rubric": {"pronunciation": 4, "teaching_presence": 4, "professionalism": 4, "credentials": 4}},
        format='json'
    )
    assert verify_res.status_code == 200
    assert verify_res.json()['is_verified'] is True

    profile.refresh_from_db()
    assert profile.is_verified is True


@pytest.mark.django_db
def test_dispute_resolution_50_50_split(admin_user, teacher_user, student_user):
    now = timezone.now()
    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now - timedelta(hours=2),
        end_time_utc=now - timedelta(hours=1, minutes=35),
        status=Booking.Status.DISPUTED
    )
    _fund(booking)
    dispute = DisputeCase.objects.create(
        booking=booking,
        student=student_user,
        teacher=teacher_user,
        student_statement="Call dropped mid-session",
        teacher_statement="Power dipped for 3 minutes",
        status=DisputeCase.Status.OPEN
    )

    client = APIClient()
    client.force_authenticate(user=admin_user)

    # Resolve with 50/50 Split (Platform absorbs cost)
    res = client.post(
        f'/api/v1/admin/disputes/{dispute.id}/resolve/',
        {
            "resolution": "split_50_50",
            "admin_notes": "Both parties acted in good faith; platform issues courtesy refund and pays tutor."
        },
        format='json'
    )
    assert res.status_code == 200
    assert res.json()['success'] is True
    assert res.json()['resolution'] == 'split_50_50'

    dispute.refresh_from_db()
    booking.refresh_from_db()

    assert dispute.status == DisputeCase.Status.RESOLVED
    assert dispute.resolution == DisputeCase.Resolution.SPLIT_50_50
    assert booking.status == Booking.Status.COMPLETED

    # Student has received 1 refunded credit
    bundle = CreditBundle.objects.filter(user=student_user).first()
    assert bundle is not None
    assert bundle.remaining_credits == 1  # exactly one credit, not two


@pytest.mark.django_db
def test_execute_payout_batch(admin_user, teacher_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)

    # 1. Fetch batch preview
    batch_res = client.get('/api/v1/admin/payouts/batch/')
    assert batch_res.status_code == 200
    assert batch_res.json() == []

    # 2. Execute batch
    exec_res = client.post('/api/v1/admin/payouts/execute-batch/')
    assert exec_res.status_code == 503
    data = exec_res.json()
    assert data['success'] is False
    assert data['code'] == 'payout_execution_disabled'
    assert not PayoutBatch.objects.exists()


@pytest.mark.django_db
def test_admin_authorization_and_edge_cases(admin_user, teacher_user, student_user):
    import uuid
    client = APIClient()

    # 1. Unauthenticated request to admin telemetry -> 401 or 403
    res_unauth = client.get('/api/v1/admin/telemetry/')
    assert res_unauth.status_code in [401, 403]

    # 2. Teacher forbidden on admin dispute list
    client.force_authenticate(user=teacher_user.user)
    res_disputes_forbidden = client.get('/api/v1/admin/disputes/')
    assert res_disputes_forbidden.status_code == 403

    # 3. Student forbidden on payout batch execution
    client.force_authenticate(user=student_user)
    res_payout_forbidden = client.post('/api/v1/admin/payouts/execute-batch/')
    assert res_payout_forbidden.status_code == 403

    # 4. Admin edge cases: Non-existent teacher verify -> 404
    client.force_authenticate(user=admin_user)
    fake_uuid = uuid.uuid4()
    res_verify_404 = client.patch(
        f'/api/v1/admin/teachers/{fake_uuid}/verify/',
        {"is_verified": True},
        format='json'
    )
    assert res_verify_404.status_code == 404

    # 5. Admin edge cases: Invalid payload on verify -> 400
    res_verify_400 = client.patch(
        f'/api/v1/admin/teachers/{fake_uuid}/verify/',
        {"is_verified": "not-a-bool"},
        format='json'
    )
    assert res_verify_400.status_code == 400

    # 6. Admin edge cases: Non-existent dispute resolve -> 404
    res_disp_404 = client.post(
        f'/api/v1/admin/disputes/{fake_uuid}/resolve/',
        {"resolution": "full_refund_student"},
        format='json'
    )
    assert res_disp_404.status_code == 404

    # 7. Admin edge cases: Invalid resolution choice -> 400
    res_disp_400 = client.post(
        f'/api/v1/admin/disputes/{fake_uuid}/resolve/',
        {"resolution": "arbitrary_choice"},
        format='json'
    )
    assert res_disp_400.status_code == 400


@pytest.mark.django_db
def test_dispute_resolution_full_refund_and_release_tutor(admin_user, teacher_user, student_user):
    now = timezone.now()

    # Test full_refund_student
    booking1 = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now - timedelta(hours=3),
        end_time_utc=now - timedelta(hours=2, minutes=35),
        status=Booking.Status.DISPUTED
    )
    _fund(booking1)
    disp1 = DisputeCase.objects.create(
        booking=booking1,
        student=student_user,
        teacher=teacher_user,
        student_statement="Tutor never showed up",
        status=DisputeCase.Status.OPEN
    )

    client = APIClient()
    client.force_authenticate(user=admin_user)
    res1 = client.post(
        f'/api/v1/admin/disputes/{disp1.id}/resolve/',
        {"resolution": "full_refund_student", "admin_notes": "Tutor no-show verified via audit logs"},
        format='json'
    )
    assert res1.status_code == 200
    booking1.refresh_from_db()
    disp1.refresh_from_db()
    assert booking1.status == Booking.Status.CANCELLED
    assert disp1.status == DisputeCase.Status.RESOLVED

    # Test release_tutor
    booking2 = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=now - timedelta(hours=4),
        end_time_utc=now - timedelta(hours=3, minutes=35),
        status=Booking.Status.DISPUTED
    )
    _fund(booking2)
    disp2 = DisputeCase.objects.create(
        booking=booking2,
        student=student_user,
        teacher=teacher_user,
        student_statement="Minor audio lag",
        status=DisputeCase.Status.OPEN
    )
    res2 = client.post(
        f'/api/v1/admin/disputes/{disp2.id}/resolve/',
        {"resolution": "release_tutor", "admin_notes": "Class was fully completed per Zoom telemetry"},
        format='json'
    )
    assert res2.status_code == 200
    booking2.refresh_from_db()
    disp2.refresh_from_db()
    assert booking2.status == Booking.Status.COMPLETED
    assert disp2.status == DisputeCase.Status.RESOLVED

