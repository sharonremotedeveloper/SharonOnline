"""
Lesson credits (the student wallet), kept as immutable *lots* with their own expiry.

* Every grant is its own `CreditBundle` row plus an append-only `CreditWalletEntry` (the wallet history).
* Lots expire (`CREDIT_EXPIRY_DAYS_*`, decision D-6: 30 days) and are spent soonest-expiry-first; expired lots are never spendable,
  even before the daily job writes them off.
* `grant_credit()` is the only way to add credits. The caller posts the matching ledger entry (wallet liability, 2040); this module
  posts only the expiry write-off, because only it knows what expired.
"""
import logging
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.payments.models import (BookingFunding, CreditBundle, CreditPurchase, CreditWalletEntry, LedgerAccount,
                                  LedgerEntry, PaymentTransaction)

logger = logging.getLogger(__name__)
CENT = Decimal('0.01')


class InsufficientCredits(Exception):
    """The student does not have that many unexpired credits."""


def _expiry_days(source: str) -> int:
    return {
        CreditBundle.Source.PURCHASE: settings.CREDIT_EXPIRY_DAYS_BUNDLE,
        CreditBundle.Source.BONUS: settings.CREDIT_EXPIRY_DAYS_BONUS,
    }.get(source, settings.CREDIT_EXPIRY_DAYS_REFUND)


# What a grant of each source is called in the wallet history.
_ENTRY_TYPE = {
    CreditBundle.Source.PURCHASE: CreditWalletEntry.EntryType.PURCHASE,
    CreditBundle.Source.REFUND: CreditWalletEntry.EntryType.REFUND,
    CreditBundle.Source.BONUS: CreditWalletEntry.EntryType.BONUS,
    CreditBundle.Source.RESTITUTION: CreditWalletEntry.EntryType.REFUND,
}


def available_credits(user, now=None) -> int:
    """Credits the student can still spend (expired lots excluded immediately, before the expiry job has run)."""
    return int(CreditBundle.objects.active(now).filter(user=user).aggregate(t=Sum('remaining_credits'))['t'] or 0)


wallet_balance = available_credits       # the name the wallet history code uses


def _spend_order(qs):
    """Soonest to expire first; lots without a date (legacy) last."""
    return qs.order_by(F('expires_at').asc(nulls_last=True), 'created_at', 'id')


@transaction.atomic
def grant_credit(
    user,
    *,
    credits: int = 1,
    pack_name: str = 'Lesson Credit',
    source: str = CreditBundle.Source.RESTITUTION,
    unit_amount=Decimal('0.00'),
    currency: str = 'USD',
    fx_rate_to_zar=Decimal('1.000000'),
    fx_source: str = 'operational_credit',
    entry_type: str | None = None,
    booking=None,
    idempotency_key: str | None = None,
    expires_in_days: int | None = None,
) -> CreditBundle:
    """
    Grant a new credit lot (with its wallet-history entry) and return it. Idempotent when `idempotency_key` is given.
    `unit_amount` is the money value of ONE credit in `currency`: the expiry job needs it to post the write-off.
    Call this inside the transaction that justifies the grant.
    """
    if credits < 1:
        raise ValueError('credits must be >= 1')
    if idempotency_key:
        existing = CreditWalletEntry.objects.select_related('bundle').filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing.bundle

    unit = Decimal(str(unit_amount)).quantize(CENT, ROUND_HALF_UP)
    fx = Decimal(str(fx_rate_to_zar))
    days = _expiry_days(source) if expires_in_days is None else expires_in_days
    before = available_credits(user)
    bundle = CreditBundle.objects.create(
        user=user, pack_name=pack_name, total_credits=credits, remaining_credits=credits,
        amount_paid=(unit * credits).quantize(CENT), currency=currency.upper(), source=source,
        unit_amount=unit, fx_rate_to_zar=fx, fx_source=fx_source, expires_at=timezone.now() + timedelta(days=days),
    )
    CreditWalletEntry.objects.create(
        user=user, bundle=bundle, entry_type=entry_type or _ENTRY_TYPE.get(source, CreditWalletEntry.EntryType.BONUS),
        credit_delta=credits, balance_after=before + credits, amount=(unit * credits).quantize(CENT),
        currency=currency.upper(), fx_rate_to_zar=fx, fx_source=fx_source,
        booking=booking, description=pack_name, idempotency_key=idempotency_key,
    )
    try:
        from apps.notifications.service import notify
        notify(user, 'credit_granted', key=f'credit-granted:{bundle.id}',
               payload={'credits': credits, 'reason': str(source)}, booking=booking)
    except Exception as exc:
        logger.warning('credit_granted notification failed for bundle %s: %s', bundle.id, type(exc).__name__)
    return bundle


