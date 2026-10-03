import logging
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from celery import shared_task

from apps.bookings.models import Booking, AttendanceAudit
from apps.bookings.services.state_machine import transition_booking
from apps.payments.services.settlement import RELEASABLE_STATUSES, attendance_verified_for_release, settled_exists
from apps.payments.models import PaymentTransaction
from apps.payments.services.reconciliation import reconcile_initialized_transaction
from apps.payments.services.funding import funding_for_settlement
from apps.admin_api.models import DisputeCase
from apps.common.locks import distributed_task_lock
from apps.integrations.services.attendance import TEACHER, credited_attendance_minutes

logger = logging.getLogger(__name__)


@shared_task(name='apps.payments.tasks.release_cleared_escrow_task')
@distributed_task_lock('lock:beat:release_cleared_escrow', timeout_seconds=800)
def release_cleared_escrow_task():
    """
    Periodic task running every 15 minutes:
    Dual verification escrow release engine:
    1. 24 hours have elapsed since lesson end (end_time_utc <= now - 24h).
    2. Attendance validated: tutor logged >= 20 minutes (completed lessons) or was present at T+10m (student no-show).
    3. Excludes bookings with an open DisputeCase and bookings whose escrow is already settled (arbitration, refund, outage).
    4. Settles 80% net to tutor and marks transaction escrow_cleared = True.
    """
    now = timezone.now()
    cutoff_24h = now - timedelta(hours=24)
    cleared_count = 0
    total_cleared_usd = Decimal('0.00')

    with transaction.atomic():
        open_dispute_booking_ids = DisputeCase.objects.filter(
            status=DisputeCase.Status.OPEN
        ).values_list('booking_id', flat=True)

        candidates = list(
            Booking.objects.select_for_update(of=('self',), skip_locked=True)
            .filter(
                status__in=RELEASABLE_STATUSES,
                end_time_utc__lte=cutoff_24h,
                escrow_cleared_at__isnull=True
            )
            .exclude(id__in=open_dispute_booking_ids)
            .exclude(settled_exists())  # arbitration / refunds may already have settled this booking's escrow
            .select_related('teacher__user')[:50]
        )

        for booking in candidates:
            # Dual verification: check attendance minutes
            teacher_minutes = credited_attendance_minutes(booking, TEACHER, through=booking.end_time_utc)

            if not attendance_verified_for_release(booking, teacher_minutes):
                logger.warning(
                    f"Escrow release held for booking {booking.id}: teacher attendance was {teacher_minutes}m (<20m)."
                )
                continue

            funding = funding_for_settlement(booking, context='release_cleared_escrow_task')
            if funding is None:
                logger.error('Escrow release stopped for booking %s: missing funding provenance.', booking.id)
                continue
            tx = funding.payment_transaction
            gross = funding.captured_amount
            tutor_net = (gross * Decimal('0.80')).quantize(Decimal('0.01'))
            platform_fee = gross - tutor_net

            if tx:
                tx.escrow_cleared = True
                tx.save(update_fields=['escrow_cleared', 'updated_at'])

            booking.escrow_cleared_at = now
            booking.save(update_fields=['escrow_cleared_at', 'updated_at'])
            if booking.status == Booking.Status.COMPLETED_PENDING_MEMO:
                transition_booking(booking, Booking.Status.COMPLETED, actor='system:escrow_release',
                                   reason='24h escrow window cleared')

            # Record GAAP/SARB double-entry ledger clearance entries
            from apps.payments.services.ledger_service import record_escrow_clearance_entry
            record_escrow_clearance_entry(
                booking=booking,
                payment_transaction=tx,
                funding=funding,
            )

            cleared_count += 1
            if funding.currency == 'USD':
                total_cleared_usd += tutor_net
            logger.info(
                f"[ESCROW CLEARED] Booking {booking.id}: Net {tutor_net} {funding.currency} to tutor "
                f"{booking.teacher.user.username}, fee {platform_fee} {funding.currency} to platform."
            )

    return {
        "cleared_count": cleared_count,
        "total_cleared_usd": str(total_cleared_usd)
    }


@shared_task(name='apps.payments.tasks.reconcile_pending_transactions_task')
@distributed_task_lock('lock:beat:reconcile_pending_tx', timeout_seconds=3000)
def reconcile_pending_transactions_task():
    """
    Hourly maintenance task:
    Queries provider-aware reconciliation for old initialized checkouts. A transaction is marked
    failed only when the provider says so; unavailable or inconclusive status remains initialized
    and creates a durable anomaly for operator follow-up.
    """
    now = timezone.now()
    cutoff_2h = now - timedelta(hours=2)

    abandoned_txs = list(PaymentTransaction.objects.filter(
        status=PaymentTransaction.Status.INITIALIZED,
        created_at__lt=cutoff_2h
    ).select_related('booking', 'credit_purchase')[:100])
    results = {'failed': 0, 'pending': 0, 'unresolved': 0, 'completed': 0, 'errors': 0}
    for payment_transaction in abandoned_txs:
        try:
            result = reconcile_initialized_transaction(payment_transaction)
        except Exception:
            # One poisoned row must not stop the rest of the batch from ever being reconciled; it is logged in full and
            # retried next run (its state is untouched), so it stays visible rather than silently skipped.
            logger.exception("Reconciliation of transaction %s raised; continuing with the batch", payment_transaction.pk)
            results['errors'] += 1
            continue
        results[result.state] = results.get(result.state, 0) + 1

    logger.info("Gateway reconciliation inspected %s transactions: %s", len(abandoned_txs), results)
    return {"reconciled_count": len(abandoned_txs), **results}


@shared_task(name='apps.payments.tasks.expire_credits_task')
@distributed_task_lock('lock:beat:expire_credits', timeout_seconds=3000)
def expire_credits_task():
    """Daily: write off wallet credit lots whose 30-day expiry has passed (value moves from 2040 to breakage revenue 4020)."""
    from apps.payments.services.credits import expire_credits
    return expire_credits()


@shared_task(name='apps.payments.tasks.process_pending_refunds_task')
@distributed_task_lock('lock:beat:process_pending_refunds', timeout_seconds=800)
def process_pending_refunds_task():
    """Every 15 minutes: send queued refunds to the configured gateway (Task 10.7 plugs in PayPal / PayFast)."""
    from apps.payments.services.refunds import process_pending_refunds
    return process_pending_refunds()
