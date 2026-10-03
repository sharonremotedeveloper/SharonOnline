import logging
import uuid
from decimal import Decimal
from typing import List, Optional, Dict, Any
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from apps.payments.models import LEGACY_FX_SOURCE, LedgerEntry, LedgerAccount, MissingLedgerFx, PaymentTransaction

logger = logging.getLogger(__name__)

__all__ = ['MissingLedgerFx']


def _snapshot(payment_transaction, fx_rate_to_zar, fx_source):
    """An explicit valuation wins; otherwise the transaction's own captured snapshot. Never a constant."""
    if fx_rate_to_zar is None:
        fx_rate_to_zar = payment_transaction.fx_rate_to_zar
    if not fx_source:
        fx_source = payment_transaction.fx_source
    return fx_rate_to_zar, fx_source


class UnbalancedJournalEntryError(ValueError):
    """Raised when journal debits do not equal credits for a transaction batch."""
    pass


def record_journal_entries(
    *,
    entries: List[Dict[str, Any]],
    event_type: str,
    description: str,
    booking=None,
    payment_transaction=None,
    dispute_case=None,
    payout_batch=None,
    user=None,
    currency: str = 'USD',
    fx_rate_to_zar: Optional[Decimal] = None,
    fx_source: Optional[str] = None,
    journal_batch_id: Optional[uuid.UUID] = None,
) -> List[LedgerEntry]:
    """
    Core double-entry journal posting engine.
    Guarantees atomic persistence and strict zero-sum balancing invariant:
    SUM(Debits) == SUM(Credits) in transaction currency and ZAR equivalent.
    """
    if not entries:
        raise ValueError("Cannot record empty journal entries list.")
    # The ledger never invents a valuation: the caller must supply the rate the money was captured at, and where it came from.
    if fx_rate_to_zar is None or not fx_source:
        raise MissingLedgerFx(
            f"Journal '{event_type}' has no FX snapshot (rate={fx_rate_to_zar!r}, source={fx_source!r}); "
            "pass the captured rate and its source (ZAR journals: 1 / 'transaction_currency').")
    fx_rate_to_zar = Decimal(str(fx_rate_to_zar))
    if fx_rate_to_zar <= 0:
        raise MissingLedgerFx(f"Journal '{event_type}' has a non-positive FX rate ({fx_rate_to_zar}).")
    if fx_source == LEGACY_FX_SOURCE:
        raise MissingLedgerFx("fx_source 'legacy_default' is reserved for historical rows and may not be posted again.")

    batch_id = journal_batch_id or uuid.uuid4()
    
    totals_by_currency = {}

    prepared_records = []
    for item in entries:
        account = item['account']
        entry_type = item['entry_type']
        amount = Decimal(str(item['amount'])).quantize(Decimal('0.01'))
        item_currency = item.get('currency', currency).upper()

        if amount <= Decimal('0.00'):
            raise ValueError(f"Ledger entry amount must be positive, got {amount} for {account}")

        currency_totals = totals_by_currency.setdefault(
            item_currency, {'debit': Decimal('0.00'), 'credit': Decimal('0.00')})
        if entry_type == LedgerEntry.EntryType.DEBIT:
            currency_totals['debit'] += amount
        elif entry_type == LedgerEntry.EntryType.CREDIT:
            currency_totals['credit'] += amount
        else:
            raise ValueError(f"Invalid entry_type: {entry_type}")

        # Compute SARB ZAR valuation
        if item_currency == 'ZAR':
            amount_zar = amount
        else:
            amount_zar = (amount * fx_rate_to_zar).quantize(Decimal('0.01'))

        prepared_records.append({
            'journal_batch_id': batch_id,
            'account': account,
            'entry_type': entry_type,
            'amount': amount,
            'currency': item_currency,
            'fx_rate_to_zar': fx_rate_to_zar,
            'fx_source': fx_source,
            'amount_zar': amount_zar,
            'event_type': event_type,
            'description': item.get('description', description),
            'booking': booking,
            'payment_transaction': payment_transaction,
            'dispute_case': dispute_case,
            'payout_batch': payout_batch,
            'user': user or (booking.student if booking else (payment_transaction.booking.student if payment_transaction and payment_transaction.booking else None)),
        })

    # Zero-sum invariant assertion for every transaction currency represented in the journal.
    for item_currency, totals in totals_by_currency.items():
        if totals['debit'] != totals['credit']:
            raise UnbalancedJournalEntryError(
                f"Unbalanced journal entry batch {batch_id}: Total Debits ({totals['debit']} {item_currency}) "
                f"!= Total Credits ({totals['credit']} {item_currency}). Event: {event_type}"
            )

    # Statutory SARB zero-sum invariant assertion & sub-cent rounding balance
    total_debits_zar = sum(r['amount_zar'] for r in prepared_records if r['entry_type'] == LedgerEntry.EntryType.DEBIT)
    total_credits_zar = sum(r['amount_zar'] for r in prepared_records if r['entry_type'] == LedgerEntry.EntryType.CREDIT)
    if total_debits_zar != total_credits_zar:
        diff = total_debits_zar - total_credits_zar
        if abs(diff) <= Decimal('0.05'):
            for rec in reversed(prepared_records):
                if rec['entry_type'] == LedgerEntry.EntryType.CREDIT:
                    rec['amount_zar'] += diff
                    break
    total_debits_zar = sum(r['amount_zar'] for r in prepared_records if r['entry_type'] == LedgerEntry.EntryType.DEBIT)
    total_credits_zar = sum(r['amount_zar'] for r in prepared_records if r['entry_type'] == LedgerEntry.EntryType.CREDIT)
    if total_debits_zar != total_credits_zar:
        raise UnbalancedJournalEntryError(
            f"Unbalanced ZAR valuation for journal {batch_id}: {total_debits_zar} != {total_credits_zar}."
        )
    journal_currencies = set(totals_by_currency)
    if len(journal_currencies) != 1:
        raise UnbalancedJournalEntryError(
            f"Journal {batch_id} must use exactly one transaction currency; got {sorted(journal_currencies)}."
        )
    journal_currency = next(iter(journal_currencies))

    with transaction.atomic():
        created_entries = [
            LedgerEntry.objects.create(**rec) for rec in prepared_records
        ]

    logger.info(
        f"[LEDGER JOURNAL RECORDED] Batch {batch_id} | Event: {event_type} | "
        f"Balanced {totals_by_currency} ({len(created_entries)} lines)"
    )
    return created_entries


