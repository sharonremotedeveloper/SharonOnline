import logging
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from celery import shared_task

from apps.bookings.models import Booking, AttendanceAudit
from apps.payments.models import PaymentTransaction
from apps.admin_api.models import DisputeCase
from apps.common.locks import distributed_task_lock

logger = logging.getLogger(__name__)


@shared_task(name='apps.payments.tasks.release_cleared_escrow_task')
@distributed_task_lock('lock:beat:release_cleared_escrow', timeout_seconds=800)
def release_cleared_escrow_task():
    """
    Periodic task running every 15 minutes:
    Dual verification escrow release engine:
    1. 24 hours have elapsed since lesson completion (end_time_utc <= now - 24h).
    2. Attendance validated: tutor logged at least 20 minutes in session (or excused power outage).
    3. Excludes any booking with an active open DisputeCase.
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
                status__in=[
                    Booking.Status.COMPLETED,
                    Booking.Status.COMPLETED_PENDING_MEMO,
                    Booking.Status.COMPLETED_MEMO_FORFEITED
                ],
                end_time_utc__lte=cutoff_24h,
                escrow_cleared_at__isnull=True
            )
            .exclude(id__in=open_dispute_booking_ids)
            .select_related('teacher__user')[:50]
        )

        for booking in candidates:
            # Dual verification: check attendance minutes
            teacher_email = booking.teacher.user.email
            teacher_minutes = AttendanceAudit.objects.filter(
                booking=booking,
                participant_email=teacher_email
            ).aggregate(total=Sum('total_minutes'))['total'] or 0

            # Allow escrow clearance if teacher attended >= 20 mins or if power outage was excused
            is_attendance_verified = (teacher_minutes >= 20) or (booking.status == Booking.Status.INTERRUPTED_POWER)

            if not is_attendance_verified:
                logger.warning(
                    f"Escrow release held for booking {booking.id}: teacher attendance was {teacher_minutes}m (<20m)."
                )
                continue

            # Find matching successful transaction
            tx = PaymentTransaction.objects.filter(
                booking=booking,
                status=PaymentTransaction.Status.SUCCESS,
                escrow_cleared=False
            ).first()

            amount_usd = tx.amount if tx else booking.teacher.price_per_25min_usd
            tutor_net_usd = (amount_usd * Decimal('0.80')).quantize(Decimal('0.01'))
            platform_fee_usd = amount_usd - tutor_net_usd

            if tx:
                tx.escrow_cleared = True
                tx.save(update_fields=['escrow_cleared', 'updated_at'])

            booking.escrow_cleared_at = now
            if booking.status == Booking.Status.COMPLETED_PENDING_MEMO:
                booking.status = Booking.Status.COMPLETED
            booking.save(update_fields=['escrow_cleared_at', 'status', 'updated_at'])

            # Record GAAP/SARB double-entry ledger clearance entries
            from apps.payments.services.ledger_service import record_escrow_clearance_entry
            record_escrow_clearance_entry(
                booking=booking,
                payment_transaction=tx,
                amount_usd=amount_usd
            )

            cleared_count += 1
            total_cleared_usd += tutor_net_usd
            logger.info(
                f"[ESCROW CLEARED] Booking {booking.id}: Net ${tutor_net_usd} to tutor "
                f"{booking.teacher.user.username}, fee ${platform_fee_usd} to platform."
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
    Reconciles orphaned or unconfirmed payment transactions older than 2 hours.
    Marks abandoned sessions as FAILED to prevent ledger drift.
    """
    now = timezone.now()
    cutoff_2h = now - timedelta(hours=2)

    with transaction.atomic():
        abandoned_txs = PaymentTransaction.objects.select_for_update(skip_locked=True).filter(
            status=PaymentTransaction.Status.INITIALIZED,
            created_at__lt=cutoff_2h
        )
        count = abandoned_txs.count()
        abandoned_txs.update(status=PaymentTransaction.Status.FAILED)

    logger.info(f"Reconciled {count} abandoned payment transactions to FAILED.")
    return {"reconciled_count": count}
