from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from apps.bookings.models import Booking
from .models import PaymentTransaction, CreditBundle
from .services.webhook_handler import process_payment_webhook
import uuid

class CheckoutInitializeView(APIView):
    """
    Initializes checkout parameters for either PayFast (ZAR) or PayPal (USD/EUR/JPY).
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        booking_id = request.data.get('booking_id')
        gateway = request.data.get('gateway', 'paypal')

        booking = get_object_or_404(Booking, id=booking_id, student=request.user)

        # Base pricing
        amount_usd = float(booking.teacher.price_per_25min_usd)
        # Approximate exchange rate for South Africa PayFast checkout
        amount_zar = round(amount_usd * 18.0, 2)

        transaction_reference = f"TX-{uuid.uuid4().hex[:12].upper()}"

        if gateway == 'payfast':
            return Response({
                "gateway": "payfast",
                "transaction_reference": transaction_reference,
                "amount": amount_zar,
                "currency": "ZAR",
                "item_name": f"25-Min Lesson with {booking.teacher.user.first_name or booking.teacher.user.username}",
                "custom_str1": str(booking.id),
                "merchant_id": "10000100", # Dev sandbox ID
                "action_url": "https://sandbox.payfast.co.za/eng/process"
            })
        else:
            return Response({
                "gateway": "paypal",
                "transaction_reference": transaction_reference,
                "amount": amount_usd,
                "currency": "USD",
                "item_name": f"25-Min Lesson with {booking.teacher.user.first_name or booking.teacher.user.username}",
                "custom_id": str(booking.id)
            })

@method_decorator(csrf_exempt, name='dispatch')
class PayFastWebhookView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        payload = request.data
        booking_id = payload.get('custom_str1')
        pf_payment_id = payload.get('pf_payment_id') or payload.get('m_payment_id') or str(uuid.uuid4())
        payment_status = payload.get('payment_status')
        amount_gross = float(payload.get('amount_gross', 0.0))

        if payment_status == 'COMPLETE':
            tx_status = PaymentTransaction.Status.SUCCESS
        else:
            tx_status = PaymentTransaction.Status.FAILED

        if booking_id:
            process_payment_webhook(
                booking_id=booking_id,
                gateway=PaymentTransaction.Gateway.PAYFAST,
                transaction_id=str(pf_payment_id),
                amount=amount_gross,
                currency='ZAR',
                status=tx_status,
                raw_payload=payload
            )

        return Response("OK", status=status.HTTP_200_OK)

@method_decorator(csrf_exempt, name='dispatch')
class PayPalWebhookView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        payload = request.data
        event_type = payload.get('event_type')
        resource = payload.get('resource', {})

        paypal_order_id = resource.get('id', str(uuid.uuid4()))
        booking_id = resource.get('custom_id')

        # Check for successful capture
        if event_type in ['CHECKOUT.ORDER.COMPLETED', 'PAYMENT.CAPTURE.COMPLETED']:
            tx_status = PaymentTransaction.Status.SUCCESS
            amount = float(resource.get('amount', {}).get('value', 9.0))
            currency = resource.get('amount', {}).get('currency_code', 'USD')

            if booking_id:
                process_payment_webhook(
                    booking_id=booking_id,
                    gateway=PaymentTransaction.Gateway.PAYPAL,
                    transaction_id=paypal_order_id,
                    amount=amount,
                    currency=currency,
                    status=tx_status,
                    raw_payload=payload
                )

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
