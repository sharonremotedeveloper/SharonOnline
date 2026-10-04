import logging
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Exists, F, OuterRef, Sum
from celery import shared_task
from django.utils.html import escape

from apps.bookings.models import Booking, AttendanceAudit
from apps.bookings.services.state_machine import transition_booking
from apps.payments.services.settlement import RELEASABLE_STATUSES, attendance_verified_for_release, settled_exists
from apps.payments.models import BookingFunding, PaymentTransaction, RefundRequest, SettlementAnomaly
from apps.payments.services.alerts import alert_admin
from apps.payments.services.reconciliation import reconcile_initialized_transaction, reconcile_pending_capture
from apps.payments.services.funding import funding_for_settlement
from apps.admin_api.models import DisputeCase
from apps.common.locks import distributed_task_lock
from apps.integrations.email import EmailDeliveryError, send_email
from apps.integrations.services.attendance import TEACHER, credited_attendance_minutes

logger = logging.getLogger(__name__)

PENDING_ALERT_AFTER = timedelta(days=7)
# PayPal itself gives up on an unresolved pending after about a month: from then on a person must decide.
PENDING_CRITICAL_AFTER = timedelta(days=35)


@shared_task(bind=True, autoretry_for=(EmailDeliveryError,), retry_backoff=30, retry_backoff_max=900, max_retries=8)
def send_admin_alert_email_task(self, subject: str, detail: str):
    """One e-mail to the support inbox for an admin alert (the durable record is the GatewayAnomaly row)."""
    from django.conf import settings
    send_email(settings.SUPPORT_TO_EMAIL, f"[Sharon Online alert] {subject}", f"<p>{escape(detail)}</p>", detail)


@shared_task(bind=True, autoretry_for=(EmailDeliveryError,), retry_backoff=30, retry_backoff_max=900, max_retries=5)
def send_payment_failure_email_task(self, transaction_id: str, kind: str, ticket_id: str):
    """Tell the student, in plain words, that a pending payment did not go through."""
    from apps.payments.services.notices import student_email
    tx = PaymentTransaction.objects.select_related('booking__student', 'credit_purchase__user').filter(pk=transaction_id).first()
    if tx is None:
        return
    student = tx.credit_purchase.user if tx.credit_purchase_id else tx.booking.student
    if not student.email:
        return
    subject, html, text = student_email(student, tx, kind, ticket_id)
    send_email(student.email, subject, html, text)


def _flag_payment_still_pending(booking, funding) -> None:
    """T+24h and the grace payment is still PENDING: a durable SettlementAnomaly plus one admin alert, never a payout."""
    anomaly, created = SettlementAnomaly.objects.get_or_create(
        booking=booking, code='grace_payment_still_pending', resolved=False,
        defaults={'detail': f"Lesson finished and its dispute window passed, but PayPal capture "
                            f"{funding.payment_transaction.gateway_reference} is still pending. Tutor payout is blocked."})
    logger.warning("Escrow release blocked for booking %s: grace payment still pending.", booking.id)
    alert_admin(
        'grace_payment_still_pending', 'A delivered lesson is still waiting for its payment to clear',
        f"Booking {booking.id}: PayPal capture {funding.payment_transaction.gateway_reference} "
        f"({funding.captured_amount} {funding.currency}) is still pending 24h after the lesson. The tutor is not paid until it clears or fails.",
        key=str(booking.id), tx=funding.payment_transaction, booking=booking)


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
            # a grace booking already flagged "payment still pending" is waiting for a person / the reconcile job; do not
            # let such rows fill the 50-row batch every 15 minutes (on_completed / on_failed resolve the anomaly)
            .exclude(Exists(SettlementAnomaly.objects.filter(
                booking=OuterRef('pk'), code='grace_payment_still_pending', resolved=False)))
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
            if funding.source_type == BookingFunding.SourceType.GATEWAY_PENDING:
                # Grace booking: the lesson is over and PayPal still has not cleared the money. Nothing is released and
                # nobody is paid; a person has to look at it (it re-raises nothing while the anomaly is open).
                _flag_payment_still_pending(booking, funding)
                continue
            tx = funding.payment_transaction
            absorbed = funding.source_type == BookingFunding.SourceType.PLATFORM_ABSORBED
            gross = funding.captured_amount
            tutor_net = (gross * Decimal('0.80')).quantize(Decimal('0.01'))
            platform_fee = gross - tutor_net

            if tx and not absorbed:
                tx.escrow_cleared = True
                tx.save(update_fields=['escrow_cleared', 'updated_at'])

            booking.escrow_cleared_at = now
            booking.save(update_fields=['escrow_cleared_at', 'updated_at'])
            if booking.status == Booking.Status.COMPLETED_PENDING_MEMO:
                transition_booking(booking, Booking.Status.COMPLETED, actor='system:escrow_release',
                                   reason='24h escrow window cleared')

            # Record GAAP/SARB double-entry ledger clearance entries
            if absorbed:
                # The student's payment failed after the lesson: the platform funds the tutor's share (ledger 5040 -> 2020).
                from apps.payments.services.ledger_service import record_absorbed_tutor_payment_entry
                record_absorbed_tutor_payment_entry(booking, funding)
            else:
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

    # PayPal captures that came back PENDING (grace bookings or held slots): poll them by capture id until they resolve,
    # and tell the admin about any that has been pending for more than a week.
    pending_txs = list(PaymentTransaction.objects.filter(
        status=PaymentTransaction.Status.PENDING_CAPTURE).select_related('booking', 'credit_purchase')
        .order_by(F('last_reconciled_at').asc(nulls_first=True), 'created_at')[:100])
    pending_results = {'completed': 0, 'failed': 0, 'pending': 0, 'unresolved': 0}
    for payment_transaction in pending_txs:
        result = reconcile_pending_capture(payment_transaction)
        pending_results[result.state] = pending_results.get(result.state, 0) + 1
        if result.state in ('pending', 'unresolved') and now - payment_transaction.created_at > PENDING_ALERT_AFTER:
            alert_admin(
                'grace_pending_over_7_days', 'A PayPal payment has been pending for more than 7 days',
                f"Capture {payment_transaction.gateway_reference} ({payment_transaction.amount} {payment_transaction.currency}) "
                f"has been pending since {payment_transaction.created_at:%Y-%m-%d}. Check it in PayPal.",
                key=payment_transaction.merchant_reference or str(payment_transaction.pk), tx=payment_transaction)
        if result.state in ('pending', 'unresolved') and now - payment_transaction.created_at > PENDING_CRITICAL_AFTER:
            alert_admin(
                'grace_pending_over_35_days', 'CRITICAL: a PayPal payment is still pending after 35 days',
                f"Capture {payment_transaction.gateway_reference} ({payment_transaction.amount} {payment_transaction.currency}) "
                f"has been pending since {payment_transaction.created_at:%Y-%m-%d}. PayPal normally returns an unresolved "
                f"payment to the buyer after about a month: decide now whether the lesson stands, and contact the student.",
                key=payment_transaction.merchant_reference or str(payment_transaction.pk), tx=payment_transaction)
    return {"reconciled_count": len(abandoned_txs), **results, "pending_captures": pending_results}


