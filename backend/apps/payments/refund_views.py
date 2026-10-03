"""A student's own refunds: see what is owed back and, while it is still pending, turn it into wallet credit (Task 9.6)."""
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsStudent
from .models import RefundRequest
from .services import refunds


class RefundSerializer(serializers.ModelSerializer):
    booking_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = RefundRequest
        fields = ('id', 'booking_id', 'amount', 'currency', 'reason', 'status', 'created_at', 'processed_at')
        read_only_fields = fields


@extend_schema(responses=RefundSerializer(many=True))
class RefundListView(generics.ListAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = RefundSerializer

    def get_queryset(self):
        return RefundRequest.objects.filter(user=self.request.user)


@extend_schema(request=None, responses=RefundSerializer)
class ConvertRefundToWalletView(APIView):
    """
    Turn a still-pending gateway refund into 30-day wallet credit (instead of waiting for the card/PayPal refund). Only before the
    gateway has been asked: afterwards the money may already be on its way, and the answer is 409 `refund_in_progress`.
    """
    permission_classes = (IsStudent,)

    def post(self, request, refund_id):
        refund = get_object_or_404(RefundRequest, pk=refund_id, user=request.user)
        try:
            refunds.convert_to_wallet(refund.pk)
        except refunds.RefundInProgress as exc:
            return Response({"error": str(exc), "code": "refund_in_progress"}, status=status.HTTP_409_CONFLICT)
        except refunds.RefundStateError as exc:
            return Response({"error": str(exc), "code": "already_processed"}, status=status.HTTP_409_CONFLICT)
        refund.refresh_from_db()
        return Response(RefundSerializer(refund).data)
