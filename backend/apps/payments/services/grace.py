"""
Pending-payment grace bookings (Task 10.2, plan section 2). INTERFACE STUB: slice E implements these functions; other
slices (webhook events, failure runbook) call them and must not need to know the policy.

A grace booking is a lesson confirmed (Zoom link issued) while PayPal still reports the capture PENDING. Policy
(docs/PHASE_10_2_PAYPAL_ORDERS_PLAN.md P-1..P-7):
  * one open grace booking per student account AND per PayPal payer;
  * only for merchant-side reasons and PENDING_REVIEW; never for ECHECK / VERIFICATION_REQUIRED / OTHER / DECLINED;
  * never for credit-pack purchases;
  * circuit breaker: settings.GRACE_MAX_OPEN risk-based grace bookings open at once switches grace off.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GraceDecision:
    allowed: bool
    reason: str = ''          # why grace was refused, or the rule that allowed it (for logs/admin)


def evaluate_grace(tx, outcome) -> GraceDecision:
    """Decide whether a PENDING capture may confirm its booking now. STUB: never allows."""
    return GraceDecision(False, 'grace_not_implemented')


def confirm_grace_booking(tx) -> None:
    """Confirm the booking of a PENDING_CAPTURE transaction as a grace booking. STUB."""
    raise NotImplementedError('slice E')


def on_completed(tx) -> None:
    """A PENDING_CAPTURE transaction cleared (COMPLETED). Upgrade funding, post the ledger, lift payout gates. STUB."""
    raise NotImplementedError('slice E')


def on_failed(tx) -> None:
    """A PENDING_CAPTURE transaction failed (DENIED/FAILED/REVERSED). Cancel or absorb per the runbook. STUB."""
    raise NotImplementedError('slice E / G')
