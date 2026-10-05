"""
Staff actions on a tutor's lifecycle (slice T1b, docs/TUTOR_STATUS_MACHINE.md §9).

    POST /api/v1/admin/teachers/<id>/{start-review,approve,request-changes,reject,suspend,reactivate,revet,reopen}/
    POST /api/v1/admin/teachers/<id>/cancel-future-lessons/    staff cancel of a suspended / removed tutor's lessons
    GET  /api/v1/admin/teachers/suspended-with-lessons/       work queue (paginated)

`IsPlatformAdmin` + a scoped throttle on every view; typed request / response serializers; ids and statuses only in logs.
"""
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.bookings.services import admin_cancellation
from apps.teachers import review, vetting
from apps.users.permissions import IsPlatformAdmin

REASON_MAX = 500
_ERROR = inline_serializer('AdminTeacherError', {'error': serializers.CharField(), 'code': serializers.CharField()})


class TeacherReviewRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default='', max_length=REASON_MAX,
                                   help_text='Required (non-blank) for request-changes, reject and suspend.')


class TeacherReviewResultSerializer(serializers.Serializer):
    teacher_id = serializers.UUIDField()
    action = serializers.CharField()
    previous_status = serializers.CharField()
    status = serializers.CharField()
    changed = serializers.BooleanField()
    change_ids = serializers.ListField(child=serializers.UUIDField())
    affected_booking_ids = serializers.ListField(
        child=serializers.UUIDField(),
        help_text="suspend: the tutor's future pending / confirmed lessons, left untouched; cancel them with "
                  "cancel-future-lessons.")


class AdminCancelRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
    booking_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=True, max_length=200,
                                        help_text="Default: every future pending / confirmed lesson of the tutor.")


class AdminCancelRowSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField()
    outcome = serializers.ChoiceField(choices=['admin_refund', 'released', 'already_cancelled', 'not_cancellable',
                                               'funding_unavailable', 'not_found'])
    status = serializers.CharField(allow_blank=True)


class AdminCancelResultSerializer(serializers.Serializer):
    teacher_id = serializers.UUIDField()
    cancelled_count = serializers.IntegerField()
    results = AdminCancelRowSerializer(many=True)


class TutorWorkQueueItemSerializer(serializers.Serializer):
    teacher_id = serializers.UUIDField(source='id')
    full_name = serializers.SerializerMethodField()
    status = serializers.CharField()
    future_lesson_count = serializers.IntegerField()
    next_lesson_start_utc = serializers.DateTimeField()

    def get_full_name(self, obj) -> str:
        return obj.user.get_full_name() or obj.user.username


def _error(exc):
    code = 'not_found' if exc.http_status == 404 else ('invalid_transition' if exc.http_status == 409 else
                                                       ('forbidden' if exc.http_status == 403 else 'invalid'))
    return Response({'error': str(exc) if exc.http_status in (400, 404) else 'This tutor cannot be moved to that status.',
                     'code': code}, status=exc.http_status)


class _StaffThrottled(APIView):
    permission_classes = [IsPlatformAdmin]
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'admin_teacher_review'


@extend_schema(request=TeacherReviewRequestSerializer,
               responses={200: TeacherReviewResultSerializer, 400: _ERROR, 404: _ERROR, 409: _ERROR})
class TeacherReviewActionView(_StaffThrottled):
    action_name = None          # set per URL in admin_api/urls.py

    def post(self, request, pk):
        body = TeacherReviewRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            result = review.apply_review_action(pk, self.action_name, actor=request.user, reason=body.validated_data['reason'])
        except vetting.VettingError as exc:
            return _error(exc)
        return Response(TeacherReviewResultSerializer({
            'teacher_id': result.teacher_id, 'action': result.action, 'previous_status': result.previous_status,
            'status': result.status, 'changed': result.changed, 'change_ids': list(result.change_ids),
            'affected_booking_ids': list(result.affected_booking_ids)}).data)


@extend_schema(request=AdminCancelRequestSerializer,
               responses={200: AdminCancelResultSerializer, 400: _ERROR, 404: _ERROR, 409: _ERROR},
               description="Cancels a suspended or removed tutor's future lessons, one transaction per lesson: full refund, no "
                           "strike, ADMIN_CANCEL_BONUS_CREDITS bonus (0). Idempotent. 409 `tutor_not_suspended` otherwise.")
class CancelTutorFutureLessonsView(_StaffThrottled):
    def post(self, request, pk):
        body = AdminCancelRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            rows = admin_cancellation.cancel_future_lessons(pk, request.user, reason=body.validated_data['reason'].strip(),
                                                            booking_ids=body.validated_data.get('booking_ids'))
        except admin_cancellation.AdminCancelError as exc:
            return Response({'error': exc.message, 'code': exc.code}, status=exc.status_code)
        cancelled = sum(1 for r in rows if r.outcome in ('admin_refund', 'released'))
        return Response(AdminCancelResultSerializer({
            'teacher_id': pk, 'cancelled_count': cancelled,
            'results': [{'booking_id': r.booking_id, 'outcome': r.outcome, 'status': r.status} for r in rows]}).data)


class TutorWorkQueuePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class SuspendedTutorsWithLessonsView(generics.ListAPIView):
    """Suspended or removed tutors who still have future lessons (soonest first): cancel them with cancel-future-lessons."""
    permission_classes = [IsPlatformAdmin]
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'admin_teacher_review'
    serializer_class = TutorWorkQueueItemSerializer
    pagination_class = TutorWorkQueuePagination

    def get_queryset(self):
        return admin_cancellation.tutors_needing_action()
