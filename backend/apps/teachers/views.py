from datetime import timedelta
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view, inline_serializer
from rest_framework import generics, permissions, filters, serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from apps.common.throttles import (
    ObservedScopedRateThrottle,
    ResilientScopedRateThrottle as ScopedRateThrottle,
    ResilientUserRateThrottle as UserRateThrottle,
)
from rest_framework.views import APIView
from django.db.models import Q
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from apps.common import clock
from apps.users.permissions import IsTeacher
from .models import TeacherProfile, TeacherAvailability, TeacherDateOverride, TeacherTimeOff
from .models import TeacherAsset
from .assets import commit_asset, audit_private_access
from apps.common.r2_client import generate_presigned_download_url
from .profile import update_own_profile
from .serializers import (
    AvailabilityChangeSerializer, AvailabilityMatrixSerializer, AvailabilityReplaceResultSerializer,
    AvailabilityUpdateSerializer, ConflictErrorSerializer, DateOverrideCreateSerializer, DateOverrideResultSerializer,
    DeletedSerializer, PowerBackupSerializer, TeacherDateOverrideSerializer, TeacherDetailSerializer, TeacherListSerializer,
    TeacherAvailabilitySerializer, TeacherTimeOffSerializer, TimeOffCreateSerializer, TimeOffResultSerializer,
    TeacherOwnProfileSerializer, TeacherAssetCommitSerializer, TeacherAssetCommitResponseSerializer,
)
from .services import availability
from .services.directory import DirectoryUnavailable, free_teacher_ids


def _directory_boolean(request, name):
    values = request.query_params.getlist(name)
    if not values:
        return False
    if len(values) != 1 or values[0] not in ('true', 'false'):
        raise ValidationError({name: 'Use true or false.'})
    return values[0] == 'true'


class TeacherDirectoryPagination(PageNumberPagination):
    page_size_query_param = 'page_size'
    max_page_size = 50


@extend_schema_view(get=extend_schema(parameters=[
    OpenApiParameter('backup_power', bool, description='Only tutors who declared inverter backup.'),
    OpenApiParameter('free_next_24h', bool, description='Only tutors with a bookable lesson fully within the next 24 hours.'),
    OpenApiParameter('page_size', int, description='Tutors per page (maximum 50).'),
], responses={
    200: TeacherListSerializer(many=True),
    503: inline_serializer(name='TeacherDirectoryUnavailable', fields={
        'code': serializers.ChoiceField(choices=['directory_budget_exceeded', 'directory_cache_unavailable']),
        'detail': serializers.CharField(),
    }),
}))
class TeacherListView(generics.ListAPIView):
    serializer_class = TeacherListSerializer
    pagination_class = TeacherDirectoryPagination
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (ObservedScopedRateThrottle,)
    throttle_scope = 'public_teacher_directory'

    def list(self, request, *args, **kwargs):
        free_next_24h = _directory_boolean(request, 'free_next_24h')
        queryset = self.filter_queryset(self.get_queryset())
        if not free_next_24h:
            return super().list(request, *args, **kwargs)

        # Keep the full filtered count and stable ordering before selecting a page.
        try:
            ids = free_teacher_ids(queryset)
        except DirectoryUnavailable as exc:
            if exc.code == 'directory_budget_exceeded':
                return Response({'code': exc.code, 'detail': 'Too many tutors or slots to search. Refine your filters.'},
                                status=status.HTTP_503_SERVICE_UNAVAILABLE)
            return Response({'code': exc.code, 'detail': 'Tutor availability is temporarily unavailable. Please retry.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE, headers={'Retry-After': '30'})
        page_ids = self.paginate_queryset(ids)
        selected = ids if page_ids is None else page_ids
        teachers_by_id = {teacher.id: teacher for teacher in TeacherProfile.objects.bookable().filter(
            pk__in=selected).select_related('user')}
        teachers = [teachers_by_id[pk] for pk in selected if pk in teachers_by_id]
        serializer = self.get_serializer(teachers, many=True)
        if page_ids is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def get_queryset(self):
        queryset = TeacherProfile.objects.bookable().select_related('user')
        if _directory_boolean(self.request, 'backup_power'):
            queryset = queryset.filter(has_inverter_backup=True)
        
        # Accent filter
        accent = self.request.query_params.get('accent')
        if accent:
            queryset = queryset.filter(accent=accent)

        # Specialty filter
        specialty = self.request.query_params.get('specialty')
        if specialty:
            queryset = queryset.filter(specialties__contains=[specialty])

        # Min rating filter
        min_rating = self.request.query_params.get('min_rating')
        if min_rating:
            try:
                queryset = queryset.filter(rating_avg__gte=float(min_rating))
            except ValueError:
                pass

        # No price filter: every tutor has the catalog price (Task 10.1); `?max_price=` was removed in T1c.

        # Search query
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user__username__icontains=search) |
                Q(headline__icontains=search) |
                Q(bio__icontains=search)
            )

        return queryset.order_by('-rating_avg', '-rating_count', 'pk')

