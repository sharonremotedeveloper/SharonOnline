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
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Optional, Protocol

from django.conf import settings

from apps.payments.gateways import paypal

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


# --- PayPal ------------------------------------------------------------------------------------------------------

# PayPal 404s naming the resource itself: a capture/refund id that this environment does not know (sandbox id on live or the
# reverse) is far more likely than a vanished capture, so it is a configuration problem, not a verdict on the refund.
_MISMATCH_404 = frozenset({'RESOURCE_NOT_FOUND', 'INVALID_RESOURCE_ID'})
_CONFIG_STATUSES = frozenset({401, 403})
_RETRYABLE_STATUSES = frozenset({408, 409, 429})


def _error_code(exc) -> str:
    return (exc.issue or exc.name or '')[:64]


def _from_unavailable(exc) -> RefundResult:
    status = exc.status_code
    return RefundResult('transient', detail=f'PayPal answered {status}', http_status=status,
                        retry_after_s=exc.retry_after_s, provider_level=status in _CONFIG_STATUSES)


def _from_rejected(exc, *, sending: bool) -> RefundResult:
    status = exc.status_code
    code = _error_code(exc)
    if status in _RETRYABLE_STATUSES:
        return RefundResult('transient', detail=f'PayPal answered {status}', code=code, http_status=status)
    if status == 404 and (exc.name in _MISMATCH_404 or exc.issue in _MISMATCH_404):
        # Sending: an ordinary per-row transient, so this refund's own attempts and the exhaustion rule apply (one bad capture must
        # not retry forever); the per-gateway breaker still trips when several refunds in a sweep see it, which is the real
        # sandbox/live-mismatch signal. A lookup of a refund id we were given stays provider-level.
        return RefundResult('transient', detail='PayPal does not know this id (sandbox/live mismatch?)', code=code,
                            http_status=status, provider_level=not sending)
    if status in (400, 404, 422):
        return RefundResult('rejected', detail=f'PayPal refused the refund ({status} {code})'.strip(), code=code, http_status=status)
    # Any other 4xx (405, 415, ...) means our request is wrong, not that this refund is refused: provider-level, retry later.
    return RefundResult('transient', detail=f'PayPal answered {status}', code=code, http_status=status, provider_level=True)


def _from_refund_json(body, *, fallback_reference: str = '') -> RefundResult:
    outcome = paypal.classify_refund(body)
    reference = str(body.get('id') or '') if isinstance(body, dict) else ''
    reference = reference or fallback_reference
    if outcome.state == 'completed' and reference:
        return RefundResult('completed', reference=reference)
    if outcome.state == 'pending' and reference:
        return RefundResult('submitted', reference=reference, detail=outcome.reason[:64])
    if outcome.state == 'rejected':
        return RefundResult('rejected', reference=reference, detail='PayPal reports the refund did not go through',
                            code=outcome.reason[:64])
    # unknown status, or completed/pending with no refund id to keep: never treat it as money returned.
    return RefundResult('transient', reference=reference, detail='PayPal answer not understood')


class PayPalRefundGateway:
    """Refunds a PayPal capture in full (`order.amount`, the captured amount) through POST /v2/payments/captures/{id}/refund."""

    def refund(self, order: RefundOrder) -> RefundResult:
        try:
            body = paypal.create_refund(capture_id=order.capture_ref, amount=order.amount, currency=order.currency,
                                        note=order.note, invoice_id=order.invoice_id, request_id=order.request_id)
        except ValueError:
            return RefundResult('rejected', detail='refund request is malformed (capture id or amount)', code='INVALID_REFUND_REQUEST')
        except paypal.PayPalUnavailable as exc:
            return _from_unavailable(exc)
        except paypal.PayPalRejected as exc:
            return _from_rejected(exc, sending=True)
        except paypal.PayPalError:
            return RefundResult('transient', detail='PayPal transport error')
        return _from_refund_json(body)

    def lookup(self, order: RefundOrder) -> RefundResult:
        if not order.provider_refund_id:
            return RefundResult('manual', detail='no provider refund id to look up')
        try:
            body = paypal.lookup_refund(order.provider_refund_id)
        except ValueError:
            return RefundResult('manual', detail='provider refund id is malformed')
        except paypal.PayPalUnavailable as exc:
            return _from_unavailable(exc)
        except paypal.PayPalRejected as exc:
            return _from_rejected(exc, sending=False)
        except paypal.PayPalError:
            return RefundResult('transient', detail='PayPal transport error')
        return _from_refund_json(body, fallback_reference=order.provider_refund_id)


# --- PayFast -----------------------------------------------------------------------------------------------------

class PayFastRefundGateway:
    """PayFast refunds are deferred: nothing is called, a person refunds from the PayFast dashboard (docs/PAYFAST_REFUNDS_UNVERIFIED.md)."""

    def refund(self, order: RefundOrder) -> RefundResult:
        return RefundResult('manual', detail='PayFast refunds are not enabled')

    def lookup(self, order: RefundOrder) -> RefundResult:
        return RefundResult('manual', detail='PayFast refunds are not enabled')


# --- Router ------------------------------------------------------------------------------------------------------

class RoutingRefundGateway:
    """
    What a production REFUND_GATEWAY_BACKEND points at. Picks the adapter by `order.gateway`, answers `manual` (offline) when
    PayPal credentials are missing or PayFast refunds are disabled, and turns any unexpected exception into `transient`
    (logging only the exception type name) so one bug cannot dead-end a refund.
    """

    def __init__(self):
        self._paypal = PayPalRefundGateway()
        self._payfast = PayFastRefundGateway()

    def _select(self, order: RefundOrder):
        """The adapter for this order, or a RefundResult('manual') when this backend must not move money."""
        gateway = (order.gateway or '').lower()
        if gateway == 'paypal':
            if not (settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET):
                return RefundResult('manual', detail='PayPal credentials are not configured')
            return self._paypal
        if gateway == 'payfast':
            if not getattr(settings, 'PAYFAST_REFUNDS_ENABLED', False):
                return RefundResult('manual', detail='PayFast refunds are not enabled')
            return self._payfast
        return RefundResult('manual', detail='no refund adapter for this gateway')

    def _run(self, op: str, order: RefundOrder) -> RefundResult:
        started = time.monotonic()
        try:
            adapter = self._select(order)
            result = adapter if isinstance(adapter, RefundResult) else getattr(adapter, op)(order)
        except Exception as exc:  # noqa: BLE001 - adapters must never raise; log the type only, never the text
            name = type(exc).__name__
            logger.error('refund_gateway_error op=%s refund_id=%s gateway=%s request_id=%s error_type=%s',
                         op, order.refund_id, order.gateway, order.request_id, name)
            return RefundResult('transient', detail=name, provider_level=False)
        logger.info('refund_gateway op=%s refund_id=%s gateway=%s request_id=%s state=%s http_status=%s error_code=%s duration_ms=%d',
                    op, order.refund_id, order.gateway, order.request_id, result.state, result.http_status, result.code,
                    int((time.monotonic() - started) * 1000))
        return result

    def refund(self, order: RefundOrder) -> RefundResult:
        return self._run('refund', order)

    def lookup(self, order: RefundOrder) -> RefundResult:
        return self._run('lookup', order)
