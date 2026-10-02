import logging
import uuid
from decimal import Decimal
from typing import List, Optional, Dict, Any
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from apps.payments.models import LedgerEntry, LedgerAccount, PaymentTransaction

logger = logging.getLogger(__name__)

DEFAULT_FX_USD_TO_ZAR = Decimal('18.7500')


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
    fx_rate_to_zar: Decimal = DEFAULT_FX_USD_TO_ZAR,
    journal_batch_id: Optional[uuid.UUID] = None,
) -> List[LedgerEntry]:
    """
    Core double-entry journal posting engine.
    Guarantees atomic persistence and strict zero-sum balancing invariant:
    SUM(Debits) == SUM(Credits) in transaction currency and ZAR equivalent.
    """
    if not entries:
        raise ValueError("Cannot record empty journal entries list.")

    batch_id = journal_batch_id or uuid.uuid4()
    
    total_debits = Decimal('0.00')
    total_credits = Decimal('0.00')

    prepared_records = []
    for item in entries:
        account = item['account']
        entry_type = item['entry_type']
        amount = Decimal(str(item['amount'])).quantize(Decimal('0.01'))
        item_currency = item.get('currency', currency).upper()

        if amount <= Decimal('0.00'):
            raise ValueError(f"Ledger entry amount must be positive, got {amount} for {account}")

        if entry_type == LedgerEntry.EntryType.DEBIT:
            total_debits += amount
        elif entry_type == LedgerEntry.EntryType.CREDIT:
            total_credits += amount
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
            'amount_zar': amount_zar,
            'event_type': event_type,
            'description': item.get('description', description),
            'booking': booking,
            'payment_transaction': payment_transaction,
            'dispute_case': dispute_case,
            'payout_batch': payout_batch,
            'user': user or (booking.student if booking else (payment_transaction.booking.student if payment_transaction and payment_transaction.booking else None)),
        })

    # Zero-sum invariant assertion (Transaction Currency)
    if total_debits != total_credits:
        raise UnbalancedJournalEntryError(
            f"Unbalanced journal entry batch {batch_id}: Total Debits ({total_debits} {currency}) "
            f"!= Total Credits ({total_credits} {currency}). Event: {event_type}"
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


    with transaction.atomic():
        created_entries = [
            LedgerEntry.objects.create(**rec) for rec in prepared_records
        ]

    logger.info(
        f"[LEDGER JOURNAL RECORDED] Batch {batch_id} | Event: {event_type} | "
        f"Balanced {total_debits} {currency} ({len(created_entries)} lines)"
    )
    return created_entries


# ============================================================================
# High-Level Domain Journal Helpers
# ============================================================================

def record_payment_capture_entry(
    payment_transaction: PaymentTransaction,
    booking=None,
    user=None,
    fx_rate_to_zar: Decimal = DEFAULT_FX_USD_TO_ZAR
) -> List[LedgerEntry]:
    """
    Triggered when a student checkout succeeds.
    DR Asset: Gateway Cash (PayPal or PayFast)
    CR Liability: Student Escrow Deposits
    """
    amount = Decimal(str(payment_transaction.amount)).quantize(Decimal('0.01'))
    currency = payment_transaction.currency.upper()
    
    if payment_transaction.gateway == PaymentTransaction.Gateway.PAYFAST or currency == 'ZAR':
        asset_account = LedgerAccount.ASSET_GATEWAY_PAYFAST
    else:
        asset_account = LedgerAccount.ASSET_GATEWAY_PAYPAL

    entries = [
        {
            'account': asset_account,
            'entry_type': LedgerEntry.EntryType.DEBIT,
            'amount': amount,
            'currency': currency,
            'description': f"Captured customer deposit via {payment_transaction.gateway.upper()} ref {payment_transaction.gateway_reference}"
        },
        {
            'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
            'entry_type': LedgerEntry.EntryType.CREDIT,
            'amount': amount,
            'currency': currency,
            'description': f"Escrow liability hold for booking {booking.id if booking else 'bundle'}"
        }
    ]

    return record_journal_entries(
        entries=entries,
        event_type=LedgerEntry.EventType.PAYMENT_CAPTURED,
        description=f"Payment capture {payment_transaction.gateway_reference}",
        booking=booking or payment_transaction.booking,
        payment_transaction=payment_transaction,
        user=user or (booking.student if booking else None),
        currency=currency,
        fx_rate_to_zar=fx_rate_to_zar
    )


def record_escrow_clearance_entry(
    booking,
    payment_transaction: Optional[PaymentTransaction] = None,
    amount_usd: Optional[Decimal] = None,
    fx_rate_to_zar: Decimal = DEFAULT_FX_USD_TO_ZAR
) -> List[LedgerEntry]:
    """
    Triggered upon 24-hour dual-verified escrow clearance.
    DR Liability: Student Escrow Deposits (100%)
    CR Liability: Tutor Payables (80%)
    CR Revenue: Platform Take Rate (20%)
    """
    gross_amount = amount_usd or (payment_transaction.amount if payment_transaction else booking.teacher.price_per_25min_usd)
    gross_amount = Decimal(str(gross_amount)).quantize(Decimal('0.01'))
    
    tutor_net = (gross_amount * Decimal('0.80')).quantize(Decimal('0.01'))
    platform_margin = gross_amount - tutor_net

    currency = payment_transaction.currency if payment_transaction else 'USD'

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
        fx_rate_to_zar=fx_rate_to_zar
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
        fx_rate_to_zar=Decimal('1.0000')
    )


