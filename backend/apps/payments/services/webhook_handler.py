from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from apps.payments.services.credits import capture_credit_purchase, grant_credit
from apps.payments.models import BookingFunding, CreditPurchase, PaymentTransaction, GatewayAnomaly, FulfillmentDispatch
from apps.payments.services.funding import ensure_gateway_funding, gateway_fx_snapshot, persist_capture_snapshot
from apps.payments.services.ledger_service import (
    record_payment_capture_entry, record_def501_quarantine_entry, record_unallocated_payment_entry)
from apps.bookings.models import Booking
from apps.bookings.services.lock_service import release_slot_lock
from apps.bookings.services.state_machine import transition_booking
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
    persist_capture_snapshot(tx)       # the ledger values the journal at the rate stored on the transaction
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
    persist_capture_snapshot(tx)       # the ledger values the journal at the rate stored on the transaction
    record_unallocated_payment_entry(payment_transaction=tx, booking=booking, user=booking.student)
    GatewayAnomaly.objects.create(
        gateway=gateway, reference=transaction_id, reason=reason, detail=detail,
        booking=booking, payment_transaction=tx, payload=raw_payload or {})
    logger.error("[UNALLOCATED PAYMENT] %s %s %s on booking %s: %s (refund required)",
                 gateway, transaction_id, f"{amount} {currency}", booking.id, reason)
    return {"status": "unallocated", "reason": reason, "transaction_id": transaction_id}


def dispatch_fulfillment(booking_id: str) -> None:
    """Queue lesson fulfilment. A conditional UPDATE (bookings/services/fulfillment.py::requeue) never re-queues a dispatch that
    succeeded, failed for good, or is held by a live worker, so a duplicate webhook or sweep cannot start a second run."""
    from apps.bookings.services.fulfillment import requeue
    if not requeue(booking_id):
        return
    try:
        from apps.integrations.tasks import dispatch_booking_fulfillment
        dispatch_booking_fulfillment.delay(booking_id)
    except Exception as exc:
        now = timezone.now()
        FulfillmentDispatch.objects.filter(booking_id=booking_id, status=FulfillmentDispatch.Status.QUEUED).update(
            status=FulfillmentDispatch.Status.RETRYABLE, attempts=F('attempts') + 1, last_error=str(exc)[:2000],
            next_retry_at=now + timedelta(minutes=1), updated_at=now)
        logger.error("Could not dispatch fulfillment for booking %s (%s) - the retry sweep will re-dispatch it",
                     booking_id, type(exc).__name__)
        return


_SLOT_OWNING_STATUSES = (
    Booking.Status.CONFIRMED,
    Booking.Status.IN_PROGRESS,
    Booking.Status.COMPLETED,
    Booking.Status.COMPLETED_PENDING_MEMO,
    Booking.Status.COMPLETED_MEMO_FORFEITED,
)


def slot_unavailable_reason(booking, now=None) -> str:
    """
    DEF-501 guard shared by the normal payment confirmation and the grace confirmation: '' when the booking may still be
    confirmed, else why not ('slot_rebooked_by_another_student' / 'lesson_window_elapsed' / 'tutor_not_bookable').
    A hold can outlive its tutor's suspension (or the training gate): such a payment is quarantined like any other DEF-501
    case (DISPUTED, restitution credit, open DisputeCase, ledger 2030), never confirmed (slice T1b).
    """
    slot_conflict = Booking.objects.filter(
        teacher=booking.teacher, start_time_utc=booking.start_time_utc, status__in=_SLOT_OWNING_STATUSES,
    ).exclude(id=booking.id).exists()
    if slot_conflict:
        return "slot_rebooked_by_another_student"
    if booking.start_time_utc <= (now or timezone.now()):
        return "lesson_window_elapsed"
    if not booking.teacher.is_bookable:
        return "tutor_not_bookable"
    return ''


def finish_confirmed_booking(booking) -> None:
    """After a booking was confirmed: free the temporary Redis hold and queue Zoom / GCal / e-mail on commit."""
    # Release the temporary Redis lock now that it's permanently confirmed in PostgreSQL
    release_slot_lock(str(booking.teacher_id), booking.start_time_utc.isoformat(), str(booking.student_id),
                      token=booking.slot_lock_token or None)

    # Trigger background fulfillment (Zoom, GCal, Resend) only AFTER the commit, so the worker can never
    # observe the booking still PENDING_PAYMENT, and a rolled-back payment never queues a task.
    booking_id_str = str(booking.id)
    transaction.on_commit(lambda: dispatch_fulfillment(booking_id_str))


