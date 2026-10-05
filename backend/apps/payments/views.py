import json
from apps.common.schema import WalletSerializer
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
import logging
import uuid
from urllib.parse import urlencode
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
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
from apps.users.permissions import IsTeacher
from apps.bookings.services.holds import SLOT_OWNING_STATUSES, hold_expires_at, hold_is_live, inflight_grace, max_hold
from apps.bookings.services.booking_block import booking_block_message
from apps.bookings.services.lock_service import extend_slot_lock
from .gateways import payfast, paypal
from .services import grace
from .models import BookingFunding, FxRate, LessonPrice, CreditBundle, CreditPack, CreditPurchase, CreditWalletEntry, GatewayAnomaly, PaymentTransaction, TutorPayoutAccount
from .serializers import (
    PayoutAccountMaskedSerializer, PayoutAccountWriteSerializer, TutorWalletSerializer, masked_payout_account,
)
from .services.anomalies import record_anomaly
from .services.paypal_capture import (
    CaptureRejected, record_failed_capture, record_pending_capture, settle_completed_capture, verify_capture_amount,
)
from .services import paypal_events
from .services.paypal_orders import create_checkout_order
from .services.fx import FxRateStale, FxRateUnavailable, current_rate, fx_source_label
from .services.pricing import CURRENCY_EXPONENT, PriceNotConfigured, lesson_price, quantize_money
from .services.payout_crypto import PayoutDataError
from .throttles import WritesOnlyScopedThrottle
from .services.tutor_wallet import tutor_wallet_payload
from .services.webhook_handler import process_payment_webhook, record_unallocated_payment

logger = logging.getLogger(__name__)

CENT = Decimal('0.01')


SETTLED_STATES = (PaymentTransaction.Status.SUCCESS, PaymentTransaction.Status.UNALLOCATED)


def _with_ref(url: str, reference: str) -> str:
    """Append the opaque TX- reference (never a token or internal id) to a buyer-redirect URL."""
    if not url:
        return ''
    return f"{url}{'&' if '?' in url else '?'}{urlencode({'ref': reference})}"