# ============================================================================
# High-Level Domain Journal Helpers
# ============================================================================

def record_payment_capture_entry(
    payment_transaction: PaymentTransaction,
    booking=None,
    user=None,
    fx_rate_to_zar: Optional[Decimal] = None,
    fx_source: Optional[str] = None,
) -> List[LedgerEntry]:
    """
    Triggered when a student checkout succeeds.
    DR Asset: Gateway Cash (PayPal or PayFast)
    CR Liability: Student Escrow Deposits
    """
    amount = Decimal(str(payment_transaction.amount)).quantize(Decimal('0.01'))
    currency = payment_transaction.currency.upper()
    fx_rate_to_zar, fx_source = _snapshot(payment_transaction, fx_rate_to_zar, fx_source)
    
    if payment_transaction.gateway == PaymentTransaction.Gateway.PAYFAST or currency == 'ZAR':
        asset_account = LedgerAccount.ASSET_GATEWAY_PAYFAST
    else:
        asset_account = LedgerAccount.ASSET_GATEWAY_PAYPAL

    fee = payment_transaction.provider_fee_amount or Decimal('0.00')
    if fee and (payment_transaction.provider_fee_currency or currency).upper() != currency:
        raise ValueError('Provider fee currency must match the captured transaction currency.')
    net_asset = amount - fee
    entries = []
    if net_asset > 0:
        entries.append({
            'account': asset_account,
            'entry_type': LedgerEntry.EntryType.DEBIT,
            'amount': net_asset,
            'currency': currency,
            'description': f"Captured customer deposit via {payment_transaction.gateway.upper()} ref {payment_transaction.gateway_reference}"
        })
    if fee > 0:
        entries.append({
            'account': LedgerAccount.EXPENSE_GATEWAY_FEES,
            'entry_type': LedgerEntry.EntryType.DEBIT,
            'amount': fee,
            'currency': currency,
            'description': f"Gateway processing fee for {payment_transaction.gateway_reference}",
        })
    entries.append({
            'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
            'entry_type': LedgerEntry.EntryType.CREDIT,
            'amount': amount,
            'currency': currency,
            'description': f"Escrow liability hold for booking {booking.id if booking else 'bundle'}"
        })

    return record_journal_entries(
        entries=entries,
        event_type=LedgerEntry.EventType.PAYMENT_CAPTURED,
        description=f"Payment capture {payment_transaction.gateway_reference}",
        booking=booking or payment_transaction.booking,
        payment_transaction=payment_transaction,
        user=user or (booking.student if booking else None),
        currency=currency,
        fx_rate_to_zar=fx_rate_to_zar,
        fx_source=fx_source,
    )


