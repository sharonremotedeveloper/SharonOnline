"""
PayPal webhook events beyond COMPLETED (Task 10.4 / 10.2 slice F).

Contract shared by every handler here (the view has already verified PayPal's signature before any of this runs):
  * the webhook body is only a pointer: what matters (status, amounts, which payment it concerns) is RE-READ from PayPal;
  * we match to our PaymentTransaction by the capture's `custom_id` (our merchant reference), falling back to the capture id;
  * everything is idempotent under a row lock on the transaction, so a redelivery or a race with the capture endpoint /
    reconciliation job cannot post twice;
  * a notification we cannot match is quarantined as a durable GatewayAnomaly and acknowledged (a 200 stops PayPal's
    retries; the money question is a human's);
  * chargebacks never move money automatically: they open an anomaly and a DisputeCase for an admin to decide.

Handlers return a short status string for the 200 body. `CaptureRejected` -> 400 (the caller's problem), `PayPalError`
(lookup failed) -> 503 so PayPal retries.
"""
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from django.db import transaction

from apps.admin_api.models import DisputeCase
from apps.payments.gateways import paypal
from apps.payments.models import CreditPurchase, PaymentTransaction, RefundRequest
from apps.payments.services import grace, refunds
from apps.payments.services.alerts import alert_admin
from apps.payments.services.anomalies import record_anomaly
from apps.payments.services.paypal_capture import (CaptureRejected, record_failed_capture, record_pending_capture,
                                                   settle_completed_capture, verify_capture_amount)
from apps.payments.services.pricing import quantize_money

logger = logging.getLogger(__name__)

MAX_ID_LENGTH = 255          # PaymentTransaction.gateway_reference / GatewayAnomaly.reference
EXTERNAL_REFUND_REASON = 'external_refund'   # RefundRequest.reason for a refund made outside our own flow (max_length 20)
UNSETTLED = (PaymentTransaction.Status.INITIALIZED, PaymentTransaction.Status.PENDING_CAPTURE)


