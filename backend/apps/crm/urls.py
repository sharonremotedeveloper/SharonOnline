from django.urls import path
from apps.crm.views import TeacherStudentDossierListView, TeacherStudentDossierUpdateView

urlpatterns = [
    path('', TeacherStudentDossierListView.as_view(), name='teacher-students-dossier'),
    path('<uuid:student_id>/dossier/', TeacherStudentDossierUpdateView.as_view(), name='teacher-student-dossier-update'),
]