_anomaly = record_anomaly


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
        tx_fx = {}
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
            if gateway == 'payfast':
                currency = 'ZAR'
            else:
                currency = str(request.data.get('currency') or 'USD').upper()
                if currency not in {'USD', 'EUR', 'JPY'}:
                    return Response({"error": "PayPal lesson currency must be USD, EUR, or JPY."},
                                    status=status.HTTP_400_BAD_REQUEST)
            try:
                amount = lesson_price(currency)
            except PriceNotConfigured:
                return Response({"error": "Lesson price is not configured."}, status=status.HTTP_409_CONFLICT)
            if currency in FxRate.SUPPORTED:
                try:
                    fx_row = current_rate(currency)
                except (FxRateUnavailable, FxRateStale) as exc:
                    return Response({"error": f"{currency} payments are temporarily unavailable: {exc}"},
                                    status=status.HTTP_503_SERVICE_UNAVAILABLE)
                tx_fx = {'fx_rate_to_zar': fx_row.rate_to_zar, 'fx_source': fx_source_label(fx_row)}
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

        if gateway == 'paypal' and not (settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET):
            if purchase:
                purchase.delete()
            return Response({"error": "PayPal is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        tx = PaymentTransaction.objects.create(
            booking=booking, credit_purchase=purchase, gateway=gateway, gateway_reference=f"INIT-{reference}",
            merchant_reference=reference, amount=amount, currency=currency, **tx_fx,
            status=PaymentTransaction.Status.INITIALIZED,
        )
        order_id = None
        if gateway == 'paypal':
            try:
                order_id = create_checkout_order(tx, item_name)
            except paypal.PayPalError as exc:
                logger.error("PayPal order creation failed for %s: %s", reference, exc)
                tx.delete()
                if purchase:
                    purchase.delete()
                return Response({"error": "PayPal is temporarily unavailable. Please try again."},
                                status=status.HTTP_502_BAD_GATEWAY)
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
                    booking_id=target_id, notify_url=settings.PAYFAST_NOTIFY_URL,
                    return_url=_with_ref(settings.PAYFAST_RETURN_URL, reference),
                    cancel_url=_with_ref(settings.PAYFAST_CANCEL_URL, reference)),
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
            "order_id": order_id,
        })

    @staticmethod
    def _validate_booking(booking):
        blocked = booking_block_message(booking.student)
        if blocked:
            return Response({"error": blocked, "code": "booking_blocked"}, status=409)
        if booking.status != Booking.Status.PENDING_PAYMENT:
            return Response({"error": f"Booking is '{booking.status}' and cannot be paid for."}, status=409)
        if not booking.teacher.is_bookable:
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

    def _fail_initialized(self, tx, pairs, data):
        """CANCELLED / FAILED: the buyer did not pay. Only a still-INITIALIZED transaction may be failed, never a settled one."""
        if tx.status != PaymentTransaction.Status.INITIALIZED:
            return Response("OK", status=status.HTTP_200_OK)
        if not payfast.server_confirms(pairs):               # network call, outside any row lock
            return self._reject("server postback not VALID", m_payment_id=tx.merchant_reference)
        with transaction.atomic():
            tx = PaymentTransaction.objects.select_for_update().get(pk=tx.pk)
            if tx.status == PaymentTransaction.Status.INITIALIZED:
                tx.status = PaymentTransaction.Status.FAILED
                tx.raw_webhook_payload = data
                tx.save(update_fields=['status', 'raw_webhook_payload', 'updated_at'])
                if tx.credit_purchase_id:
                    CreditPurchase.objects.filter(pk=tx.credit_purchase_id, status=CreditPurchase.Status.INITIALIZED).update(
                        status=CreditPurchase.Status.FAILED)
        logger.info("PayFast ITN %s status=%s: transaction marked failed", tx.merchant_reference, data.get('payment_status'))
        return Response("OK", status=status.HTTP_200_OK)

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
        if len(reference) > 255 or len(pf_payment_id) > 255:
            return self._reject("oversized m_payment_id/pf_payment_id")
        payment_status = data.get('payment_status')

        # Phase 1 - read-only checks, no row lock held.
        tx = (PaymentTransaction.objects.select_related('booking', 'credit_purchase__pack')
              .filter(merchant_reference=reference, gateway=PaymentTransaction.Gateway.PAYFAST).first())
        if tx is None:
            # Authenticated (signature + IP + merchant) but ours to nobody: quarantine for a human and acknowledge, so
            # PayFast stops retrying a notification we can never apply.
            if payment_status == 'COMPLETE':
                _anomaly('payfast', reference, 'unknown_reference', f"pf_payment_id={pf_payment_id}", payload=data)
            logger.error("PayFast ITN %s (%s) matches no transaction: quarantined", reference, payment_status)
            return Response("OK", status=status.HTTP_200_OK)
        try:
            gross = Decimal(data.get('amount_gross', ''))
        except Exception:
            return self._reject("unparseable amount_gross")
        if tx.currency != 'ZAR' or gross.quantize(CENT) != tx.amount.quantize(CENT):
            _anomaly('payfast', reference, 'amount_mismatch',
                     f"expected {tx.amount} {tx.currency}, gateway says {gross}", tx=tx, payload=data)
            return self._reject("amount mismatch", expected=str(tx.amount), got=str(gross))

        if payment_status in ('CANCELLED', 'FAILED'):
            return self._fail_initialized(tx, pairs, data)
        if payment_status != 'COMPLETE':
            known = payment_status == 'PENDING'
            (logger.info if known else logger.warning)(
                "PayFast ITN %s status=%s acknowledged without action%s", reference, payment_status,
                '' if known else ' (UNKNOWN status)')
            return Response("OK", status=status.HTTP_200_OK)

        if tx.status in SETTLED_STATES and tx.gateway_reference == pf_payment_id:
            return Response("OK", status=status.HTTP_200_OK)  # duplicate delivery of an already-processed ITN

        # Server-to-server postback happens OUTSIDE the transaction/row lock (it is a 10s network call).
        if not payfast.server_confirms(pairs):
            return self._reject("server postback not VALID", m_payment_id=reference)

        # Phase 2 - lock and apply; re-check state because it may have changed during the postback.
        with transaction.atomic():
            tx = PaymentTransaction.objects.select_for_update(of=('self',)).select_related('booking').get(pk=tx.pk)
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

        handler = paypal_events.HANDLERS.get(event.get('event_type'))
        if handler is None:
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)
        try:
            result = handler(event)
        except CaptureRejected as exc:
            return self._reject(exc.reason.replace('_', ' '), **exc.context)
        except paypal.PayPalError as exc:
            logger.error("%s", exc)
            return Response({"error": "lookup_unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": result if result in ('ignored', 'quarantined') else 'received'}, status=status.HTTP_200_OK)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
