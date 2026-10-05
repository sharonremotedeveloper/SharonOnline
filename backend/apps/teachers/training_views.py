"""
Tutor onboarding training API (slice T6, docs/TUTOR_STATUS_MACHINE.md §13). Owner-only; published modules only.

    GET  /api/v1/teachers/me/training/                  light list + the tutor's progress
    GET  /api/v1/teachers/me/training/<slug>/           one module with its content
    POST /api/v1/teachers/me/training/<slug>/complete/  idempotent; 409 until the application is approved
"""
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.schema import ErrorCodeSerializer
from apps.teachers import training
from apps.teachers.models import TrainingModule, TrainingProgress
from apps.users.permissions import IsTeacher


class TrainingModuleItemSerializer(serializers.Serializer):
    slug = serializers.CharField()
    title = serializers.CharField()
    summary = serializers.CharField(allow_blank=True)
    position = serializers.IntegerField()
    estimated_minutes = serializers.IntegerField()
    is_required = serializers.BooleanField()
    completed = serializers.BooleanField()


class TrainingModuleDetailSerializer(TrainingModuleItemSerializer):
    body = serializers.CharField(allow_blank=True, help_text='Markdown.')


class TrainingOverviewSerializer(serializers.Serializer):
    modules = TrainingModuleItemSerializer(many=True)
    required_total = serializers.IntegerField()
    required_completed = serializers.IntegerField()
    completed_at = serializers.DateTimeField(allow_null=True)
    can_train = serializers.BooleanField(help_text='False until the application is approved.')


class _TrainingView(APIView):
    permission_classes = (permissions.IsAuthenticated, IsTeacher)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'training'

    def teacher(self, request):
        profile = getattr(request.user, 'teacher_profile', None)
        if profile is None:
            raise PermissionDenied('A teacher profile is required.')
        return profile

    def module(self, slug):
        found = TrainingModule.objects.filter(slug=slug, is_published=True).first()
        if found is None:
            raise NotFound('Training module not found.')
        return found

    def item(self, module, done_ids):
        return {'slug': module.slug, 'title': module.title, 'summary': module.summary, 'position': module.position,
                'estimated_minutes': module.estimated_minutes, 'is_required': module.is_required,
                'completed': module.id in done_ids}

    def overview(self, teacher):
        modules = list(TrainingModule.objects.filter(is_published=True))
        done = set(TrainingProgress.objects.filter(teacher=teacher).values_list('module_id', flat=True))
        return {**training.summary(teacher), 'modules': [self.item(m, done) for m in modules],
                'can_train': teacher.status == 'approved'}


class TeacherTrainingView(_TrainingView):
    @extend_schema(operation_id='teachers_me_training_overview', responses={200: TrainingOverviewSerializer})
    def get(self, request):
        return Response(TrainingOverviewSerializer(self.overview(self.teacher(request))).data)


class TeacherTrainingModuleView(_TrainingView):
    @extend_schema(operation_id='teachers_me_training_module',
                   responses={200: TrainingModuleDetailSerializer, 404: ErrorCodeSerializer})
    def get(self, request, slug):
        teacher, module = self.teacher(request), self.module(slug)
        done = set(TrainingProgress.objects.filter(teacher=teacher, module=module).values_list('module_id', flat=True))
        return Response(TrainingModuleDetailSerializer({**self.item(module, done), 'body': module.body}).data)


class TeacherTrainingCompleteView(_TrainingView):
    @extend_schema(operation_id='teachers_me_training_complete', request=None,
                   responses={200: TrainingOverviewSerializer, 404: ErrorCodeSerializer, 409: ErrorCodeSerializer})
    def post(self, request, slug):
        teacher, module = self.teacher(request), self.module(slug)
        try:
            training.complete_module(teacher, module)
        except training.TrainingNotAvailable as exc:
            return Response({'error': str(exc), 'code': 'training_unavailable'}, status=status.HTTP_409_CONFLICT)
        return Response(TrainingOverviewSerializer(self.overview(teacher)).data)