class TeacherDetailView(generics.RetrieveAPIView):
    serializer_class = TeacherDetailSerializer
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (ObservedScopedRateThrottle,)
    throttle_scope = 'public_teacher_detail'
    lookup_field = 'id'

    def get_queryset(self):
        # Evaluated per request: the training gate is a setting (slice T1b).
        return TeacherProfile.objects.bookable().select_related('user').prefetch_related('availabilities')


class SchedulePagination(PageNumberPagination):
    """Schedule lists are capped far below this (services.availability.MAX_*), so one page is the whole list."""
    page_size = 100
    max_page_size = 100


class TutorScheduleMixin:
    """Owner-only, throttled base of every availability / time-off / override endpoint (T2)."""
    permission_classes = (permissions.IsAuthenticated, IsTeacher)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'availability'
    pagination_class = SchedulePagination

    def get_teacher(self):
        profile = getattr(self.request.user, 'teacher_profile', None)
        if profile is None:
            raise PermissionDenied('A teacher profile is required (your application has not been set up yet).')
        return profile

    def get_serializer_context(self):
        context = super().get_serializer_context()
        profile = getattr(self.request.user, 'teacher_profile', None)
        if profile is not None:
            context['teacher'] = profile
        return context

    def acknowledged(self) -> bool:
        """Body flag for writes with a body, query flag for DELETE."""
        value = self.request.data.get('acknowledge_conflicts') if hasattr(self.request.data, 'get') else None
        if value is None:
            value = self.request.query_params.get('acknowledge_conflicts')
        return str(value).lower() in ('1', 'true', 'yes')


CONFLICT_RESPONSES = {409: ConflictErrorSerializer}


