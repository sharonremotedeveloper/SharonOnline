import json
import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.bookings.models import Booking
from .gateways import payfast, paypal
from .models import CreditBundle, PaymentTransaction
from .services.webhook_handler import process_payment_webhook

logger = logging.getLogger(__name__)

CENT = Decimal('0.01')


def _bind_gateway_reference(tx: PaymentTransaction, gateway_reference: str, raw_payload: dict):
    """Attach the gateway's own id to our INITIALIZED row so the idempotent handler reuses it."""
    if tx.gateway_reference != gateway_reference:
        if PaymentTransaction.objects.filter(gateway_reference=gateway_reference).exclude(pk=tx.pk).exists():
            return False
        tx.gateway_reference = gateway_reference
    tx.raw_webhook_payload = raw_payload
    tx.save(update_fields=['gateway_reference', 'raw_webhook_payload', 'updated_at'])
    return True


class CheckoutInitializeView(APIView):
    """
    Initializes checkout for PayFast (ZAR) or PayPal (USD). Persists an INITIALIZED transaction holding the
    server-computed expected amount; webhooks are verified against it, never against client/gateway-supplied totals.
    """
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'checkout'

    def post(self, request):
        booking_id = request.data.get('booking_id')
        gateway = request.data.get('gateway', 'paypal')
        if gateway not in ('payfast', 'paypal'):
            return Response({"error": "gateway must be 'payfast' or 'paypal'."}, status=status.HTTP_400_BAD_REQUEST)

        booking = get_object_or_404(Booking, id=booking_id, student=request.user)
        if booking.status != Booking.Status.PENDING_PAYMENT:
            return Response({"error": f"Booking is '{booking.status}' and cannot be paid for."},
                            status=status.HTTP_409_CONFLICT)

        amount_usd = Decimal(str(booking.teacher.price_per_25min_usd)).quantize(CENT, ROUND_HALF_UP)
        reference = f"TX-{uuid.uuid4().hex[:12].upper()}"
        item_name = f"25-Min Lesson with {booking.teacher.user.first_name or booking.teacher.user.username}"

        if gateway == 'payfast':
            if not (settings.PAYFAST_MERCHANT_ID and settings.PAYFAST_MERCHANT_KEY):
                return Response({"error": "PayFast is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            amount = (amount_usd * Decimal(str(settings.ZAR_PER_USD))).quantize(CENT, ROUND_HALF_UP)
            currency = 'ZAR'
        else:
            amount, currency = amount_usd, 'USD'

        PaymentTransaction.objects.create(
            booking=booking, gateway=gateway, gateway_reference=f"INIT-{reference}",
            merchant_reference=reference, amount=amount, currency=currency,
            status=PaymentTransaction.Status.INITIALIZED,
        )

        if gateway == 'payfast':
            return Response({
                "gateway": "payfast",
                "transaction_reference": reference,
                "amount": str(amount),
                "currency": currency,
                "item_name": item_name,
                "action_url": payfast.process_url(),
                "fields": payfast.build_checkout_fields(
                    reference=reference, amount=amount, item_name=item_name,
                    booking_id=str(booking.id), notify_url=settings.PAYFAST_NOTIFY_URL),
            })
        return Response({
            "gateway": "paypal",
            "transaction_reference": reference,
            "amount": str(amount),
            "currency": currency,
            "item_name": item_name,
            "custom_id": reference,  # PayPal echoes this back; webhooks match on it
        })


@method_decorator(csrf_exempt, name='dispatch')
class PayFastWebhookView(APIView):
    """PayFast ITN. Trusted only after signature + source IP + amount match + server postback all pass."""
    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'webhook'

    def _reject(self, reason, **context):
        logger.warning("PayFast ITN rejected: %s %s", reason, context)
        return Response({"error": "invalid_notification"}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        pairs = payfast.parse_itn_body(request._request.body)
        data = dict(pairs)
        if not pairs:
            return self._reject("empty body")
        if not payfast.verify_signature(pairs, settings.PAYFAST_PASSPHRASE):
            return self._reject("bad signature", m_payment_id=data.get('m_payment_id'))
        if not payfast.source_ip_allowed(request._request):
            return self._reject("source ip not allowed", ip=payfast.client_ip(request._request))
        if data.get('merchant_id') != settings.PAYFAST_MERCHANT_ID:
            return self._reject("merchant mismatch")

        reference = data.get('m_payment_id')
        pf_payment_id = data.get('pf_payment_id')
        if not reference or not pf_payment_id:
            return self._reject("missing m_payment_id/pf_payment_id")

        with transaction.atomic():
            tx = (PaymentTransaction.objects.select_for_update()
                  .filter(merchant_reference=reference, gateway=PaymentTransaction.Gateway.PAYFAST).first())
            if tx is None:
                return self._reject("unknown m_payment_id", m_payment_id=reference)
            try:
                gross = Decimal(data.get('amount_gross', ''))
            except Exception:
                return self._reject("unparseable amount_gross")
            if tx.currency != 'ZAR' or gross.quantize(CENT) != tx.amount.quantize(CENT):
                return self._reject("amount mismatch", expected=str(tx.amount), got=str(gross))

            if data.get('payment_status') != 'COMPLETE':
                logger.info("PayFast ITN %s status=%s acknowledged without action", reference, data.get('payment_status'))
                return Response("OK", status=status.HTTP_200_OK)

            if tx.status == PaymentTransaction.Status.SUCCESS:
                return Response("OK", status=status.HTTP_200_OK)  # duplicate delivery

            if not payfast.server_confirms(pairs):
                return self._reject("server postback not VALID", m_payment_id=reference)
            if not _bind_gateway_reference(tx, pf_payment_id, data):
                return self._reject("gateway reference already used", pf_payment_id=pf_payment_id)

            process_payment_webhook(
                booking_id=str(tx.booking_id), gateway=PaymentTransaction.Gateway.PAYFAST,
                transaction_id=pf_payment_id, amount=tx.amount, currency='ZAR',
                status=PaymentTransaction.Status.SUCCESS, raw_payload=data)
        return Response("OK", status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class PayPalWebhookView(APIView):
    """PayPal webhook. Verified via PayPal's signature API, then amounts re-read from PayPal itself."""
    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'webhook'

    def _reject(self, reason, **context):
        logger.warning("PayPal webhook rejected: %s %s", reason, context)
        return Response({"error": "invalid_notification"}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        try:
            event = json.loads(request._request.body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return self._reject("body is not JSON")
        if not isinstance(event, dict):
            return self._reject("body is not an object")

        try:
            if not paypal.verify_webhook_signature(request._request.META, event):
                return self._reject("signature verification failed")
        except paypal.PayPalError as exc:
            logger.error("%s", exc)
            return Response({"error": "verification_unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if event.get('event_type') != 'PAYMENT.CAPTURE.COMPLETED':
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        capture_id = (event.get('resource') or {}).get('id')
        if not capture_id:
            return self._reject("missing capture id")

        try:
            capture = paypal.get_capture(capture_id)
        except paypal.PayPalError as exc:
            logger.error("%s", exc)
            return Response({"error": "lookup_unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        reference = capture.get('custom_id')
        amount_info = capture.get('amount') or {}

        with transaction.atomic():
            tx = (PaymentTransaction.objects.select_for_update()
                  .filter(merchant_reference=reference, gateway=PaymentTransaction.Gateway.PAYPAL).first()
                  if reference else None)
            if tx is None:
                return self._reject("unknown custom_id", custom_id=reference)
            if capture.get('status') != 'COMPLETED':
                return self._reject("capture not COMPLETED", status=capture.get('status'))
            try:
                paid = Decimal(str(amount_info.get('value', '')))
            except Exception:
                return self._reject("unparseable amount")
            if amount_info.get('currency_code') != tx.currency or paid.quantize(CENT) != tx.amount.quantize(CENT):
                return self._reject("amount/currency mismatch", expected=f"{tx.amount} {tx.currency}",
                                    got=f"{paid} {amount_info.get('currency_code')}")
            if tx.status == PaymentTransaction.Status.SUCCESS:
                return Response({"status": "received"}, status=status.HTTP_200_OK)  # duplicate delivery
            if not _bind_gateway_reference(tx, capture_id, event):
                return self._reject("gateway reference already used", capture_id=capture_id)

            process_payment_webhook(
                booking_id=str(tx.booking_id), gateway=PaymentTransaction.Gateway.PAYPAL,
                transaction_id=capture_id, amount=tx.amount, currency=tx.currency,
                status=PaymentTransaction.Status.SUCCESS, raw_payload=event)
        return Response({"status": "received"}, status=status.HTTP_200_OK)


class CreditBalanceView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        bundles = CreditBundle.objects.filter(user=request.user)
        total_available = sum(b.remaining_credits for b in bundles)
        return Response({
            "total_credits": total_available,
            "bundles": [
                {
                    "pack_name": b.pack_name,
                    "remaining": b.remaining_credits,
                    "total": b.total_credits,
                    "purchased_at": b.created_at.isoformat()
                }
                for b in bundles
            ]
        })