@transaction.atomic
def capture_credit_purchase(purchase: CreditPurchase, payment_transaction: PaymentTransaction) -> CreditBundle:
    """Idempotently turn a verified gateway capture into a funded credit lot."""
    purchase = CreditPurchase.objects.select_for_update().select_related('pack', 'user').get(pk=purchase.pk)
    existing = CreditBundle.objects.filter(credit_purchase=purchase).first()
    if existing:
        return existing

    payment_transaction.status = PaymentTransaction.Status.SUCCESS
    payment_transaction.save(update_fields=['status', 'updated_at'])
    purchase.status = CreditPurchase.Status.SUCCESS
    purchase.save(update_fields=['status', 'updated_at'])

    unit = (purchase.amount / Decimal(purchase.pack.credits)).quantize(CENT, ROUND_HALF_UP)
    before = available_credits(purchase.user)
    bundle = CreditBundle.objects.create(
        user=purchase.user, pack_name=purchase.pack.name, total_credits=purchase.pack.credits,
        remaining_credits=purchase.pack.credits, amount_paid=purchase.amount,
        currency=purchase.currency, credit_purchase=purchase, unit_amount=unit,
        fx_rate_to_zar=purchase.fx_rate_to_zar, fx_source=purchase.fx_source, source=CreditBundle.Source.PURCHASE,
        expires_at=timezone.now() + timedelta(days=settings.CREDIT_EXPIRY_DAYS_BUNDLE),
    )
    CreditWalletEntry.objects.create(
        user=purchase.user, bundle=bundle, entry_type=CreditWalletEntry.EntryType.PURCHASE,
        credit_delta=purchase.pack.credits, balance_after=before + purchase.pack.credits,
        amount=purchase.amount, currency=purchase.currency, fx_rate_to_zar=purchase.fx_rate_to_zar,
        fx_source=purchase.fx_source, credit_purchase=purchase,
        description=f'{purchase.pack.name} purchase', idempotency_key=f'purchase:{purchase.id}',
    )

    from apps.payments.services.ledger_service import record_credit_purchase_capture_entry
    record_credit_purchase_capture_entry(payment_transaction=payment_transaction, purchase=purchase)
    return bundle


def spend_credit(user, *, credits: int = 1, now=None):
    """
    Take `credits` from the lots that expire soonest. Returns [(lot, taken), ...]. All-or-nothing: raises InsufficientCredits
    (and spends nothing) when the unexpired balance is too small. Call inside the caller's transaction.
    """
    if credits < 1:
        raise ValueError("credits must be >= 1")
    with transaction.atomic():
        lots = list(_spend_order(CreditBundle.objects.select_for_update().active(now).filter(user=user, remaining_credits__gt=0)))
        have = sum(l.remaining_credits for l in lots)
        if have < credits:
            raise InsufficientCredits(f"Needs {credits} credit(s); {have} available.")
        taken, left = [], credits
        for lot in lots:
            n = min(lot.remaining_credits, left)
            lot.remaining_credits -= n
            lot.save(update_fields=['remaining_credits'])
            taken.append((lot, n))
            left -= n
            if not left:
                break
        return taken


class CreditRedemptionError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


