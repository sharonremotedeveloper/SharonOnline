from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from decimal import Decimal
import uuid


class LedgerImmutabilityError(ValidationError):
    """Raised when an immutable financial record is changed or deleted."""
    pass


LEGACY_FX_SOURCE = 'legacy_default'     # historical value on rows that predate Task 10.1; never written again


class MissingLedgerFx(ValueError):
    """A journal line was about to be posted without the exchange rate and source it was captured at.
    The ledger never values money at an invented rate."""


class ImmutableFinancialQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise LedgerImmutabilityError('Immutable financial records cannot be updated.')

    def delete(self):
        raise LedgerImmutabilityError('Immutable financial records cannot be deleted.')

class PaymentTransaction(models.Model):
    class Gateway(models.TextChoices):
        PAYFAST = 'payfast', 'PayFast (ZAR)'
        PAYPAL = 'paypal', 'PayPal (USD/EUR/JPY)'

    class Status(models.TextChoices):
        INITIALIZED = 'initialized', 'Initialized'
        # The gateway accepted the capture but has not guaranteed the money (PayPal PENDING). Never settled: no ledger
        # posting, no escrow, no payout until it resolves (Task 10.2 grace bookings).
        PENDING_CAPTURE = 'pending_capture', 'Pending capture (not yet guaranteed)'
        SUCCESS = 'success', 'Successful'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'
        # Money captured by the gateway that could not be applied to its booking (duplicate payment, booking already
        # confirmed/completed). Held in ledger acct 2030 pending a gateway refund; never enters escrow or payouts.
        UNALLOCATED = 'unallocated', 'Unallocated (refund pending)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey('bookings.Booking', on_delete=models.PROTECT, null=True, blank=True, related_name='transactions')
    credit_purchase = models.ForeignKey('payments.CreditPurchase', on_delete=models.PROTECT, null=True, blank=True,
                                        related_name='transactions')
    # PayPal Orders v2: the order created at checkout (the capture id later replaces gateway_reference).
    gateway_order_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    # Why PayPal left the capture pending (status_details.reason) and who the payer is (per-payer grace cap).
    pending_reason = models.CharField(max_length=64, blank=True)
    payer_id = models.CharField(max_length=64, blank=True, db_index=True)
    payer_email = models.EmailField(blank=True)
    gateway = models.CharField(max_length=20, choices=Gateway.choices)
    gateway_reference = models.CharField(max_length=255, unique=True, db_index=True)
    # Our own reference (sent to the gateway as m_payment_id / custom_id) so webhooks can find the expected amount.
    merchant_reference = models.CharField(max_length=64, unique=True, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    fx_rate_to_zar = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    fx_source = models.CharField(max_length=64, blank=True)
    provider_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    provider_fee_currency = models.CharField(max_length=3, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INITIALIZED, db_index=True)
    escrow_cleared = models.BooleanField(default=False, db_index=True)
    raw_webhook_payload = models.JSONField(default=dict)
    reconciliation_attempts = models.PositiveIntegerField(default=0)
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(booking__isnull=False) & models.Q(credit_purchase__isnull=True)) |
                    (models.Q(booking__isnull=True) & models.Q(credit_purchase__isnull=False))
                ),
                name='payment_transaction_exactly_one_target',
            ),
        ]

    def __str__(self):
        return f"{self.gateway.upper()} {self.amount} {self.currency} - {self.status} ({self.gateway_reference})"


