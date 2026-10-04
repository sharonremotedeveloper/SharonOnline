"""Q0: plain-function factories in tests/factories.py (docs/QUALITY_GATES.md)."""
from decimal import Decimal

import pytest

from apps.bookings.models import Booking, BookingStatusChange
from apps.payments.models import BookingFunding, PaymentTransaction
from apps.teachers.models import TeacherProfile
from apps.users.models import StudentProfile, User
import factories as f

pytestmark = pytest.mark.django_db
S = Booking.Status


@pytest.mark.parametrize('role', [User.Role.STUDENT, User.Role.TEACHER, User.Role.ADMIN])
def test_make_user_per_role_is_unique_and_usable(role):
    a, b = f.make_user(role=role), f.make_user(role=role)
    assert a.role == b.role == role
    assert a.username != b.username and a.email != b.email
    assert a.check_password(f.DEFAULT_PASSWORD)
    assert (a.is_staff, a.is_superuser) == ((True, True) if role == User.Role.ADMIN else (False, False))


def test_role_shortcuts():
    assert f.make_student().role == User.Role.STUDENT
    assert f.make_admin().is_staff
    assert f.make_user(role='teacher', timezone='Africa/Johannesburg').timezone == 'Africa/Johannesburg'


# Plan §3.1 truth table (the only one): status -> (is_verified, is_active)
TRUTH_TABLE = {
    'applied': (False, True), 'submitted': (False, True), 'in_review': (False, True), 'changes_requested': (False, True),
    'rejected': (False, False), 'approved': (True, True), 'suspended': (True, False),
}


@pytest.mark.parametrize('status,flags', TRUTH_TABLE.items())
def test_teacher_profile_status_follows_the_truth_table(status, flags):
    profile = f.make_teacher_profile(status=status)
    profile.refresh_from_db()
    assert (profile.is_verified, profile.is_active) == flags
    assert profile.user.role == User.Role.TEACHER


def test_teacher_profile_defaults_to_an_approved_bookable_tutor_with_availability():
    profile = f.make_teacher_profile()
    assert (profile.is_verified, profile.is_active) == (True, True)
    assert profile.availabilities.filter(is_active=True).exists()
    assert f.make_teacher_profile(availability=False).availabilities.count() == 0


def test_teacher_profile_rejects_unknown_status_and_direct_flags():
    with pytest.raises(ValueError):
        f.make_teacher_profile(status='verified')
    with pytest.raises(TypeError):
        f.make_teacher_profile(is_verified=True)          # flags are derived from status (T1a makes them GeneratedFields)


def test_teacher_profile_for_an_existing_user_and_extra_fields():
    user = f.make_user(role='teacher')
    profile = f.make_teacher_profile(user=user, headline='Business English', price_per_25min_usd=Decimal('11.00'))
    assert profile.user == user and profile.headline == 'Business English'
    assert TeacherProfile.objects.get(user=user).price_per_25min_usd == Decimal('11.00')


def test_student_profile():
    profile = f.make_student_profile(target_level='B2')
    assert isinstance(profile, StudentProfile) and profile.user.role == User.Role.STUDENT and profile.target_level == 'B2'


@pytest.mark.parametrize('status', list(S.values))
def test_make_booking_in_every_status(status):
    booking = f.make_booking(status=status)
    booking.refresh_from_db()
    assert booking.status == status
    assert booking.end_time_utc - booking.start_time_utc == f.LESSON
    assert BookingStatusChange.objects.count() == 0     # documented test-only path: no audit row


def test_make_booking_funded_creates_a_successful_payment_and_funding():
    booking = f.make_booking(status=S.CONFIRMED, funded=True)
    tx = PaymentTransaction.objects.get(booking=booking)
    assert tx.status == PaymentTransaction.Status.SUCCESS
    assert BookingFunding.objects.filter(booking=booking).exists()


def test_advance_booking_goes_through_the_state_machine_with_audit_rows():
    booking = f.make_booking(status=S.PENDING_PAYMENT, offset_hours=48)
    f.advance_booking(booking, S.CONFIRMED, S.IN_PROGRESS)
    assert booking.status == S.IN_PROGRESS
    assert list(BookingStatusChange.objects.order_by('created_at').values_list('to_status', flat=True)) == [S.CONFIRMED, S.IN_PROGRESS]


def test_make_payment_transaction_defaults_and_overrides():
    tx = f.make_payment_transaction()
    assert tx.booking is not None and tx.amount == Decimal('9.00') and tx.currency == 'USD'
    other = f.make_payment_transaction(booking=tx.booking, gateway='payfast', amount=Decimal('168.75'), currency='ZAR',
                                       status=PaymentTransaction.Status.INITIALIZED)
    assert other.gateway_reference != tx.gateway_reference and other.currency == 'ZAR'