class PayPalCaptureView(APIView):
    """
    Capture an approved PayPal order. The browser only says "this order was approved"; the amount, currency and status
    are read from PayPal's own response and verified against the transaction we created, then applied through the same
    locked, idempotent path the webhook uses (PAYPAL_CAPTURE_CONFIRMS=False leaves confirmation to the webhook).
    """
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'checkout'
    GRACE_MESSAGE = ('PayPal is still verifying this payment. Your lesson is booked. '
                     'If the payment cannot be completed we will contact you.')

    @staticmethod
    def _is_grace_confirmed(tx):
        return bool(tx.booking_id) and BookingFunding.objects.filter(
            payment_transaction=tx, source_type=BookingFunding.SourceType.GATEWAY_PENDING,
            booking__status=Booking.Status.CONFIRMED).exists()

    @staticmethod
    def _reply(outcome, tx, message='', retryable=False, http=status.HTTP_200_OK):
        return Response({
            'outcome': outcome,
            'booking_id': str(tx.booking_id) if tx.booking_id else None,
            'credit_purchase_id': str(tx.credit_purchase_id) if tx.credit_purchase_id else None,
            'message': message, 'retryable': retryable,
        }, status=http)

    def post(self, request):
        order_id = request.data.get('order_id') if isinstance(request.data, dict) else None
        if not order_id or not isinstance(order_id, str):
            return Response({"error": "order_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        tx = (PaymentTransaction.objects.select_related('booking', 'credit_purchase')
              .filter(gateway=PaymentTransaction.Gateway.PAYPAL, gateway_order_id=order_id).first())
        owner_id = None
        if tx is not None:
            owner_id = tx.booking.student_id if tx.booking_id else tx.credit_purchase.user_id
        if tx is None or owner_id != request.user.id:
            return Response({"error": "Unknown order."}, status=status.HTTP_404_NOT_FOUND)

        # Replays never call PayPal again.
        if tx.status == PaymentTransaction.Status.SUCCESS:
            return self._settled_reply(tx)
        if tx.status == PaymentTransaction.Status.PENDING_CAPTURE:
            if self._is_grace_confirmed(tx):
                return self._reply('pending_confirmed', tx, self.GRACE_MESSAGE)
            return self._reply('pending', tx, 'PayPal is still verifying this payment.')
        if tx.status in (PaymentTransaction.Status.FAILED, PaymentTransaction.Status.REFUNDED,
                         PaymentTransaction.Status.UNALLOCATED):
            return self._reply('failed', tx, 'This payment cannot be completed.', http=status.HTTP_200_OK)

        if tx.booking_id:
            invalid = self._validate_still_payable(tx.booking)
            if invalid:
                return invalid

        try:
            order = paypal.capture_order(order_id, request_id=f'capture-{tx.merchant_reference}-{uuid.uuid4().hex[:12]}')
        except paypal.PayPalDeclined:
            return self._reply('declined', tx, 'PayPal declined this payment method. Please choose another.', retryable=True)
        except paypal.PayPalRejected as exc:
            logger.warning("PayPal refused capture of %s: %s %s", order_id, exc.name, exc.issue)
            return self._reply('failed', tx, 'PayPal could not capture this order.', http=status.HTTP_409_CONFLICT)
        except paypal.PayPalError as exc:
            logger.error("PayPal capture unavailable for %s: %s", order_id, exc)
            return self._reply('pending', tx, 'PayPal is not responding. Please try again in a moment.', retryable=True,
                               http=status.HTTP_503_SERVICE_UNAVAILABLE)

        capture = paypal.extract_capture(order)
        if capture is None:
            logger.error("PayPal capture response for %s had no capture object", order_id)
            return self._reply('pending', tx, 'PayPal returned an unexpected response.', retryable=True,
                               http=status.HTTP_502_BAD_GATEWAY)
        if capture.get('custom_id') != tx.merchant_reference:
            _anomaly('paypal', capture.get('id'), 'capture_reference_mismatch',
                     f"order {order_id}: custom_id {capture.get('custom_id')} != {tx.merchant_reference}",
                     tx=tx, payload=order)
            return self._reply('failed', tx, 'This capture does not belong to this checkout.', http=status.HTTP_409_CONFLICT)

        outcome = paypal.classify_capture(capture)
        if outcome.state in ('declined', 'failed'):
            record_failed_capture(tx.pk)
            return self._reply('failed', tx, 'PayPal could not complete this payment.')
        try:
            verify_capture_amount(tx, capture, payload=order)
        except CaptureRejected:
            return self._reply('failed', tx, 'The captured amount did not match this checkout.',
                               http=status.HTTP_422_UNPROCESSABLE_ENTITY)

        if outcome.state == 'pending':
            record_pending_capture(tx.pk, capture, outcome, order)
            tx.refresh_from_db()
            # Grace booking (plan P-1): confirm the lesson now if policy allows; the money is awaited, nothing is posted yet.
            if grace.handle_pending_capture(tx, outcome).allowed:
                return self._reply('pending_confirmed', tx, self.GRACE_MESSAGE)
            return self._reply('pending', tx, 'PayPal is still verifying this payment.')
        if not settings.PAYPAL_CAPTURE_CONFIRMS:
            return self._reply('pending', tx, 'Payment received; confirming shortly.')
        try:
            settle_completed_capture(tx.pk, capture, payload=order)
        except CaptureRejected:
            return self._reply('failed', tx, 'This capture was already used.', http=status.HTTP_409_CONFLICT)
        tx.refresh_from_db()
        return self._settled_reply(tx)

    def _settled_reply(self, tx):
        """
        Settling can end in 'confirmed' OR in a quarantine (DEF-501: the slot was taken, booking DISPUTED with a credit;
        or surplus money held as UNALLOCATED). The student is only ever told 'confirmed' for a lesson they really have.
        """
        tx.refresh_from_db()
        if tx.status == PaymentTransaction.Status.SUCCESS and tx.booking_id:
            booking = Booking.objects.get(pk=tx.booking_id)
            if booking.status == Booking.Status.DISPUTED:
                return self._reply('failed', tx, 'Your payment was received, but this lesson time is no longer available. '
                                                 'We have added 1 lesson credit to your account.')
        elif tx.status != PaymentTransaction.Status.SUCCESS:
            return self._reply('failed', tx, 'Your payment was received but could not be applied to this booking. '
                                             'Our team will refund it and contact you by e-mail.')
        return self._reply('confirmed', tx)

    @staticmethod
    def _validate_still_payable(booking):
        booking.refresh_from_db()
        if booking.status != Booking.Status.PENDING_PAYMENT or not hold_is_live(booking, timezone.now()):
            return Response({"error": "This booking can no longer be paid for. Please book a new time.",
                             "outcome": "failed", "retryable": False}, status=status.HTTP_409_CONFLICT)
        return None


@extend_schema(responses=WalletSerializer)
class CreditBalanceView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        bundles = CreditBundle.objects.filter(user=request.user).order_by('created_at', 'id')
        history = CreditWalletEntry.objects.filter(user=request.user).select_related('bundle')
        total_available = sum(b.remaining_credits for b in bundles.active())      # expired lots are not spendable
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
                    "purchased_at": b.created_at.isoformat(),
                    "expires_at": b.expires_at.isoformat() if b.expires_at else None,
                }
                for b in bundles.active().filter(remaining_credits__gt=0)
            ]
        })


