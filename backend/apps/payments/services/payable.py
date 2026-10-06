"""
What the platform owes a tutor: the balance of ledger account 2020, in ZAR. One definition shared by the tutor wallet, the admin
payout preview and the payout batches, so the three can never disagree about "cleared balance".
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Q, Sum

from apps.payments.models import LedgerAccount, LedgerEntry

CENT = Decimal('0.01')


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENT, ROUND_HALF_UP)


def payable_totals(user) -> dict:
    """{'credits', 'debits', 'lessons'} on 2020 for one tutor (`lessons` = cleared lessons that built the balance)."""
    totals = LedgerEntry.objects.filter(user=user, account=LedgerAccount.LIABILITY_TUTOR_PAYABLE).aggregate(
        credits=Sum('amount_zar', filter=Q(entry_type=LedgerEntry.EntryType.CREDIT)),
        debits=Sum('amount_zar', filter=Q(entry_type=LedgerEntry.EntryType.DEBIT)),
        lessons=Count('booking', distinct=True, filter=Q(event_type__in=[
            LedgerEntry.EventType.ESCROW_CLEARED, LedgerEntry.EventType.PAYMENT_FAILURE_ABSORBED])),
    )
    return {'credits': _money(totals['credits']), 'debits': _money(totals['debits']), 'lessons': totals['lessons'] or 0}


def payable_balance_zar(user) -> Decimal:
    """Cleared money owed to the tutor (ledger credits minus debits on 2020)."""
    totals = payable_totals(user)
    return totals['credits'] - totals['debits']


def open_commitment_zar(user) -> Decimal:
    """Money already committed to a payout batch that has neither paid it nor released it."""
    from apps.admin_api.models import PayoutBatchLine
    return _money(PayoutBatchLine.objects.filter(teacher__user=user, is_open=True).aggregate(total=Sum('amount_zar'))['total'])


def available_balance_zar(user) -> Decimal:
    """What a new batch may still take: the ledger balance minus what open batches already hold."""
    return payable_balance_zar(user) - open_commitment_zar(user)
