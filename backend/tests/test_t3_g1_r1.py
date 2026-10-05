from datetime import timedelta
from unittest import mock

from cryptography.fernet import Fernet
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from apps.bookings.models import AttendanceAudit, Booking
from apps.bookings.retention import purge_attendance_payloads
from apps.common.crypto import decrypt_integration_secret
from apps.integrations.google_calendar import exchange_oauth_code
from apps.integrations.models import CalendarCredential
from apps.teachers.assets import _matches, commit_asset
from apps.teachers.models import TeacherAsset
from factories import make_booking


def test_t3_magic_bytes_are_format_specific():
    assert _matches(TeacherAsset.Kind.AVATAR, 'image/webp', b'RIFFxxxxWEBPdata')
    assert not _matches(TeacherAsset.Kind.AVATAR, 'image/webp', b'RIFFxxxxNOPEdata')
    assert _matches(TeacherAsset.Kind.INTRO_VIDEO, 'video/mp4', b'xxxxftypisom')
    assert not _matches(TeacherAsset.Kind.INTRO_VIDEO, 'video/mp4', b'ftyp')


def test_t3_commits_from_private_quarantine_to_final_bucket(teacher_user, fake_r2, settings,
                                                            django_capture_on_commit_callbacks):
    settings.CLOUDFLARE_R2_PRIVATE_BUCKET_NAME = 'private-assets'
    settings.CLOUDFLARE_R2_BUCKET_NAME = 'public-assets'
    quarantine = f'incoming/{teacher_user.user_id}/avatar.png'
    fake_r2.put_object(Bucket='private-assets', Key=quarantine, Body=b'\x89PNG\r\n\x1a\nbytes', ContentType='image/png')

    with django_capture_on_commit_callbacks(execute=True):      # the quarantine copy is deleted only after the DB commit
        asset = commit_asset(teacher_user, actor=teacher_user.user, kind=TeacherAsset.Kind.AVATAR,
                             quarantine_key=quarantine)
        assert ('private-assets', quarantine) in fake_r2.objects         # still there until the transaction commits

    assert asset.object_key.startswith(f'teachers/avatar/{teacher_user.user_id}/')
    assert fake_r2.objects[('public-assets', asset.object_key)]['body'].startswith(b'\x89PNG')
    assert ('private-assets', quarantine) not in fake_r2.objects


@override_settings(INTEGRATION_DATA_KEYS={}, INTEGRATION_DATA_ACTIVE_KEY='')
def test_g1_exchange_encrypts_refresh_token_and_consumes_state(teacher_user, settings):
    key = Fernet.generate_key().decode()
    settings.INTEGRATION_DATA_KEYS = {'v1': key}
    settings.INTEGRATION_DATA_ACTIVE_KEY = 'v1'
    cache.set('gcal:oauth:one-use', str(teacher_user.user_id), timeout=600)
    response = mock.Mock(status_code=200)
    response.json.return_value = {'refresh_token': 'refresh-secret', 'scope': 'calendar.events calendar.freebusy'}

    with mock.patch('apps.integrations.google_calendar.requests.post', return_value=response):
        assert exchange_oauth_code(teacher_user.user, 'code', 'one-use') is True

    credential = CalendarCredential.objects.get(user=teacher_user.user)
    assert decrypt_integration_secret(credential.refresh_token_enc) == 'refresh-secret'
    assert cache.get('gcal:oauth:one-use') is None
    assert teacher_user.user.refresh_from_db() is None
    assert teacher_user.user.google_calendar_token is None


def test_r1_purges_only_old_unprotected_raw_payloads(teacher_user, student_user):
    now = timezone.now()
    old = make_booking(teacher_user, student_user, status=Booking.Status.COMPLETED,
                       start=now - timedelta(days=100), escrow_cleared_at=now)
    disputed = make_booking(teacher_user, student_user, status=Booking.Status.DISPUTED,
                            start=now - timedelta(days=100))
    for booking in (old, disputed):
        row = AttendanceAudit.objects.create(booking=booking, participant_email='student@example.com',
                                             raw_payload={'ip': '192.0.2.1'})
        AttendanceAudit.objects.filter(pk=row.pk).update(created_at=now - timedelta(days=91))

    result = purge_attendance_payloads(now=now)

    assert result['purged_count'] == 1
    assert AttendanceAudit.objects.get(booking=old).raw_payload == {}
    assert AttendanceAudit.objects.get(booking=disputed).raw_payload == {'ip': '192.0.2.1'}