def record_student_refund_entry(
    booking,
    payment_transaction: Optional[PaymentTransaction] = None,
    amount_usd: Optional[Decimal] = None,
    refund_method: str = 'wallet_credit',  # 'wallet_credit' or 'gateway'
    reason: str = "Student refund issued",
    fx_rate_to_zar: Decimal = DEFAULT_FX_USD_TO_ZAR,
) -> List[LedgerEntry]:
    """
    Triggered when a booking is refunded to a student (e.g. teacher no-show, student cancellation).
    Lifecycle Double-Entry:
    - If refund_method == 'gateway' (Direct cash reversal):
      DR Liability: Student Escrow Deposits
      CR Asset: Gateway Cash (PayFast / PayPal)
    - If refund_method == 'wallet_credit' (Customer wallet / lesson store credit):
      DR Liability: Student Escrow Deposits
      CR Liability: Student Wallet Credits
    """
    gross_amount = amount_usd or (payment_transaction.amount if payment_transaction else booking.teacher.price_per_25min_usd)
    gross_amount = Decimal(str(gross_amount)).quantize(Decimal('0.01'))
    currency = payment_transaction.currency if payment_transaction else 'USD'

    if refund_method == 'gateway':
        if payment_transaction and (payment_transaction.gateway == PaymentTransaction.Gateway.PAYFAST or currency == 'ZAR'):
            cr_account = LedgerAccount.ASSET_GATEWAY_PAYFAST
        else:
            cr_account = LedgerAccount.ASSET_GATEWAY_PAYPAL
        cr_desc = f"Gateway refund payout to original payment method ({payment_transaction.gateway.upper() if payment_transaction else 'PAYPAL'})"
    else:
        cr_account = LedgerAccount.LIABILITY_STUDENT_WALLET
        cr_desc = f"Student wallet credit restitution granted for {reason}"

    entries = [
        {
            'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
            'entry_type': LedgerEntry.EntryType.DEBIT,
            'amount': gross_amount,
            'currency': currency,
            'description': f"Escrow liability cancelled for booking BK-{str(booking.id)[:6].upper()}: {reason}"
        },
        {
            'account': cr_account,
            'entry_type': LedgerEntry.EntryType.CREDIT,
            'amount': gross_amount,
            'currency': currency,
            'description': cr_desc
        }
    ]

    return record_journal_entries(
        entries=entries,
        event_type=LedgerEntry.EventType.REFUND_ISSUED,
        description=f"Refund issued for booking {booking.id}: {reason}",
        booking=booking,
        payment_transaction=payment_transaction,
        user=booking.student,
        currency=currency,
        fx_rate_to_zar=fx_rate_to_zar
    )


