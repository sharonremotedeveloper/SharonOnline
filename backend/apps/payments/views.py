import json
from apps.common.schema import WalletSerializer
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
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

from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services.holds import SLOT_OWNING_STATUSES, hold_expires_at, hold_is_live, inflight_grace, max_hold
from apps.bookings.services.lock_service import extend_slot_lock
from .gateways import payfast, paypal
from .models import CreditBundle, CreditPack, CreditPurchase, CreditWalletEntry, GatewayAnomaly, PaymentTransaction
from .services.webhook_handler import process_payment_webhook, record_unallocated_payment

logger = logging.getLogger(__name__)

CENT = Decimal('0.01')


SETTLED_STATES = (PaymentTransaction.Status.SUCCESS, PaymentTransaction.Status.UNALLOCATED)


def _anomaly(gateway, reference, reason, detail='', tx=None, payload=None):
    """
    Persist an authenticated-but-unappliable notification (money may have moved). Only call AFTER signature/IP checks
    so unauthenticated callers cannot fill the table. De-duplicated so gateway retries don't multiply rows.
    """
    GatewayAnomaly.objects.get_or_create(
        gateway=gateway, reference=str(reference or '')[:255], reason=reason, resolved=False,
        defaults={'detail': detail, 'payload': payload or {}, 'payment_transaction': tx,
                  'booking': tx.booking if tx is not None and tx.booking_id else None})


