"""
Slice P2: the tutor's statement. A CSV over ledger account 2020 (what the platform owes the tutor): every earning, payout and
bank return in ZAR with a running balance, so the tutor can reconcile their bank account. It reads the same rows as the wallet
and the payout batches, so the three always agree. Nothing here includes the student's identity or bank details.
"""
import csv
import io
from datetime import date, datetime, time, timezone as dt_timezone
from decimal import Decimal

from apps.payments.models import LedgerAccount, LedgerEntry
from apps.payments.services.payout_export import defuse

HEADER = ['Date (UTC)', 'Description', 'Reference', 'Earned (ZAR)', 'Paid out (ZAR)', 'Balance (ZAR)']
LABELS = {
    LedgerEntry.EventType.ESCROW_CLEARED: 'Lesson earnings',
    LedgerEntry.EventType.PAYMENT_FAILURE_ABSORBED: 'Lesson earnings (paid by Sharon ESL)',
    LedgerEntry.EventType.DISPUTE_RESOLVED: 'Dispute adjustment',
    LedgerEntry.EventType.PAYOUT_EXECUTED: 'Payout to your bank account',
    LedgerEntry.EventType.PAYOUT_RETURNED: 'Payout returned by the bank',
}


def _reference(entry) -> str:
    if entry.booking_id:
        return f'BK-{str(entry.booking_id)[:6].upper()}'
    if entry.payout_batch_id:
        return entry.payout_batch.batch_reference
    return ''


def statement_rows(user, start: date | None = None, end: date | None = None) -> list:
    """Chronological rows (dicts) for [start, end] inclusive, each with the balance after it; the opening balance comes first."""
    entries = list(LedgerEntry.objects.filter(user=user, account=LedgerAccount.LIABILITY_TUTOR_PAYABLE)
                   .select_related('payout_batch').order_by('created_at', 'id'))
    lo = datetime.combine(start, time.min, tzinfo=dt_timezone.utc) if start else None
    hi = datetime.combine(end, time.max, tzinfo=dt_timezone.utc) if end else None
    balance, opening, rows = Decimal('0.00'), None, []
    for entry in entries:
        signed = entry.amount_zar if entry.entry_type == LedgerEntry.EntryType.CREDIT else -entry.amount_zar
        if lo and entry.created_at < lo:
            balance += signed
            continue
        if hi and entry.created_at > hi:
            break
        if opening is None:
            opening = balance
        balance += signed
        rows.append({'date': entry.created_at, 'description': LABELS.get(entry.event_type, entry.get_event_type_display()),
                     'reference': _reference(entry), 'earned': signed if signed > 0 else Decimal('0.00'),
                     'paid_out': -signed if signed < 0 else Decimal('0.00'), 'balance': balance})
    return [{'opening': opening if opening is not None else balance}, *rows]


def statement_csv(user, start=None, end=None) -> str:
    opening, *rows = statement_rows(user, start, end)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator='\r\n')
    writer.writerow(HEADER)
    writer.writerow(['', 'Opening balance', '', '', '', f"{opening['opening']:.2f}"])
    for row in rows:
        writer.writerow([f"{row['date']:%Y-%m-%d %H:%M}", defuse(row['description']), defuse(row['reference']),
                         f"{row['earned']:.2f}", f"{row['paid_out']:.2f}", f"{row['balance']:.2f}"])
    return out.getvalue()
