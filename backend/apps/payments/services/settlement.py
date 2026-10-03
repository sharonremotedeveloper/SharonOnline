"""
Where the money for a lesson goes once the lesson's outcome is known (Task 9.7). See docs/SETTLEMENT_PATHS.md.

A captured payment sits in escrow (ledger 2010) until exactly ONE settlement posts against it. Every settlement writes a
ledger entry with one of SETTLEMENT_EVENT_TYPES, so "has this booking already been settled?" is answered from the ledger
itself and no path (24h release, arbitration, no-show refund, outage refund) can pay a second time.
"""
from django.conf import settings
from django.db.models import Exists, OuterRef

from apps.bookings.models import AttendanceAudit, Booking
from apps.payments.models import LedgerEntry, PaymentTransaction

SETTLEMENT_EVENT_TYPES = (
    LedgerEntry.EventType.ESCROW_CLEARED,      # 24h release to the tutor (80/20)
    LedgerEntry.EventType.DISPUTE_RESOLVED,    # arbitration decision (refund, release or split)
    LedgerEntry.EventType.REFUND_ISSUED,       # teacher no-show etc.
    LedgerEntry.EventType.OUTAGE_REFUND,       # power outage
)

# Outcomes whose escrow is released to the tutor by the periodic job once the 24h dispute window has passed.
RELEASABLE_STATUSES = (
    Booking.Status.COMPLETED,
    Booking.Status.COMPLETED_PENDING_MEMO,
    Booking.Status.COMPLETED_MEMO_FORFEITED,
    Booking.Status.STUDENT_NO_SHOW,            # student never came, tutor was there: tutor earns the lesson
    Booking.Status.STUDENT_LATE_CANCELLED,     # student cancelled inside the free window: fee kept, tutor earns it
)


def settled_exists():
    """Annotation-friendly EXISTS: some settlement is already on the ledger for this booking."""
    return Exists(LedgerEntry.objects.filter(booking=OuterRef('pk'), event_type__in=SETTLEMENT_EVENT_TYPES))


def is_settled(booking) -> bool:
    return LedgerEntry.objects.filter(booking=booking, event_type__in=SETTLEMENT_EVENT_TYPES).exists()


def attendance_verified_for_release(booking, teacher_minutes: int) -> bool:
    """
    Completed lessons need >= 20 teacher minutes. A student no-show was already adjudicated on the tutor's presence at
    T+10m (an attendance record exists), so it is not held to the 20-minute rule - the lesson could not run without the student.
    """
    if booking.status == Booking.Status.STUDENT_LATE_CANCELLED:
        return True                              # nothing to attend: the student gave the slot up
    if booking.status == Booking.Status.STUDENT_NO_SHOW:
        return AttendanceAudit.objects.filter(booking=booking, participant_email=booking.teacher.user.email).exists()
    return teacher_minutes >= settings.LESSON_DELIVERED_MIN_TEACHER_MINUTES


def successful_transaction(booking):
    return (PaymentTransaction.objects.filter(booking=booking, status=PaymentTransaction.Status.SUCCESS)
            .order_by('-created_at').first())
