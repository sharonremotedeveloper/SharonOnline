"""
Tutor application funnel API (slice T5a, docs/TUTOR_STATUS_MACHINE.md section 14). Owner-only.

    GET   /api/v1/teachers/me/application/          the five steps, requirements, can_submit
    PATCH /api/v1/teachers/me/application/          speed_test / confirm_power_backup / accept_declaration (409 once sent)
    POST  /api/v1/teachers/me/application/submit/   applied | changes_requested -> submitted (400 lists the missing steps)
"""
from decimal import Decimal

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.schema import ErrorCodeSerializer
from apps.teachers import application, vetting

MAX_MBPS = Decimal('10000')
WRITABLE = frozenset({'speed_test', 'confirm_power_backup', 'accept_declaration'})


class StepSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=['profile', 'uploads', 'power_backup', 'speed_test', 'declaration'])
    complete = serializers.BooleanField()
    missing = serializers.ListField(child=serializers.CharField())
    detail = serializers.CharField(allow_blank=True)


class RequirementsSerializer(serializers.Serializer):
    upload_kinds = serializers.ListField(child=serializers.CharField())
    min_download_mbps = serializers.FloatField()
    min_upload_mbps = serializers.FloatField()
    speed_test_max_age_hours = serializers.IntegerField()


class ApplicationOverviewSerializer(serializers.Serializer):
    status = serializers.CharField()
    editable = serializers.BooleanField()
    can_submit = serializers.BooleanField()
    steps = StepSerializer(many=True)
    requirements = RequirementsSerializer()
    submitted_at = serializers.DateTimeField(allow_null=True)


class IncompleteSerializer(ErrorCodeSerializer):
    missing = serializers.ListField(child=serializers.CharField(), required=False)


class SpeedTestSerializer(serializers.Serializer):
    download_mbps = serializers.DecimalField(max_digits=7, decimal_places=1, min_value=Decimal('0.1'), max_value=MAX_MBPS)
    upload_mbps = serializers.DecimalField(max_digits=7, decimal_places=1, min_value=Decimal('0.1'), max_value=MAX_MBPS)


class ApplicationUpdateSerializer(serializers.Serializer):
    # Any key outside WRITABLE (submitted_at, status, unknown) is a 400 naming it, never silently ignored.
    speed_test = SpeedTestSerializer(required=False)
    confirm_power_backup = serializers.BooleanField(required=False)
    accept_declaration = serializers.BooleanField(required=False)

    def to_internal_value(self, data):
        if hasattr(data, 'keys'):
            errors = {key: ['This field cannot be changed here.'] for key in data.keys() if key not in WRITABLE}
            if errors:
                raise serializers.ValidationError(errors)
        return super().to_internal_value(data)

    def validate(self, attrs):
        for key in ('confirm_power_backup', 'accept_declaration'):
            if key in attrs and attrs[key] is not True:
                raise serializers.ValidationError({key: ['Only a confirmation (true) can be sent.']})
        return attrs


class _ApplicationView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'application'

    def teacher(self, request):
        profile = getattr(request.user, 'teacher_profile', None)
        if profile is None or getattr(request.user, 'role', None) != 'teacher':
            raise PermissionDenied('A tutor account is required.')
        return profile

    @staticmethod
    def fail(exc):
        body = {'error': str(exc), 'code': exc.code}
        if isinstance(exc, application.ApplicationIncomplete):
            body['missing'] = exc.missing
        return Response(body, status=exc.http_status)


class TeacherApplicationView(_ApplicationView):
    http_method_names = ('get', 'patch', 'head', 'options')

    @extend_schema(operation_id='teachers_me_application_retrieve', responses={200: ApplicationOverviewSerializer})
    def get(self, request):
        return Response(ApplicationOverviewSerializer(application.overview(self.teacher(request))).data)

    @extend_schema(operation_id='teachers_me_application_update', request=ApplicationUpdateSerializer,
                   responses={200: ApplicationOverviewSerializer, 400: ErrorCodeSerializer, 409: ErrorCodeSerializer})
    def patch(self, request):
        teacher = self.teacher(request)
        body = ApplicationUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            application.update_application(teacher, body.validated_data)
        except application.ApplicationError as exc:
            return self.fail(exc)
        return Response(ApplicationOverviewSerializer(application.overview(teacher)).data)


class TeacherApplicationSubmitView(_ApplicationView):
    @extend_schema(operation_id='teachers_me_application_submit', request=None,
                   responses={200: ApplicationOverviewSerializer, 400: IncompleteSerializer, 409: ErrorCodeSerializer})
    def post(self, request):
        teacher = self.teacher(request)
        try:
            application.submit_application(teacher, actor=request.user)
        except application.ApplicationError as exc:
            return self.fail(exc)
        except vetting.VettingError:                  # a concurrent status change: same answer as cannot_submit
            return Response({'error': 'This application cannot be submitted in its current status.', 'code': 'cannot_submit'},
                            status=status.HTTP_409_CONFLICT)
        return Response(ApplicationOverviewSerializer(application.overview(teacher)).data)
