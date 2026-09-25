import pytest
from apps.users.models import User
from apps.teachers.models import TeacherProfile, TeacherAvailability
from datetime import time

@pytest.fixture(autouse=True)
def test_environment_settings(settings):
    """
    Configures isolated in-memory cache and eager Celery execution
    so tests execute immediately in milliseconds without external Redis dependencies.
    """
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'isolated-test-cache',
        }
    }
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.CELERY_BROKER_URL = 'memory://'
    settings.CELERY_RESULT_BACKEND = 'cache+memory://'

@pytest.fixture
def teacher_user(db):
    user = User.objects.create_user(
        username="test_tutor",
        email="tutor@test.com",
        password="password123",
        role=User.Role.TEACHER,
        country="ZA",
        timezone="Africa/Johannesburg"
    )
    profile = TeacherProfile.objects.create(
        user=user,
        headline="TEFL Tutor",
        accent=TeacherProfile.Accent.SOUTH_AFRICAN,
        price_per_25min_usd=9.00,
        is_verified=True,
        is_active=True
    )
    # Give availability on Monday from 09:00 to 12:00 SAST
    TeacherAvailability.objects.create(
        teacher=profile,
        day_of_week=0, # Monday
        start_time=time(9, 0),
        end_time=time(12, 0),
        is_active=True
    )
    return profile

@pytest.fixture
def student_user(db):
    return User.objects.create_user(
        username="test_student",
        email="student@test.com",
        password="password123",
        role=User.Role.STUDENT,
        country="JP",
        timezone="Asia/Tokyo"
    )