@transaction.atomic
def redeem_booking_credit(*, booking, student):
    """Consume the soonest-to-expire funded lot and confirm a held booking as one transaction."""
    from apps.bookings.models import Booking
    from apps.bookings.services.holds import SLOT_OWNING_STATUSES, hold_is_live
    from apps.bookings.services.lock_service import extend_slot_lock, release_slot_lock
    from apps.bookings.services.state_machine import InvalidTransition, transition_booking

    booking = (Booking.objects.select_for_update().select_related('teacher__user', 'student')
               .get(pk=booking.pk))
    if booking.student_id != student.id:
        raise CreditRedemptionError(404, 'Booking not found.')

    existing = BookingFunding.objects.filter(booking=booking).first()
    if existing and booking.status == Booking.Status.CONFIRMED:
        return booking, False
    from apps.bookings.services.booking_block import booking_block_message
    blocked = booking_block_message(student)
    if blocked:
        raise CreditRedemptionError(409, blocked)
    if booking.status != Booking.Status.PENDING_PAYMENT:
        raise CreditRedemptionError(409, f"Booking is '{booking.status}' and cannot redeem a credit.")
    if not booking.teacher.is_bookable:            # a hold can outlive a suspension (slice T1b)
        raise CreditRedemptionError(409, 'This tutor is not currently bookable.')
    if not hold_is_live(booking, timezone.now()):
        raise CreditRedemptionError(409, 'This reservation has expired. Please choose the time slot again.')
    from apps.bookings.services.notice import TOO_CLOSE_MESSAGE, notice_closed      # T2: notice is enforced at pay time
    if notice_closed(booking.start_time_utc, timezone.now()):
        raise CreditRedemptionError(409, TOO_CLOSE_MESSAGE)
    if Booking.objects.filter(
        teacher=booking.teacher,
        start_time_utc=booking.start_time_utc,
        status__in=SLOT_OWNING_STATUSES,
    ).exclude(pk=booking.pk).exists():
        raise CreditRedemptionError(409, 'This time slot has just been booked by someone else.')
    if not extend_slot_lock(
        str(booking.teacher_id), booking.start_time_utc.isoformat(), str(student.id), 60,
        token=booking.slot_lock_token or None,
    ):
        raise CreditRedemptionError(409, 'This time slot has just been taken. Please choose another.')

    bundle = _spend_order(CreditBundle.objects.select_for_update().active().filter(user=student, remaining_credits__gt=0)).first()
    if bundle is None:
        raise CreditRedemptionError(409, 'No lesson credits are available.')

    CreditBundle.objects.filter(pk=bundle.pk).update(remaining_credits=F('remaining_credits') - 1)
    bundle.refresh_from_db(fields=['remaining_credits'])
    unit = bundle.unit_amount
    if unit == 0 and bundle.total_credits:
        unit = (bundle.amount_paid / Decimal(bundle.total_credits)).quantize(CENT, ROUND_HALF_UP)
    if unit <= 0:
        raise CreditRedemptionError(409, 'This legacy credit has no funding value and requires support review.')
    balance_after = available_credits(student)
    wallet_entry = CreditWalletEntry.objects.create(
        user=student, bundle=bundle, entry_type=CreditWalletEntry.EntryType.REDEMPTION,
        credit_delta=-1, balance_after=balance_after, amount=unit, currency=bundle.currency,
        fx_rate_to_zar=bundle.fx_rate_to_zar, fx_source=bundle.fx_source, booking=booking,
        description=f'Lesson credit redeemed for booking {booking.id}',
        idempotency_key=f'redeem:{booking.id}',
    )
    funding = BookingFunding.objects.create(
        booking=booking, source_type=BookingFunding.SourceType.CREDIT,
        captured_amount=unit, currency=bundle.currency,
        fx_rate_to_zar=bundle.fx_rate_to_zar, fx_source=bundle.fx_source,
        credit_wallet_entry=wallet_entry,
    )
    from apps.payments.services.ledger_service import record_credit_redemption_entry
    record_credit_redemption_entry(booking=booking, funding=funding)
    try:
        transition_booking(booking, Booking.Status.CONFIRMED, actor=student, reason='lesson credit redeemed')
    except InvalidTransition as exc:
        raise CreditRedemptionError(409, str(exc)) from exc

    def after_commit():
        release_slot_lock(
            str(booking.teacher_id), booking.start_time_utc.isoformat(), str(student.id),
            token=booking.slot_lock_token or None,
        )
        from apps.payments.services.webhook_handler import dispatch_fulfillment
        dispatch_fulfillment(str(booking.id))

    transaction.on_commit(after_commit)
    return booking, True


def expire_credits(now=None) -> dict:
    """
    Write off every lot whose expiry has passed. Idempotent: a lot is expired once (`expired_at`), under a row lock.
    The unspent value moves from the wallet liability (2040) to breakage revenue (4020), and the wallet history records it.
    """
    from apps.payments.services.ledger_service import record_journal_entries   # local: ledger_service imports models too

    now = now or timezone.now()
    lots_done, credits_done = 0, 0
    due = CreditBundle.objects.filter(expires_at__lte=now, expired_at__isnull=True, remaining_credits__gt=0).values_list('pk', flat=True)
    for pk in list(due):
        with transaction.atomic():
            lot = CreditBundle.objects.select_for_update().select_related('user').get(pk=pk)
            if lot.expired_at is not None or lot.remaining_credits < 1:
                continue
            gone = lot.remaining_credits
            value = (lot.unit_amount * gone).quantize(CENT)
            if value > 0:
                record_journal_entries(
                    entries=[
                        {'account': LedgerAccount.LIABILITY_STUDENT_WALLET, 'entry_type': LedgerEntry.EntryType.DEBIT,
                         'amount': value, 'currency': lot.currency, 'description': f"{gone} expired credit(s) written off"},
                        {'account': LedgerAccount.REVENUE_CREDIT_BREAKAGE, 'entry_type': LedgerEntry.EntryType.CREDIT,
                         'amount': value, 'currency': lot.currency, 'description': f"Breakage on expired credit lot {lot.pk}"},
                    ],
                    event_type=LedgerEntry.EventType.CREDIT_EXPIRED,
                    description=f"Credit lot {lot.pk} expired for {lot.user.username}",
                    user=lot.user, currency=lot.currency,
                    fx_rate_to_zar=lot.fx_rate_to_zar, fx_source=lot.fx_source)
            lot.expired_credits += gone
            lot.remaining_credits = 0
            lot.expired_at = now
            lot.save(update_fields=['expired_credits', 'remaining_credits', 'expired_at'])
            CreditWalletEntry.objects.create(
                user=lot.user, bundle=lot, entry_type=CreditWalletEntry.EntryType.EXPIRY, credit_delta=-gone,
                balance_after=available_credits(lot.user, now), amount=value, currency=lot.currency,
                fx_rate_to_zar=lot.fx_rate_to_zar, fx_source=lot.fx_source,
                description=f'{gone} credit(s) expired', idempotency_key=f'expiry:{lot.pk}')
            lots_done += 1
            credits_done += gone
    if lots_done:
        logger.info("[CREDITS] Expired %s credit(s) in %s lot(s)", credits_done, lots_done)
    return {'lots': lots_done, 'credits': credits_done}
