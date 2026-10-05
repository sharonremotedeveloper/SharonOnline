from django.urls import path
from .views import (
    TeacherListView, TeacherDetailView, TeacherAvailabilityManageView, TeacherAvailabilityDetailView,
    TeacherAvailabilityReplaceView, TeacherTimeOffListView, TeacherTimeOffDetailView, TeacherDateOverrideListView,
    TeacherDateOverrideDetailView, TeacherOwnProfileView, TeacherPowerBackupView,
)

urlpatterns = [
    path('', TeacherListView.as_view(), name='teacher-list'),
    path('me/', TeacherOwnProfileView.as_view(), name='teacher-own-profile'),
    path('<uuid:id>/', TeacherDetailView.as_view(), name='teacher-detail'),
    path('availability/manage/', TeacherAvailabilityManageView.as_view(), name='teacher-availability-manage'),
    path('availability/manage/<uuid:pk>/', TeacherAvailabilityDetailView.as_view(), name='teacher-availability-detail'),
    path('availability/replace/', TeacherAvailabilityReplaceView.as_view(), name='teacher-availability-replace'),
    path('availability/time-off/', TeacherTimeOffListView.as_view(), name='teacher-time-off'),
    path('availability/time-off/<uuid:pk>/', TeacherTimeOffDetailView.as_view(), name='teacher-time-off-detail'),
    path('availability/overrides/', TeacherDateOverrideListView.as_view(), name='teacher-date-overrides'),
    path('availability/overrides/<uuid:pk>/', TeacherDateOverrideDetailView.as_view(), name='teacher-date-override-detail'),
    path('profile/power-backup/', TeacherPowerBackupView.as_view(), name='teacher-power-backup'),
]