def _bind_gateway_reference(tx: PaymentTransaction, gateway_reference: str, raw_payload: dict):
    """Attach the gateway's own id to our INITIALIZED row so the idempotent handler reuses it."""
    if tx.gateway_reference != gateway_reference:
        if PaymentTransaction.objects.filter(gateway_reference=gateway_reference).exclude(pk=tx.pk).exists():
            return False
        tx.gateway_reference = gateway_reference
    tx.raw_webhook_payload = raw_payload
    tx.save(update_fields=['gateway_reference', 'raw_webhook_payload', 'updated_at'])
    return True


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class CheckoutInitializeView(APIView):
    """
    Initializes checkout for PayFast (ZAR) or PayPal (USD). Persists an INITIALIZED transaction holding the
    server-computed expected amount; webhooks are verified against it, never against client/gateway-supplied totals.
    """
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'checkout'

    def post(self, request):
        if not isinstance(request.data, dict):
            return Response({"error": "JSON object expected."}, status=status.HTTP_400_BAD_REQUEST)
        gateway = request.data.get('gateway', 'paypal')
        if gateway not in ('payfast', 'paypal'):
            return Response({"error": "gateway must be 'payfast' or 'paypal'."}, status=status.HTTP_400_BAD_REQUEST)
        reference = f"TX-{uuid.uuid4().hex[:12].upper()}"
        booking_raw = request.data.get('booking_id')
        pack_raw = request.data.get('credit_pack_id')
        if bool(booking_raw) == bool(pack_raw):
            return Response({"error": "Provide exactly one of booking_id or credit_pack_id."},
                            status=status.HTTP_400_BAD_REQUEST)

        booking = None
        purchase = None
        if booking_raw:
            try:
                booking_id = uuid.UUID(str(booking_raw))
            except ValueError:
                return Response({"error": "booking_id must be a valid UUID."}, status=status.HTTP_400_BAD_REQUEST)
            booking = get_object_or_404(
                Booking.objects.select_related('teacher__user'), id=booking_id, student=request.user)
            invalid = self._validate_booking(booking)
            if invalid:
                return invalid
            amount_usd = Decimal(str(booking.teacher.price_per_25min_usd)).quantize(CENT, ROUND_HALF_UP)
            if amount_usd <= 0:
                return Response({"error": "Lesson price is not configured."}, status=status.HTTP_409_CONFLICT)
            if gateway == 'payfast':
                amount = (amount_usd * Decimal(str(settings.ZAR_PER_USD))).quantize(CENT, ROUND_HALF_UP)
                currency = 'ZAR'
            else:
                amount, currency = amount_usd, 'USD'
            item_name = f"25-Min Lesson with {booking.teacher.user.first_name or booking.teacher.user.username}"
            target_id = str(booking.id)
        else:
            try:
                pack_id = int(pack_raw)
            except (TypeError, ValueError):
                return Response({"error": "credit_pack_id must be a valid integer."}, status=status.HTTP_400_BAD_REQUEST)
            pack = get_object_or_404(CreditPack, pk=pack_id, is_active=True)
            currency = ('ZAR' if gateway == 'payfast' else str(request.data.get('currency', 'USD')).upper())
            if gateway == 'paypal' and currency not in {'USD', 'EUR', 'JPY'}:
                return Response({"error": "PayPal pack currency must be USD, EUR, or JPY."},
                                status=status.HTTP_400_BAD_REQUEST)
            amount = pack.price_for(currency).quantize(CENT, ROUND_HALF_UP)
            fx_rate = (pack.price_zar / amount).quantize(Decimal('0.000001'))
            purchase = CreditPurchase.objects.create(
                user=request.user, pack=pack, amount=amount, currency=currency,
                fx_rate_to_zar=fx_rate, fx_source='credit_catalog',
            )
            item_name = f'{pack.name} - {pack.credits} lesson credits'
            target_id = str(purchase.id)

        if gateway == 'payfast' and not (settings.PAYFAST_MERCHANT_ID and settings.PAYFAST_MERCHANT_KEY):
            if purchase:
                purchase.delete()
            return Response({"error": "PayFast is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        tx = PaymentTransaction.objects.create(
            booking=booking, credit_purchase=purchase, gateway=gateway, gateway_reference=f"INIT-{reference}",
            merchant_reference=reference, amount=amount, currency=currency,
            status=PaymentTransaction.Status.INITIALIZED,
        )
        hold_until = hold_expires_at(booking).isoformat() if booking else None
        if gateway == 'payfast':
            return Response({
                "gateway": "payfast",
                "hold_expires_at": hold_until,
                "target_type": "booking" if booking else "credit_purchase",
                "target_id": target_id,
                "transaction_reference": reference,
                "amount": str(amount),
                "currency": currency,
                "item_name": item_name,
                "action_url": payfast.process_url(),
                "fields": payfast.build_checkout_fields(
                    reference=reference, amount=amount, item_name=item_name,
                    booking_id=target_id, notify_url=settings.PAYFAST_NOTIFY_URL),
            })
        return Response({
            "gateway": "paypal",
            "hold_expires_at": hold_until,
            "target_type": "booking" if booking else "credit_purchase",
            "target_id": target_id,
            "transaction_reference": reference,
            "amount": str(amount),
            "currency": currency,
            "item_name": item_name,
            "custom_id": reference,  # PayPal echoes this back; webhooks match on it
        })

    @staticmethod
    def _validate_booking(booking):
        if booking.status != Booking.Status.PENDING_PAYMENT:
            return Response({"error": f"Booking is '{booking.status}' and cannot be paid for."}, status=409)
        if not (booking.teacher.is_active and booking.teacher.is_verified):
            return Response({"error": "This tutor is not currently bookable."}, status=409)
        now = timezone.now()
        if booking.start_time_utc <= now:
            return Response({"error": "This lesson slot has already started."}, status=409)
        if not hold_is_live(booking, now):
            return Response({"error": "This reservation has expired. Please choose the time slot again."}, status=409)
        if Booking.objects.filter(
            teacher=booking.teacher, start_time_utc=booking.start_time_utc,
            status__in=SLOT_OWNING_STATUSES,
        ).exclude(id=booking.id).exists():
            return Response({"error": "This time slot has just been booked by someone else."}, status=409)
        grace = int(inflight_grace().total_seconds())
        remaining_cap = int((booking.created_at + max_hold() - now).total_seconds())
        if not extend_slot_lock(
            str(booking.teacher_id), booking.start_time_utc.isoformat(), str(booking.student_id),
            max(1, min(grace, remaining_cap)), token=booking.slot_lock_token or None,
        ):
            return Response({"error": "This time slot has just been taken. Please choose another."}, status=409)
        return None


@method_decorator(csrf_exempt, name='dispatch')
@extend_schema(exclude=True)  # machine-to-machine webhook, not part of the client API
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

        # Phase 1 - read-only checks, no row lock held.
        tx = (PaymentTransaction.objects.select_related('booking', 'credit_purchase__pack')
              .filter(merchant_reference=reference, gateway=PaymentTransaction.Gateway.PAYFAST).first())
        if tx is None:
            _anomaly('payfast', reference, 'unknown_reference', f"pf_payment_id={pf_payment_id}", payload=data)
            return self._reject("unknown m_payment_id", m_payment_id=reference)
        try:
            gross = Decimal(data.get('amount_gross', ''))
        except Exception:
            return self._reject("unparseable amount_gross")
        if tx.currency != 'ZAR' or gross.quantize(CENT) != tx.amount.quantize(CENT):
            _anomaly('payfast', reference, 'amount_mismatch',
                     f"expected {tx.amount} {tx.currency}, gateway says {gross}", tx=tx, payload=data)
            return self._reject("amount mismatch", expected=str(tx.amount), got=str(gross))

        if data.get('payment_status') != 'COMPLETE':
            logger.info("PayFast ITN %s status=%s acknowledged without action", reference, data.get('payment_status'))
            return Response("OK", status=status.HTTP_200_OK)

        if tx.status in SETTLED_STATES and tx.gateway_reference == pf_payment_id:
            return Response("OK", status=status.HTTP_200_OK)  # duplicate delivery of an already-processed ITN

        # Server-to-server postback happens OUTSIDE the transaction/row lock (it is a 10s network call).
        if not payfast.server_confirms(pairs):
            return self._reject("server postback not VALID", m_payment_id=reference)

        # Phase 2 - lock and apply; re-check state because it may have changed during the postback.
        with transaction.atomic():
            tx = PaymentTransaction.objects.select_for_update().select_related('booking').get(pk=tx.pk)
            if tx.status in SETTLED_STATES:
                if tx.gateway_reference == pf_payment_id:
                    return Response("OK", status=status.HTTP_200_OK)
                if tx.credit_purchase_id:
                    _anomaly('payfast', pf_payment_id, 'duplicate_credit_purchase_capture',
                             f'purchase {tx.credit_purchase_id} already settled by {tx.gateway_reference}', tx=tx, payload=data)
                    return Response("OK", status=status.HTTP_200_OK)
                # A DIFFERENT PayFast payment against an already-settled m_payment_id (e.g. the signed form paid twice):
                # real money was taken, so hold it for refund instead of silently dropping it.
                record_unallocated_payment(
                    booking=tx.booking, gateway=PaymentTransaction.Gateway.PAYFAST, transaction_id=pf_payment_id,
                    amount=tx.amount, currency='ZAR', raw_payload=data, reason='duplicate_payment',
                    detail=f"m_payment_id {reference} already settled by {tx.gateway_reference}")
                return Response("OK", status=status.HTTP_200_OK)
            if not _bind_gateway_reference(tx, pf_payment_id, data):
                _anomaly('payfast', pf_payment_id, 'gateway_reference_reused', f"m_payment_id={reference}", tx=tx, payload=data)
                return self._reject("gateway reference already used", pf_payment_id=pf_payment_id)

            process_payment_webhook(
                booking_id=str(tx.booking_id) if tx.booking_id else None,
                credit_purchase_id=str(tx.credit_purchase_id) if tx.credit_purchase_id else None,
                gateway=PaymentTransaction.Gateway.PAYFAST,
                transaction_id=pf_payment_id, amount=tx.amount, currency='ZAR',
                status=PaymentTransaction.Status.SUCCESS, raw_payload=data,
                provider_fee_amount=data.get('amount_fee'), provider_fee_currency='ZAR')
        return Response("OK", status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
@extend_schema(exclude=True)  # machine-to-machine webhook, not part of the client API
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
        raw_body = request._request.body
        try:
            event = json.loads(raw_body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return self._reject("body is not JSON")
        if not isinstance(event, dict):
            return self._reject("body is not an object")

        try:
            if not paypal.verify_webhook_signature(request._request.META, raw_body):
                return self._reject("signature verification failed")
        except paypal.PayPalError as exc:
            logger.error("%s", exc)
            return Response({"error": "verification_unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if event.get('event_type') != 'PAYMENT.CAPTURE.COMPLETED':
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        capture_id = (event.get('resource') or {}).get('id')
        if not capture_id or not isinstance(capture_id, str):
            return self._reject("missing capture id")

        try:
            capture = paypal.get_capture(capture_id)
        except paypal.PayPalError as exc:
            logger.error("%s", exc)
            return Response({"error": "lookup_unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        reference = capture.get('custom_id')
        amount_info = capture.get('amount') or {}

        tx = (PaymentTransaction.objects.select_related('booking', 'credit_purchase__pack')
              .filter(merchant_reference=reference, gateway=PaymentTransaction.Gateway.PAYPAL).first()
              if reference else None)
        if tx is None:
            _anomaly('paypal', capture_id, 'unknown_reference', f"custom_id={reference}", payload=event)
            return self._reject("unknown custom_id", custom_id=reference)
        if capture.get('status') != 'COMPLETED':
            return self._reject("capture not COMPLETED", status=capture.get('status'))
        try:
            paid = Decimal(str(amount_info.get('value', '')))
        except Exception:
            return self._reject("unparseable amount")
        if amount_info.get('currency_code') != tx.currency or paid.quantize(CENT) != tx.amount.quantize(CENT):
            _anomaly('paypal', capture_id, 'amount_mismatch',
                     f"expected {tx.amount} {tx.currency}, PayPal says {paid} {amount_info.get('currency_code')}",
                     tx=tx, payload=event)
            return self._reject("amount/currency mismatch", expected=f"{tx.amount} {tx.currency}",
                                got=f"{paid} {amount_info.get('currency_code')}")

        with transaction.atomic():
            tx = PaymentTransaction.objects.select_for_update().select_related('booking').get(pk=tx.pk)
            if tx.status in SETTLED_STATES:
                if tx.gateway_reference == capture_id:
                    return Response({"status": "received"}, status=status.HTTP_200_OK)  # duplicate delivery
                if tx.credit_purchase_id:
                    _anomaly('paypal', capture_id, 'duplicate_credit_purchase_capture',
                             f'purchase {tx.credit_purchase_id} already settled by {tx.gateway_reference}', tx=tx, payload=event)
                    return Response({"status": "received"}, status=status.HTTP_200_OK)
                # A DIFFERENT capture against an already-settled order reference: hold for refund, never drop silently.
                record_unallocated_payment(
                    booking=tx.booking, gateway=PaymentTransaction.Gateway.PAYPAL, transaction_id=capture_id,
                    amount=tx.amount, currency=tx.currency, raw_payload=event, reason='duplicate_payment',
                    detail=f"custom_id {reference} already settled by {tx.gateway_reference}")
                return Response({"status": "received"}, status=status.HTTP_200_OK)
            if not _bind_gateway_reference(tx, capture_id, event):
                _anomaly('paypal', capture_id, 'gateway_reference_reused', f"custom_id={reference}", tx=tx, payload=event)
                return self._reject("gateway reference already used", capture_id=capture_id)

            process_payment_webhook(
                booking_id=str(tx.booking_id) if tx.booking_id else None,
                credit_purchase_id=str(tx.credit_purchase_id) if tx.credit_purchase_id else None,
                gateway=PaymentTransaction.Gateway.PAYPAL,
                transaction_id=capture_id, amount=tx.amount, currency=tx.currency,
                status=PaymentTransaction.Status.SUCCESS, raw_payload=event,
                provider_fee_amount=((capture.get('seller_receivable_breakdown') or {}).get('paypal_fee') or {}).get('value'),
                provider_fee_currency=((capture.get('seller_receivable_breakdown') or {}).get('paypal_fee') or {}).get('currency_code', ''))
        return Response({"status": "received"}, status=status.HTTP_200_OK)


@extend_schema(responses=WalletSerializer)
class CreditBalanceView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        bundles = CreditBundle.objects.filter(user=request.user).order_by('created_at', 'id')
        history = CreditWalletEntry.objects.filter(user=request.user).select_related('bundle')
        total_available = sum(b.remaining_credits for b in bundles)
        ledger = [
            {
                'id': str(entry.id),
                'description': entry.description,
                'credits_delta': entry.credit_delta,
                'date': entry.created_at.date().isoformat(),
                'type': entry.entry_type,
            }
            for entry in history
        ]
        # Raw bundles created by old tests/imports have no immutable rows; deployed legacy rows are backfilled by 0008.
        recorded_bundle_ids = {entry.bundle_id for entry in history}
        ledger.extend(
            {
                'id': str(bundle.id),
                'description': f'Legacy opening balance: {bundle.pack_name}',
                'credits_delta': bundle.remaining_credits,
                'date': bundle.created_at.date().isoformat(),
                'type': 'opening',
            }
            for bundle in bundles if bundle.id not in recorded_bundle_ids
        )
        return Response({
            "total_credits": total_available,
            "ledger": ledger,
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


@extend_schema(responses=OpenApiTypes.OBJECT)
class CreditPackListView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        return Response([
            {
                'id': pack.id,
                'code': pack.code,
                'name': pack.name,
                'credits': pack.credits,
                'prices': {
                    'USD': str(pack.price_usd), 'ZAR': str(pack.price_zar),
                    'EUR': str(pack.price_eur), 'JPY': str(pack.price_jpy),
                },
            }
            for pack in CreditPack.objects.filter(is_active=True)
        ])


@extend_schema(responses=OpenApiTypes.OBJECT)
class CreditPurchaseStatusView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, purchase_id):
        purchase = get_object_or_404(
            CreditPurchase.objects.select_related('pack'), pk=purchase_id, user=request.user)
        return Response({
            'id': str(purchase.id),
            'status': purchase.status,
            'pack': {'id': purchase.pack_id, 'name': purchase.pack.name, 'credits': purchase.pack.credits},
            'amount': str(purchase.amount),
            'currency': purchase.currency,
            'created_at': purchase.created_at.isoformat(),
        })
