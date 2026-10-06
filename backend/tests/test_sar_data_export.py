import io
import json
import zipfile
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.teachers.models import TeacherProfile

User = get_user_model()


@pytest.fixture
def auth_client():
    client = APIClient()
    user = User.objects.create_user(
        username="sar_student",
        email="student_sar@example.com",
        password="ValidPassword123!",
        role=User.Role.STUDENT,
        country="JP",
        timezone="Asia/Tokyo",
    )
    client.force_authenticate(user=user)
    return client, user


@pytest.fixture
def teacher_auth_client():
    client = APIClient()
    user = User.objects.create_user(
        username="sar_teacher",
        email="teacher_sar@example.com",
        password="ValidPassword123!",
        role=User.Role.TEACHER,
        country="ZA",
        timezone="Africa/Johannesburg",
    )
    TeacherProfile.objects.create(
        user=user,
        headline="Senior TEFL Expert",
        bio="Passionate educator with 10 years experience",
        specialties=["Business English", "TOEIC"],
    )
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
def test_sar_export_unauthenticated_rejected():
    client = APIClient()
    resp = client.get("/api/v1/auth/me/data-export/")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_sar_export_json_format(auth_client):
    client, user = auth_client
    resp = client.get("/api/v1/auth/me/data-export/?format=json")
    assert resp.status_code == 200
    data = resp.json()

    assert "export_metadata" in data
    assert data["export_metadata"]["legal_basis"].startswith("Data Subject Access Request")
    assert "account_profile" in data
    assert data["account_profile"]["email"] == "student_sar@example.com"
    assert data["account_profile"]["timezone"] == "Asia/Tokyo"

    # Verify sensitive operational fields are NEVER leaked
    assert "password" not in data["account_profile"]
    assert "google_calendar_token" not in data["account_profile"]
    assert "booking_blocked_reason" not in data["account_profile"]


@pytest.mark.django_db
def test_sar_export_zip_format(auth_client):
    client, _ = auth_client
    resp = client.get("/api/v1/auth/me/data-export/")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/zip"
    assert "attachment" in resp["Content-Disposition"]

    # Verify zip content
    zip_buf = io.BytesIO(resp.content)
    with zipfile.ZipFile(zip_buf, "r") as zf:
        file_names = zf.namelist()
        assert "data_export.json" in file_names
        assert "README.txt" in file_names

        json_bytes = zf.read("data_export.json")
        data = json.loads(json_bytes.decode("utf-8"))
        assert data["account_profile"]["username"] == "sar_student"


@pytest.mark.django_db
def test_sar_export_teacher_profile(teacher_auth_client):
    client, _ = teacher_auth_client
    resp = client.get("/api/v1/auth/me/data-export/?format=json")
    assert resp.status_code == 200
    data = resp.json()

    assert "teacher_profile" in data
    assert data["teacher_profile"]["headline"] == "Senior TEFL Expert"
    assert "Business English" in data["teacher_profile"]["specialties"]
