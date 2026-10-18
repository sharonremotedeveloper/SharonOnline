"""
Staff management of lesson materials (Wave 2, docs/ADMIN_CONTENT_MANAGEMENT_PENDING.md; ADM-07 materials half, Task 15.4).

    GET    /api/v1/admin/materials/            every material (drafts too); ?status=draft|published, ?search=
    POST   /api/v1/admin/materials/            create (always a draft unless is_published is sent)
    GET    /api/v1/admin/materials/<id>/       one material with its (cleaned) lesson HTML
    PATCH  /api/v1/admin/materials/<id>/       edit / publish / unpublish; remove_pdf / remove_audio detach a file
    DELETE /api/v1/admin/materials/<id>/       drafts only (a published material is unpublished first)

Only `IsPlatformAdmin` (decision 1). Workflow is Draft -> Published (decision 3). `content_html` is cleaned by
`Material.save` (materials/sanitize.py). Files are attached with the existing quarantine flow: presign an
`incoming/<admin id>/...` key, upload, then POST /api/v1/materials/<id>/assets/commit/ (materials/assets.py checks it).
"""
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.schema import ErrorCodeSerializer
from apps.common.throttles import ResilientScopedRateThrottle as ScopedRateThrottle
from apps.materials.models import Material
from apps.materials.sanitize import clean_lesson_html
from apps.users.permissions import IsPlatformAdmin

LIST_LIMIT = 500


class AdminMaterialSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    slug = serializers.CharField()
    category = serializers.CharField()
    category_display = serializers.CharField()
    cefr_level = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    is_published = serializers.BooleanField()
    pdf_url = serializers.CharField(allow_blank=True)
    audio_url = serializers.CharField(allow_blank=True)
    updated_at = serializers.DateTimeField()


class AdminMaterialDetailSerializer(AdminMaterialSerializer):
    content_html = serializers.CharField(allow_blank=True)


class AdminMaterialListSerializer(serializers.Serializer):
    materials = AdminMaterialSerializer(many=True)
    published = serializers.IntegerField()
    drafts = serializers.IntegerField()


class AdminMaterialWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    slug = serializers.SlugField(max_length=255)
    category = serializers.ChoiceField(choices=Material.Category.choices)
    cefr_level = serializers.ChoiceField(choices=Material.CEFRLevel.choices)
    description = serializers.CharField(allow_blank=True, required=False, default='', max_length=2000)
    content_html = serializers.CharField(allow_blank=True, required=False, default='', max_length=200_000)
    is_published = serializers.BooleanField(required=False, default=False)
    remove_pdf = serializers.BooleanField(required=False, default=False)
    remove_audio = serializers.BooleanField(required=False, default=False)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('A title is required.')
        return value

    def validate_slug(self, value):
        taken = Material.objects.filter(slug=value)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError('Another material already uses this slug.')
        return value


def _row(material, detail=False):
    row = {'id': material.id, 'title': material.title, 'slug': material.slug, 'category': material.category,
           'category_display': material.get_category_display(), 'cefr_level': material.cefr_level,
           'description': material.description, 'is_published': material.is_published,
           'pdf_url': material.resolved_pdf_url, 'audio_url': material.resolved_audio_url,
           'updated_at': material.updated_at}
    if detail:
        row['content_html'] = clean_lesson_html(material.content_html)
    return row


def _detail(material):
    return AdminMaterialDetailSerializer(_row(material, detail=True)).data


class _AdminMaterialView(APIView):
    permission_classes = (permissions.IsAuthenticated, IsPlatformAdmin)
    throttle_classes = (ScopedRateThrottle,)

    def get_throttles(self):
        self.throttle_scope = 'admin_read' if self.request.method == 'GET' else 'admin_content'
        return super().get_throttles()


class AdminMaterialListView(_AdminMaterialView):
    @extend_schema(operation_id='admin_materials_list', responses={200: AdminMaterialListSerializer}, parameters=[
        OpenApiParameter('status', str, enum=['draft', 'published']), OpenApiParameter('search', str)])
    def get(self, request):
        qs = Material.objects.order_by('-updated_at')
        wanted = request.query_params.get('status')
        if wanted in ('draft', 'published'):
            qs = qs.filter(is_published=wanted == 'published')
        search = (request.query_params.get('search') or '').strip()[:100]
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search) | Q(slug__icontains=search))
        published = Material.objects.filter(is_published=True).count()
        return Response(AdminMaterialListSerializer({
            'materials': [_row(m) for m in qs[:LIST_LIMIT]],
            'published': published,
            'drafts': Material.objects.count() - published,
        }).data)

    @extend_schema(operation_id='admin_materials_create', request=AdminMaterialWriteSerializer,
                   responses={201: AdminMaterialDetailSerializer, 400: ErrorCodeSerializer})
    def post(self, request):
        serializer = AdminMaterialWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop('remove_pdf'), data.pop('remove_audio')
        material = Material.objects.create(**data)
        return Response(_detail(material), status=status.HTTP_201_CREATED)


class AdminMaterialDetailView(_AdminMaterialView):
    @extend_schema(operation_id='admin_materials_retrieve', responses={200: AdminMaterialDetailSerializer})
    def get(self, request, material_id):
        return Response(_detail(get_object_or_404(Material, pk=material_id)))

    @extend_schema(operation_id='admin_materials_update', request=AdminMaterialWriteSerializer,
                   responses={200: AdminMaterialDetailSerializer, 400: ErrorCodeSerializer})
    def patch(self, request, material_id):
        material = get_object_or_404(Material, pk=material_id)
        serializer = AdminMaterialWriteSerializer(material, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if data.pop('remove_pdf', False):
            material.pdf_file, material.pdf_file_url = None, ''
        if data.pop('remove_audio', False):
            material.audio_snippet_file, material.audio_snippet_url = None, ''
        for name, value in data.items():
            setattr(material, name, value)
        material.save()
        return Response(_detail(material))

    @extend_schema(operation_id='admin_materials_destroy', responses={204: None, 409: ErrorCodeSerializer})
    def delete(self, request, material_id):
        material = get_object_or_404(Material, pk=material_id)
        if material.is_published:
            return Response({'error': 'Unpublish this material before deleting it.', 'code': 'material_published'},
                            status=status.HTTP_409_CONFLICT)
        material.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