def record_credit_purchase_capture_entry(payment_transaction, purchase) -> List[LedgerEntry]:
    """Record verified pack-sale cash against the student's wallet liability."""
    amount = Decimal(str(payment_transaction.amount)).quantize(Decimal('0.01'))
    currency = payment_transaction.currency.upper()
    asset_account = (
        LedgerAccount.ASSET_GATEWAY_PAYFAST
        if payment_transaction.gateway == PaymentTransaction.Gateway.PAYFAST or currency == 'ZAR'
        else LedgerAccount.ASSET_GATEWAY_PAYPAL
    )
    fee = payment_transaction.provider_fee_amount or Decimal('0.00')
    if fee and (payment_transaction.provider_fee_currency or currency).upper() != currency:
        raise ValueError('Provider fee currency must match the captured transaction currency.')
    entries = []
    if amount - fee > 0:
        entries.append({
                'account': asset_account,
                'entry_type': LedgerEntry.EntryType.DEBIT,
                'amount': amount - fee,
                'currency': currency,
                'description': f'Captured credit pack payment {payment_transaction.gateway_reference}',
            })
    if fee > 0:
        entries.append({
            'account': LedgerAccount.EXPENSE_GATEWAY_FEES,
            'entry_type': LedgerEntry.EntryType.DEBIT,
            'amount': fee,
            'currency': currency,
            'description': f'Gateway processing fee for {payment_transaction.gateway_reference}',
        })
    entries.append({
                'account': LedgerAccount.LIABILITY_STUDENT_WALLET,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': amount,
                'currency': currency,
                'description': f'Wallet liability for {purchase.pack.name}',
            })
    return record_journal_entries(
        entries=entries,
        event_type=LedgerEntry.EventType.PAYMENT_CAPTURED,
        description=f'Credit purchase capture {payment_transaction.gateway_reference}',
        payment_transaction=payment_transaction,
        user=purchase.user,
        currency=currency,
        fx_rate_to_zar=purchase.fx_rate_to_zar,
        fx_source=purchase.fx_source,
    )


def record_credit_redemption_entry(*, booking, funding) -> List[LedgerEntry]:
    """Move one funded credit from wallet liability into lesson escrow."""
    amount = Decimal(str(funding.captured_amount)).quantize(Decimal('0.01'))
    return record_journal_entries(
        entries=[
            {
                'account': LedgerAccount.LIABILITY_STUDENT_WALLET,
                'entry_type': LedgerEntry.EntryType.DEBIT,
                'amount': amount,
                'currency': funding.currency,
                'description': f'Wallet credit consumed for booking {booking.id}',
            },
            {
                'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': amount,
                'currency': funding.currency,
                'description': f'Escrow funded by wallet credit for booking {booking.id}',
            },
        ],
        event_type=LedgerEntry.EventType.CREDIT_REDEEMED,
        description=f'Credit redemption for booking {booking.id}',
        booking=booking,
        user=booking.student,
        currency=funding.currency,
        fx_rate_to_zar=funding.fx_rate_to_zar,
        fx_source=funding.fx_source,
    )
