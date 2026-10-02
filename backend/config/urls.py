from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from drf_spectacular.views import SpectacularAPIView

def health_check(request):
    return JsonResponse({
        "status": "healthy",
        "service": "esl_backend",
        "version": "1.0.0"
    })

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health-check'),
    path('api/schema/', SpectacularAPIView.as_view(), name='api-schema'),  # admin-only (SPECTACULAR_SETTINGS)
    path('api/v1/auth/', include('apps.users.urls')),
    path('api/v1/teachers/', include('apps.teachers.urls')),
    path('api/v1/bookings/', include('apps.bookings.urls')),
    path('api/v1/materials/', include('apps.materials.urls')),
    path('api/v1/payments/', include('apps.payments.urls')),
    path('api/v1/admin/', include('apps.admin_api.urls')),
    path('api/v1/teacher/students/', include('apps.crm.urls')),
    path('api/v1/student/', include('apps.srs.urls')),
    path('api/v1/integrations/', include('apps.integrations.urls')),
]
