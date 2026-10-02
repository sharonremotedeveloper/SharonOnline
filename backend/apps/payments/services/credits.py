from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import F, Sum

from apps.payments.models import BookingFunding, CreditBundle, CreditPurchase, CreditWalletEntry, PaymentTransaction


CENT = Decimal('0.01')


def wallet_balance(user) -> int:
    return int(CreditBundle.objects.filter(user=user).aggregate(total=Sum('remaining_credits'))['total'] or 0)


@transaction.atomic
def grant_credit(
    user,
    *,
    credits: int = 1,
    pack_name: str = 'Lesson Credit',
    unit_amount=Decimal('0.00'),
    currency: str = 'USD',
    fx_rate_to_zar=Decimal('1.000000'),
    fx_source: str = 'operational_credit',
    entry_type: str = CreditWalletEntry.EntryType.BONUS,
    booking=None,
    idempotency_key: str | None = None,
) -> CreditBundle:
    """Grant a new immutable credit lot and matching wallet entry."""
    if credits < 1:
        raise ValueError('credits must be >= 1')
    if idempotency_key:
        existing = CreditWalletEntry.objects.select_related('bundle').filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing.bundle

    unit = Decimal(str(unit_amount)).quantize(CENT, ROUND_HALF_UP)
    fx = Decimal(str(fx_rate_to_zar))
    before = wallet_balance(user)
    bundle = CreditBundle.objects.create(
        user=user, pack_name=pack_name, total_credits=credits, remaining_credits=credits,
        amount_paid=(unit * credits).quantize(CENT), currency=currency.upper(),
        unit_amount=unit, fx_rate_to_zar=fx, fx_source=fx_source,
    )
    CreditWalletEntry.objects.create(
        user=user, bundle=bundle, entry_type=entry_type, credit_delta=credits,
        balance_after=before + credits, amount=(unit * credits).quantize(CENT),
        currency=currency.upper(), fx_rate_to_zar=fx, fx_source=fx_source,
        booking=booking, description=pack_name, idempotency_key=idempotency_key,
    )
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
    before = wallet_balance(purchase.user)
    bundle = CreditBundle.objects.create(
        user=purchase.user, pack_name=purchase.pack.name, total_credits=purchase.pack.credits,
        remaining_credits=purchase.pack.credits, amount_paid=purchase.amount,
        currency=purchase.currency, credit_purchase=purchase, unit_amount=unit,
        fx_rate_to_zar=purchase.fx_rate_to_zar, fx_source=purchase.fx_source,
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


class CreditRedemptionError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


@transaction.atomic
def redeem_booking_credit(*, booking, student):
    """Consume the oldest funded lot and confirm a held booking as one transaction."""
    from django.utils import timezone
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
    if booking.status != Booking.Status.PENDING_PAYMENT:
        raise CreditRedemptionError(409, f"Booking is '{booking.status}' and cannot redeem a credit.")
    if not hold_is_live(booking, timezone.now()):
        raise CreditRedemptionError(409, 'This reservation has expired. Please choose the time slot again.')
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

    bundle = (CreditBundle.objects.select_for_update().filter(user=student, remaining_credits__gt=0)
              .order_by('created_at', 'id').first())
    if bundle is None:
        raise CreditRedemptionError(409, 'No lesson credits are available.')

    CreditBundle.objects.filter(pk=bundle.pk).update(remaining_credits=F('remaining_credits') - 1)
    bundle.refresh_from_db(fields=['remaining_credits'])
    unit = bundle.unit_amount
    if unit == 0 and bundle.total_credits:
        unit = (bundle.amount_paid / Decimal(bundle.total_credits)).quantize(CENT, ROUND_HALF_UP)
    if unit <= 0:
        raise CreditRedemptionError(409, 'This legacy credit has no funding value and requires support review.')
    balance_after = wallet_balance(student)
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
