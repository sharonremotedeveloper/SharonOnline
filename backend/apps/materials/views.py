from rest_framework import generics, permissions
from .models import Material
from .serializers import MaterialListSerializer, MaterialDetailSerializer

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
