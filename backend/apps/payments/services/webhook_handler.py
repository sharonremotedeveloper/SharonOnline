from django.db import transaction, IntegrityError
from django.utils import timezone
from apps.payments.models import PaymentTransaction, CreditBundle, GatewayAnomaly
from apps.payments.services.ledger_service import (
    record_payment_capture_entry, record_def501_quarantine_entry, record_unallocated_payment_entry)
from apps.bookings.models import Booking
from apps.bookings.services.lock_service import release_slot_lock
from apps.admin_api.models import DisputeCase
import logging

logger = logging.getLogger(__name__)

# A payment may only confirm a booking that is still waiting for it (or whose hold just expired -> DEF-501 path).
# Any other state (already confirmed / in progress / completed / disputed ...) means this money is surplus and must
# NOT touch the booking, otherwise a second payment could flip a COMPLETED lesson to DISPUTED and freeze payouts.
PAYABLE_BOOKING_STATES = (Booking.Status.PENDING_PAYMENT, Booking.Status.CANCELLED)


def _hold_unallocated(tx, booking, reason: str, detail: str = '') -> None:
    """Park captured-but-unappliable money in ledger acct 2030 and raise a durable anomaly for follow-up/refund."""
    tx.status = PaymentTransaction.Status.UNALLOCATED
    tx.save(update_fields=['status', 'updated_at'])
    record_unallocated_payment_entry(payment_transaction=tx, booking=booking, user=booking.student)
    GatewayAnomaly.objects.create(
        gateway=tx.gateway, reference=tx.gateway_reference, reason=reason, detail=detail,
        booking=booking, payment_transaction=tx, payload=tx.raw_webhook_payload or {})
    logger.error("[UNALLOCATED PAYMENT] %s %s %s on booking %s: %s (refund required)",
                 tx.gateway, tx.gateway_reference, f"{tx.amount} {tx.currency}", booking.id, reason)


@transaction.atomic
def record_unallocated_payment(*, booking, gateway: str, transaction_id: str, amount, currency: str,
                               raw_payload: dict, reason: str, detail: str = '') -> dict:
    """Idempotently record an authenticated surplus/duplicate payment that has no transaction row yet."""
    tx, created = PaymentTransaction.objects.select_for_update().get_or_create(
        gateway_reference=transaction_id,
        defaults={'booking': booking, 'gateway': gateway, 'amount': amount, 'currency': currency,
                  'status': PaymentTransaction.Status.UNALLOCATED, 'raw_webhook_payload': raw_payload})
    if not created:
        return {"status": "already_processed"}
    # The row was created UNALLOCATED; post the ledger legs + anomaly (without re-saving status).
    record_unallocated_payment_entry(payment_transaction=tx, booking=booking, user=booking.student)
    GatewayAnomaly.objects.create(
        gateway=gateway, reference=transaction_id, reason=reason, detail=detail,
        booking=booking, payment_transaction=tx, payload=raw_payload or {})
    logger.error("[UNALLOCATED PAYMENT] %s %s %s on booking %s: %s (refund required)",
                 gateway, transaction_id, f"{amount} {currency}", booking.id, reason)
    return {"status": "unallocated", "reason": reason, "transaction_id": transaction_id}


def _dispatch_fulfillment(booking_id: str) -> None:
    try:
        from apps.integrations.tasks import dispatch_booking_fulfillment
        dispatch_booking_fulfillment.delay(booking_id)
    except Exception:
        # The booking is already CONFIRMED and paid; a lost dispatch means no Zoom link/email. Make it loud.
        logger.exception("Could not dispatch fulfillment for booking %s - needs manual or reconcile re-dispatch", booking_id)


