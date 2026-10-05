import pytest
from django.urls import include, path
from django.utils import timezone
from rest_framework.test import APIClient

from apps.notifications.models import Notification, NotificationPreference

import factories as f

urlpatterns = [path('api/v1/notifications/', include('apps.notifications.urls'))]


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture(autouse=True)
def notification_urls(settings):
    settings.ROOT_URLCONF = __name__


@pytest.fixture
def notification_users():
    return f.make_student(email='student-one@example.com'), f.make_student(email='student-two@example.com')


def _notification(user, key, *, read=False, error=''):
    return Notification.objects.create(
        user=user, kind='sample_lesson_notice', title='Lesson', body='Body', payload={'booking_id': '1'},
        idempotency_key=key, in_app=True, read_at=None if not read else timezone.now(),
        email_state=Notification.EmailState.SENT, email_last_error=error,
    )


@pytest.mark.django_db
def test_notification_list_is_paginated_and_owner_only(api, notification_users):
    owner, other = notification_users
    first = _notification(owner, 'api:one')
    _notification(owner, 'api:two')
    _notification(other, 'api:other')
    api.force_authenticate(owner)

    response = api.get('/api/v1/notifications/')

    assert response.status_code == 200
    assert response.data['count'] == 2
    assert {row['id'] for row in response.data['results']} == {str(first.id), str(Notification.objects.get(idempotency_key='api:two').id)}
    assert 'email_last_error' not in response.data['results'][0]


@pytest.mark.django_db
def test_notification_read_and_read_all_are_owner_scoped(api, notification_users):
    owner, other = notification_users
    row = _notification(owner, 'api:read')
    foreign = _notification(other, 'api:foreign')
    api.force_authenticate(owner)

    assert api.post(f'/api/v1/notifications/{row.id}/read/').status_code == 200
    assert Notification.objects.get(pk=row.pk).read_at is not None
    assert api.post(f'/api/v1/notifications/{foreign.id}/read/').status_code == 404
    assert api.post('/api/v1/notifications/read-all/').status_code == 200


@pytest.mark.django_db
def test_unread_count_and_preferences_enforce_mandatory_kinds(api, notification_users):
    owner, _other = notification_users
    _notification(owner, 'api:unread')
    api.force_authenticate(owner)

    assert api.get('/api/v1/notifications/unread-count/').data == {'count': 1}
    response = api.patch('/api/v1/notifications/preferences/', {
        'email_by_kind': {'sample_lesson_notice': False},
        'in_app_by_kind': {'sample_lesson_notice': False},
    }, format='json')
    assert response.status_code == 200
    assert NotificationPreference.objects.get(user=owner).email_by_kind['sample_lesson_notice'] is False

    rejected = api.patch('/api/v1/notifications/preferences/', {
        'email_by_kind': {'admin_alert': False},
    }, format='json')
    assert rejected.status_code == 400


@pytest.mark.django_db
def test_staff_can_see_error_code_but_regular_users_cannot(api, notification_users):
    owner, _other = notification_users
    _notification(owner, 'api:error', error='provider_error')
    api.force_authenticate(owner)
    assert 'email_last_error' not in api.get('/api/v1/notifications/').data['results'][0]
    owner.is_staff = True
    owner.save(update_fields=['is_staff'])
    assert api.get('/api/v1/notifications/').data['results'][0]['email_last_error'] == 'provider_error'