def record_escrow_clearance_entry(
    booking,
    payment_transaction: Optional[PaymentTransaction] = None,
    amount_usd: Optional[Decimal] = None,
    funding=None,
) -> List[LedgerEntry]:
    """
    Triggered upon 24-hour dual-verified escrow clearance.
    DR Liability: Student Escrow Deposits (100%)
    CR Liability: Tutor Payables (80%)
    CR Revenue: Platform Take Rate (20%)
    """
    if funding is None:
        from apps.payments.services.funding import funding_for_settlement
        funding = funding_for_settlement(booking, context='record_escrow_clearance_entry')
    if funding is None:
        raise ValueError(f'Booking {booking.id} has no funding provenance; escrow clearance stopped.')
    gross_amount = Decimal(str(funding.captured_amount)).quantize(Decimal('0.01'))
    
    tutor_net = (gross_amount * Decimal('0.80')).quantize(Decimal('0.01'))
    platform_margin = gross_amount - tutor_net

    currency = funding.currency
    fx_rate_to_zar = funding.fx_rate_to_zar
    fx_source = funding.fx_source
    payment_transaction = funding.payment_transaction

    entries = [
        {
            'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
            'entry_type': LedgerEntry.EntryType.DEBIT,
            'amount': gross_amount,
            'currency': currency,
            'description': f"Escrow release for verified lesson BK-{str(booking.id)[:6].upper()}"
        },
        {
            'account': LedgerAccount.LIABILITY_TUTOR_PAYABLE,
            'entry_type': LedgerEntry.EntryType.CREDIT,
            'amount': tutor_net,
            'currency': currency,
            'description': f"Tutor 80% payable to {booking.teacher.user.username}"
        },
        {
            'account': LedgerAccount.REVENUE_PLATFORM_COMMISSION,
            'entry_type': LedgerEntry.EntryType.CREDIT,
            'amount': platform_margin,
            'currency': currency,
            'description': f"Platform 20% take rate for booking BK-{str(booking.id)[:6].upper()}"
        }
    ]

    return record_journal_entries(
        entries=entries,
        event_type=LedgerEntry.EventType.ESCROW_CLEARED,
        description=f"Dual-verified escrow clearance for booking {booking.id}",
        booking=booking,
        payment_transaction=payment_transaction,
        user=booking.teacher.user,
        currency=currency,
        fx_rate_to_zar=fx_rate_to_zar,
        fx_source=fx_source,
    )


def record_payout_batch_entry(
    payout_batch,
    amount_zar: Decimal,
    user=None,
    description: Optional[str] = None
) -> List[LedgerEntry]:
    """
    Triggered when an admin executes a bi-weekly tutor bank EFT batch.
    DR Liability: Tutor Payables (ZAR)
    CR Asset: Operating Bank Cash (ZAR)
    """
    amount = Decimal(str(amount_zar)).quantize(Decimal('0.01'))
    desc = description or f"EFT batch settlement {payout_batch.batch_reference} for {payout_batch.recipients_count} tutors"

    entries = [
        {
            'account': LedgerAccount.LIABILITY_TUTOR_PAYABLE,
            'entry_type': LedgerEntry.EntryType.DEBIT,
            'amount': amount,
            'currency': 'ZAR',
            'description': desc
        },
        {
            'account': LedgerAccount.ASSET_OPERATING_BANK,
            'entry_type': LedgerEntry.EntryType.CREDIT,
            'amount': amount,
            'currency': 'ZAR',
            'description': desc
        }
    ]

    return record_journal_entries(
        entries=entries,
        event_type=LedgerEntry.EventType.PAYOUT_EXECUTED,
        description=desc,
        payout_batch=payout_batch,
        user=user,
        currency='ZAR',
        fx_rate_to_zar=Decimal('1.000000'),
        fx_source='transaction_currency',
    )


