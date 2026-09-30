import pytest
from rest_framework.test import APIClient
from apps.users.models import User
from apps.teachers.models import TeacherProfile
from apps.materials.models import Material

@pytest.mark.django_db
def test_health_check_endpoint():
    client = APIClient()
    response = client.get('/api/health/')
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["service"] == "esl_backend"

@pytest.mark.django_db
def test_materials_catalog_endpoint():
    Material.objects.create(
        title="AI in Global Enterprise",
        slug="ai-global-enterprise",
        category=Material.Category.BUSINESS,
        cefr_level=Material.CEFRLevel.B2,
        description="Comprehensive article analyzing generative AI productivity shifts in tech firms.",
        content_html="<p>Artificial Intelligence is transforming workplace dynamics...</p>"
    )

    client = APIClient()
    response = client.get('/api/v1/materials/')
    assert response.status_code == 200
    data = response.json()
    results = data.get("results", data)
    assert len(results) >= 1
    assert results[0]["title"] == "AI in Global Enterprise"
    assert results[0]["cefr_level"] == "B2"

@pytest.mark.django_db
def test_teacher_directory_endpoint(teacher_user):
    client = APIClient()
    response = client.get('/api/v1/teachers/')
    assert response.status_code == 200
    data = response.json()
    results = data.get("results", data)
    assert len(results) >= 1
    assert results[0]["is_verified"] is True