@transaction.atomic
def process_payment_webhook(booking_id: str, gateway: str, transaction_id: str, amount: float, currency: str, status: str, raw_payload: dict) -> dict:
    """
    Idempotent payment webhook ingestion.
    Guarantees that multiple retries from payment gateways (PayFast/PayPal)
    never result in double bookings, duplicate meetings, or corrupted ledgers.
    Includes DEF-501 Concurrency Guard against late payments on expired/re-booked slots.
    Records immutable GAAP/SARB double-entry ledger entries upon settlement.
    """
    tx, created = PaymentTransaction.objects.select_for_update().get_or_create(
        gateway_reference=transaction_id,
        defaults={
            'booking_id': booking_id,
            'gateway': gateway,
            'amount': amount,
            'currency': currency,
            'status': status,
            'raw_webhook_payload': raw_payload
        }
    )

    if not created and tx.status in (PaymentTransaction.Status.SUCCESS, PaymentTransaction.Status.UNALLOCATED):
        logger.info(f"Duplicate webhook ignored for transaction_id={transaction_id}")
        return {"status": "already_processed"}

    if status == PaymentTransaction.Status.SUCCESS:
        try:
            booking = Booking.objects.select_for_update().select_related('teacher', 'student').get(id=booking_id)
        except Booking.DoesNotExist:
            logger.error(f"Booking {booking_id} referenced in transaction {transaction_id} does not exist")
            return {"error": "booking_not_found"}

        # Surplus payment (booking already confirmed/in progress/completed/disputed...): hold it, never touch the booking.
        if booking.status not in PAYABLE_BOOKING_STATES:
            _hold_unallocated(tx, booking, 'booking_not_payable', f"booking status is '{booking.status}'")
            return {"status": "unallocated", "reason": "booking_not_payable", "transaction_id": transaction_id}

        tx.status = PaymentTransaction.Status.SUCCESS
        tx.save()

        # Concurrency Guard (DEF-501): Check if slot expired or was re-booked by another student
        active_statuses = [
            Booking.Status.CONFIRMED,
            Booking.Status.IN_PROGRESS,
            Booking.Status.COMPLETED,
            Booking.Status.COMPLETED_PENDING_MEMO,
            Booking.Status.COMPLETED_MEMO_FORFEITED,
        ]

        slot_conflict = Booking.objects.filter(
            teacher=booking.teacher,
            start_time_utc=booking.start_time_utc,
            status__in=active_statuses
        ).exclude(id=booking.id).exists()

        now = timezone.now()
        is_past_lesson = booking.start_time_utc <= now

        if slot_conflict or is_past_lesson:
            # Slot was re-booked by another student or lesson has already elapsed!
            reason = "slot_rebooked_by_another_student" if slot_conflict else "lesson_window_elapsed"
            logger.warning(
                f"[DEF-501 CONCURRENCY GUARD] Booking {booking_id} conflict detected ({reason}). "
                f"Quarantining to DISPUTED and auto-crediting student wallet."
            )
            booking.status = Booking.Status.DISPUTED
            booking.save(update_fields=['status', 'updated_at'])

            # Restitution: credit student 1 lesson credit so funds are not lost
            bundle, _ = CreditBundle.objects.get_or_create(
                user=booking.student,
                defaults={'remaining_credits': 0, 'total_credits': 0, 'amount_paid': 0.0}
            )
            bundle.remaining_credits += 1
            bundle.total_credits += 1
            bundle.save(update_fields=['remaining_credits', 'total_credits'])

            # Open a DisputeCase for admin review in tribunal
            DisputeCase.objects.get_or_create(
                booking=booking,
                defaults={
                    "student": booking.student,
                    "teacher": booking.teacher,
                    "student_statement": (
                        f"Automated Alert (DEF-501): Late payment webhook arrived after reservation "
                        f"expired. Conflict reason: {reason}."
                    ),
                    "teacher_statement": "Timeslot collision quarantined. 1 lesson credit awarded to student.",
                    "status": DisputeCase.Status.OPEN,
                    "admin_notes": (
                        f"Payment gateway transaction {transaction_id} ({gateway}) captured. "
                        f"Slot unavailable. Auto-compensated with 1 credit bundle."
                    )
                }
            )

            # Record DEF-501 double-entry journal entries
            record_def501_quarantine_entry(payment_transaction=tx, booking=booking, user=booking.student)

            start_iso = booking.start_time_utc.isoformat()
            release_slot_lock(str(booking.teacher_id), start_iso, str(booking.student_id))

            return {
                "status": "collision_quarantined",
                "reason": reason,
                "transaction_id": transaction_id,
                "booking_id": str(booking.id)
            }

        # Slot is free and session is in future: attempt confirmation under savepoint
        try:
            with transaction.atomic():
                booking.status = Booking.Status.CONFIRMED
                booking.save()
        except IntegrityError:
            # Microsecond race condition fallback: another transaction committed between check and save
            logger.warning(
                f"[DEF-501 RACE HAZARD] IntegrityError caught during booking {booking_id} confirmation. "
                f"Falling back to quarantine."
            )
            booking.status = Booking.Status.DISPUTED
            booking.save(update_fields=['status', 'updated_at'])

            bundle, _ = CreditBundle.objects.get_or_create(
                user=booking.student,
                defaults={'remaining_credits': 0, 'total_credits': 0, 'amount_paid': 0.0}
            )
            bundle.remaining_credits += 1
            bundle.total_credits += 1
            bundle.save(update_fields=['remaining_credits', 'total_credits'])

            DisputeCase.objects.get_or_create(
                booking=booking,
                defaults={
                    "student": booking.student,
                    "teacher": booking.teacher,
                    "student_statement": "Automated Alert (DEF-501): IntegrityError race collision during late payment confirmation.",
                    "teacher_statement": "Race collision quarantined. 1 credit awarded to student.",
                    "status": DisputeCase.Status.OPEN,
                    "admin_notes": f"Payment {transaction_id} caught race condition. Quarantined."
                }
            )
            record_def501_quarantine_entry(payment_transaction=tx, booking=booking, user=booking.student)
            return {
                "status": "collision_quarantined",
                "reason": "race_condition_quarantined",
                "transaction_id": transaction_id,
                "booking_id": str(booking.id)
            }

        # Record standard payment capture in general ledger
        record_payment_capture_entry(payment_transaction=tx, booking=booking, user=booking.student)

        # Release the temporary Redis lock now that it's permanently confirmed in PostgreSQL
        start_iso = booking.start_time_utc.isoformat()
        release_slot_lock(str(booking.teacher_id), start_iso, str(booking.student_id))

        # Trigger background fulfillment (Zoom, GCal, Resend) only AFTER the commit, so the worker can never
        # observe the booking still PENDING_PAYMENT, and a rolled-back payment never queues a task.
        booking_id_str = str(booking.id)
        transaction.on_commit(lambda: _dispatch_fulfillment(booking_id_str))

    return {"status": "success", "transaction_id": transaction_id}

