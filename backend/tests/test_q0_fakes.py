"""
Q0: shared fakes (tests/fakes.py) driven through the REAL integration code, so later slices can rely on them matching the
providers' HTTP contracts: Resend, Daily.co (rooms, tokens, presence), Google Calendar (events + freebusy + token) and an R2 stub.
"""
from datetime import timedelta

import pytest
from botocore.exceptions import ClientError
from django.utils import timezone

from apps.integrations.services import email as email_module      # the only module that calls Resend (N1c)
from apps.integrations.email import EmailDeliveryError, send_booking_confirmation_email, send_email
from apps.integrations.google_calendar import delete_teacher_gcal_event, sync_booking_to_teacher_gcal
from apps.integrations.services.daily import DailyApiError, DailyClient
from apps.common import r2_client
import factories as f


# ------------------------------------------------------------------ Resend
def test_fake_resend_records_sends(fake_resend):
    send_email('a@example.test', 'Hello', '<p>Hi</p>', 'Hi')
    assert len(fake_resend.sent) == 1
    sent = fake_resend.sent[0]
    assert sent['to'] == ['a@example.test'] and sent['subject'] == 'Hello' and sent['text'] == 'Hi'
    assert fake_resend.requests[0].headers['Authorization'].startswith('Bearer ')


def test_fake_resend_can_fail_with_a_status(fake_resend):
    fake_resend.fail_with(422)
    with pytest.raises(EmailDeliveryError, match='422'):
        send_email('a@example.test', 'x', '<p>x</p>')
    assert fake_resend.sent == []
    send_email('a@example.test', 'x', '<p>x</p>')          # one-shot failure by default
    assert len(fake_resend.sent) == 1


def test_fake_resend_network_error(fake_resend):
    fake_resend.fail_with_network_error()
    with pytest.raises(EmailDeliveryError):
        send_email('a@example.test', 'x', '<p>x</p>')


@pytest.mark.django_db
def test_fake_resend_with_attachments(fake_resend):
    booking = f.make_booking(status='confirmed')
    assert send_booking_confirmation_email(booking).status == 'sent'     # N1c returns the EmailResult
    assert fake_resend.sent[0]['attachments'][0]['filename'] == 'lesson-invite.ics'


def test_fake_resend_only_answers_resend(fake_resend):
    with pytest.raises(AssertionError, match='unexpected'):
        email_module.requests.post('https://example.test/other', json={}, timeout=5)


def test_fakes_insist_on_a_timeout(fake_resend):
    with pytest.raises(AssertionError, match='timeout'):
        email_module.requests.post('https://api.resend.com/emails', json={})


# ------------------------------------------------------------------ Daily.co
def test_fake_daily_room_lifecycle(fake_daily):
    client = DailyClient()
    room = client.ensure_room('lesson-1', 100, 200)
    assert room['name'] == 'lesson-1' and fake_daily.created == ['lesson-1']
    assert client.ensure_room('lesson-1', 100, 200) == room and fake_daily.created == ['lesson-1']     # reused as is
    moved = client.ensure_room('lesson-1', 300, 400)                                                  # window moves, same room
    assert moved['config']['exp'] == 400 and fake_daily.updated == ['lesson-1'] and fake_daily.created == ['lesson-1']
    assert client.delete_room('lesson-1') is True and 'lesson-1' not in fake_daily.rooms
    assert client.delete_room('lesson-1') is True                                                     # 404 counts as deleted


def test_fake_daily_tokens_and_presence(fake_daily):
    client = DailyClient()
    client.ensure_room('lesson-2', 1, 2)
    token = client.create_meeting_token('lesson-2', 'u1', 'User One', True, 1, 2)
    assert token.startswith('fake-daily-token-') and fake_daily.tokens[0]['user_id'] == 'u1' and fake_daily.tokens[0]['is_owner'] is True
    assert client.get_room_presence('lesson-2') == ('ok', [])
    fake_daily.set_presence('lesson-2', ['u1', 'u2'])
    state, roster = client.get_room_presence('lesson-2')
    assert state == 'ok' and [p['userId'] for p in roster] == ['u1', 'u2']
    assert client.get_room_presence('missing') == ('not_found', [])


def test_fake_daily_failures(fake_daily):
    client = DailyClient()
    fake_daily.fail_next('room_create', 500)
    with pytest.raises(DailyApiError, match='500'):
        client.ensure_room('lesson-3', 1, 2)
    fake_daily.fail_next('presence', 429)
    assert client.get_room_presence('lesson-3')[0] == 'rate_limited'
    fake_daily.fail_next('token', 401)
    with pytest.raises(DailyApiError, match='401'):
        client.create_meeting_token('lesson-3', 'u1', 'User', False, 1, 2)


def test_fake_daily_is_what_the_app_gets(fake_daily):
    from apps.integrations.services.daily import is_daily_configured
    assert is_daily_configured() and DailyClient().api_key == 'fake-daily-live-key'