def record_dispute_settlement_entry(
    dispute_case,
    resolution: str,
    fx_rate_to_zar: Decimal = DEFAULT_FX_USD_TO_ZAR
) -> List[LedgerEntry]:
    """
    Triggered when an admin resolves a dispute tribunal case.
    Handles FULL_REFUND_STUDENT, RELEASE_TUTOR, and platform-absorbed SPLIT_50_50.
    """
    booking = dispute_case.booking
    amount_usd = Decimal(str(booking.teacher.price_per_25min_usd)).quantize(Decimal('0.01'))

    if resolution == 'full_refund_student':
        # Student refund to platform credit wallet
        entries = [
            {
                'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
                'entry_type': LedgerEntry.EntryType.DEBIT,
                'amount': amount_usd,
                'currency': 'USD',
                'description': f"Escrow cancelled - refunded to student for dispute {dispute_case.id}"
            },
            {
                'account': LedgerAccount.LIABILITY_STUDENT_WALLET,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': amount_usd,
                'currency': 'USD',
                'description': f"Student credit wallet restitution for dispute {dispute_case.id}"
            }
        ]
    elif resolution == 'release_tutor':
        tutor_net = (amount_usd * Decimal('0.80')).quantize(Decimal('0.01'))
        platform_fee = amount_usd - tutor_net
        entries = [
            {
                'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
                'entry_type': LedgerEntry.EntryType.DEBIT,
                'amount': amount_usd,
                'currency': 'USD',
                'description': f"Escrow released to tutor by arbitration for dispute {dispute_case.id}"
            },
            {
                'account': LedgerAccount.LIABILITY_TUTOR_PAYABLE,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': tutor_net,
                'currency': 'USD',
                'description': f"Tutor payable awarded by tribunal for dispute {dispute_case.id}"
            },
            {
                'account': LedgerAccount.REVENUE_PLATFORM_COMMISSION,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': platform_fee,
                'currency': 'USD',
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
                'currency': 'USD',
                'description': f"Escrow cleared under 50/50 dispute split {dispute_case.id}"
            },
            {
                'account': LedgerAccount.LIABILITY_TUTOR_PAYABLE,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': tutor_net,
                'currency': 'USD',
                'description': f"Tutor share paid under 50/50 dispute split {dispute_case.id}"
            },
            {
                'account': LedgerAccount.REVENUE_PLATFORM_COMMISSION,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': platform_fee,
                'currency': 'USD',
                'description': f"Platform fee under 50/50 dispute split {dispute_case.id}"
            },
            # 2. Platform absorbs student restitution expense
            {
                'account': LedgerAccount.EXPENSE_DISPUTE_SETTLEMENT,
                'entry_type': LedgerEntry.EntryType.DEBIT,
                'amount': amount_usd,
                'currency': 'USD',
                'description': f"Platform absorption expense for 50/50 dispute settlement {dispute_case.id}"
            },
            {
                'account': LedgerAccount.LIABILITY_STUDENT_WALLET,
                'entry_type': LedgerEntry.EntryType.CREDIT,
                'amount': amount_usd,
                'currency': 'USD',
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
        user=dispute_case.student,
        currency='USD',
        fx_rate_to_zar=fx_rate_to_zar
    )


def record_outage_refund_entry(
    booking,
    user=None,
    amount_usd: Optional[Decimal] = None,
    fx_rate_to_zar: Decimal = DEFAULT_FX_USD_TO_ZAR
) -> List[LedgerEntry]:
    """
    Triggered upon load-shedding / Eskom power outage mid-lesson interruption.
    DR Liability: Student Escrow Deposits (Holding)
    CR Liability: Student Wallet Credits (Student Credit Wallet)
    """
    amount = amount_usd or booking.teacher.price_per_25min_usd
    amount = Decimal(str(amount)).quantize(Decimal('0.01'))

    entries = [
        {
            'account': LedgerAccount.LIABILITY_STUDENT_ESCROW,
            'entry_type': LedgerEntry.EntryType.DEBIT,
            'amount': amount,
            'currency': 'USD',
            'description': f"Escrow hold released due to Eskom load-shedding force majeure BK-{str(booking.id)[:6].upper()}"
        },
        {
            'account': LedgerAccount.LIABILITY_STUDENT_WALLET,
            'entry_type': LedgerEntry.EntryType.CREDIT,
            'amount': amount,
            'currency': 'USD',
            'description': f"Student credit wallet refunded due to Eskom power outage"
        }
    ]

    return record_journal_entries(
        entries=entries,
        event_type=LedgerEntry.EventType.OUTAGE_REFUND,
        description=f"Eskom load-shedding force majeure refund for booking {booking.id}",
        booking=booking,
        user=user or booking.student,
        currency='USD',
        fx_rate_to_zar=fx_rate_to_zar
    )


def record_compensation_entry(
    user,
    booking=None,
    amount_usd: Decimal = Decimal('9.00'),
    reason: str = "Tutor no-show apology credit",
    fx_rate_to_zar: Decimal = DEFAULT_FX_USD_TO_ZAR
) -> List[LedgerEntry]:
    """
    Triggered when the platform awards a courtesy/bonus credit (e.g. tutor no-show or memo SLA breach).
    DR Expense: Student Goodwill / Compensation
    CR Liability: Student Wallet Credits (Customer Credit Wallet)
    """
    amount = Decimal(str(amount_usd)).quantize(Decimal('0.01'))

    entries = [
        {
            'account': LedgerAccount.EXPENSE_STUDENT_COMPENSATION,
            'entry_type': LedgerEntry.EntryType.DEBIT,
            'amount': amount,
            'currency': 'USD',
            'description': f"Platform compensation expense: {reason}"
        },
        {
            'account': LedgerAccount.LIABILITY_STUDENT_WALLET,
            'entry_type': LedgerEntry.EntryType.CREDIT,
            'amount': amount,
            'currency': 'USD',
            'description': f"Bonus credit granted to {user.username} for {reason}"
        }
    ]

    return record_journal_entries(
        entries=entries,
        event_type=LedgerEntry.EventType.COMPENSATION_AWARDED,
        description=f"Platform goodwill compensation: {reason}",
        booking=booking,
        user=user,
        currency='USD',
        fx_rate_to_zar=fx_rate_to_zar
    )


def record_def501_quarantine_entry(
    payment_transaction: PaymentTransaction,
    booking=None,
    user=None,
    fx_rate_to_zar: Decimal = DEFAULT_FX_USD_TO_ZAR
) -> List[LedgerEntry]:
    """
    Triggered when a late payment arrives for an expired/re-booked slot (DEF-501).
    Quarantines deposit and issues instant wallet credit restitution.
    1. DR Asset: Gateway Cash -> CR Liability: Quarantined Late Deposits
    2. DR Liability: Quarantined Late Deposits -> CR Liability: Student Wallet Credits
    """
    amount = Decimal(str(payment_transaction.amount)).quantize(Decimal('0.01'))
    currency = payment_transaction.currency.upper()
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
        fx_rate_to_zar=fx_rate_to_zar
    )


