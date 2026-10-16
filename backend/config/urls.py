from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.decorators.http import require_safe
from drf_spectacular.views import SpectacularAPIView
from config import health, scheduler_heartbeat

def health_check(request):
    return JsonResponse({
        "status": "healthy",
        "service": "esl_backend",
        "version": "1.0.0"
    })


@require_safe
def readiness_check(request):
    ready = health.check_dependencies()
    response = JsonResponse({
        "status": "ready" if ready else "unavailable",
        "service": "esl_backend",
    }, status=200 if ready else 503)
    response["Cache-Control"] = "no-store"
    return response


@require_safe
def scheduler_readiness_check(request):
    ready = scheduler_heartbeat.is_fresh()
    response = JsonResponse({"status": "ready" if ready else "unavailable"}, status=200 if ready else 503)
    response["Cache-Control"] = "no-store"
    return response

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health-check'),
    path('api/ready/', readiness_check, name='readiness-check'),
    path('api/scheduler-ready/', scheduler_readiness_check, name='scheduler-readiness-check'),
    path('api/schema/', SpectacularAPIView.as_view(), name='api-schema'),  # admin-only (SPECTACULAR_SETTINGS)
    path('api/v1/auth/', include('apps.users.urls')),
    path('api/v1/teachers/', include('apps.teachers.urls')),
    path('api/v1/bookings/', include('apps.bookings.urls')),
    path('api/v1/materials/', include('apps.materials.urls')),
    path('api/v1/payments/', include('apps.payments.urls')),
    path('api/v1/refunds/', include('apps.payments.refund_urls')),
    path('api/v1/admin/', include('apps.admin_api.urls')),
    path('api/v1/teacher/students/', include('apps.crm.urls')),
    path('api/v1/student/', include('apps.srs.urls')),
    path('api/v1/integrations/', include('apps.integrations.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),     # slice N1b
]