# ------------------------------------------------------------------ Google Calendar
@pytest.mark.django_db
def test_fake_google_insert_and_delete(fake_google):
    booking = f.make_booking(status='confirmed')
    tutor = booking.teacher.user
    tutor.google_calendar_token = {'access_token': fake_google.access_token}
    tutor.save(update_fields=['google_calendar_token'])
    event_id = sync_booking_to_teacher_gcal(booking)
    assert event_id and fake_google.events[event_id]['start']['dateTime'] == booking.start_time_utc.isoformat()
    assert delete_teacher_gcal_event(tutor, event_id) is True
    assert event_id not in fake_google.events
    assert delete_teacher_gcal_event(tutor, event_id) is True          # 410 Gone counts as done


def test_fake_google_update_freebusy_and_token(fake_google):
    import requests as real_requests
    from apps.integrations import google_calendar
    http = google_calendar.requests
    base = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'
    auth = {'Authorization': f'Bearer {fake_google.access_token}'}
    created = http.post(base, headers=auth, json={'summary': 'a'}, timeout=5).json()
    updated = http.patch(f"{base}/{created['id']}", headers=auth, json={'summary': 'b'}, timeout=5)
    assert updated.status_code == 200 and fake_google.events[created['id']]['summary'] == 'b'
    start = timezone.now()
    fake_google.add_busy(start, start + timedelta(hours=1))
    busy = http.post('https://www.googleapis.com/calendar/v3/freeBusy', headers=auth, timeout=5,
                     json={'timeMin': start.isoformat(), 'timeMax': (start + timedelta(days=1)).isoformat(),
                           'items': [{'id': 'primary'}]}).json()
    assert len(busy['calendars']['primary']['busy']) == 1
    token = http.post('https://oauth2.googleapis.com/token', data={'grant_type': 'refresh_token'}, timeout=5)
    assert token.json()['access_token'] == fake_google.access_token
    fake_google.revoke()
    revoked = http.post('https://oauth2.googleapis.com/token', data={'grant_type': 'refresh_token'}, timeout=5)
    assert revoked.status_code == 400 and revoked.json()['error'] == 'invalid_grant'
    with pytest.raises(real_requests.HTTPError):
        revoked.raise_for_status()


def test_fake_google_rejects_a_missing_bearer(fake_google):
    from apps.integrations import google_calendar
    resp = google_calendar.requests.delete('https://www.googleapis.com/calendar/v3/calendars/primary/events/x', timeout=5)
    assert resp.status_code == 401


# ------------------------------------------------------------------ R2
def test_fake_r2_head_get_range_copy_delete(fake_r2):
    fake_r2.put_object(Bucket='b', Key='incoming/u1/a.pdf', Body=b'%PDF-1.7 rest of file', ContentType='application/pdf')
    head = fake_r2.head_object(Bucket='b', Key='incoming/u1/a.pdf')
    assert head['ContentLength'] == 21 and head['ContentType'] == 'application/pdf'
    etag = head['ETag']
    part = fake_r2.get_object(Bucket='b', Key='incoming/u1/a.pdf', Range='bytes=0-4', IfMatch=etag)
    assert part['Body'].read() == b'%PDF-'
    fake_r2.copy_object(Bucket='b', Key='final/x.pdf', CopySource={'Bucket': 'b', 'Key': 'incoming/u1/a.pdf'},
                        CopySourceIfMatch=etag)
    fake_r2.delete_object(Bucket='b', Key='incoming/u1/a.pdf')
    assert fake_r2.objects[('b', 'final/x.pdf')]['body'].startswith(b'%PDF')
    with pytest.raises(ClientError) as missing:
        fake_r2.head_object(Bucket='b', Key='incoming/u1/a.pdf')
    assert missing.value.response['Error']['Code'] == '404'
    fake_r2.delete_object(Bucket='b', Key='incoming/u1/a.pdf')          # idempotent, like S3


def test_fake_r2_etag_preconditions(fake_r2):
    fake_r2.put_object(Bucket='b', Key='k', Body=b'one')
    with pytest.raises(ClientError) as stale:
        fake_r2.get_object(Bucket='b', Key='k', IfMatch='"not-the-etag"')
    assert stale.value.response['Error']['Code'] == 'PreconditionFailed'
    with pytest.raises(ClientError):
        fake_r2.copy_object(Bucket='b', Key='k2', CopySource='b/k', CopySourceIfMatch='"nope"')


def test_fake_r2_is_what_the_app_gets(fake_r2, settings):
    assert r2_client.get_r2_client() is fake_r2
    url = r2_client.generate_presigned_download_url('private/vetting/x.pdf', expires_in=900)
    assert 'private/vetting/x.pdf' in url and 'X-Amz-Expires=900' in url
    assert fake_r2.presigned[-1]['ClientMethod'] == 'get_object'