def record_dispute_settlement_entry(
    dispute_case,
    resolution: str,
    payment_transaction: Optional[PaymentTransaction] = None,
) -> List[LedgerEntry]:
    """
    Triggered when an admin resolves a dispute tribunal case.
    Handles FULL_REFUND_STUDENT, RELEASE_TUTOR, and platform-absorbed SPLIT_50_50.
    """
    booking = dispute_case.booking
    from apps.payments.services.funding import funding_for_settlement
    funding = funding_for_settlement(booking, context='record_dispute_settlement_entry')
    if funding is None:
        raise ValueError(f'Booking {booking.id} has no funding provenance; dispute settlement stopped.')
    amount_usd = Decimal(str(funding.captured_amount)).quantize(Decimal('0.01'))
    currency = funding.currency
    fx_rate_to_zar = funding.fx_rate_to_zar
    fx_source = funding.fx_source
    payment_transaction = funding.payment_transaction

    if resolution == 'full_refund_student':
        # A refund to the student is never booked here: it goes through payments/services/refunds.py::request_refund (gateway
        # refund, or a restored credit), which is the single place that decides where the money goes.
        raise ValueError("Full refunds are issued with refunds.request_refund, not as a dispute settlement entry.")
    elif resolution == 'release_tutor':
        tutor_net = (amount_usd * Decimal('0.80')).quantize(Decimal('0.01'))
        platform_fee = amount_usd - tutor_net
        entries = [
            {
                'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
                'entry_type': LedgerEntry.EntryType.DEBIT,
                'amount': amount_usd,
                'currency': currency,
                'description': f"Escrow released to tutor by arbitration for dispute {dispute_case.id}"
            },
            {
                'account': LedgerAccount.LIABILITY_TUTOR_PAYABLE,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': tutor_net,
                'currency': currency,
                'description': f"Tutor payable awarded by tribunal for dispute {dispute_case.id}"
            },
            {
                'account': LedgerAccount.REVENUE_PLATFORM_COMMISSION,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': platform_fee,
                'currency': currency,
                'description': f"Platform commission on arbitrated release for dispute {dispute_case.id}"
            }
        ]
    elif resolution == 'split_50_50':
        # Platform absorbs cost: tutor gets paid + student gets courtesy credit refund
        tutor_net = (amount_usd * Decimal('0.80')).quantize(Decimal('0.01'))
        platform_fee = amount_usd - tutor_net
        
        entries = [
            # 1. Escrow cleared to tutor & platform
            {
                'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
                'entry_type': LedgerEntry.EntryType.DEBIT,
                'amount': amount_usd,
                'currency': currency,
                'description': f"Escrow cleared under 50/50 dispute split {dispute_case.id}"
            },
            {
                'account': LedgerAccount.LIABILITY_TUTOR_PAYABLE,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': tutor_net,
                'currency': currency,
                'description': f"Tutor share paid under 50/50 dispute split {dispute_case.id}"
            },
            {
                'account': LedgerAccount.REVENUE_PLATFORM_COMMISSION,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': platform_fee,
                'currency': currency,
                'description': f"Platform fee under 50/50 dispute split {dispute_case.id}"
            },
            # 2. Platform absorbs student restitution expense
            {
                'account': LedgerAccount.EXPENSE_DISPUTE_SETTLEMENT,
                'entry_type': LedgerEntry.EntryType.DEBIT,
                'amount': amount_usd,
                'currency': currency,
                'description': f"Platform absorption expense for 50/50 dispute settlement {dispute_case.id}"
            },
            {
                'account': LedgerAccount.LIABILITY_STUDENT_WALLET,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': amount_usd,
                'currency': currency,
                'description': f"Restitution credit issued to student {dispute_case.student.username}"
            }
        ]
    else:
        raise ValueError(f"Unknown dispute resolution: {resolution}")

    return record_journal_entries(
        entries=entries,
        event_type=LedgerEntry.EventType.DISPUTE_RESOLVED,
        description=f"Dispute {dispute_case.id} resolved as {resolution}",
        booking=booking,
        dispute_case=dispute_case,
        payment_transaction=payment_transaction,
        user=dispute_case.student,
        currency=currency,
        fx_rate_to_zar=fx_rate_to_zar,
        fx_source=fx_source,
    )


def record_compensation_entry(
    user,
    booking=None,
    amount_usd: Optional[Decimal] = None,
    reason: str = "Tutor no-show apology credit",
    fx_rate_to_zar: Optional[Decimal] = None,
    currency: str = 'USD',
    fx_source: Optional[str] = None,
) -> List[LedgerEntry]:
    """
    Triggered when the platform awards a courtesy/bonus credit (e.g. tutor no-show or memo SLA breach).
    DR Expense: Student Goodwill / Compensation
    CR Liability: Student Wallet Credits (Customer Credit Wallet)
    """
    currency = (currency or 'USD').upper()          # an explicit currency is honoured (bonus credits are valued in the captured currency)
    if amount_usd is None:
        if booking is None:
            raise ValueError('Compensation requires an explicit amount or funded booking.')
        from apps.payments.services.funding import funding_for_settlement
        funding = funding_for_settlement(booking, context='record_compensation_entry')
        if funding is None:
            raise ValueError(f'Booking {booking.id} has no funding provenance; compensation stopped.')
        amount_usd = funding.captured_amount
        fx_rate_to_zar = funding.fx_rate_to_zar
        fx_source = funding.fx_source
        currency = funding.currency
    amount = Decimal(str(amount_usd)).quantize(Decimal('0.01'))

    entries = [
        {
            'account': LedgerAccount.EXPENSE_STUDENT_COMPENSATION,
            'entry_type': LedgerEntry.EntryType.DEBIT,
            'amount': amount,
            'currency': currency,
            'description': f"Platform compensation expense: {reason}"
        },
        {
            'account': LedgerAccount.LIABILITY_STUDENT_WALLET,
            'entry_type': LedgerEntry.EntryType.CREDIT,
            'amount': amount,
            'currency': currency,
            'description': f"Bonus credit granted to {user.username} for {reason}"
        }
    ]

    return record_journal_entries(
        entries=entries,
        event_type=LedgerEntry.EventType.COMPENSATION_AWARDED,
        description=f"Platform goodwill compensation: {reason}",
        booking=booking,
        user=user,
        currency=currency,
        fx_rate_to_zar=fx_rate_to_zar,
        fx_source=fx_source,
    )