@extend_schema(responses=OpenApiTypes.OBJECT)
class LessonPriceListView(APIView):
    """Public: the platform's flat price for one 25-minute lesson per currency (D-1), amounts as exact strings."""
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        return Response([
            {'currency': row.currency, 'amount': str(quantize_money(row.amount, row.currency)),
             'decimals': CURRENCY_EXPONENT[row.currency]}
            for row in LessonPrice.objects.filter(is_active=True)
        ])


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


@extend_schema(responses=TutorWalletSerializer)
class TutorWalletView(APIView):
    permission_classes = (IsTeacher,)

    def get(self, request):
        payload = tutor_wallet_payload(request.user)
        account = TutorPayoutAccount.objects.filter(tutor=request.user).first()
        try:
            payload['payout_bank_account'] = masked_payout_account(account) if account else None
        except (PayoutDataError, ImproperlyConfigured):
            logger.exception('Tutor payout account could not be read for user_id=%s', request.user.id)
            return Response({'code': 'payout_settings_unavailable'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(payload)


@extend_schema(
    request=PayoutAccountWriteSerializer,
    responses={200: PayoutAccountMaskedSerializer, 201: PayoutAccountMaskedSerializer},
)
class PayoutSettingsView(APIView):
    permission_classes = (IsTeacher,)
    throttle_classes = (WritesOnlyScopedThrottle,)
    throttle_scope = 'payout_settings'      # 5 changes / hour: every change re-checks the password

    def get(self, request):
        account = TutorPayoutAccount.objects.filter(tutor=request.user).first()
        try:
            return Response(masked_payout_account(account))
        except (PayoutDataError, ImproperlyConfigured):
            logger.exception('Tutor payout account could not be read for user_id=%s', request.user.id)
            return Response({'code': 'payout_settings_unavailable'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    def post(self, request):
        return self._save(request)

    def patch(self, request):
        return self._save(request)

    def _save(self, request):
        serializer = PayoutAccountWriteSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        existed = TutorPayoutAccount.objects.filter(tutor=request.user).exists()
        try:
            account = serializer.save()
        except ImproperlyConfigured:
            logger.exception('Payout encryption is not configured for user_id=%s', request.user.id)
            return Response({'code': 'payout_encryption_unavailable'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(masked_payout_account(account), status=status.HTTP_200_OK if existed else status.HTTP_201_CREATED)
