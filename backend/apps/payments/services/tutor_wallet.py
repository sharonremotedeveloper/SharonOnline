from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q, Sum

from apps.bookings.models import Booking
from apps.payments.models import BookingFunding, LedgerAccount, LedgerEntry


CENT = Decimal('0.01')
PENDING_STATUSES = (
    Booking.Status.CONFIRMED,
    Booking.Status.IN_PROGRESS,
    Booking.Status.COMPLETED_PENDING_MEMO,
    Booking.Status.COMPLETED,
)


def _money(value):
    return Decimal(value or 0).quantize(CENT, ROUND_HALF_UP)


def tutor_wallet_payload(user):
    payable_entries = LedgerEntry.objects.filter(user=user, account=LedgerAccount.LIABILITY_TUTOR_PAYABLE)
    totals = payable_entries.aggregate(
        credits=Sum('amount_zar', filter=Q(entry_type=LedgerEntry.EntryType.CREDIT)),
        debits=Sum('amount_zar', filter=Q(entry_type=LedgerEntry.EntryType.DEBIT)),
    )
    cleared_balance_zar = _money(totals['credits']) - _money(totals['debits'])

    cleared = {
        entry.booking_id: entry
        for entry in payable_entries.filter(
            entry_type=LedgerEntry.EntryType.CREDIT,
            booking__isnull=False,
        ).select_related('booking__student')
    }
    funding_rows = list(
        BookingFunding.objects.filter(booking__teacher__user=user)
        .select_related('booking__student')
        .order_by('-created_at')
    )

    transactions = []
    pending_escrow_zar = Decimal('0.00')
    fx_seen = set()
    fx_context = []
    for funding in funding_rows:
        booking = funding.booking
        net_amount = _money(Decimal(funding.captured_amount) * Decimal('0.80'))
        gross_zar = _money(Decimal(funding.captured_amount) * Decimal(funding.fx_rate_to_zar))
        net_zar = _money(net_amount * Decimal(funding.fx_rate_to_zar))
        ledger_entry = cleared.get(booking.id)
        if ledger_entry is not None:
            net_amount = ledger_entry.amount
            net_zar = ledger_entry.amount_zar
            state = 'cleared'
        elif booking.escrow_cleared_at is None and booking.status in PENDING_STATUSES:
            pending_escrow_zar += net_zar
            state = 'pending'
        else:
            continue

        fx_key = (funding.currency, funding.fx_rate_to_zar, funding.fx_source)
        if fx_key not in fx_seen:
            fx_seen.add(fx_key)
            fx_context.append({
                'currency': funding.currency,
                'fx_rate_to_zar': funding.fx_rate_to_zar,
                'fx_source': funding.fx_source,
            })
        transactions.append({
            'id': str(ledger_entry.id if ledger_entry else funding.id),
            'date': ledger_entry.created_at if ledger_entry else funding.created_at,
            'booking_ref': f'BK-{str(booking.id)[:6].upper()}',
            'student_name': booking.student.get_full_name() or booking.student.username,
            'gross_amount': funding.captured_amount,
            'currency': funding.currency,
            'gross_zar': gross_zar,
            'net_amount': net_amount,
            'net_zar': net_zar,
            'fx_rate_to_zar': funding.fx_rate_to_zar,
            'fx_source': funding.fx_source,
            'status': state,
        })

    for entry in payable_entries.filter(
        entry_type=LedgerEntry.EntryType.DEBIT,
        event_type=LedgerEntry.EventType.PAYOUT_EXECUTED,
    ).order_by('-created_at'):
        transactions.append({
            'id': str(entry.id),
            'date': entry.created_at,
            'booking_ref': '',
            'student_name': 'Payout to bank',
            'gross_amount': entry.amount,
            'currency': entry.currency,
            'gross_zar': entry.amount_zar,
            'net_amount': entry.amount,
            'net_zar': entry.amount_zar,
            'fx_rate_to_zar': entry.fx_rate_to_zar,
            'fx_source': entry.fx_source,
            'status': 'paid_out',
        })

    transactions.sort(key=lambda row: row['date'], reverse=True)
    fx_context.sort(key=lambda row: row['currency'])
    return {
        'pending_escrow_zar': pending_escrow_zar.quantize(CENT),
        'cleared_balance_zar': cleared_balance_zar.quantize(CENT),
        'fx_context': fx_context,
        'transactions': transactions,
    }
