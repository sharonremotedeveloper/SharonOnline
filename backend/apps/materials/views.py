from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.users.permissions import IsPlatformAdmin

from .assets import AssetRejected, commit_material_asset
from .models import Material
from .serializers import (
    MaterialAssetCommitResponseSerializer, MaterialAssetCommitSerializer, MaterialDetailSerializer,
    MaterialListSerializer,
)

class MaterialListView(generics.ListAPIView):
    serializer_class = MaterialListSerializer
    permission_classes = (permissions.AllowAny,)

    def get_queryset(self):
        queryset = Material.objects.filter(is_approved=True)
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        cefr = self.request.query_params.get('cefr')
        if cefr:
            queryset = queryset.filter(cefr_level=cefr)
        return queryset

class MaterialDetailView(generics.RetrieveAPIView):
    queryset = Material.objects.filter(is_approved=True)
    serializer_class = MaterialDetailSerializer
    permission_classes = (permissions.AllowAny,)
    lookup_field = 'slug'


@extend_schema(request=MaterialAssetCommitSerializer, responses=MaterialAssetCommitResponseSerializer)
class MaterialAssetCommitView(APIView):
    """T3b: attach a quarantined PDF or audio upload to a material (admin only)."""
    permission_classes = (permissions.IsAuthenticated, IsPlatformAdmin)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'upload'

    def post(self, request, material_id):
        material = get_object_or_404(Material, pk=material_id)
        serializer = MaterialAssetCommitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            key, etag, content_type = commit_material_asset(
                material, actor=request.user, kind=data['kind'], quarantine_key=data['key'], expected_etag=data['etag'])
        except AssetRejected as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        url = material.resolved_pdf_url if data['kind'] == 'pdf' else material.resolved_audio_url
        return Response(MaterialAssetCommitResponseSerializer({
            'kind': data['kind'], 'key': key, 'url': url, 'etag': etag, 'content_type': content_type}).data)
