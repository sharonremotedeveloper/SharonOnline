"""
Refund gateway contract (Task 10.7), approved by the Architect review in docs/TASK_10_7_REFUND_GATEWAYS_PLAN.md section 2b.
INTERFACE STUB: slice R-A fills in the PayPal / PayFast adapters and the router; slice R-B drives them from
`refunds.process_pending_refunds`.

An adapter turns one `RefundOrder` (a frozen snapshot, never an ORM row) into a provider call and reports what happened as a
`RefundResult`. Adapters never touch the ledger or the database and MUST NOT raise: the router converts any unexpected exception to
`transient` (never to `rejected`/`failed`) and logs `type(exc).__name__` only - no exception text, headers, URLs, tokens or
signatures. Adapters are idempotent: `refund` twice for the same `request_id` must never return money twice.

States
  completed  the provider returned the money (`reference` = provider refund id)
  submitted  the provider accepted the refund but it is not finished (PayPal PENDING); `reference` is set; poll with `lookup`
  rejected   the provider refused this refund permanently (time limit, already refunded, amount, instrument); `code` says why
  transient  could not tell (timeout, 429, 5xx, transport, provider/config problem): retry later with the same request id
  manual     this backend does not move money (sandbox, creds missing, PayFast refunds disabled): a person acts, no retry budget used
"""
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Optional, Protocol

logger = logging.getLogger(__name__)

RefundState = Literal['completed', 'submitted', 'rejected', 'transient', 'manual']


@dataclass(frozen=True)
class RefundOrder:
    """Everything an adapter needs, built by refunds.py from the locked RefundRequest row."""
    refund_id: str                  # RefundRequest.id (uuid string)
    request_id: str                 # stable idempotency key, e.g. 'refund-<id>' or 'refund-<id>-r<epoch>'
    gateway: str                    # 'paypal' | 'payfast' (from the PaymentTransaction)
    capture_ref: str                # PayPal capture id / PayFast pf_payment_id (never an 'INIT-' reference)
    provider_refund_id: str         # '' until the provider accepted a refund (set for polling)
    amount: Decimal                 # exactly the captured amount, already quantised for `currency`
    currency: str
    invoice_id: str                 # our refund id, for the provider's records
    note: str                       # text shown to the payer


@dataclass(frozen=True)
class RefundResult:
    state: RefundState
    reference: str = ''             # provider refund id when known
    detail: str = ''                # short, log-safe explanation (no provider body, no secrets)
    code: str = ''                  # provider error name/issue, e.g. 'CAPTURE_FULLY_REFUNDED'; '' when none
    http_status: int = 0
    retry_after_s: Optional[int] = None
    provider_level: bool = False    # True for config/outage errors (401/403, sandbox-live mismatch): counts toward the provider breaker, not the row


class RefundGateway(Protocol):
    def refund(self, order: RefundOrder) -> RefundResult:
        """Ask the provider to return `order.amount` `order.currency` to the original payment method."""

    def lookup(self, order: RefundOrder) -> RefundResult:
        """Where is a refund that was `submitted`? Reads provider state only; never creates a refund."""


class ManualSandboxRefundGateway:
    """Moves no money: refunds wait for a person (sandbox, credentials missing, or a provider whose refund API is not enabled)."""

    def refund(self, order: RefundOrder) -> RefundResult:
        return RefundResult('manual', detail='manual refund backend')

    def lookup(self, order: RefundOrder) -> RefundResult:
        return RefundResult('manual', detail='manual refund backend')
