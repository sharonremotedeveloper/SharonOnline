"""
Plain-function test factories (Q0; no factory_boy). Import with `import factories as f` (tests/ is on sys.path).

    tutor = f.make_teacher_profile(status='approved')          # an approved, bookable tutor with Monday availability
    booking = f.make_booking(teacher=tutor, status='confirmed', funded=True)
    f.advance_booking(booking, 'in_progress')                   # through the real state machine (audit rows)

Bookings: `make_booking(status=...)` writes the status directly with `Booking.objects.create`. That is the documented
TEST-ONLY path: the guard `TestNoDirectStatusWrites` (tests/test_booking_state_machine.py) scans `apps/` only, and
fixtures need bookings that are already in a state without replaying their history. Tests that care about the audit trail
or the transition rules use `advance_booking`, which calls `transition_booking`.

Existing fixtures in conftest.py and helpers in payment_helpers.py are unchanged; new tests should prefer these factories.
"""
import itertools
from datetime import time, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services.state_machine import transition_booking
from apps.payments.models import PaymentTransaction
from apps.payments.services.funding import ensure_gateway_funding
from apps.teachers.models import TeacherAvailability, TeacherProfile
from apps.users.models import StudentProfile, User

DEFAULT_PASSWORD = 'password123'
LESSON = timedelta(minutes=25)
_seq = itertools.count(1)

ROLE_DEFAULTS = {
    User.Role.STUDENT: {'country': 'JP', 'timezone': 'Asia/Tokyo'},
    User.Role.TEACHER: {'country': 'ZA', 'timezone': 'Africa/Johannesburg'},
    User.Role.ADMIN: {'country': 'ZA', 'timezone': 'Africa/Johannesburg', 'is_staff': True, 'is_superuser': True},
}

# Plan §3.1, the only truth table: status -> (is_verified, is_active).
TEACHER_STATUS_FLAGS = {
    'applied': (False, True),
    'submitted': (False, True),
    'in_review': (False, True),
    'changes_requested': (False, True),
    'rejected': (False, False),
    'approved': (True, True),
    'suspended': (True, False),
}


def make_user(role=User.Role.STUDENT, *, password=DEFAULT_PASSWORD, **fields):
    n = next(_seq)
    data = {'username': f'{role}_{n}', 'email': f'{role}_{n}@example.test', **ROLE_DEFAULTS[User.Role(role)], **fields}
    return User.objects.create_user(password=password, role=role, **data)


def make_student(**fields):
    return make_user(User.Role.STUDENT, **fields)


def make_admin(**fields):
    return make_user(User.Role.ADMIN, **fields)


def make_student_profile(user=None, **fields):
    return StudentProfile.objects.create(user=user or make_student(), **fields)


def _has_status_field():
    return any(field.name == 'status' for field in TeacherProfile._meta.concrete_fields)


def make_teacher_profile(user=None, *, status='approved', availability=True, **fields):
    """
    A tutor in a plan §3.1 status. Today `status` is mapped onto `is_verified` / `is_active`.
    TODO(T1a): once TeacherProfile.status exists (and the booleans are GeneratedFields) pass `status` only; the branch
    below already does that as soon as the field appears, and the flag kwargs stay refused.
    """
    if status not in TEACHER_STATUS_FLAGS:
        raise ValueError(f'Unknown tutor status {status!r}; one of {sorted(TEACHER_STATUS_FLAGS)}')
    if {'is_verified', 'is_active'} & fields.keys():
        raise TypeError('Pass status=... instead of is_verified/is_active (they are derived from status, plan §3.1)')
    if _has_status_field():
        fields['status'] = status
    if not getattr(TeacherProfile._meta.get_field('is_verified'), 'generated', False):
        fields['is_verified'], fields['is_active'] = TEACHER_STATUS_FLAGS[status]
    fields.setdefault('headline', 'TEFL Tutor')
    fields.setdefault('accent', TeacherProfile.Accent.SOUTH_AFRICAN)
    fields.setdefault('price_per_25min_usd', Decimal('9.00'))
    profile = TeacherProfile.objects.create(user=user or make_user(User.Role.TEACHER), **fields)
    if availability:
        TeacherAvailability.objects.create(teacher=profile, day_of_week=0, start_time=time(9, 0), end_time=time(12, 0),
                                           is_active=True)
    return profile


def advance_teacher(profile, *statuses, actor=None, reason='test'):
    """Move a tutor through `statuses` with the real service (teachers/vetting.py); default actor: a platform admin."""
    from apps.teachers.vetting import transition_teacher
    actor = actor or make_admin()
    for status in statuses:
        transition_teacher(profile, status, actor=actor, reason=reason)
    return profile


def make_payment_transaction(booking=None, *, gateway=PaymentTransaction.Gateway.PAYPAL, amount=Decimal('9.00'),
                             currency='USD', status=PaymentTransaction.Status.SUCCESS, **fields):
    n = next(_seq)
    booking = booking or make_booking(status=Booking.Status.PENDING_PAYMENT)
    fields.setdefault('gateway_reference', f'TEST-{gateway}-{n}')
    return PaymentTransaction.objects.create(booking=booking, gateway=gateway, amount=Decimal(amount), currency=currency,
                                             status=status, **fields)


def make_booking(teacher=None, student=None, *, status=Booking.Status.CONFIRMED, start=None, offset_hours=48, funded=False,
                 **fields):
    """A booking already in `status` (test-only direct write, see the module docstring)."""
    start = start or timezone.now() + timedelta(hours=offset_hours)
    booking = Booking.objects.create(teacher=teacher or make_teacher_profile(), student=student or make_student(),
                                     start_time_utc=start, end_time_utc=start + LESSON, status=status, **fields)
    if funded:
        ensure_gateway_funding(make_payment_transaction(booking), booking)
    return booking


def advance_booking(booking, *statuses, actor='system:test', reason='test'):
    """Move a booking through `statuses` with the real state machine (allowed-transition map + audit rows)."""
    for status in statuses:
        transition_booking(booking, status, actor=actor, reason=reason)
    return booking