@transaction.atomic
def process_payment_webhook(*, booking_id=None, credit_purchase_id=None, gateway: str, transaction_id: str,
                            amount: float, currency: str, status: str, raw_payload: dict,
                            provider_fee_amount=None, provider_fee_currency: str = '') -> dict:
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
            'credit_purchase_id': credit_purchase_id,
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
        persist_capture_snapshot(tx)
        if provider_fee_amount is not None:
            fee = abs(Decimal(str(provider_fee_amount))).quantize(Decimal('0.01'))
            if fee > tx.amount:
                raise ValueError('Provider fee cannot exceed the captured amount.')
            tx.provider_fee_amount = fee
            tx.provider_fee_currency = (provider_fee_currency or tx.currency).upper()
            tx.save(update_fields=['provider_fee_amount', 'provider_fee_currency', 'updated_at'])

    if status == PaymentTransaction.Status.SUCCESS and (credit_purchase_id or tx.credit_purchase_id):
        purchase_id = credit_purchase_id or tx.credit_purchase_id
        try:
            purchase = CreditPurchase.objects.select_for_update().select_related('pack', 'user').get(pk=purchase_id)
        except CreditPurchase.DoesNotExist:
            logger.error('Credit purchase %s referenced in transaction %s does not exist', purchase_id, transaction_id)
            return {'error': 'credit_purchase_not_found'}
        capture_credit_purchase(purchase, tx)
        return {'status': 'success', 'transaction_id': transaction_id, 'credit_purchase_id': str(purchase.id)}

    if status == PaymentTransaction.Status.SUCCESS:
        try:
            booking = Booking.objects.select_for_update().select_related('teacher', 'student').get(id=booking_id)
        except Booking.DoesNotExist:
            logger.error(f"Booking {booking_id} referenced in transaction {transaction_id} does not exist")
            return {"error": "booking_not_found"}

        # A grace booking (confirmed while this very capture was PENDING) whose payment has now cleared is NOT a surplus
        # payment: the booking already exists and is already confirmed, so do not touch it, just settle the money.
        funding = BookingFunding.objects.select_for_update().filter(booking=booking).first()
        if (funding is not None and funding.source_type == BookingFunding.SourceType.GATEWAY_PENDING
                and funding.payment_transaction_id == tx.id):
            from apps.payments.services import grace
            grace.on_completed(tx)
            return {"status": "success", "transaction_id": transaction_id, "grace_cleared": True}

        # A booking that already has funding (a credit, or another payment, incl. a failed grace payment) is not paid for
        # again by a different transaction: that money is surplus.
        if funding is not None and funding.payment_transaction_id != tx.id:
            _hold_unallocated(tx, booking, 'booking_not_payable', 'booking already has funding from another source')
            return {"status": "unallocated", "reason": "booking_not_payable", "transaction_id": transaction_id}

        # Surplus payment (booking already confirmed/in progress/completed/disputed...): hold it, never touch the booking.
        if booking.status not in PAYABLE_BOOKING_STATES:
            _hold_unallocated(tx, booking, 'booking_not_payable', f"booking status is '{booking.status}'")
            return {"status": "unallocated", "reason": "booking_not_payable", "transaction_id": transaction_id}

        tx.status = PaymentTransaction.Status.SUCCESS
        tx.save()

        # Concurrency Guard (DEF-501): Check if slot expired or was re-booked by another student
        reason = slot_unavailable_reason(booking)
        if reason:
            # Slot was re-booked by another student or lesson has already elapsed!
            logger.warning(
                f"[DEF-501 CONCURRENCY GUARD] Booking {booking_id} conflict detected ({reason}). "
                f"Quarantining to DISPUTED and auto-crediting student wallet."
            )
            transition_booking(booking, Booking.Status.DISPUTED, actor=f'system:{gateway}_webhook',
                               reason=f'DEF-501: {reason}')

            # Restitution: credit student 1 lesson credit so funds are not lost
            fx_rate, fx_source = gateway_fx_snapshot(tx.currency)
            grant_credit(
                booking.student, credits=1, pack_name='DEF-501 restitution', unit_amount=tx.amount,
                currency=tx.currency, fx_rate_to_zar=fx_rate, fx_source=fx_source,
                entry_type='refund', booking=booking, idempotency_key=f'def501:{tx.id}',
            )

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
            persist_capture_snapshot(tx)
            record_def501_quarantine_entry(payment_transaction=tx, booking=booking, user=booking.student)

            start_iso = booking.start_time_utc.isoformat()
            release_slot_lock(str(booking.teacher_id), start_iso, str(booking.student_id),
                              token=booking.slot_lock_token or None)

            return {
                "status": "collision_quarantined",
                "reason": reason,
                "transaction_id": transaction_id,
                "booking_id": str(booking.id)
            }

        # Slot is free and session is in future: attempt confirmation under savepoint
        try:
            with transaction.atomic():
                transition_booking(booking, Booking.Status.CONFIRMED, actor=f'system:{gateway}_webhook',
                                   reason=f'payment {transaction_id} verified')
        except IntegrityError:
            # Microsecond race condition fallback: another transaction committed between check and save
            logger.warning(
                f"[DEF-501 RACE HAZARD] IntegrityError caught during booking {booking_id} confirmation. "
                f"Falling back to quarantine."
            )
            transition_booking(booking, Booking.Status.DISPUTED, actor=f'system:{gateway}_webhook',
                               reason='DEF-501: IntegrityError race on confirmation')

            fx_rate, fx_source = gateway_fx_snapshot(tx.currency)
            grant_credit(
                booking.student, credits=1, pack_name='DEF-501 race restitution', unit_amount=tx.amount,
                currency=tx.currency, fx_rate_to_zar=fx_rate, fx_source=fx_source,
                entry_type='refund', booking=booking, idempotency_key=f'def501-race:{tx.id}',
            )

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
            persist_capture_snapshot(tx)
            record_def501_quarantine_entry(payment_transaction=tx, booking=booking, user=booking.student)
            return {
                "status": "collision_quarantined",
                "reason": "race_condition_quarantined",
                "transaction_id": transaction_id,
                "booking_id": str(booking.id)
            }

        # Record standard payment capture in general ledger
        funding = ensure_gateway_funding(tx, booking)
        record_payment_capture_entry(
            payment_transaction=tx, booking=booking, user=booking.student,
            fx_rate_to_zar=funding.fx_rate_to_zar, fx_source=funding.fx_source,
        )

        finish_confirmed_booking(booking)

    return {"status": "success", "transaction_id": transaction_id}

