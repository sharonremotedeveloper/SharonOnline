from django.urls import path
from .views import (
    TeacherListView, TeacherDetailView, TeacherAvailabilityManageView, TeacherAvailabilityDetailView,
    TeacherAvailabilityReplaceView, TeacherTimeOffListView, TeacherTimeOffDetailView, TeacherDateOverrideListView,
    TeacherDateOverrideDetailView, TeacherOwnProfileView, TeacherPowerBackupView,
    TeacherAssetCommitView, TeacherPrivateAssetDownloadView,
)

from .application_views import TeacherApplicationView, TeacherApplicationSubmitView  # slice T5a
from .training_views import TeacherTrainingView, TeacherTrainingModuleView, TeacherTrainingCompleteView  # slice T6

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
    path('me/application/', TeacherApplicationView.as_view(), name='teacher-application'),
    path('me/application/submit/', TeacherApplicationSubmitView.as_view(), name='teacher-application-submit'),
    path('me/training/', TeacherTrainingView.as_view(), name='teacher-training'),
    path('me/training/<slug:slug>/', TeacherTrainingModuleView.as_view(), name='teacher-training-module'),
    path('me/training/<slug:slug>/complete/', TeacherTrainingCompleteView.as_view(), name='teacher-training-complete'),
    path('me/assets/commit/', TeacherAssetCommitView.as_view(), name='teacher-asset-commit'),
    path('me/assets/<str:kind>/download/', TeacherPrivateAssetDownloadView.as_view(), name='teacher-private-asset-download'),
]
