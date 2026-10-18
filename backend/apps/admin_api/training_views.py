"""
Staff management of tutor training modules (Wave 2, docs/ADMIN_CONTENT_MANAGEMENT_PENDING.md; ADM-07 training half).

    GET   /api/v1/admin/training/modules/          every module (drafts too) with completion counts, plus tutor totals
    POST  /api/v1/admin/training/modules/          create
    GET   /api/v1/admin/training/modules/<id>/     one module with its Markdown body
    PATCH /api/v1/admin/training/modules/<id>/     edit / publish / unpublish
    POST  /api/v1/admin/training/reorder/          {"ids": [...every module id in the new order]}

Only `IsPlatformAdmin` (decision 1: admins author). Writes go through `teachers/training.py::save_module`, which re-gates
tutors when a module becomes published + required; that answers 409 `regate_confirmation_required` with the number of
tutors affected until the request repeats with `confirm_regate: true`. Videos are YouTube links reduced to the video id.
"""
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.schema import ErrorCodeSerializer
from apps.common.throttles import ResilientScopedRateThrottle as ScopedRateThrottle
from apps.teachers import training
from apps.teachers.models import TeacherProfile, TrainingModule
from apps.users.permissions import IsPlatformAdmin


class AdminTrainingModuleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()
    summary = serializers.CharField(allow_blank=True)
    video_youtube_id = serializers.CharField(allow_blank=True)
    position = serializers.IntegerField()
    estimated_minutes = serializers.IntegerField()
    is_required = serializers.BooleanField()
    is_published = serializers.BooleanField()
    completed_count = serializers.IntegerField(help_text='Tutors who completed this module.')
    updated_at = serializers.DateTimeField()


class AdminTrainingModuleDetailSerializer(AdminTrainingModuleSerializer):
    body = serializers.CharField(allow_blank=True, help_text='Markdown.')


class AdminTrainingListSerializer(serializers.Serializer):
    modules = AdminTrainingModuleSerializer(many=True)
    approved_tutors = serializers.IntegerField()
    trained_tutors = serializers.IntegerField(help_text='Approved tutors holding a training date.')
    gate_enabled = serializers.BooleanField(help_text='TUTOR_TRAINING_GATE_ENABLED: while false nobody is hidden.')


class AdminTrainingModuleWriteSerializer(serializers.Serializer):
    slug = serializers.SlugField(max_length=80)
    title = serializers.CharField(max_length=200)
    summary = serializers.CharField(max_length=500, allow_blank=True, required=False, default='')
    body = serializers.CharField(allow_blank=True, required=False, default='', max_length=100_000)
    video_url = serializers.CharField(allow_blank=True, required=False, default='', max_length=300,
                                      help_text='A YouTube link; only the video id is stored.')
    position = serializers.IntegerField(min_value=1, max_value=10_000, required=False)
    estimated_minutes = serializers.IntegerField(min_value=1, max_value=600, required=False, default=10)
    is_required = serializers.BooleanField(required=False, default=True)
    is_published = serializers.BooleanField(required=False, default=False)
    confirm_regate = serializers.BooleanField(required=False, default=False)

    def validate_slug(self, value):
        taken = TrainingModule.objects.filter(slug=value)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError('Another module already uses this slug.')
        return value

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('A title is required.')
        return value

    def validate_video_url(self, value):
        try:
            return training.parse_youtube_id(value)
        except training.InvalidVideoLink as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def fields_to_save(self):
        data = dict(self.validated_data)
        data.pop('confirm_regate', None)
        if 'video_url' in data:
            data['video_youtube_id'] = data.pop('video_url')
        return data


def _row(module, detail=False):
    row = {'id': module.id, 'slug': module.slug, 'title': module.title, 'summary': module.summary,
           'video_youtube_id': module.video_youtube_id, 'position': module.position,
           'estimated_minutes': module.estimated_minutes, 'is_required': module.is_required,
           'is_published': module.is_published, 'completed_count': getattr(module, 'completed_count', 0),
           'updated_at': module.updated_at}
    if detail:
        row['body'] = module.body
    return row


def _modules():
    return TrainingModule.objects.annotate(completed_count=Count('progress')).order_by('position', 'slug')  # GROUP BY drops Meta.ordering


def _regate_conflict(exc):
    return Response({'error': str(exc), 'code': 'regate_confirmation_required', 'tutors_affected': exc.count},
                    status=status.HTTP_409_CONFLICT)


