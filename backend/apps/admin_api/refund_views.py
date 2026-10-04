"""
Staff view of student refunds (Task 10.7 slice R-C, docs/TASK_10_7_REFUND_GATEWAYS_PLAN.md section 2b).

    GET  /api/v1/admin/refunds/             what is stuck and why (filters + bucket counts for a banner), oldest first
    POST /api/v1/admin/refunds/<id>/retry/  send a failed refund back to the gateway

Only `IsPlatformAdmin`. Nothing here returns raw provider bodies, claim tokens or request ids: staff see ids, statuses, codes
and a short, stripped failure note. Money is an exact string in the row's own currency (never a float).
"""
from collections import Counter

from django.db.models import OuterRef, Prefetch, Q, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.money import money_str
from apps.payments.models import RefundAttempt, RefundRequest
from apps.payments.services import refunds
from apps.users.permissions import IsPlatformAdmin

RS = RefundRequest.Status
RECENT_ATTEMPTS = 5
FAILURE_DETAIL_MAX = 200


def _latest_attempt_state():
    return Subquery(RefundAttempt.objects.filter(refund=OuterRef('pk')).order_by('-seq').values('result_state')[:1])


def _annotated():
    return RefundRequest.objects.annotate(latest_state=_latest_attempt_state())


def _waiting_manual_q() -> Q:
    """Pending, and the last thing the gateway said was 'this backend does not move money': a person has to pay it."""
    return Q(status=RS.PENDING_GATEWAY, latest_state='manual')


def _in_flight_q(now) -> Q:
    return Q(claimed_until__gt=now)


class AdminRefundAttemptSerializer(serializers.Serializer):
    seq = serializers.IntegerField()
    kind = serializers.CharField()
    result_state = serializers.CharField()
    http_status = serializers.IntegerField(allow_null=True)
    error_code = serializers.CharField()
    created_at = serializers.DateTimeField()
    actor = serializers.CharField(allow_null=True, help_text="Username of the admin, or null for the system.")


class AdminRefundSerializer(serializers.ModelSerializer):
    booking_id = serializers.UUIDField(read_only=True)
    student = serializers.SerializerMethodField(help_text="Display name only (never an e-mail address).")
    amount = serializers.SerializerMethodField(help_text="Exact decimal string in `currency`.")
    gateway = serializers.CharField(source='payment_transaction.gateway', read_only=True)
    failure_detail = serializers.SerializerMethodField(help_text="Stripped and truncated to 200 characters.")
    age_hours = serializers.SerializerMethodField()
    recent_attempts = serializers.SerializerMethodField()

    class Meta:
        model = RefundRequest
        fields = ('id', 'booking_id', 'student', 'amount', 'currency', 'reason', 'status', 'failure_kind', 'failure_detail', 'attempts',
                  'next_attempt_at', 'last_http_status', 'last_error_code', 'gateway', 'created_at', 'age_hours', 'recent_attempts')
        read_only_fields = fields

    def get_student(self, obj) -> str:
        return obj.user.get_full_name().strip() or obj.user.username

    def get_amount(self, obj) -> str:
        return money_str(obj.amount, obj.currency)

    def get_failure_detail(self, obj) -> str:
        return (obj.failure_detail or '').strip()[:FAILURE_DETAIL_MAX].strip()

    def get_age_hours(self, obj) -> float:
        return round((timezone.now() - obj.created_at).total_seconds() / 3600, 1)

    @extend_schema_field(AdminRefundAttemptSerializer(many=True))
    def get_recent_attempts(self, obj):
        rows = sorted(obj.attempt_log.all(), key=lambda a: a.seq, reverse=True)[:RECENT_ATTEMPTS]
        return AdminRefundAttemptSerializer(
            [{'seq': a.seq, 'kind': a.kind, 'result_state': a.result_state, 'http_status': a.http_status, 'error_code': a.error_code,
              'created_at': a.created_at, 'actor': a.actor.username if a.actor_id else None} for a in rows], many=True).data


class AdminRefundPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data['buckets'] = self.buckets
        return response


class AdminRefundRetrySerializer(serializers.Serializer):
    confirm_not_refunded_in_gateway = serializers.BooleanField(
        required=False, default=False,
        help_text="Required for ambiguous failures (exhausted, replay_window, already_refunded): the admin has checked the "
                  "gateway and the money did NOT go out.")