def record_def501_quarantine_entry(
    payment_transaction: PaymentTransaction,
    booking=None,
    user=None,
    fx_rate_to_zar: Optional[Decimal] = None,
    fx_source: Optional[str] = None,
) -> List[LedgerEntry]:
    """
    Triggered when a late payment arrives for an expired/re-booked slot (DEF-501).
    Quarantines deposit and issues instant wallet credit restitution.
    1. DR Asset: Gateway Cash -> CR Liability: Quarantined Late Deposits
    2. DR Liability: Quarantined Late Deposits -> CR Liability: Student Wallet Credits
    """
    amount = Decimal(str(payment_transaction.amount)).quantize(Decimal('0.01'))
    currency = payment_transaction.currency.upper()
    fx_rate_to_zar, fx_source = _snapshot(payment_transaction, fx_rate_to_zar, fx_source)
    asset_account = LedgerAccount.ASSET_GATEWAY_PAYFAST if (payment_transaction.gateway == PaymentTransaction.Gateway.PAYFAST or currency == 'ZAR') else LedgerAccount.ASSET_GATEWAY_PAYPAL

    entries = [
        # Ingestion into quarantine
        {
            'account': asset_account,
            'entry_type': LedgerEntry.EntryType.DEBIT,
            'amount': amount,
            'currency': currency,
            'description': f"Late payment captured for re-booked slot ref {payment_transaction.gateway_reference}"
        },
        {
            'account': LedgerAccount.LIABILITY_QUARANTINE_DEPOSIT,
            'entry_type': LedgerEntry.EntryType.CREDIT,
            'amount': amount,
            'currency': currency,
            'description': f"DEF-501 quarantine deposit hold for ref {payment_transaction.gateway_reference}"
        },
        # Auto-restitution credit transfer
        {
            'account': LedgerAccount.LIABILITY_QUARANTINE_DEPOSIT,
            'entry_type': LedgerEntry.EntryType.DEBIT,
            'amount': amount,
            'currency': currency,
            'description': f"DEF-501 auto-restitution credit allocation to student"
        },
        {
            'account': LedgerAccount.LIABILITY_STUDENT_WALLET,
            'entry_type': LedgerEntry.EntryType.CREDIT,
            'amount': amount,
            'currency': currency,
            'description': f"Restitution wallet credit added for student"
        }
    ]

    return record_journal_entries(
        entries=entries,
        event_type=LedgerEntry.EventType.LATE_PAYMENT_QUARANTINE,
        description=f"DEF-501 late payment quarantine and restitution {payment_transaction.gateway_reference}",
        booking=booking or payment_transaction.booking,
        payment_transaction=payment_transaction,
        user=user or (booking.student if booking else None),
        currency=currency,
        fx_rate_to_zar=fx_rate_to_zar,
        fx_source=fx_source,
    )


def record_unallocated_payment_entry(
    payment_transaction: PaymentTransaction,
    booking=None,
    user=None,
    fx_rate_to_zar: Optional[Decimal] = None,
    fx_source: Optional[str] = None,
) -> List[LedgerEntry]:
    """
    Money captured by a gateway that cannot be applied to its booking (duplicate payment, booking already
    confirmed/completed). Held in the quarantine liability until it is refunded to the payer at the gateway (D-6).
    Deliberately NO student wallet credit: the funds go back to the original payment method.
    DR Asset: Gateway Cash -> CR Liability: Quarantined Deposits
    """
    amount = Decimal(str(payment_transaction.amount)).quantize(Decimal('0.01'))
    currency = payment_transaction.currency.upper()
    fx_rate_to_zar, fx_source = _snapshot(payment_transaction, fx_rate_to_zar, fx_source)
    asset_account = LedgerAccount.ASSET_GATEWAY_PAYFAST if (payment_transaction.gateway == PaymentTransaction.Gateway.PAYFAST or currency == 'ZAR') else LedgerAccount.ASSET_GATEWAY_PAYPAL
    ref = payment_transaction.gateway_reference
    entries = [
        {'account': asset_account, 'entry_type': LedgerEntry.EntryType.DEBIT, 'amount': amount, 'currency': currency,
         'description': f"Unallocated payment captured, ref {ref}"},
        {'account': LedgerAccount.LIABILITY_QUARANTINE_DEPOSIT, 'entry_type': LedgerEntry.EntryType.CREDIT,
         'amount': amount, 'currency': currency,
         'description': f"Held pending gateway refund, ref {ref}"},
    ]
    return record_journal_entries(
        entries=entries,
        event_type=LedgerEntry.EventType.UNALLOCATED_PAYMENT,
        description=f"Unallocated/duplicate payment held for refund {ref}",
        booking=booking or payment_transaction.booking,
        payment_transaction=payment_transaction,
        user=user or (booking.student if booking else None),
        currency=currency,
        fx_rate_to_zar=fx_rate_to_zar,
        fx_source=fx_source,
    )