class _AdminTrainingView(APIView):
    permission_classes = (permissions.IsAuthenticated, IsPlatformAdmin)
    throttle_classes = (ScopedRateThrottle,)

    def get_throttles(self):
        self.throttle_scope = 'admin_read' if self.request.method == 'GET' else 'admin_content'
        return super().get_throttles()


_REGATE_409 = inline_serializer('TrainingRegateConflict', fields={
    'error': serializers.CharField(), 'code': serializers.CharField(), 'tutors_affected': serializers.IntegerField()})


def _list_payload():
    approved = TeacherProfile.objects.filter(status=TeacherProfile.Status.APPROVED)
    return AdminTrainingListSerializer({
        'modules': [_row(m) for m in _modules()],
        'approved_tutors': approved.count(),
        'trained_tutors': approved.filter(training_completed_at__isnull=False).count(),
        'gate_enabled': bool(settings.TUTOR_TRAINING_GATE_ENABLED),
    }).data


class AdminTrainingModuleListView(_AdminTrainingView):
    @extend_schema(operation_id='admin_training_modules_list', responses={200: AdminTrainingListSerializer})
    def get(self, request):
        return Response(_list_payload())

    @extend_schema(operation_id='admin_training_modules_create', request=AdminTrainingModuleWriteSerializer,
                   responses={201: AdminTrainingModuleDetailSerializer, 400: ErrorCodeSerializer, 409: _REGATE_409})
    def post(self, request):
        serializer = AdminTrainingModuleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = serializer.fields_to_save()
        if 'position' not in fields:
            fields['position'] = (TrainingModule.objects.aggregate(top=Max('position'))['top'] or 0) + 1
        try:
            module, _ = training.save_module(None, fields, confirm_regate=serializer.validated_data['confirm_regate'])
        except training.RegateConfirmationRequired as exc:
            return _regate_conflict(exc)
        return Response(AdminTrainingModuleDetailSerializer(_row(_modules().get(pk=module.pk), detail=True)).data,
                        status=status.HTTP_201_CREATED)


class AdminTrainingModuleDetailView(_AdminTrainingView):
    @extend_schema(operation_id='admin_training_modules_retrieve', responses={200: AdminTrainingModuleDetailSerializer})
    def get(self, request, module_id):
        return Response(AdminTrainingModuleDetailSerializer(_row(get_object_or_404(_modules(), pk=module_id), detail=True)).data)

    @extend_schema(operation_id='admin_training_modules_update', request=AdminTrainingModuleWriteSerializer,
                   responses={200: AdminTrainingModuleDetailSerializer, 400: ErrorCodeSerializer, 409: _REGATE_409})
    def patch(self, request, module_id):
        module = get_object_or_404(TrainingModule, pk=module_id)
        serializer = AdminTrainingModuleWriteSerializer(module, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            training.save_module(module, serializer.fields_to_save(),
                                 confirm_regate=serializer.validated_data.get('confirm_regate', False))
        except training.RegateConfirmationRequired as exc:
            return _regate_conflict(exc)
        return Response(AdminTrainingModuleDetailSerializer(_row(_modules().get(pk=module.pk), detail=True)).data)


class AdminTrainingReorderView(_AdminTrainingView):
    @extend_schema(operation_id='admin_training_reorder',
                   request=inline_serializer('TrainingReorder', fields={'ids': serializers.ListField(child=serializers.UUIDField())}),
                   responses={200: AdminTrainingListSerializer, 400: ErrorCodeSerializer})
    def post(self, request):
        ids = request.data.get('ids')
        if not isinstance(ids, list):
            return Response({'error': 'ids must be a list of every module id.', 'code': 'invalid'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            wanted = [str(serializers.UUIDField().to_internal_value(i)) for i in ids]
        except serializers.ValidationError:
            return Response({'error': 'ids must be module ids.', 'code': 'invalid'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            modules = {str(m.pk): m for m in TrainingModule.objects.select_for_update()}
            if len(wanted) != len(set(wanted)) or set(wanted) != set(modules):
                return Response({'error': 'List every module exactly once.', 'code': 'invalid'},
                                status=status.HTTP_400_BAD_REQUEST)
            for position, pk in enumerate(wanted, start=1):
                if modules[pk].position != position:
                    TrainingModule.objects.filter(pk=pk).update(position=position)
        return Response(_list_payload())
