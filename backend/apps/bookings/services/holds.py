"""
What it means for a PENDING_PAYMENT booking to still "hold" its slot (Task 9.4). One definition, used by the purge job,
reservation, checkout and the booking API, so they can never disagree.

    base hold      created_at + 10 min                      (the Redis lock TTL)
    in-flight      an INITIALIZED PaymentTransaction younger than PAYMENT_INFLIGHT_GRACE_SECONDS extends the hold to
                   tx.created_at + grace, so a customer who is mid-payment at minute 9 is not cancelled under their feet
    hard cap       created_at + PAYMENT_HOLD_MAX_SECONDS    (re-initialising payments cannot hold a slot forever)

A hold that is not live is purgeable: `Booking.objects.filter(status=PENDING_PAYMENT).exclude(live_hold_q(now))`.
"""
from datetime import timedelta

from django.conf import settings
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services.lock_service import LOCK_DURATION_SECONDS
from apps.payments.models import PaymentTransaction


# Statuses that own a slot for good (the same set the unique_teacher_active_timeslot constraint protects).
SLOT_OWNING_STATUSES = (
    Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED,
    Booking.Status.COMPLETED_PENDING_MEMO, Booking.Status.COMPLETED_MEMO_FORFEITED,
)


def inflight_grace() -> timedelta:
    return timedelta(seconds=settings.PAYMENT_INFLIGHT_GRACE_SECONDS)


def max_hold() -> timedelta:
    return timedelta(seconds=settings.PAYMENT_HOLD_MAX_SECONDS)


def _inflight_exists(now):
    return Exists(PaymentTransaction.objects.filter(
        booking=OuterRef('pk'), status=PaymentTransaction.Status.INITIALIZED, created_at__gte=now - inflight_grace()))


def live_hold_q(now) -> Q:
    """Pending bookings that currently hold their slot (inside the base window, or paying and under the hard cap)."""
    base = Q(created_at__gte=now - timedelta(seconds=LOCK_DURATION_SECONDS))
    paying = Q(_inflight_exists(now)) & Q(created_at__gte=now - max_hold())
    return Q(status=Booking.Status.PENDING_PAYMENT) & (base | paying)


def hold_expires_at(booking: Booking, now=None):
    """When this booking's hold lapses (the UI timer and the purge job both use this)."""
    base = booking.created_at + timedelta(seconds=LOCK_DURATION_SECONDS)
    if booking.status != Booking.Status.PENDING_PAYMENT:
        return base
    now = now or timezone.now()
    latest = (PaymentTransaction.objects
              .filter(booking=booking, status=PaymentTransaction.Status.INITIALIZED, created_at__gte=now - inflight_grace())
              .order_by('-created_at').values_list('created_at', flat=True).first())
    if latest is None:
        return base
    return min(max(base, latest + inflight_grace()), booking.created_at + max_hold())


def hold_is_live(booking: Booking, now=None) -> bool:
    now = now or timezone.now()
    return booking.status == Booking.Status.PENDING_PAYMENT and hold_expires_at(booking, now) > now
