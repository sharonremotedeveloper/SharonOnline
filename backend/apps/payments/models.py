from django.db import models
from django.conf import settings
from decimal import Decimal
import uuid

class PaymentTransaction(models.Model):
    class Gateway(models.TextChoices):
        PAYFAST = 'payfast', 'PayFast (ZAR)'
        PAYPAL = 'paypal', 'PayPal (USD/EUR/JPY)'

    class Status(models.TextChoices):
        INITIALIZED = 'initialized', 'Initialized'
        SUCCESS = 'success', 'Successful'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'
        # Money captured by the gateway that could not be applied to its booking (duplicate payment, booking already
        # confirmed/completed). Held in ledger acct 2030 pending a gateway refund; never enters escrow or payouts.
        UNALLOCATED = 'unallocated', 'Unallocated (refund pending)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE, related_name='transactions')
    gateway = models.CharField(max_length=20, choices=Gateway.choices)
    gateway_reference = models.CharField(max_length=255, unique=True, db_index=True)
    # Our own reference (sent to the gateway as m_payment_id / custom_id) so webhooks can find the expected amount.
    merchant_reference = models.CharField(max_length=64, unique=True, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INITIALIZED, db_index=True)
    escrow_cleared = models.BooleanField(default=False, db_index=True)
    raw_webhook_payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

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
    # Money value of ONE credit in `currency`, i.e. what the 2040 wallet liability was credited per lesson. Used to post the
    # breakage entry when the lot expires.
    unit_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    expired_credits = models.PositiveIntegerField(default=0)
    expired_at = models.DateTimeField(null=True, blank=True)
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
        PENDING_GATEWAY = 'pending_gateway', 'Waiting for the gateway'
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
    gateway_reference = models.CharField(max_length=255, blank=True)
    failure_detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['booking', 'reason'], name='uniq_refund_per_booking_reason')]

    def __str__(self):
        return f"Refund {self.amount} {self.currency} ({self.reason}, {self.status})"


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


from django.core.exceptions import ValidationError

class LedgerImmutabilityError(ValidationError):
    """Raised when an operation attempts to update or delete immutable LedgerEntry records."""
    pass

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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    journal_batch_id = models.UUIDField(db_index=True, help_text="Groups balancing debits and credits of a single transaction")
    account = models.CharField(max_length=64, choices=LedgerAccount.choices, db_index=True)
    entry_type = models.CharField(max_length=10, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')

    # SARB / SARS Statutory Valuation
    fx_rate_to_zar = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('18.7500'))
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
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutabilityError(
            f"LedgerEntry {self.pk} is strictly immutable and cannot be deleted. "
            "SARB and GAAP compliance mandate an immutable audit trail."
        )

    def __str__(self):
        return f"[{self.journal_batch_id}] {self.entry_type.upper()} {self.amount} {self.currency} -> {self.account}"


