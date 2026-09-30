import pytest
from rest_framework.test import APIClient
from apps.users.models import User
from apps.teachers.models import TeacherProfile
from apps.crm.models import StudentTutorDossier

@pytest.mark.django_db
def test_crm_dossier_access_security(student_user, teacher_user):
    client = APIClient()

    # Student cannot access teacher CRM dossier
    client.force_authenticate(user=student_user)
    res = client.get('/api/v1/teacher/students/')
    assert res.status_code == 403

    # Teacher can access CRM endpoint
    client.force_authenticate(user=teacher_user.user)
    res = client.get('/api/v1/teacher/students/')
    assert res.status_code == 200


@pytest.mark.django_db
def test_teacher_can_update_student_dossier(teacher_user, student_user):
    dossier = StudentTutorDossier.objects.create(
        teacher=teacher_user,
        student=student_user,
        private_pedagogical_notes="Initial baseline notes",
        common_grammar_mistakes=["prepositions"]
    )

    client = APIClient()
    client.force_authenticate(user=teacher_user.user)

    # List dossiers
    list_res = client.get('/api/v1/teacher/students/')
    assert list_res.status_code == 200
    data = list_res.json()
    assert any(d['student_id'] == str(student_user.id) for d in data)

    # Patch dossier with updated notes and mistakes
    patch_res = client.patch(
        f'/api/v1/teacher/students/{student_user.id}/dossier/',
        {
            "private_pedagogical_notes": "Significant progress on passive voice; focus next on conditional clauses.",
            "common_grammar_mistakes": ["prepositions", "second conditional inversion"]
        },
        format='json'
    )
    assert patch_res.status_code == 200
    assert patch_res.json()['success'] is True

    dossier.refresh_from_db()
    assert "passive voice" in dossier.private_pedagogical_notes
    assert "second conditional inversion" in dossier.common_grammar_mistakes


@pytest.mark.django_db
def test_crm_dossier_edge_cases(teacher_user):
    import uuid
    client = APIClient()

    # 1. Unauthenticated request -> 401 or 403
    unauth_res = client.get('/api/v1/teacher/students/')
    assert unauth_res.status_code in [401, 403]

    # 2. Patching non-existent student -> 404
    client.force_authenticate(user=teacher_user.user)
    fake_student_id = uuid.uuid4()
    not_found_res = client.patch(
        f'/api/v1/teacher/students/{fake_student_id}/dossier/',
        {"private_pedagogical_notes": "Note for non-existent student"},
        format='json'
    )
    assert not_found_res.status_code == 404