@extend_schema_view(
    get=extend_schema(summary='My weekly availability windows (tutor local clock)'),
    post=extend_schema(summary='Add one weekly window', responses={201: TeacherAvailabilitySerializer}),
)
class TeacherAvailabilityManageView(TutorScheduleMixin, generics.ListCreateAPIView):
    serializer_class = TeacherAvailabilitySerializer

    def get_queryset(self):
        profile = getattr(self.request.user, 'teacher_profile', None)
        return profile.availabilities.all() if profile else TeacherAvailability.objects.none()

    def create(self, request, *args, **kwargs):
        teacher = self.get_teacher()
        serializer = self.get_serializer(data=request.data)
        availability.create_row(teacher, serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TeacherAvailabilityDetailView(TutorScheduleMixin, APIView):
    @extend_schema(summary='Edit one weekly window', request=AvailabilityUpdateSerializer,
                   responses={200: AvailabilityChangeSerializer, **CONFLICT_RESPONSES})
    def patch(self, request, pk):
        teacher = self.get_teacher()
        row = get_object_or_404(teacher.availabilities, pk=pk)
        serializer = AvailabilityUpdateSerializer(row, data=request.data, partial=True, context={'teacher': teacher})
        outcome = availability.update_row(teacher, row, serializer)
        return Response({'availability': TeacherAvailabilitySerializer(outcome.obj).data, 'conflicts': outcome.conflicts})

    @extend_schema(summary='Delete one weekly window',
                   parameters=[OpenApiParameter('acknowledge_conflicts', bool, description='Apply even if confirmed lessons fall outside the new hours.')],
                   responses={200: DeletedSerializer, **CONFLICT_RESPONSES})
    def delete(self, request, pk):
        teacher = self.get_teacher()
        get_object_or_404(teacher.availabilities, pk=pk)
        outcome = availability.delete_row(teacher, pk, acknowledged=self.acknowledged())
        return Response({'deleted': True, 'conflicts': outcome.conflicts})


class TeacherAvailabilityReplaceView(TutorScheduleMixin, APIView):
    @extend_schema(summary='Atomically replace the whole weekly matrix', request=AvailabilityMatrixSerializer,
                   responses={200: AvailabilityReplaceResultSerializer, **CONFLICT_RESPONSES})
    def put(self, request):
        teacher = self.get_teacher()
        serializer = AvailabilityMatrixSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        outcome = availability.replace_weekly_matrix(
            teacher, serializer.validated_data['rows'], acknowledged=serializer.validated_data['acknowledge_conflicts'])
        return Response({'rows': TeacherAvailabilitySerializer(outcome.obj, many=True).data, 'conflicts': outcome.conflicts})


@extend_schema_view(
    get=extend_schema(summary='My upcoming time off'),
    post=extend_schema(summary='Add time off', request=TimeOffCreateSerializer,
                       responses={201: TimeOffResultSerializer, **CONFLICT_RESPONSES}),
)
class TeacherTimeOffListView(TutorScheduleMixin, generics.ListCreateAPIView):
    serializer_class = TeacherTimeOffSerializer

    def get_queryset(self):
        profile = getattr(self.request.user, 'teacher_profile', None)
        return profile.time_off.filter(end_utc__gt=clock.now()) if profile else TeacherTimeOff.objects.none()

    def create(self, request, *args, **kwargs):
        teacher = self.get_teacher()
        serializer = TimeOffCreateSerializer(data=request.data, context={'teacher': teacher})
        serializer.is_valid(raise_exception=True)
        data = {k: v for k, v in serializer.validated_data.items() if k != 'acknowledge_conflicts'}
        outcome = availability.create_time_off(teacher, data, acknowledged=self.acknowledged())
        return Response({'time_off': TeacherTimeOffSerializer(outcome.obj).data, 'conflicts': outcome.conflicts},
                        status=status.HTTP_201_CREATED)


class TeacherTimeOffDetailView(TutorScheduleMixin, APIView):
    @extend_schema(summary='Delete a time-off period', responses={200: DeletedSerializer})
    def delete(self, request, pk):
        teacher = self.get_teacher()
        get_object_or_404(teacher.time_off, pk=pk)
        outcome = availability.delete_time_off(teacher, pk)
        return Response({'deleted': True, 'conflicts': outcome.conflicts})


@extend_schema_view(
    get=extend_schema(summary='My upcoming specific-date overrides'),
    post=extend_schema(summary='Add or remove hours on one date', request=DateOverrideCreateSerializer,
                       responses={201: DateOverrideResultSerializer, **CONFLICT_RESPONSES}),
)
class TeacherDateOverrideListView(TutorScheduleMixin, generics.ListCreateAPIView):
    serializer_class = TeacherDateOverrideSerializer

    def get_queryset(self):
        profile = getattr(self.request.user, 'teacher_profile', None)
        if profile is None:
            return TeacherDateOverride.objects.none()
        return profile.date_overrides.filter(date__gte=clock.now().date() - timedelta(days=1))

    def create(self, request, *args, **kwargs):
        teacher = self.get_teacher()
        serializer = DateOverrideCreateSerializer(data=request.data, context={'teacher': teacher})
        serializer.is_valid(raise_exception=True)
        data = {k: v for k, v in serializer.validated_data.items() if k != 'acknowledge_conflicts'}
        outcome = availability.create_override(teacher, data, acknowledged=self.acknowledged())
        return Response({'override': TeacherDateOverrideSerializer(outcome.obj).data, 'conflicts': outcome.conflicts},
                        status=status.HTTP_201_CREATED)


class TeacherDateOverrideDetailView(TutorScheduleMixin, APIView):
    @extend_schema(summary='Delete a date override',
                   parameters=[OpenApiParameter('acknowledge_conflicts', bool, description='Apply even if confirmed lessons fall outside the new hours.')],
                   responses={200: DeletedSerializer, **CONFLICT_RESPONSES})
    def delete(self, request, pk):
        teacher = self.get_teacher()
        get_object_or_404(teacher.date_overrides, pk=pk)
        outcome = availability.delete_override(teacher, pk, acknowledged=self.acknowledged())
        return Response({'deleted': True, 'conflicts': outcome.conflicts})


class TeacherOwnProfileView(generics.RetrieveUpdateAPIView):
    # The signed-in tutor's own profile (T1c; docs/TUTOR_STATUS_MACHINE.md §8). Owner-only by construction (no id in the
    # URL). PATCH accepts only the whitelisted fields in teachers/profile.py and saves them with explicit update_fields.
    # (Comments, not a docstring: drf-spectacular would publish a docstring in the OpenAPI file, ERR-152.)
    serializer_class = TeacherOwnProfileSerializer
    permission_classes = (permissions.IsAuthenticated, IsTeacher)
    throttle_scope = 'teacher_profile'
    http_method_names = ('get', 'patch', 'head', 'options')

    def get_throttles(self):
        # Reads ride the normal per-user rate; writes also count against their own scope.
        if self.request.method == 'PATCH':
            return [UserRateThrottle(), ScopedRateThrottle()]
        return [UserRateThrottle()]

    def get_object(self):
        try:
            return TeacherProfile.objects.select_related('user').get(user=self.request.user)
        except TeacherProfile.DoesNotExist:
            raise NotFound('No tutor profile exists for this account.') from None

    def perform_update(self, serializer):
        update_own_profile(serializer.instance, serializer.validated_data)
        # The response reports the live service-owned values, not the copy loaded before a concurrent status change.
        serializer.instance.refresh_from_db(fields=['status', 'is_verified', 'is_active', 'sla_strikes', 'updated_at'])


class TeacherPowerBackupView(generics.UpdateAPIView):
    serializer_class = PowerBackupSerializer
    permission_classes = (permissions.IsAuthenticated, IsTeacher)
    http_method_names = ('patch',)
    throttle_classes = (ObservedScopedRateThrottle,)
    throttle_scope = 'teacher_settings'

    def get_object(self):
        if not hasattr(self.request.user, 'teacher_profile'):
            raise PermissionDenied('A teacher profile is required.')
        return self.request.user.teacher_profile


@extend_schema(request=TeacherAssetCommitSerializer, responses=TeacherAssetCommitResponseSerializer)
class TeacherAssetCommitView(APIView):
    permission_classes = (permissions.IsAuthenticated, IsTeacher)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'upload'

    def post(self, request):
        teacher = getattr(request.user, 'teacher_profile', None)
        if teacher is None:
            raise NotFound('No tutor profile exists for this account.')
        serializer = TeacherAssetCommitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            asset = commit_asset(teacher, actor=request.user,
                                 kind=serializer.validated_data['kind'],
                                 quarantine_key=serializer.validated_data['key'],
                                 expected_etag=serializer.validated_data['etag'])
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(TeacherAssetCommitResponseSerializer({
            'id': asset.id, 'kind': asset.kind, 'key': asset.object_key,
            'etag': asset.etag, 'content_type': asset.content_type,
        }).data, status=status.HTTP_200_OK)


@extend_schema(responses=OpenApiTypes.OBJECT)
class TeacherPrivateAssetDownloadView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ObservedScopedRateThrottle,)
    throttle_scope = 'private_asset'

    def get(self, request, kind):
        teacher = getattr(request.user, 'teacher_profile', None)
        if request.user.is_staff and request.query_params.get('teacher_id'):
            teacher = TeacherProfile.objects.filter(pk=request.query_params['teacher_id']).first()
        asset = TeacherAsset.objects.filter(teacher=teacher, kind=kind, replaced_at__isnull=True).first()
        if asset is None or kind not in {TeacherAsset.Kind.TEFL_CERTIFICATE, TeacherAsset.Kind.IDENTITY_DOCUMENT}:
            raise NotFound('Private asset not found.')
        if not (request.user.is_staff or request.user == teacher.user):
            return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)
        audit_private_access(request.user, teacher, asset.object_key)
        return Response({'download_url': generate_presigned_download_url(asset.object_key, private=True), 'expires_in': 900})