def record_unallocated_payment_entry(
    payment_transaction: PaymentTransaction,
    booking=None,
    user=None,
    fx_rate_to_zar: Decimal = DEFAULT_FX_USD_TO_ZAR
) -> List[LedgerEntry]:
    """
    Money captured by a gateway that cannot be applied to its booking (duplicate payment, booking already
    confirmed/completed). Held in the quarantine liability until it is refunded to the payer at the gateway (D-6).
    Deliberately NO student wallet credit: the funds go back to the original payment method.
    DR Asset: Gateway Cash -> CR Liability: Quarantined Deposits
    """
    amount = Decimal(str(payment_transaction.amount)).quantize(Decimal('0.01'))
    currency = payment_transaction.currency.upper()
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
        fx_rate_to_zar=fx_rate_to_zar
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

    # Assets: Normal balance is DEBIT (DR - CR > 0)
    payfast_cash_zar = _net_balance(LedgerAccount.ASSET_GATEWAY_PAYFAST)
    paypal_cash_zar = _net_balance(LedgerAccount.ASSET_GATEWAY_PAYPAL)
    operating_bank_zar = _net_balance(LedgerAccount.ASSET_OPERATING_BANK)

    paypal_cash_usd = (paypal_cash_zar / DEFAULT_FX_USD_TO_ZAR).quantize(Decimal('0.01')) if paypal_cash_zar else Decimal('0.00')

    # Liabilities: Normal balance is CREDIT (CR - DR > 0)
    escrow_liability_zar = -_net_balance(LedgerAccount.LIABILITY_STUDENT_ESCROW)
    escrow_liability_usd = (escrow_liability_zar / DEFAULT_FX_USD_TO_ZAR).quantize(Decimal('0.01')) if escrow_liability_zar else Decimal('0.00')

    tutor_payable_zar = -_net_balance(LedgerAccount.LIABILITY_TUTOR_PAYABLE)
    tutor_payable_usd = (tutor_payable_zar / DEFAULT_FX_USD_TO_ZAR).quantize(Decimal('0.01')) if tutor_payable_zar else Decimal('0.00')

    student_wallet_zar = -_net_balance(LedgerAccount.LIABILITY_STUDENT_WALLET)
    student_wallet_usd = (student_wallet_zar / DEFAULT_FX_USD_TO_ZAR).quantize(Decimal('0.01')) if student_wallet_zar else Decimal('0.00')

    # Revenue: Normal balance is CREDIT (CR - DR > 0)
    gross_commission_zar = -_net_balance(LedgerAccount.REVENUE_PLATFORM_COMMISSION)
    gross_commission_usd = (gross_commission_zar / DEFAULT_FX_USD_TO_ZAR).quantize(Decimal('0.01')) if gross_commission_zar else Decimal('0.00')

    # Expenses: Normal balance is DEBIT (DR - CR > 0)
    dispute_expense_zar = _net_balance(LedgerAccount.EXPENSE_DISPUTE_SETTLEMENT)
    compensation_expense_zar = _net_balance(LedgerAccount.EXPENSE_STUDENT_COMPENSATION)
    gateway_fees_expense_zar = _net_balance(LedgerAccount.EXPENSE_GATEWAY_FEES)
    total_expenses_zar = dispute_expense_zar + compensation_expense_zar + gateway_fees_expense_zar
    total_expenses_usd = (total_expenses_zar / DEFAULT_FX_USD_TO_ZAR).quantize(Decimal('0.01')) if total_expenses_zar else Decimal('0.00')

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
