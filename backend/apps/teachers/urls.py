from django.urls import path
from .views import TeacherListView, TeacherDetailView, TeacherAvailabilityManageView

urlpatterns = [
    path('', TeacherListView.as_view(), name='teacher-list'),
    path('<uuid:id>/', TeacherDetailView.as_view(), name='teacher-detail'),
    path('availability/manage/', TeacherAvailabilityManageView.as_view(), name='teacher-availability-manage'),
]