@shared_task(name='apps.payments.tasks.expire_credits_task')
@distributed_task_lock('lock:beat:expire_credits', timeout_seconds=3000)
def expire_credits_task():
    """Daily: write off wallet credit lots whose 30-day expiry has passed (value moves from 2040 to breakage revenue 4020)."""
    from apps.payments.services.credits import expire_credits
    return expire_credits()


@shared_task(name='apps.payments.tasks.process_pending_refunds_task')
@distributed_task_lock('lock:beat:process_pending_refunds', timeout_seconds=800)
def process_pending_refunds_task():
    """
    Every 15 minutes: claim due refunds and hand them to the configured gateway, poll the ones the gateway accepted but has not
    finished (Task 10.7). Bounded by REFUND_SWEEP_LIMIT rows / REFUND_SWEEP_BUDGET_SECONDS (600 s, under this lock's 800 s TTL);
    the lock is best-effort, the compare-and-swap claim in `refunds.claim_due_refunds` is what keeps two workers apart.
    """
    from apps.payments.services.refunds import process_pending_refunds
    return process_pending_refunds()


@shared_task(bind=True, autoretry_for=(EmailDeliveryError,), retry_backoff=30, retry_backoff_max=900, max_retries=5)
def send_refund_processed_email_task(self, refund_id: str):
    """
    Tell the student, once, that their refund has been sent. Queued exactly when the refund becomes `processed` (that transition
    happens once); the cache key makes a duplicate delivery of the task itself harmless. Plain words, no provider references.
    """
    from django.core.cache import cache
    from apps.common.money import money_str
    refund = RefundRequest.objects.select_related('user').filter(pk=refund_id).first()
    if refund is None or refund.status != RefundRequest.Status.PROCESSED or not refund.user.email:
        return
    key = f'refund-processed-email:{refund.pk}'
    if not cache.add(key, 1, timeout=60 * 86400):         # atomic claim BEFORE sending: a duplicate delivery during the send finds it taken
        return
    name = refund.user.first_name or refund.user.username
    amount = f"{money_str(refund.amount, refund.currency)} {refund.currency}"
    lines = [f"Your refund of {amount} has been sent back to the payment method you used.",
             "It can take 3 to 5 business days to show up on your statement or in your PayPal account.",
             "If you do not see it after that, reply to this e-mail and we will look into it."]
    text = f"Hi {name},\n\n" + "\n\n".join(lines) + "\n\nSharon Online"
    html = f"<p>Hi {escape(name)},</p>" + "".join(f"<p>{escape(line)}</p>" for line in lines) + "<p>Sharon Online</p>"
    try:
        send_email(refund.user.email, "Your refund has been sent", html, text)
    except Exception:
        cache.delete(key)                                  # nothing was delivered: release the claim so the retry can send
        raise