# ============================================================================
# Audit & Financial Reporting Utilities
# ============================================================================

def get_general_ledger_trial_balance() -> Dict[str, Any]:
    """
    Calculates the general ledger trial balance across all accounts and checks
    the fundamental accounting identity: SUM(DR) - SUM(CR) == 0.
    """
    accounts = LedgerAccount.choices
    trial_rows = []
    grand_debit_zar = Decimal('0.00')
    grand_credit_zar = Decimal('0.00')

    for code, name in accounts:
        dr_sum = LedgerEntry.objects.filter(
            account=code, entry_type=LedgerEntry.EntryType.DEBIT
        ).aggregate(total=Sum('amount_zar'))['total'] or Decimal('0.00')

        cr_sum = LedgerEntry.objects.filter(
            account=code, entry_type=LedgerEntry.EntryType.CREDIT
        ).aggregate(total=Sum('amount_zar'))['total'] or Decimal('0.00')

        dr_sum = Decimal(str(dr_sum)).quantize(Decimal('0.01'))
        cr_sum = Decimal(str(cr_sum)).quantize(Decimal('0.01'))

        net_balance = dr_sum - cr_sum
        grand_debit_zar += dr_sum
        grand_credit_zar += cr_sum

        trial_rows.append({
            'account_code': code,
            'account_name': name,
            'debit_zar': float(dr_sum),
            'credit_zar': float(cr_sum),
            'net_zar': float(net_balance)
        })

    is_balanced = (grand_debit_zar == grand_credit_zar)

    return {
        'trial_rows': trial_rows,
        'grand_debit_zar': float(grand_debit_zar),
        'grand_credit_zar': float(grand_credit_zar),
        'variance_zar': float(grand_debit_zar - grand_credit_zar),
        'is_balanced': is_balanced
    }


