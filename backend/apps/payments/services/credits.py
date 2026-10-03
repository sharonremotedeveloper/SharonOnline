"""
Lesson credits (the student wallet), kept as *lots*: every grant is its own `CreditBundle` row with its own expiry, so
credits are spent oldest-expiry-first and an expired lot is written off exactly (Task 9.6, decision D-6: 30 days).

`grant_credit()` is still the only way to add credits. The caller is responsible for the matching ledger entry (2040
student wallet liability) - this module only posts the *expiry* entry, because only it knows what expired.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.payments.models import CreditBundle, LedgerAccount, LedgerEntry

logger = logging.getLogger(__name__)


class InsufficientCredits(Exception):
    """The student does not have that many unexpired credits."""


def _expiry_days(source: str) -> int:
    return {
        CreditBundle.Source.PURCHASE: settings.CREDIT_EXPIRY_DAYS_BUNDLE,
        CreditBundle.Source.BONUS: settings.CREDIT_EXPIRY_DAYS_BONUS,
    }.get(source, settings.CREDIT_EXPIRY_DAYS_REFUND)


def grant_credit(user, *, credits: int = 1, pack_name: str = 'Lesson Credit',
                 source: str = CreditBundle.Source.RESTITUTION, unit_value: Decimal = Decimal('0.00'),
                 currency: str = 'USD', expires_in_days: int | None = None) -> CreditBundle:
    """
    Add `credits` lesson credits to the user's wallet as a new lot and return it.

    `unit_value` is the money value of one credit in `currency` (what the 2040 liability was credited per lesson); the
    expiry job needs it to post the write-off. Call this inside the transaction that justifies the grant.
    """
    if credits < 1:
        raise ValueError("credits must be >= 1")
    days = _expiry_days(source) if expires_in_days is None else expires_in_days
    return CreditBundle.objects.create(
        user=user, pack_name=pack_name, total_credits=credits, remaining_credits=credits, amount_paid=0,
        currency=currency, source=source, unit_value=Decimal(str(unit_value)).quantize(Decimal('0.01')),
        expires_at=timezone.now() + timedelta(days=days))


def available_credits(user, now=None) -> int:
    """Credits the student can still spend (expired lots excluded immediately, before the expiry job has run)."""
    return CreditBundle.objects.active(now).filter(user=user).aggregate(t=Sum('remaining_credits'))['t'] or 0


def spend_credit(user, *, credits: int = 1, now=None):
    """
    Take `credits` from the lots that expire soonest. Returns [(lot, taken), ...]. All-or-nothing: raises
    InsufficientCredits (and spends nothing) when the unexpired balance is too small. Call inside the caller's transaction.
    """
    if credits < 1:
        raise ValueError("credits must be >= 1")
    with transaction.atomic():
        lots = list(CreditBundle.objects.select_for_update().active(now)
                    .filter(user=user, remaining_credits__gt=0).order_by('expires_at', 'created_at'))
        if sum(l.remaining_credits for l in lots) < credits:
            raise InsufficientCredits(f"Needs {credits} credit(s); {sum(l.remaining_credits for l in lots)} available.")
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


def expire_credits(now=None) -> dict:
    """
    Write off every lot whose expiry has passed. Idempotent: a lot is expired once (`expired_at`), under a row lock.
    The unspent value moves from the wallet liability (2040) to breakage revenue (4020).
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
            value = (lot.unit_value * gone).quantize(Decimal('0.01'))
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
                    user=lot.user, currency=lot.currency)
            lot.expired_credits += gone
            lot.remaining_credits = 0
            lot.expired_at = now
            lot.save(update_fields=['expired_credits', 'remaining_credits', 'expired_at'])
            lots_done += 1
            credits_done += gone
    if lots_done:
        logger.info("[CREDITS] Expired %s credit(s) in %s lot(s)", credits_done, lots_done)
    return {'lots': lots_done, 'credits': credits_done}
