"""Explicitly gated development booking confirmation for provider/browser E2E tests."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services.booking_block import booking_block_message
from apps.bookings.services.holds import hold_is_live
from apps.bookings.services.lock_service import extend_slot_lock, release_slot_lock
from apps.bookings.services.state_machine import InvalidTransition, transition_booking


class TestBookingError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


@transaction.atomic
def confirm_test_booking(*, booking, student):
    """Confirm a held booking without money only when the test switch is explicitly enabled."""
    if settings.PAYMENTS_ENABLED or not settings.TEST_BOOKINGS_ENABLED:
        raise TestBookingError(503, 'Test bookings are not enabled in this environment.')

    booking = (Booking.objects.select_for_update()
               .select_related('teacher__user', 'student')
               .get(pk=booking.pk))
    if booking.student_id != student.id:
        raise TestBookingError(404, 'Booking not found.')
    if booking.status == Booking.Status.CONFIRMED:
        return booking, False
    if booking.status != Booking.Status.PENDING_PAYMENT:
        raise TestBookingError(409, f"Booking is '{booking.status}' and cannot be confirmed.")
    blocked = booking_block_message(student)
    if blocked:
        raise TestBookingError(409, blocked)
    if not booking.teacher.is_bookable:
        raise TestBookingError(409, 'This tutor is not currently bookable.')
    now = timezone.now()
    if not hold_is_live(booking, now):
        raise TestBookingError(409, 'This reservation has expired. Please choose the time slot again.')
    if booking.start_time_utc <= now:
        raise TestBookingError(409, 'Choose a future slot for a development test booking.')
    if not extend_slot_lock(
        str(booking.teacher_id), booking.start_time_utc.isoformat(), str(student.id), 60,
        token=booking.slot_lock_token or None,
    ):
        raise TestBookingError(409, 'This time slot has just been taken. Please choose another.')
    try:
        transition_booking(booking, Booking.Status.CONFIRMED, actor=student,
                           reason='development test booking confirmed')
    except InvalidTransition as exc:
        raise TestBookingError(409, str(exc)) from exc

    booking_id = str(booking.id)
    transaction.on_commit(lambda: _finish_test_booking(booking, booking_id, student))
    return booking, True


def _finish_test_booking(booking, booking_id, student):
    release_slot_lock(
        str(booking.teacher_id), booking.start_time_utc.isoformat(), str(student.id),
        token=booking.slot_lock_token or None,
    )
    from apps.payments.services.webhook_handler import dispatch_fulfillment
    dispatch_fulfillment(booking_id)