def get_ledger_telemetry() -> Dict[str, Any]:
    """
    Computes real-time general ledger balances and financial metrics directly from LedgerEntry.
    Calculates live balances for:
    - Gateway Cash (PayFast ZAR, PayPal USD, Operating Bank ZAR)
    - Pending Escrow Liability (Student Escrow Deposits)
    - Tutor Liabilities (Tutor Payables)
    - Student Wallet Credits (Contract Liabilities)
    - Net Platform Revenue (Platform Commissions - Absorbed Expenses)
    - Trial Balance Zero-Sum status
    """
    trial_data = get_general_ledger_trial_balance()

    def _net_balance(account_code: str) -> Decimal:
        row = next((r for r in trial_data['trial_rows'] if r['account_code'] == account_code), None)
        return Decimal(str(row['net_zar'])) if row else Decimal('0.00')

    def _net_currency(account_code: str, currency: str) -> Decimal:
        rows = LedgerEntry.objects.filter(account=account_code, currency=currency).aggregate(
            debits=Sum('amount', filter=Q(entry_type=LedgerEntry.EntryType.DEBIT)),
            credits=Sum('amount', filter=Q(entry_type=LedgerEntry.EntryType.CREDIT)),
        )
        return (rows['debits'] or Decimal('0.00')) - (rows['credits'] or Decimal('0.00'))

    # Assets: Normal balance is DEBIT (DR - CR > 0)
    payfast_cash_zar = _net_balance(LedgerAccount.ASSET_GATEWAY_PAYFAST)
    paypal_cash_zar = _net_balance(LedgerAccount.ASSET_GATEWAY_PAYPAL)
    operating_bank_zar = _net_balance(LedgerAccount.ASSET_OPERATING_BANK)

    paypal_cash_usd = _net_currency(LedgerAccount.ASSET_GATEWAY_PAYPAL, 'USD')

    # Liabilities: Normal balance is CREDIT (CR - DR > 0)
    escrow_liability_zar = -_net_balance(LedgerAccount.LIABILITY_STUDENT_ESCROW)
    escrow_liability_usd = -_net_currency(LedgerAccount.LIABILITY_STUDENT_ESCROW, 'USD')

    tutor_payable_zar = -_net_balance(LedgerAccount.LIABILITY_TUTOR_PAYABLE)
    tutor_payable_usd = -_net_currency(LedgerAccount.LIABILITY_TUTOR_PAYABLE, 'USD')

    student_wallet_zar = -_net_balance(LedgerAccount.LIABILITY_STUDENT_WALLET)
    student_wallet_usd = -_net_currency(LedgerAccount.LIABILITY_STUDENT_WALLET, 'USD')

    # Revenue: Normal balance is CREDIT (CR - DR > 0)
    gross_commission_zar = -_net_balance(LedgerAccount.REVENUE_PLATFORM_COMMISSION)
    gross_commission_usd = -_net_currency(LedgerAccount.REVENUE_PLATFORM_COMMISSION, 'USD')

    # Expenses: Normal balance is DEBIT (DR - CR > 0)
    dispute_expense_zar = _net_balance(LedgerAccount.EXPENSE_DISPUTE_SETTLEMENT)
    compensation_expense_zar = _net_balance(LedgerAccount.EXPENSE_STUDENT_COMPENSATION)
    gateway_fees_expense_zar = _net_balance(LedgerAccount.EXPENSE_GATEWAY_FEES)
    total_expenses_zar = dispute_expense_zar + compensation_expense_zar + gateway_fees_expense_zar
    total_expenses_usd = sum(
        _net_currency(account, 'USD') for account in (
            LedgerAccount.EXPENSE_DISPUTE_SETTLEMENT,
            LedgerAccount.EXPENSE_STUDENT_COMPENSATION,
            LedgerAccount.EXPENSE_GATEWAY_FEES,
        )
    )

    net_revenue_zar = gross_commission_zar - total_expenses_zar
    net_revenue_usd = gross_commission_usd - total_expenses_usd

    live_balances = {
        'gateway_cash_payfast_zar': float(max(payfast_cash_zar, Decimal('0.00'))),
        'gateway_cash_paypal_usd': float(max(paypal_cash_usd, Decimal('0.00'))),
        'gateway_cash_paypal_zar': float(max(paypal_cash_zar, Decimal('0.00'))),
        'operating_bank_zar': float(max(operating_bank_zar, Decimal('0.00'))),
        'escrow_liability_usd': float(max(escrow_liability_usd, Decimal('0.00'))),
        'escrow_liability_zar': float(max(escrow_liability_zar, Decimal('0.00'))),
        'tutor_payable_usd': float(max(tutor_payable_usd, Decimal('0.00'))),
        'tutor_payable_zar': float(max(tutor_payable_zar, Decimal('0.00'))),
        'student_wallet_usd': float(max(student_wallet_usd, Decimal('0.00'))),
        'student_wallet_zar': float(max(student_wallet_zar, Decimal('0.00'))),
        'gross_commission_usd': float(max(gross_commission_usd, Decimal('0.00'))),
        'gross_commission_zar': float(max(gross_commission_zar, Decimal('0.00'))),
        'total_expenses_usd': float(max(total_expenses_usd, Decimal('0.00'))),
        'total_expenses_zar': float(max(total_expenses_zar, Decimal('0.00'))),
        'net_revenue_usd': float(net_revenue_usd),
        'net_revenue_zar': float(net_revenue_zar),
    }

    summary = {
        'total_assets_zar': float(max(payfast_cash_zar + paypal_cash_zar + operating_bank_zar, Decimal('0.00'))),
        'total_liabilities_zar': float(max(escrow_liability_zar + tutor_payable_zar + student_wallet_zar, Decimal('0.00'))),
        'net_revenue_zar': float(net_revenue_zar),
        'is_balanced': trial_data['is_balanced'],
        'variance_zar': trial_data['variance_zar']
    }

    return {
        'live_balances': live_balances,
        'summary': summary,
        'trial_balance': trial_data,
    }
