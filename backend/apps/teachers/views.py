from rest_framework import generics, permissions, filters, status
from rest_framework.response import Response
from django.db.models import Q
from .models import TeacherProfile, TeacherAvailability
from .serializers import TeacherListSerializer, TeacherDetailSerializer, TeacherAvailabilitySerializer

class TeacherListView(generics.ListAPIView):
    serializer_class = TeacherListSerializer
    permission_classes = (permissions.AllowAny,)

    def get_queryset(self):
        queryset = TeacherProfile.objects.filter(is_active=True, is_verified=True).select_related('user')
        
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

        # Max price filter
        max_price = self.request.query_params.get('max_price')
        if max_price:
            try:
                queryset = queryset.filter(price_per_25min_usd__lte=float(max_price))
            except ValueError:
                pass

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

        return queryset.order_by('-rating_avg', '-rating_count')

class TeacherDetailView(generics.RetrieveAPIView):
    queryset = TeacherProfile.objects.filter(is_active=True).select_related('user').prefetch_related('availabilities')
    serializer_class = TeacherDetailSerializer
    permission_classes = (permissions.AllowAny,)
    lookup_field = 'id'

class TeacherAvailabilityManageView(generics.ListCreateAPIView):
    serializer_class = TeacherAvailabilitySerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        if not hasattr(user, 'teacher_profile'):
            return TeacherAvailability.objects.none()
        return TeacherAvailability.objects.filter(teacher=user.teacher_profile)

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user.teacher_profile)
