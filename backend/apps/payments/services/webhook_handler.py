from django.db import transaction, IntegrityError
from django.utils import timezone
from apps.payments.models import PaymentTransaction, CreditBundle
from apps.payments.services.ledger_service import record_payment_capture_entry, record_def501_quarantine_entry
from apps.bookings.models import Booking
from apps.bookings.services.lock_service import release_slot_lock
from apps.admin_api.models import DisputeCase
import logging

logger = logging.getLogger(__name__)

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

    if not created and tx.status == PaymentTransaction.Status.SUCCESS:
        logger.info(f"Duplicate webhook ignored for transaction_id={transaction_id}")
        return {"status": "already_processed"}

    if status == PaymentTransaction.Status.SUCCESS:
        tx.status = PaymentTransaction.Status.SUCCESS
        tx.save()

        try:
            booking = Booking.objects.select_for_update().select_related('teacher', 'student').get(id=booking_id)
        except Booking.DoesNotExist:
            logger.error(f"Booking {booking_id} referenced in transaction {transaction_id} does not exist")
            return {"error": "booking_not_found"}

        # If already confirmed, nothing more to do
        if booking.status == Booking.Status.CONFIRMED:
            start_iso = booking.start_time_utc.isoformat()
            release_slot_lock(str(booking.teacher_id), start_iso, str(booking.student_id))
            return {"status": "success", "transaction_id": transaction_id}

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

        # Trigger asynchronous background task for external APIs (Zoom, GCal, Resend)
        try:
            from apps.integrations.tasks import dispatch_booking_fulfillment
            dispatch_booking_fulfillment.delay(str(booking.id))
        except Exception as e:
            logger.warning(f"Could not dispatch async Celery task (will run or retry): {e}")

    return {"status": "success", "transaction_id": transaction_id}