class GatewayAnomaly(models.Model):
    """
    Durable record of a gateway notification that passed authentication (signature/IP) but could not be applied
    (amount mismatch, unknown reference, duplicate payment...). Money may have moved, so these need a human or the
    reconciliation job - a log line is not enough. Only written AFTER authentication, so unauthenticated callers cannot
    fill this table.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway = models.CharField(max_length=20, choices=PaymentTransaction.Gateway.choices)
    reference = models.CharField(max_length=255, blank=True, db_index=True)
    reason = models.CharField(max_length=64, db_index=True)
    detail = models.TextField(blank=True)
    booking = models.ForeignKey('bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='gateway_anomalies')
    payment_transaction = models.ForeignKey(PaymentTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='anomalies')
    payload = models.JSONField(default=dict)
    resolved = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.gateway} {self.reason} {self.reference} ({'resolved' if self.resolved else 'OPEN'})"


class CreditBundleQuerySet(models.QuerySet):
    def active(self, now=None):
        """Lots whose credits can still be spent. A lot with no expiry date (legacy rows) never expires."""
        from django.utils import timezone
        return self.filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now or timezone.now()))


class CreditPack(models.Model):
    """Server-authoritative, versionable launch catalog."""
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    credits = models.PositiveSmallIntegerField()
    price_usd = models.DecimalField(max_digits=10, decimal_places=2)
    price_zar = models.DecimalField(max_digits=10, decimal_places=2)
    price_eur = models.DecimalField(max_digits=10, decimal_places=2)
    price_jpy = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', 'credits']

    def price_for(self, currency: str) -> Decimal:
        field = f'price_{currency.lower()}'
        if field not in {'price_usd', 'price_zar', 'price_eur', 'price_jpy'}:
            raise ValueError(f'Unsupported credit-pack currency: {currency}')
        return getattr(self, field)

    def __str__(self):
        return f"{self.name} ({self.credits} credits)"


class LessonPrice(models.Model):
    """
    D-1: the platform-set flat retail price of one 25-minute lesson, one row per currency. The single source of truth
    for lesson amounts; tutors do not set prices. JPY has no minor unit, so its amount must be a whole number.
    """
    SUPPORTED = ('USD', 'EUR', 'JPY', 'ZAR')

    currency = models.CharField(max_length=3, primary_key=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['currency']
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='lessonprice_amount_positive'),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        from .services.pricing import CURRENCY_EXPONENT
        if self.currency not in self.SUPPORTED:
            raise ValidationError({'currency': f'Unsupported currency {self.currency!r}.'})
        if self.amount is not None and self.amount != self.amount.quantize(Decimal(1).scaleb(-CURRENCY_EXPONENT[self.currency])):
            raise ValidationError({'amount': f'{self.currency} amounts use {CURRENCY_EXPONENT[self.currency]} decimals.'})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.currency} {self.amount}'


class FxRate(models.Model):
    """
    ZAR value of one unit of EUR or JPY, entered by an admin (Task 10.1d, option C). Append-only: a new rate is a
    new row, so the rate in force on any past day stays provable. USD is derived from the lesson price catalog and
    ZAR is 1, so only EUR and JPY live here.
    """
    SUPPORTED = ('EUR', 'JPY')

    id = models.BigAutoField(primary_key=True)
    currency = models.CharField(max_length=3, db_index=True)
    rate_to_zar = models.DecimalField(max_digits=12, decimal_places=6)
    source = models.CharField(max_length=32, default='manual')   # 'manual' now; a provider feed writes its own name
    valid_from = models.DateTimeField(db_index=True)
    set_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableFinancialQuerySet.as_manager()

    class Meta:
        ordering = ['-valid_from', '-id']
        constraints = [models.CheckConstraint(condition=models.Q(rate_to_zar__gt=0), name='fxrate_rate_positive')]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise LedgerImmutabilityError('FX rates are immutable; add a new rate instead.')
        if self.currency not in self.SUPPORTED:
            raise ValueError(f'FX table rates exist for {self.SUPPORTED} only, not {self.currency!r}.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutabilityError('FX rates are immutable.')

    def __str__(self):
        return f'{self.currency} {self.rate_to_zar} ({self.source}, {self.valid_from:%Y-%m-%d %H:%M})'


class CreditPurchase(models.Model):
    class Status(models.TextChoices):
        INITIALIZED = 'initialized', 'Initialized'
        SUCCESS = 'success', 'Successful'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='credit_purchases')
    pack = models.ForeignKey(CreditPack, on_delete=models.PROTECT, related_name='purchases')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    fx_rate_to_zar = models.DecimalField(max_digits=12, decimal_places=6)
    fx_source = models.CharField(max_length=64, default='credit_catalog')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INITIALIZED, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class CreditBundle(models.Model):
    """
    A *lot* of lesson credits: every grant (purchase, refund conversion, bonus, restitution) is its own row with its own
    expiry (CREDIT_EXPIRY_DAYS_*), so credits can be spent oldest-expiry-first and expired exactly (Task 9.6).
    """
    class Source(models.TextChoices):
        PURCHASE = 'purchase', 'Purchased pack'
        REFUND = 'refund', 'Refund converted to credit'
        BONUS = 'bonus', 'Goodwill / compensation bonus'
        RESTITUTION = 'restitution', 'Restitution (failed booking)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='credit_bundles')
    pack_name = models.CharField(max_length=64, default="5-Lesson Pack")
    total_credits = models.PositiveIntegerField(default=5)
    remaining_credits = models.PositiveIntegerField(default=5)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.PURCHASE)   # rows that predate lots were all purchases
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    expired_credits = models.PositiveIntegerField(default=0)
    expired_at = models.DateTimeField(null=True, blank=True)
    credit_purchase = models.OneToOneField(CreditPurchase, on_delete=models.PROTECT, null=True, blank=True,
                                           related_name='credit_bundle')
    # Money value of ONE credit in `currency` (what the wallet liability was credited per lesson); the expiry job needs it
    # to write the unspent value off to breakage revenue.
    unit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    fx_rate_to_zar = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal('1.000000'))
    fx_source = models.CharField(max_length=64, default='legacy_opening')
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CreditBundleQuerySet.as_manager()

    def __str__(self):
        return f"{self.user.username} - {self.remaining_credits}/{self.total_credits} credits"


class RefundRequest(models.Model):
    """
    Money owed back to a student for one booking. The ledger moves it from escrow to 2050 (refunds payable) when the
    decision is made; a RefundGateway then returns it to the original payment method (2050 -> gateway cash), or the student
    converts it to wallet credit while it is still pending. One request per (booking, reason): the idempotency guard.
    """
    class Reason(models.TextChoices):
        STUDENT_CANCEL = 'student_cancel', 'Student cancelled in time'
        TEACHER_CANCEL = 'teacher_cancel', 'Tutor cancelled'
        TEACHER_NO_SHOW = 'teacher_no_show', 'Tutor did not attend'
        OUTAGE = 'outage', 'Power outage interrupted the lesson'
        DISPUTE = 'dispute', 'Dispute decided for the student'

    class Status(models.TextChoices):
        # The lesson was cancelled while its PayPal payment was still pending: nothing is owed until the money actually
        # arrives. It then becomes PENDING_GATEWAY (money received -> returned), or VOID (the payment failed).
        AWAITING_CLEARANCE = 'awaiting_clearance', 'Waiting for the payment to clear'
        VOID = 'void', 'Not needed (the payment never cleared)'
        PENDING_GATEWAY = 'pending_gateway', 'Waiting for the gateway'
        # The provider accepted the refund but has not finished it (PayPal PENDING). Polled by `lookup` and finished by the
        # PAYMENT.CAPTURE.REFUNDED webhook; never re-sent, never convertible to wallet credit (the money is on its way).
        SUBMITTED = 'submitted', 'On its way'
        PROCESSED = 'processed', 'Paid to the original payment method'
        CONVERTED = 'converted', 'Converted to wallet credit'
        FAILED = 'failed', 'Gateway refused (needs a human)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey('bookings.Booking', on_delete=models.PROTECT, related_name='refund_requests')
    payment_transaction = models.ForeignKey(PaymentTransaction, on_delete=models.PROTECT, related_name='refund_requests')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='refund_requests')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    reason = models.CharField(max_length=20, choices=Reason.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_GATEWAY, db_index=True)
    gateway_reference = models.CharField(max_length=255, blank=True)        # the provider's refund id
    failure_detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    # --- Task 10.7 claim / call / apply protocol (docs/TASK_10_7_REFUND_GATEWAYS_PLAN.md section 2b) ---
    class FailureKind(models.TextChoices):
        REJECTED = 'rejected', 'The provider refused it'
        ALREADY_REFUNDED = 'already_refunded', 'The provider says the payment is already fully refunded'
        GUARD = 'guard', 'A safety check refused it before any call'
        EXHAUSTED = 'exhausted', 'Retries ran out'
        REPLAY_WINDOW = 'replay_window', 'Too old to replay blind'
        PROVIDER_FAILED = 'provider_failed', 'The provider failed it after accepting it'

    submitted_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)                  # send attempts that may have reached the provider
    next_attempt_at = models.DateTimeField(null=True, blank=True)           # backoff / next poll
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    first_attempt_at = models.DateTimeField(null=True, blank=True)          # start of the transient and replay windows
    claim_token = models.CharField(max_length=32, blank=True)               # '' when no worker holds the row
    claimed_until = models.DateTimeField(null=True, blank=True)             # lease of the live claim
    gateway_request_id = models.CharField(max_length=80, blank=True)        # stable idempotency key, stored on the first claim
    request_epoch = models.PositiveSmallIntegerField(default=0)             # bumped when a human retries after a certain refusal
    failure_kind = models.CharField(max_length=24, blank=True, choices=FailureKind.choices)
    last_http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['booking', 'reason'], name='uniq_refund_per_booking_reason')]
        indexes = [models.Index(fields=['status', 'next_attempt_at'], name='refund_status_next_idx')]

    def __str__(self):
        return f"Refund {self.amount} {self.currency} ({self.reason}, {self.status})"


class RefundAttempt(models.Model):
    """
    Append-only audit of what was done to a refund: one row per claim result (send / poll), per admin action and per other status
    transition (webhook completion, wallet conversion, guard / replay-window failure, marked failed), written inside the
    transaction that applies it. Never updated or deleted. (A `manual` answer is not an attempt and leaves no row.)
    """
    class Kind(models.TextChoices):
        SEND = 'send', 'Sent to the gateway'
        POLL = 'poll', 'Polled the gateway'
        ADMIN_RETRY = 'admin_retry', 'Retried by an admin'
        ADMIN_MARK_PAID = 'admin_mark_paid', 'Marked paid by an admin'
        WEBHOOK = 'webhook', 'Completed by a PayPal webhook'
        CONVERT = 'convert', 'Converted to wallet credit'
        GUARD = 'guard', 'Stopped by a safety guard before sending'
        MARK_FAILED = 'mark_failed', 'Marked failed'

    id = models.BigAutoField(primary_key=True)
    refund = models.ForeignKey(RefundRequest, on_delete=models.PROTECT, related_name='attempt_log')
    seq = models.PositiveIntegerField()
    kind = models.CharField(max_length=16, choices=Kind.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    request_id = models.CharField(max_length=80, blank=True)
    result_state = models.CharField(max_length=16, blank=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableFinancialQuerySet.as_manager()

    class Meta:
        ordering = ['refund_id', 'seq']
        constraints = [models.UniqueConstraint(fields=['refund', 'seq'], name='uniq_refund_attempt_seq')]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise LedgerImmutabilityError('Refund attempts are immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutabilityError('Refund attempts are immutable.')

    def __str__(self):
        return f"Refund {self.refund_id} #{self.seq} {self.kind} -> {self.result_state}"


class CreditWalletEntry(models.Model):
    class EntryType(models.TextChoices):
        OPENING = 'opening', 'Opening balance'
        PURCHASE = 'purchase', 'Pack purchase'
        REDEMPTION = 'redemption', 'Lesson redemption'
        REFUND = 'refund', 'Operational refund'
        BONUS = 'bonus', 'Operational bonus'
        EXPIRY = 'expiry', 'Credits expired'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='credit_wallet_entries')
    bundle = models.ForeignKey(CreditBundle, on_delete=models.PROTECT, related_name='wallet_entries')
    entry_type = models.CharField(max_length=20, choices=EntryType.choices, db_index=True)
    credit_delta = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=3, default='USD')
    fx_rate_to_zar = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal('1.000000'))
    fx_source = models.CharField(max_length=64, default='legacy_opening')
    booking = models.ForeignKey('bookings.Booking', on_delete=models.PROTECT, null=True, blank=True,
                                related_name='credit_wallet_entries')
    credit_purchase = models.ForeignKey(CreditPurchase, on_delete=models.PROTECT, null=True, blank=True,
                                        related_name='wallet_entries')
    description = models.CharField(max_length=255)
    idempotency_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    objects = ImmutableFinancialQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise LedgerImmutabilityError('Credit wallet entries are immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutabilityError('Credit wallet entries are immutable.')


class BookingFunding(models.Model):
    class SourceType(models.TextChoices):
        GATEWAY = 'gateway', 'Gateway payment'
        # Booking confirmed while the capture is still PENDING (grace booking). Settlement and payout refuse it.
        GATEWAY_PENDING = 'gateway_pending', 'Gateway payment pending clearance'
        # The pending payment FAILED after the lesson was (or was about to be) delivered: the platform pays the tutor's
        # share from its own funds (ledger 5040) instead of from escrow (Task 10.2, plan P-3).
        PLATFORM_ABSORBED = 'platform_absorbed', 'Payment failed; platform absorbs the tutor share'
        CREDIT = 'credit', 'Wallet credit'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField('bookings.Booking', on_delete=models.PROTECT, related_name='funding')
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    captured_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    fx_rate_to_zar = models.DecimalField(max_digits=12, decimal_places=6)
    fx_source = models.CharField(max_length=64)
    payment_transaction = models.OneToOneField(PaymentTransaction, on_delete=models.PROTECT, null=True, blank=True,
                                               related_name='booking_funding')
    credit_wallet_entry = models.OneToOneField(CreditWalletEntry, on_delete=models.PROTECT, null=True, blank=True,
                                               related_name='booking_funding')
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableFinancialQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(payment_transaction__isnull=False) & models.Q(credit_wallet_entry__isnull=True)) |
                    (models.Q(payment_transaction__isnull=True) & models.Q(credit_wallet_entry__isnull=False))
                ),
                name='booking_funding_exactly_one_source',
            ),
        ]

    # The ONLY permitted change to a funding snapshot: a pending payment resolving. Amount, currency, FX and the payment
    # link never change; only the provenance flag moves, and only out of GATEWAY_PENDING.
    _RESOLUTIONS = {
        SourceType.GATEWAY_PENDING: (SourceType.GATEWAY, SourceType.PLATFORM_ABSORBED),
    }

    def resolve_pending(self, new_source_type: str) -> None:
        allowed = self._RESOLUTIONS.get(self.source_type, ())
        if new_source_type not in allowed:
            raise LedgerImmutabilityError(
                f"Funding provenance can only move out of GATEWAY_PENDING (not {self.source_type} -> {new_source_type}).")
        self.source_type = new_source_type
        models.Model.save(self, update_fields=['source_type'])

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise LedgerImmutabilityError('Booking funding snapshots are immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutabilityError('Booking funding snapshots are immutable.')


class SettlementAnomaly(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey('bookings.Booking', on_delete=models.PROTECT, related_name='settlement_anomalies')
    code = models.CharField(max_length=64, db_index=True)
    detail = models.TextField(blank=True)
    resolved = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class FulfillmentDispatch(models.Model):
    """Durable, retryable state for post-payment lesson provisioning."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending dispatch'
        QUEUED = 'queued', 'Queued'
        RUNNING = 'running', 'Running'
        RETRYABLE = 'retryable', 'Retryable failure'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Terminal failure'
        ABANDONED = 'abandoned', 'Abandoned: booking no longer confirmed'

    class StepState(models.TextChoices):
        PENDING = 'pending', 'Pending'
        DONE = 'done', 'Done'
        SKIPPED = 'skipped', 'Skipped (nothing to do, e.g. no Google Calendar connected)'
        FAILED = 'failed', 'Failed (retried)'

    booking = models.OneToOneField('bookings.Booking', on_delete=models.PROTECT, related_name='fulfillment_dispatch')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    # Per-step truth (Slice F0). The *_completed booleans are a legacy mirror (True when the step is done or skipped).
    zoom_state = models.CharField(max_length=10, choices=StepState.choices, default=StepState.PENDING)
    calendar_state = models.CharField(max_length=10, choices=StepState.choices, default=StepState.PENDING)
    email_state = models.CharField(max_length=10, choices=StepState.choices, default=StepState.PENDING)
    zoom_completed = models.BooleanField(default=False)
    calendar_completed = models.BooleanField(default=False)
    email_completed = models.BooleanField(default=False)
    # Compare-and-swap claim: the worker that set RUNNING owns the row while claim_token matches and the lease is fresh.
    claim_token = models.CharField(max_length=32, blank=True, default='')
    claimed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TutorPayoutAccount(models.Model):
    """Encrypted tutor banking payload. Only the account-number last four is plaintext metadata."""

    tutor = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payout_account', primary_key=True,
    )
    encrypted_payload = models.TextField()
    key_version = models.CharField(max_length=32)
    account_last_four = models.CharField(max_length=4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payout account for {self.tutor.username} ending {self.account_last_four}"


class LedgerAccount(models.TextChoices):
    # Assets (1000s)
    ASSET_GATEWAY_PAYFAST = '1010_asset_gateway_payfast', '1010 - Asset: Gateway Cash (PayFast ZAR)'
    ASSET_GATEWAY_PAYPAL = '1020_asset_gateway_paypal', '1020 - Asset: Gateway Cash (PayPal USD)'
    ASSET_OPERATING_BANK = '1030_asset_operating_bank', '1030 - Asset: Operating Bank Cash (ZAR)'

    # Liabilities (2000s)
    LIABILITY_STUDENT_ESCROW = '2010_liability_student_escrow', '2010 - Liability: Student Escrow Deposits'
    LIABILITY_TUTOR_PAYABLE = '2020_liability_tutor_payable', '2020 - Liability: Tutor Payables'
    LIABILITY_QUARANTINE_DEPOSIT = '2030_liability_quarantine_deposit', '2030 - Liability: Quarantined Late Deposits'
    LIABILITY_STUDENT_WALLET = '2040_liability_student_wallet', '2040 - Liability: Student Wallet Credits'
    LIABILITY_REFUNDS_PAYABLE = '2050_liability_refunds_payable', '2050 - Liability: Gateway Refunds Payable'

    # Revenue (4000s)
    REVENUE_PLATFORM_COMMISSION = '4010_revenue_platform_commission', '4010 - Revenue: Platform Take Rate (20%)'
    REVENUE_CREDIT_BREAKAGE = '4020_revenue_credit_breakage', '4020 - Revenue: Expired Credit Breakage'

    # Expenses (5000s)
    EXPENSE_DISPUTE_SETTLEMENT = '5010_expense_dispute_settlement', '5010 - Expense: Platform Dispute Settlements'
    EXPENSE_STUDENT_COMPENSATION = '5020_expense_student_compensation', '5020 - Expense: Student Goodwill / Compensation'
    EXPENSE_GATEWAY_FEES = '5030_expense_gateway_fees', '5030 - Expense: Payment Gateway Processing Fees'
    EXPENSE_ABSORBED_PAYMENT_FAILURE = (
        '5040_expense_absorbed_payment_failure', '5040 - Expense: Platform-Absorbed Payment Failure (tutor paid, student never paid)')


class LedgerEntryQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise LedgerImmutabilityError("Ledger entries are strictly immutable and cannot be updated.")

    def delete(self):
        raise LedgerImmutabilityError("Ledger entries are strictly immutable and cannot be deleted.")


class LedgerEntry(models.Model):
    class EntryType(models.TextChoices):
        DEBIT = 'debit', 'Debit (DR)'
        CREDIT = 'credit', 'Credit (CR)'

    class EventType(models.TextChoices):
        PAYMENT_CAPTURED = 'payment_captured', 'Payment Captured'
        CREDIT_REDEEMED = 'credit_redeemed', 'Credit Redeemed into Escrow'
        ESCROW_CLEARED = 'escrow_cleared', 'Escrow Cleared (Dual-Verified)'
        PAYOUT_EXECUTED = 'payout_executed', 'Tutor EFT Payout Executed'
        REFUND_ISSUED = 'refund_issued', 'Refund Issued'
        DISPUTE_RESOLVED = 'dispute_resolved', 'Dispute Resolved'
        COMPENSATION_AWARDED = 'compensation_awarded', 'Apology / Goodwill Compensation'
        OUTAGE_REFUND = 'outage_refund', 'Eskom Outage Force Majeure Refund'
        LATE_PAYMENT_QUARANTINE = 'late_payment_quarantine', 'DEF-501 Late Payment Quarantine'
        UNALLOCATED_PAYMENT = 'unallocated_payment', 'Unallocated / Duplicate Payment Held for Refund'
        GATEWAY_REFUND_PAID = 'gateway_refund_paid', 'Gateway Refund Paid to Original Payment Method'
        CREDIT_EXPIRED = 'credit_expired', 'Wallet Credit Expired (breakage)'
        PAYMENT_FAILURE_ABSORBED = 'payment_failure_absorbed', 'Tutor Paid by Platform After Pending Payment Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    journal_batch_id = models.UUIDField(db_index=True, help_text="Groups balancing debits and credits of a single transaction")
    account = models.CharField(max_length=64, choices=LedgerAccount.choices, db_index=True)
    entry_type = models.CharField(max_length=10, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')

    # SARB / SARS Statutory Valuation
    # No defaults: every row records the rate it was captured at. 'legacy_default' exists only on rows posted before
    # Task 10.1 and may not be written again (see save()).
    fx_rate_to_zar = models.DecimalField(max_digits=12, decimal_places=6)
    fx_source = models.CharField(max_length=64)
    amount_zar = models.DecimalField(max_digits=12, decimal_places=2)

    event_type = models.CharField(max_length=40, choices=EventType.choices, db_index=True)
    description = models.TextField()

    # Audit Trail Relationships (PROTECT for statutory 7-year retention)
    booking = models.ForeignKey('bookings.Booking', on_delete=models.PROTECT, null=True, blank=True, related_name='ledger_entries')
    payment_transaction = models.ForeignKey('payments.PaymentTransaction', on_delete=models.PROTECT, null=True, blank=True, related_name='ledger_entries')
    dispute_case = models.ForeignKey('admin_api.DisputeCase', on_delete=models.PROTECT, null=True, blank=True, related_name='ledger_entries')
    payout_batch = models.ForeignKey('admin_api.PayoutBatch', on_delete=models.PROTECT, null=True, blank=True, related_name='ledger_entries')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='ledger_entries')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = LedgerEntryQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['journal_batch_id']),
            models.Index(fields=['account', 'created_at']),
            models.Index(fields=['event_type', 'created_at']),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding and LedgerEntry.objects.filter(pk=self.pk).exists():
            raise LedgerImmutabilityError(
                f"LedgerEntry {self.pk} is strictly immutable and cannot be updated. "
                "Any financial adjustments must be executed via compensatory journal entries."
            )
        if self._state.adding and self.fx_source == LEGACY_FX_SOURCE:
            raise MissingLedgerFx("fx_source 'legacy_default' belongs to rows posted before Task 10.1; new rows need a captured rate.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutabilityError(
            f"LedgerEntry {self.pk} is strictly immutable and cannot be deleted. "
            "SARB and GAAP compliance mandate an immutable audit trail."
        )

    def __str__(self):
        return f"[{self.journal_batch_id}] {self.entry_type.upper()} {self.amount} {self.currency} -> {self.account}"


