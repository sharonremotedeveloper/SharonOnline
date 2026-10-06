"""Admin API for payout batches (slices P1a-c). The workflow rules live in apps/payments/services/payout_batches.py."""
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.admin_api.models import PayoutBatch, PayoutBatchLine
from apps.common.money import money_str
from apps.payments.services import payout_batches as batches
from apps.users.permissions import IsPlatformAdmin

STATUS_FOR_CODE = {
    'not_found': status.HTTP_404_NOT_FOUND,
    'maker_checker_violation': status.HTTP_403_FORBIDDEN,
    'invalid_state': status.HTTP_409_CONFLICT,
    'nothing_to_pay': status.HTTP_409_CONFLICT,
    'no_payable_lines': status.HTTP_409_CONFLICT,
    'balance_changed': status.HTTP_409_CONFLICT,
}


class PayoutLineSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    teacher_id = serializers.UUIDField()
    teacher_name = serializers.CharField()
    amount_zar = serializers.CharField()
    status = serializers.CharField()
    skip_reason = serializers.CharField()
    account_last_four = serializers.CharField()
    paid_at = serializers.DateTimeField(allow_null=True)
    returned_at = serializers.DateTimeField(allow_null=True)


class PayoutBatchSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    batch_reference = serializers.CharField()
    status = serializers.CharField()
    total_payout_zar = serializers.CharField()
    recipients_count = serializers.IntegerField()
    created_by = serializers.CharField(allow_null=True)
    approved_by = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    approved_at = serializers.DateTimeField(allow_null=True)
    exported_at = serializers.DateTimeField(allow_null=True)
    executed_at = serializers.DateTimeField(allow_null=True)
    cancel_reason = serializers.CharField()
    carried_over_count = serializers.IntegerField(required=False)
    lines = PayoutLineSerializer(many=True)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class ExportRequestSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)


def _name(user):
    return None if user is None else (user.get_full_name() or user.username)


def batch_payload(batch: PayoutBatch, **extra) -> dict:
    lines = batch.lines.select_related('teacher__user').order_by('created_at')
    return PayoutBatchSerializer({
        'id': batch.id, 'batch_reference': batch.batch_reference, 'status': batch.status,
        'total_payout_zar': money_str(batch.total_payout_zar, 'ZAR'), 'recipients_count': batch.recipients_count,
        'created_by': _name(batch.created_by), 'approved_by': _name(batch.approved_by), 'created_at': batch.created_at,
        'approved_at': batch.approved_at, 'exported_at': batch.exported_at, 'executed_at': batch.executed_at,
        'cancel_reason': batch.cancel_reason,
        'lines': [{
            'id': line.id, 'teacher_id': line.teacher_id, 'teacher_name': _name(line.teacher.user),
            'amount_zar': money_str(line.amount_zar, 'ZAR'), 'status': line.status, 'skip_reason': line.skip_reason,
            'account_last_four': line.account_last_four, 'paid_at': line.paid_at, 'returned_at': line.returned_at,
        } for line in lines],
        **extra,
    }).data


def refused(exc: batches.PayoutError) -> Response:
    body = {'code': exc.code, 'message': exc.message}
    if exc.lines:
        body['lines'] = exc.lines
    return Response(body, status=STATUS_FOR_CODE.get(exc.code, status.HTTP_400_BAD_REQUEST))


class _PayoutAdminView(APIView):
    permission_classes = [IsPlatformAdmin]
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'payout_admin'


@extend_schema(responses=PayoutBatchSerializer(many=True))
class PayoutBatchListCreateView(_PayoutAdminView):
    def get(self, request):
        recent = PayoutBatch.objects.select_related('created_by', 'approved_by')[:50]
        return Response([batch_payload(batch) for batch in recent])

    @extend_schema(request=None, responses={201: PayoutBatchSerializer})
    def post(self, request):
        try:
            batch, carried = batches.create_batch(actor=request.user)
        except batches.PayoutError as exc:
            return refused(exc)
        return Response(batch_payload(batch, carried_over_count=carried), status=status.HTTP_201_CREATED)


@extend_schema(responses=PayoutBatchSerializer)
class PayoutBatchDetailView(_PayoutAdminView):
    def get(self, request, batch_id):
        batch = PayoutBatch.objects.select_related('created_by', 'approved_by').filter(pk=batch_id).first()
        if batch is None:
            return Response({'code': 'not_found', 'message': 'No such payout batch.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(batch_payload(batch))


class _PayoutActionView(_PayoutAdminView):
    """POST /payouts/batches/<id>/<action>/ -> the batch after the action, or {code, message}."""

    @extend_schema(request=None, responses=PayoutBatchSerializer)
    def post(self, request, batch_id):
        try:
            batch = self.perform(request, batch_id)
        except batches.PayoutError as exc:
            return refused(exc)
        return Response(batch_payload(batch))

    def perform(self, request, batch_id):
        raise NotImplementedError


class PayoutBatchApproveView(_PayoutActionView):
    def perform(self, request, batch_id):
        return batches.approve_batch(batch_id, actor=request.user)


class PayoutBatchProcessView(_PayoutActionView):
    def perform(self, request, batch_id):
        return batches.mark_processed(batch_id, actor=request.user)


class PayoutBatchCancelView(_PayoutActionView):
    @extend_schema(request=ReasonSerializer, responses=PayoutBatchSerializer)
    def post(self, request, batch_id):
        return super().post(request, batch_id)

    def perform(self, request, batch_id):
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return batches.cancel_batch(batch_id, actor=request.user, reason=serializer.validated_data['reason'])


@extend_schema(request=ExportRequestSerializer, responses={(200, 'text/csv'): OpenApiTypes.BINARY})
class PayoutBatchExportView(_PayoutAdminView):
    """The bank CSV. Needs the admin's password again (fresh re-auth) and is never cached."""

    def post(self, request, batch_id):
        serializer = ExportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data['password']):
            return Response({'code': 'reauth_required', 'message': 'Your password is incorrect.'},
                            status=status.HTTP_403_FORBIDDEN)
        try:
            batch, content, _rows = batches.export_batch(batch_id, actor=request.user)
        except batches.PayoutError as exc:
            return refused(exc)
        response = HttpResponse(content, content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{batch.batch_reference}.csv"'
        response['Cache-Control'] = 'no-store'
        return response


@extend_schema(request=ReasonSerializer, responses=PayoutLineSerializer)
class PayoutLineReturnView(_PayoutAdminView):
    def post(self, request, line_id):
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            line = batches.return_line(line_id, actor=request.user, reason=serializer.validated_data['reason'])
        except batches.PayoutError as exc:
            return refused(exc)
        line = PayoutBatchLine.objects.select_related('teacher__user').get(pk=line.pk)
        return Response(PayoutLineSerializer({
            'id': line.id, 'teacher_id': line.teacher_id, 'teacher_name': _name(line.teacher.user),
            'amount_zar': money_str(line.amount_zar, 'ZAR'), 'status': line.status, 'skip_reason': line.skip_reason,
            'account_last_four': line.account_last_four, 'paid_at': line.paid_at, 'returned_at': line.returned_at,
        }).data)