_BUCKETS_SCHEMA = inline_serializer('AdminRefundBuckets', {
    'status': serializers.DictField(child=serializers.IntegerField()),
    'failure_kind': serializers.DictField(child=serializers.IntegerField()),
    'in_flight': serializers.IntegerField(),
    'waiting_manual': serializers.IntegerField(),
})
_PAGE_SCHEMA = inline_serializer('AdminRefundPage', {
    'count': serializers.IntegerField(),
    'next': serializers.CharField(allow_null=True),
    'previous': serializers.CharField(allow_null=True),
    'buckets': _BUCKETS_SCHEMA,
    'results': AdminRefundSerializer(many=True),
})
_ERROR_SCHEMA = inline_serializer('AdminRefundError', {'error': serializers.CharField(), 'code': serializers.CharField()})


def _buckets(now) -> dict:
    """Counts over EVERY refund (not the filtered page): the banner must not change when the table is filtered."""
    base = _annotated()
    return {
        'status': dict(Counter(base.values_list('status', flat=True))),
        'failure_kind': dict(Counter(k for k in base.values_list('failure_kind', flat=True) if k)),
        'in_flight': base.filter(_in_flight_q(now)).count(),
        'waiting_manual': base.filter(_waiting_manual_q()).count(),
    }


@extend_schema(
    parameters=[
        OpenApiParameter('status', str, description="A RefundRequest status."),
        OpenApiParameter('failure_kind', str, description="rejected | already_refunded | guard | exhausted | replay_window | provider_failed"),
        OpenApiParameter('gateway', str, description="paypal | payfast"),
        OpenApiParameter('in_flight', bool, description="true: only rows a worker holds a live lease on; false: only rows without one."),
        OpenApiParameter('waiting_manual', bool, description="true: pending rows whose last gateway answer was 'manual'."),
        OpenApiParameter('page_size', int),
    ],
    responses=_PAGE_SCHEMA)
class AdminRefundListView(APIView):
    permission_classes = [IsPlatformAdmin]

    @staticmethod
    def _flag(request, name):
        value = request.query_params.get(name)
        if value is None:
            return None
        return value.strip().lower() in ('1', 'true', 'yes')

    def get(self, request):
        now = timezone.now()
        qs = (_annotated().select_related('user', 'payment_transaction')
              .prefetch_related(Prefetch('attempt_log', queryset=RefundAttempt.objects.select_related('actor').order_by('-seq'))))
        params = request.query_params
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        if params.get('failure_kind'):
            qs = qs.filter(failure_kind=params['failure_kind'])
        if params.get('gateway'):
            qs = qs.filter(payment_transaction__gateway=params['gateway'])
        in_flight = self._flag(request, 'in_flight')
        if in_flight is True:
            qs = qs.filter(_in_flight_q(now))
        elif in_flight is False:
            qs = qs.exclude(_in_flight_q(now))
        waiting = self._flag(request, 'waiting_manual')
        if waiting is True:
            qs = qs.filter(_waiting_manual_q())
        elif waiting is False:
            qs = qs.exclude(_waiting_manual_q())

        paginator = AdminRefundPagination()
        paginator.buckets = _buckets(now)
        page = paginator.paginate_queryset(qs.order_by('created_at', 'pk'), request, view=self)
        return paginator.get_paginated_response(AdminRefundSerializer(page, many=True).data)


@extend_schema(
    request=AdminRefundRetrySerializer,
    responses={200: AdminRefundSerializer, 400: _ERROR_SCHEMA, 404: _ERROR_SCHEMA, 409: _ERROR_SCHEMA},
    description="409 codes: `not_failed` (only a failed refund can be retried), `confirmation_required` (ambiguous failure: send "
                "`confirm_not_refunded_in_gateway: true` after checking the gateway), `guard_failed` (a safety check still refuses it).")
class AdminRefundRetryView(APIView):
    permission_classes = [IsPlatformAdmin]
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'admin_refund_retry'

    def post(self, request, refund_id):
        body = AdminRefundRetrySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        refund = get_object_or_404(RefundRequest, pk=refund_id)
        try:
            refunds.retry_failed(refund.pk, actor=request.user,
                                 confirm_not_refunded=body.validated_data['confirm_not_refunded_in_gateway'])
        except refunds.RefundConfirmationRequired as exc:
            return Response({'error': str(exc), 'code': 'confirmation_required'}, status=status.HTTP_409_CONFLICT)
        except refunds.RefundGuardFailed as exc:
            return Response({'error': str(exc), 'code': 'guard_failed'}, status=status.HTTP_409_CONFLICT)
        except refunds.RefundStateError as exc:
            return Response({'error': str(exc), 'code': 'not_failed'}, status=status.HTTP_409_CONFLICT)
        row = (_annotated().select_related('user', 'payment_transaction')
               .prefetch_related(Prefetch('attempt_log', queryset=RefundAttempt.objects.select_related('actor').order_by('-seq')))
               .get(pk=refund.pk))
        return Response(AdminRefundSerializer(row).data)
