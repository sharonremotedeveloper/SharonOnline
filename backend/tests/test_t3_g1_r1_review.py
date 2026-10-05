from unittest import mock

import pytest
from rest_framework.test import APIRequestFactory

from apps.integrations.views import GoogleCalendarCallbackView
from apps.teachers.assets import commit_asset
from apps.teachers.models import TeacherAsset


def test_google_callback_does_not_return_provider_exception_text(teacher_user):
    request = APIRequestFactory().get('/api/v1/integrations/google-calendar/callback/', {
        'state': 'state', 'code': 'code',
    })
    with mock.patch('apps.integrations.views.oauth_state_user', return_value=teacher_user.user), \
            mock.patch('apps.integrations.views.exchange_oauth_code', side_effect=RuntimeError('secret provider detail')):
        response = GoogleCalendarCallbackView.as_view()(request)

    assert response.status_code == 400
    assert response.data == {'error': 'Google Calendar connection could not be completed.'}
    assert 'secret provider detail' not in str(response.data)


def test_commit_asset_removes_copied_object_when_database_work_rolls_back(teacher_user, fake_r2, settings):
    settings.CLOUDFLARE_R2_PRIVATE_BUCKET_NAME = 'private-assets'
    settings.CLOUDFLARE_R2_BUCKET_NAME = 'public-assets'
    quarantine = f'incoming/{teacher_user.user_id}/avatar.png'
    fake_r2.put_object(Bucket='private-assets', Key=quarantine, Body=b'\x89PNG\r\n\x1a\nbytes', ContentType='image/png')

    with mock.patch('apps.teachers.assets._apply_profile_asset', side_effect=RuntimeError('db failure')):
        with pytest.raises(RuntimeError, match='db failure'):
            commit_asset(teacher_user, actor=teacher_user.user, kind=TeacherAsset.Kind.AVATAR,
                         quarantine_key=quarantine)

    assert ('private-assets', quarantine) in fake_r2.objects
    assert not any(bucket == 'public-assets' for bucket, _key in fake_r2.objects)


def test_commit_and_callback_contracts_use_typed_serializers():
    from apps.integrations.serializers import GoogleCalendarCallbackSerializer
    from apps.teachers.serializers import TeacherAssetCommitSerializer

    assert GoogleCalendarCallbackSerializer(data={'state': 'x', 'code': 'y'}).is_valid()
    assert not GoogleCalendarCallbackSerializer(data={'state': ''}).is_valid()
    assert TeacherAssetCommitSerializer(data={'kind': 'avatar', 'key': 'k', 'etag': 'e'}).is_valid()
    assert not TeacherAssetCommitSerializer(data={'kind': 'avatar'}).is_valid()