# ------------------------------------------------------------------------------------------------ small helpers
def _id(value, what: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_ID_LENGTH:
        raise CaptureRejected(f'missing {what}')
    return value


def _resource(event: dict) -> dict:
    resource = event.get('resource')
    return resource if isinstance(resource, dict) else {}


def _json_object(value, what: str) -> dict:
    """PayPal answered 200 with something that is not an object: treat as a failed lookup (retry), never a crash."""
    if not isinstance(value, dict):
        raise paypal.PayPalError(f'PayPal {what} lookup returned an unexpected answer')
    return value


def load_capture(capture_id: str) -> dict:
    return {**_json_object(paypal.get_capture(capture_id), 'capture'), 'id': capture_id}


def match_transaction(capture: dict):
    """Our PayPal transaction for this capture: by custom_id (merchant reference), else by the capture id we bound."""
    reference = capture.get('custom_id')
    qs = PaymentTransaction.objects.select_related('booking', 'credit_purchase__pack').filter(
        gateway=PaymentTransaction.Gateway.PAYPAL)
    tx = qs.filter(merchant_reference=reference).first() if isinstance(reference, str) and reference else None
    return tx or qs.filter(gateway_reference=capture['id']).first()


def quarantine_unmatched(reference: str, capture: dict, event: dict) -> str:
    custom_id = capture.get('custom_id')
    record_anomaly('paypal', reference, 'unknown_reference',
                   f"event {event.get('event_type')}: no transaction for custom_id={custom_id!r} / capture {capture.get('id')}",
                   payload=event)
    logger.error("[PAYPAL] %s for capture %s matches no transaction (custom_id=%r): quarantined",
                 event.get('event_type'), capture.get('id'), custom_id)
    return 'quarantined'


def _amount_of(obj: dict) -> tuple[Decimal, str]:
    info = obj.get('amount') if isinstance(obj.get('amount'), dict) else {}
    try:
        value = Decimal(str(info.get('value', '')))
    except InvalidOperation:
        raise CaptureRejected('unparseable_amount') from None
    return value, str(info.get('currency_code', '')).upper()


# ------------------------------------------------------------------------------------------------ COMPLETED
def on_capture_completed(event: dict) -> str:
    capture_id = _id(_resource(event).get('id'), 'capture id')
    capture = load_capture(capture_id)
    tx = match_transaction(capture)
    if tx is None:
        return quarantine_unmatched(capture_id, capture, event)
    if capture.get('status') != 'COMPLETED':
        raise CaptureRejected('capture not COMPLETED', status=capture.get('status'))
    verify_capture_amount(tx, capture, payload=event)
    settle_completed_capture(tx.pk, capture, payload=event)
    return 'received'


# ------------------------------------------------------------------------------------------------ DENIED / DECLINED
def fail_transaction(tx_pk) -> bool:
    """
    INITIALIZED/PENDING_CAPTURE -> FAILED under the row lock; a settled transaction is never touched. When the failed
    transaction was PENDING_CAPTURE (a grace booking may exist) the grace service unwinds it - exactly once, because the
    second delivery finds the transaction already FAILED.
    """
    with transaction.atomic():
        tx = PaymentTransaction.objects.select_for_update().get(pk=tx_pk)
        prior = tx.status
        if prior not in UNSETTLED:
            return False
        record_failed_capture(tx.pk)
        if tx.credit_purchase_id:
            CreditPurchase.objects.filter(pk=tx.credit_purchase_id, status=CreditPurchase.Status.INITIALIZED).update(
                status=CreditPurchase.Status.FAILED)
        if prior == PaymentTransaction.Status.PENDING_CAPTURE:
            tx.refresh_from_db()
            grace.on_failed(tx)
        return True


def on_capture_denied(event: dict) -> str:
    capture_id = _id(_resource(event).get('id'), 'capture id')
    capture = load_capture(capture_id)
    tx = match_transaction(capture)
    if tx is None:
        return quarantine_unmatched(capture_id, capture, event)
    outcome = paypal.classify_capture(capture)
    if outcome.state not in ('declined', 'failed'):
        logger.warning("[PAYPAL] %s for capture %s but PayPal now reports %s: not failing the transaction",
                       event.get('event_type'), capture_id, capture.get('status'))
        return 'ignored'
    fail_transaction(tx.pk)
    return 'received'


# ------------------------------------------------------------------------------------------------ PENDING
def on_capture_pending(event: dict) -> str:
    capture_id = _id(_resource(event).get('id'), 'capture id')
    capture = load_capture(capture_id)
    tx = match_transaction(capture)
    if tx is None:
        return quarantine_unmatched(capture_id, capture, event)
    outcome = paypal.classify_capture(capture)
    if outcome.state != 'pending' or tx.status not in UNSETTLED:
        return 'ignored'          # PayPal has moved on (COMPLETED/DECLINED events settle or fail it) or we already have
    verify_capture_amount(tx, capture, payload=event)
    order = _json_object(paypal.get_order(tx.gateway_order_id), 'order') if tx.gateway_order_id else {}
    with transaction.atomic():
        locked = PaymentTransaction.objects.select_for_update().get(pk=tx.pk)
        if locked.status in UNSETTLED:
            record_pending_capture(locked.pk, capture, outcome, order)
    return 'received'


# ------------------------------------------------------------------------------------------------ REFUNDED
def _capture_id_of_refund(refund: dict):
    for link in refund.get('links') or []:
        if isinstance(link, dict) and link.get('rel') == 'up' and isinstance(link.get('href'), str):
            segment = urlparse(link['href']).path.rstrip('/').rsplit('/', 1)[-1]
            if segment:
                return segment
    related = ((refund.get('supplementary_data') or {}).get('related_ids') or {})
    return related.get('capture_id') if isinstance(related, dict) else None


def on_capture_refunded(event: dict) -> str:
    refund_id = _id(_resource(event).get('id'), 'refund id')
    refund = _json_object(paypal.get_refund(refund_id), 'refund')
    if refund.get('status') != 'COMPLETED':
        logger.info("[PAYPAL] refund %s is %s: nothing to record yet", refund_id, refund.get('status'))
        return 'ignored'
    capture_id = _id(_capture_id_of_refund(refund), 'capture id on refund')
    capture = load_capture(capture_id)
    tx = match_transaction(capture)
    if tx is None:
        return quarantine_unmatched(capture_id, capture, event)
    amount, currency = _amount_of(refund)
    return apply_refund(tx.pk, refund_id, amount, currency, event)


def apply_refund(tx_pk, refund_id: str, amount: Decimal, currency: str, event: dict) -> str:
    """
    A COMPLETED refund PayPal reports for one of our payments. Order matters: (1) our own refund by its provider id (a
    SUBMITTED one is finished here; a FAILED one PayPal now says was paid after all is finished too, because the money did
    move), (2) one of our open refunds with the same amount, (3) a converted/void request that is being paid twice (CRITICAL),
    (4) a refund made outside our flow.
    """
    with transaction.atomic():
        tx = PaymentTransaction.objects.select_for_update(of=('self',)).select_related('booking').get(pk=tx_pk)
        requests = RefundRequest.objects.select_for_update().filter(payment_transaction=tx)
        known = requests.filter(gateway_reference=refund_id).first()
        if known is not None:
            if known.status in (RefundRequest.Status.SUBMITTED, RefundRequest.Status.FAILED):
                refunds.mark_processed(known.pk, refund_id, via_webhook=True)     # the provider finished it: post the cash leg once
                return 'refund_completed'
            return 'duplicate'
        amount = quantize_money(amount, currency or tx.currency)
        open_states = (RefundRequest.Status.PENDING_GATEWAY, RefundRequest.Status.SUBMITTED, RefundRequest.Status.FAILED)
        ours = [r for r in requests.filter(status__in=open_states).order_by('created_at')
                if r.currency.upper() == currency and quantize_money(r.amount, r.currency) == amount]
        if ours:
            # Only states mark_processed accepts are matched and the rows are locked above, so no RefundStateError is expected here;
            # if one ever happens it propagates (the transaction rolls back and PayPal's retry meets the converted row below).
            refunds.mark_processed(ours[0].pk, refund_id, via_webhook=True)   # idempotent: posts the cash leg once
            return 'refund_completed'
        paid_twice = [r for r in requests.filter(status__in=(RefundRequest.Status.CONVERTED, RefundRequest.Status.VOID))
                      .order_by('created_at') if r.currency.upper() == currency and quantize_money(r.amount, r.currency) == amount]
        if paid_twice:
            # Money moved twice: raise the CRITICAL alert and STOP. Falling through to _external_refund would file a second,
            # blocking anomaly (and could post) for the same money.
            return _refund_after_convert(tx, paid_twice[0], refund_id, amount, currency, event)
        return _external_refund(tx, requests, refund_id, amount, currency, event)


def _refund_after_convert(tx, refund, provider_refund_id: str, amount, currency: str, event: dict) -> str:
    """The student was already given wallet credit (or the payment never cleared) and PayPal paid the money back as well: money moved twice."""
    alert_admin('refund_after_convert', f"CRITICAL: refund {refund.pk} was paid by PayPal after it was {refund.status}",
                f"PayPal refund {provider_refund_id} of {amount} {currency} on capture {tx.gateway_reference} matches refund request "
                f"{refund.pk}, which is already {refund.status} (event {event.get('event_type', 'n/a')}). The student may have been "
                f"paid twice: finance must reverse the wallet credit or recover the money. Nothing was posted automatically.",
                key=str(refund.pk), tx=tx, booking=refund.booking)
    logger.error("[PAYPAL] refund %s paid for request %s that is already %s", provider_refund_id, refund.pk, refund.status)
    return 'refund_after_convert'


def _external_refund(tx, requests, refund_id, amount, currency, event) -> str:
    """A refund we did not ask for (PayPal dashboard). Always a durable anomaly; the ledger is corrected when it is safe."""
    notes = []
    if not tx.booking_id or tx.status != PaymentTransaction.Status.SUCCESS:
        notes.append(f'transaction is {tx.status}' + ('' if tx.booking_id else ' (credit purchase)'))
    elif currency != tx.currency.upper() or amount != quantize_money(tx.amount, tx.currency):
        notes.append(f'partial or foreign-currency refund ({amount} {currency} of {tx.amount} {tx.currency})')
    elif requests.exists():
        notes.append('this payment already has a refund request: possible second refund')
    posted = False
    if not notes:
        try:
            outcome = refunds.request_refund(tx.booking, EXTERNAL_REFUND_REASON,
                                             description='Refund issued directly in the PayPal dashboard')
        except (refunds.AlreadySettled, refunds.MissingFunding) as exc:
            notes.append(str(exc))
        else:
            refunds.mark_processed(outcome.refund.pk, refund_id, via_webhook=True)
            posted = True
    record_anomaly('paypal', refund_id, 'external_refund',
                   f"refund {refund_id} of {amount} {currency} on capture {tx.gateway_reference} was not initiated by "
                   f"the platform. " + ('Ledger reversed automatically.' if posted else 'NOT posted to the ledger: '
                                        + '; '.join(notes) + ' - finance must correct it.'),
                   tx=tx, payload=event)
    logger.warning("[PAYPAL] external refund %s on %s (ledger posted: %s)", refund_id, tx.merchant_reference, posted)
    return 'external_refund'


# ------------------------------------------------------------------------------------------------ chargebacks
def flag_chargeback(tx, *, reference: str, reason: str, detail: str, event: dict) -> None:
    """Durable anomaly + DisputeCase for an admin. Deliberately posts nothing to the ledger and changes no status."""
    with transaction.atomic():
        tx = PaymentTransaction.objects.select_for_update(of=('self',)).select_related('booking__student', 'booking__teacher').get(pk=tx.pk)
        record_anomaly('paypal', reference, reason, detail, tx=tx, payload=event)
        if not tx.booking_id:
            return                                  # a credit-pack purchase: the anomaly is the flag
        booking = tx.booking
        note = f"PayPal {reference}: {detail}"
        case, created = DisputeCase.objects.get_or_create(
            booking=booking,
            defaults={'student': booking.student, 'teacher': booking.teacher, 'status': DisputeCase.Status.OPEN,
                      'student_statement': 'Automated alert: PayPal reports a chargeback / payment dispute on this lesson.',
                      'teacher_statement': 'Funds are untouched until an admin decides.', 'admin_notes': note})
        if not created and note not in case.admin_notes:
            case.admin_notes = f"{case.admin_notes}\n{note}".strip()
            case.save(update_fields=['admin_notes'])


def on_capture_reversed(event: dict) -> str:
    capture_id = _id(_resource(event).get('id'), 'capture id')
    capture = load_capture(capture_id)
    tx = match_transaction(capture)
    if tx is None:
        return quarantine_unmatched(capture_id, capture, event)
    flag_chargeback(tx, reference=capture_id, reason='chargeback_opened',
                    detail=f"capture reversed by PayPal (capture status {capture.get('status')}); a human decides on the money",
                    event=event)
    if tx.status == PaymentTransaction.Status.PENDING_CAPTURE:
        # The money PayPal had not yet guaranteed is now never coming: unwind the (grace) booking exactly like a denial.
        grace.on_failed(tx)
    return 'flagged'


def on_dispute(event: dict) -> str:
    dispute_id = _id(_resource(event).get('dispute_id') or _resource(event).get('id'), 'dispute id')
    dispute = _json_object(paypal.get_dispute(dispute_id), 'dispute')
    tx = None
    first_capture = None
    for item in dispute.get('disputed_transactions') or []:
        seller_txn = item.get('seller_transaction_id') if isinstance(item, dict) else None
        if not isinstance(seller_txn, str) or not seller_txn or len(seller_txn) > MAX_ID_LENGTH:
            continue
        capture = load_capture(seller_txn)
        first_capture = first_capture or capture
        tx = match_transaction(capture)
        if tx is not None:
            break
    if tx is None:
        return quarantine_unmatched(dispute_id, first_capture or {'id': None}, event)
    outcome = (dispute.get('dispute_outcome') or {}).get('outcome_code') if isinstance(dispute.get('dispute_outcome'), dict) else None
    if event.get('event_type') == 'CUSTOMER.DISPUTE.RESOLVED':
        flag_chargeback(tx, reference=dispute_id, reason='chargeback_resolved',
                        detail=f"dispute closed by PayPal, status {dispute.get('status')}, outcome {outcome or 'n/a'}; "
                               f"a human settles the money", event=event)
    else:
        flag_chargeback(tx, reference=dispute_id, reason='chargeback_opened',
                        detail=f"dispute opened, status {dispute.get('status')}, reason {dispute.get('reason')}; "
                               f"a human decides on the money", event=event)
    return 'flagged'


HANDLERS = {
    'PAYMENT.CAPTURE.COMPLETED': on_capture_completed,
    'PAYMENT.CAPTURE.DENIED': on_capture_denied,
    'PAYMENT.CAPTURE.DECLINED': on_capture_denied,
    'PAYMENT.CAPTURE.PENDING': on_capture_pending,
    'PAYMENT.CAPTURE.REFUNDED': on_capture_refunded,
    'PAYMENT.CAPTURE.REVERSED': on_capture_reversed,
    'CUSTOMER.DISPUTE.CREATED': on_dispute,
    'CUSTOMER.DISPUTE.RESOLVED': on_dispute,
}
