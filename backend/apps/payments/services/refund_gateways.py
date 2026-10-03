"""
Refund gateway contract (Task 10.7). INTERFACE STUB owned by the plan docs/TASK_10_7_REFUND_GATEWAYS_PLAN.md: slice R-A fills in the
PayPal / PayFast adapters and the router, slice R-B drives them from `refunds.process_pending_refunds`.

A gateway adapter turns one `RefundRequest` into a call to the payment provider and reports what happened as a `RefundResult`.
It never touches the ledger or the database: the caller applies the result in a short transaction (`refunds.mark_processed`,
`mark_submitted`, `mark_failed`, backoff). Adapters are idempotent: calling `refund` twice for the same request must never
return money twice (PayPal: a stable `PayPal-Request-Id` derived from the request id).

States
  completed  the provider returned the money (`reference` = provider refund id)
  submitted  the provider accepted the refund but it is not finished (PayPal PENDING); `reference` is set; poll with `lookup`
  rejected   the provider refused permanently (time limit, already refunded, amount, instrument): a person must act
  transient  could not tell (timeout, 429, 5xx, provider outage): retry later with the same request id
  manual     this backend does not move money (sandbox / PayFast refunds disabled): leave it for a person, no retry budget used
"""
from dataclasses import dataclass
from typing import Literal, Protocol

RefundState = Literal['completed', 'submitted', 'rejected', 'transient', 'manual']


@dataclass(frozen=True)
class RefundResult:
    state: RefundState
    reference: str = ''
    detail: str = ''


class RefundGateway(Protocol):
    def refund(self, request) -> RefundResult:
        """Ask the provider to return `request.amount` `request.currency` to the original payment method."""

    def lookup(self, request) -> RefundResult:
        """Where is a refund that was `submitted`? Reads provider state only; never creates a refund."""


class ManualSandboxRefundGateway:
    """Moves no money: refunds wait for a person (sandbox, or a provider whose refund API is not enabled)."""

    def refund(self, request) -> RefundResult:
        return RefundResult('manual', detail='manual refund backend')

    def lookup(self, request) -> RefundResult:
        return RefundResult('manual', detail='manual refund backend')
