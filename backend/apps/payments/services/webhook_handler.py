from django.db import transaction
from apps.payments.models import PaymentTransaction
from apps.bookings.models import Booking
from apps.bookings.services.lock_service import release_slot_lock
import logging

logger = logging.getLogger(__name__)

@transaction.atomic
def process_payment_webhook(booking_id: str, gateway: str, transaction_id: str, amount: float, currency: str, status: str, raw_payload: dict) -> dict:
    """
    Idempotent payment webhook ingestion.
    Guarantees that multiple retries from payment gateways (PayFast/PayPal)
    never result in double bookings, duplicate meetings, or corrupted ledgers.
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
            booking = Booking.objects.select_for_update().get(id=booking_id)
            booking.status = Booking.Status.CONFIRMED
            booking.save()

            # Release the temporary Redis lock now that it's permanently confirmed in PostgreSQL
            start_iso = booking.start_time_utc.isoformat()
            release_slot_lock(str(booking.teacher_id), start_iso, str(booking.student_id))

            # Trigger asynchronous background task for external APIs (Zoom, GCal, Resend)
            try:
                from apps.integrations.tasks import dispatch_booking_fulfillment
                dispatch_booking_fulfillment.delay(str(booking.id))
            except Exception as e:
                logger.warning(f"Could not dispatch async Celery task (will run or retry): {e}")

        except Booking.DoesNotExist:
            logger.error(f"Booking {booking_id} referenced in transaction {transaction_id} does not exist")
            return {"error": "booking_not_found"}

    return {"status": "success", "transaction_id": transaction_id}
