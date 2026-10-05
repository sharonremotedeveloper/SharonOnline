"""Task 9.8: Zoom attendance - who a participant really is, idempotent events, Zoom's own clock, meeting.started."""
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.admin_api.models import DisputeCase
from apps.bookings.models import AttendanceAudit, Booking, BookingStatusChange
from apps.bookings.tasks import audit_attendance_and_noshows_task
from apps.integrations.zoom import ZoomError, zoom_client
from test_zoom_webhooks import generate_zoom_headers

S = Booking.Status
HOST = 'ZOOM-HOST-ACCOUNT'          # the platform's Zoom account: whoever opens the host (start) link joins as this user
MEETING = '98765432101'


@pytest.fixture
def lesson(teacher_user, student_user):
    start = timezone.now() - timedelta(minutes=2)
    return Booking.objects.create(teacher=teacher_user, student=student_user, start_time_utc=start,
                                  end_time_utc=start + timedelta(minutes=25), status=S.CONFIRMED,
                                  zoom_meeting_id=MEETING, zoom_join_url='https://zoom.us/j/1', zoom_start_url='https://zoom.us/s/1')


def send(event, participant=None, *, host_id=HOST, meeting_id=MEETING, event_id=None, **obj):
    body = {'event': event, 'event_id': event_id, 'payload': {'object': {'id': meeting_id, 'host_id': host_id, **obj}}}
    if participant is not None:
        body['payload']['object']['participant'] = participant
    raw = json.dumps(body).encode()
    res = APIClient().post('/api/v1/integrations/zoom/webhook/', data=raw, content_type='application/json', **generate_zoom_headers(raw))
    assert res.status_code == 200, res.content
    return res


def tutor(sess='t1', **kw):
    """The tutor on the host link: Zoom reports the host account's id, whatever name/e-mail the host account carries."""
    return {'id': HOST, 'user_id': sess, 'participant_uuid': sess, 'user_name': 'Host', 'email': 'platform@sharon.test', **kw}


def pupil(lesson, sess='s1', **kw):
    return {'id': '', 'user_id': sess, 'participant_uuid': sess, 'user_name': 'Student', 'email': lesson.student.email, **kw}


def join(lesson, p, minutes_ago=1):
    return send('meeting.participant_joined', {**p, 'join_time': (timezone.now() - timedelta(minutes=minutes_ago)).isoformat()})


def leave(lesson, p, minutes_ago=0):
    return send('meeting.participant_left', {**p, 'leave_time': (timezone.now() - timedelta(minutes=minutes_ago)).isoformat()})


def rows(lesson, **f):
    return AttendanceAudit.objects.filter(booking=lesson, **f)


# ------------------------------------------------------------------ who is the tutor
@pytest.mark.django_db
class TestTutorIdentity:
    def test_the_host_account_is_the_tutor_whatever_email_it_carries(self, lesson):
        join(lesson, tutor())
        a = rows(lesson).get()
        assert (a.participant_email, a.identity) == (lesson.teacher.user.email, 'host')
        lesson.refresh_from_db()
        assert lesson.status == S.IN_PROGRESS

    def test_host_without_an_email_is_still_explicitly_the_teacher(self, lesson):
        lesson.teacher.user.email = ''
        lesson.teacher.user.save(update_fields=['email'])
        join(lesson, tutor(email=''))
        audit = rows(lesson).get()
        assert audit.classification == 'teacher'
        assert audit.identity == 'host'

    def test_a_guest_who_types_the_tutors_email_is_not_the_tutor(self, lesson):
        join(lesson, {'id': '', 'user_id': 'g1', 'participant_uuid': 'g1', 'email': lesson.teacher.user.email})
        a = rows(lesson).get()
        assert a.participant_email == '' and a.identity == 'unmatched'
        assert not rows(lesson, participant_email=lesson.teacher.user.email).exists()
        lesson.refresh_from_db()
        assert lesson.status == S.CONFIRMED                 # nobody verified has arrived

    def test_a_signed_in_zoom_account_with_the_tutors_email_is(self, lesson):
        join(lesson, {'id': 'ACC-9', 'user_id': 'a1', 'participant_uuid': 'a1', 'email': lesson.teacher.user.email.upper()})
        a = rows(lesson).get()
        assert (a.participant_email, a.identity) == (lesson.teacher.user.email, 'account_email')

    def test_a_guest_typing_the_tutors_email_cannot_stop_the_no_show_verdict(self, lesson, zoom_never_held):
        Booking.objects.filter(pk=lesson.pk).update(start_time_utc=timezone.now() - timedelta(minutes=11),
                                                    end_time_utc=timezone.now() + timedelta(minutes=14))
        join(lesson, pupil(lesson))
        join(lesson, {'id': '', 'user_id': 'g1', 'participant_uuid': 'g1', 'email': lesson.teacher.user.email})
        with patch.object(zoom_client, 'get_meeting_status', return_value={'status': 'waiting', 'participant_count': 0}):
            audit_attendance_and_noshows_task()
        lesson.refresh_from_db()
        assert lesson.status == S.TEACHER_NO_SHOW


# ------------------------------------------------------------------ who is the student
@pytest.mark.django_db
class TestStudentIdentity:
    def test_the_student_is_recognised_by_their_email_ignoring_case(self, lesson):
        join(lesson, pupil(lesson, email=lesson.student.email.upper()))
        a = rows(lesson).get()
        assert (a.participant_email, a.identity) == (lesson.student.email, 'email')

    def test_a_stranger_is_not_defaulted_to_the_student(self, lesson):
        join(lesson, {'id': '', 'user_id': 'x1', 'participant_uuid': 'x1', 'email': 'stranger@elsewhere.test', 'user_name': 'Bob'})
        a = rows(lesson).get()
        assert (a.participant_email, a.identity) == ('', 'unmatched')
        assert not rows(lesson, participant_email=lesson.student.email).exists()

    def test_a_participant_with_no_email_at_all_is_unmatched(self, lesson):
        join(lesson, {'user_id': 'x1', 'participant_uuid': 'x1', 'user_name': 'Phone user'})
        assert rows(lesson).get().identity == 'unmatched'

    def test_identity_metadata_and_event_id_are_preserved(self, lesson):
        send('meeting.participant_joined', {
            **pupil(lesson), 'id': 'participant-7', 'registrant_id': 'registrant-9',
            'join_time': timezone.now().isoformat(),
        }, event_id='event-123')
        audit = rows(lesson).get()
        assert audit.classification == 'student'
        assert audit.participant_id == 'participant-7'
        assert audit.registrant_id == 'registrant-9'
        assert audit.host_id == HOST
        assert audit.event_ids == ['event-123']

    def test_a_stranger_does_not_save_the_student_from_a_no_show_verdict(self, lesson):
        Booking.objects.filter(pk=lesson.pk).update(start_time_utc=timezone.now() - timedelta(minutes=11),
                                                    end_time_utc=timezone.now() + timedelta(minutes=14))
        join(lesson, tutor())
        join(lesson, {'id': '', 'user_id': 'x1', 'participant_uuid': 'x1', 'email': 'stranger@elsewhere.test'})
        audit_attendance_and_noshows_task()
        lesson.refresh_from_db()
        assert lesson.status == S.STUDENT_NO_SHOW


# ------------------------------------------------------------------ idempotent events
@pytest.mark.django_db
class TestIdempotence:
    def test_the_same_join_delivered_twice_is_one_row_and_one_transition(self, lesson):
        p = {**tutor(), 'join_time': (timezone.now() - timedelta(minutes=1)).isoformat()}
        send('meeting.participant_joined', p)
        send('meeting.participant_joined', p)
        assert rows(lesson).count() == 1
        assert BookingStatusChange.objects.filter(booking=lesson, to_status=S.IN_PROGRESS).count() == 1

    def test_the_same_leave_delivered_twice_changes_nothing(self, lesson):
        join(lesson, tutor(), minutes_ago=20)
        p = {**tutor(), 'leave_time': (timezone.now() - timedelta(minutes=2)).isoformat()}
        send('meeting.participant_left', p)
        first = rows(lesson).get().total_minutes
        send('meeting.participant_left', p)
        assert rows(lesson).count() == 1 and rows(lesson).get().total_minutes == first == 18

    def test_a_retried_join_after_the_leave_does_not_erase_it(self, lesson):
        p = {**tutor(), 'join_time': (timezone.now() - timedelta(minutes=20)).isoformat()}
        send('meeting.participant_joined', p)
        leave(lesson, tutor(), minutes_ago=5)
        send('meeting.participant_joined', p)
        a = rows(lesson).get()
        assert a.leave_time_utc is not None and a.total_minutes == 15

    def test_rejoining_is_a_second_session_and_both_count(self, lesson):
        join(lesson, tutor('t1'), minutes_ago=24)
        leave(lesson, tutor('t1'), minutes_ago=14)
        join(lesson, tutor('t2'), minutes_ago=10)
        leave(lesson, tutor('t2'), minutes_ago=0)
        a = rows(lesson, participant_email=lesson.teacher.user.email)
        assert a.count() == 2 and sorted(x.total_minutes for x in a) == [10, 10]

    def test_rejoining_under_the_same_zoom_id_is_still_a_second_session(self, lesson):
        join(lesson, tutor('same'), minutes_ago=24)
        leave(lesson, tutor('same'), minutes_ago=14)
        join(lesson, tutor('same'), minutes_ago=10)                       # same id, after the first session ended
        leave(lesson, tutor('same'), minutes_ago=0)
        mins = sorted(x.total_minutes for x in rows(lesson, participant_email=lesson.teacher.user.email))
        assert mins == [10, 10]

    def test_leave_before_join_is_completed_by_the_join(self, lesson):
        leave(lesson, tutor(), minutes_ago=0)
        a = rows(lesson).get()
        assert a.join_time_utc is None and a.total_minutes == 0
        join(lesson, tutor(), minutes_ago=24)
        a.refresh_from_db()
        assert rows(lesson).count() == 1 and a.total_minutes in (23, 24)   # the leave was stamped a moment before this join

    def test_the_database_refuses_two_rows_for_one_session(self, lesson):
        from django.db import IntegrityError, transaction
        AttendanceAudit.objects.create(booking=lesson, participant_email='', zoom_session_id='dup')
        with pytest.raises(IntegrityError), transaction.atomic():
            AttendanceAudit.objects.create(booking=lesson, participant_email='', zoom_session_id='dup')


# ------------------------------------------------------------------ Zoom's clock, not ours
@pytest.mark.django_db
class TestTimes:
    def test_meeting_ended_closes_open_sessions_at_zoom_end_time(self, lesson):
        join(lesson, tutor(), minutes_ago=20)
        end = timezone.now() - timedelta(minutes=5)
        send('meeting.ended', end_time=end.isoformat())
        a = rows(lesson).get()
        assert abs((a.leave_time_utc - end).total_seconds()) < 1 and a.total_minutes == 15

    def test_meeting_ended_without_end_time_falls_back_to_now(self, lesson):
        join(lesson, tutor(), minutes_ago=10)
        send('meeting.ended')
        assert rows(lesson).get().leave_time_utc is not None

    def test_a_leave_earlier_than_the_join_never_gives_negative_or_huge_minutes(self, lesson):
        join(lesson, tutor(), minutes_ago=5)
        leave(lesson, tutor(), minutes_ago=30)
        assert rows(lesson).get().total_minutes == 0

    def test_an_unparseable_time_is_not_a_500(self, lesson):
        send('meeting.participant_joined', {**tutor(), 'join_time': 'not-a-date'})
        assert rows(lesson).get().join_time_utc is not None

    def test_five_minute_disconnect_grace_counts_short_reconnect_gap(self, lesson):
        from apps.integrations.services.attendance import TEACHER, credited_attendance_minutes
        start = lesson.start_time_utc
        AttendanceAudit.objects.create(
            booking=lesson, participant_email=lesson.teacher.user.email, classification='teacher',
            zoom_session_id='g1', join_time_utc=start, leave_time_utc=start + timedelta(minutes=8),
            total_minutes=8,
        )
        AttendanceAudit.objects.create(
            booking=lesson, participant_email=lesson.teacher.user.email, classification='teacher',
            zoom_session_id='g2', join_time_utc=start + timedelta(minutes=12),
            leave_time_utc=start + timedelta(minutes=20), total_minutes=8,
        )
        assert credited_attendance_minutes(lesson, TEACHER, through=start + timedelta(minutes=25)) == 20

    def test_unknown_participant_count_cannot_prevent_teacher_no_show(self, lesson, zoom_never_held):
        Booking.objects.filter(pk=lesson.pk).update(
            start_time_utc=timezone.now() - timedelta(minutes=11),
            end_time_utc=timezone.now() + timedelta(minutes=14),
            status=S.CONFIRMED,
        )
        join(lesson, {'id': '', 'user_id': 'unknown', 'email': 'unknown@example.test'})
        with patch.object(zoom_client, 'get_meeting_status', return_value={'status': 'waiting', 'participant_count': 4}):
            audit_attendance_and_noshows_task()
        lesson.refresh_from_db()
        assert lesson.status == S.TEACHER_NO_SHOW


# ------------------------------------------------------------------ meeting.started
@pytest.mark.django_db
class TestMeetingStarted:
    def test_host_starting_the_meeting_counts_as_the_tutor_being_there(self, lesson):
        send('meeting.started', start_time=(timezone.now() - timedelta(minutes=1)).isoformat())
        a = rows(lesson, participant_email=lesson.teacher.user.email).get()
        assert a.identity == 'meeting_started'
        lesson.refresh_from_db()
        assert lesson.status == S.IN_PROGRESS

    def test_started_twice_or_after_the_join_adds_nothing(self, lesson):
        join(lesson, tutor())
        send('meeting.started')
        send('meeting.started')
        assert rows(lesson, participant_email=lesson.teacher.user.email).count() == 1
        assert BookingStatusChange.objects.filter(booking=lesson, to_status=S.IN_PROGRESS).count() == 1

    def test_started_saves_the_tutor_from_a_lost_join_event(self, lesson):
        Booking.objects.filter(pk=lesson.pk).update(start_time_utc=timezone.now() - timedelta(minutes=11),
                                                    end_time_utc=timezone.now() + timedelta(minutes=14))
        send('meeting.started')
        join(lesson, pupil(lesson))
        audit_attendance_and_noshows_task()
        lesson.refresh_from_db()
        assert lesson.status == S.IN_PROGRESS


# ------------------------------------------------------------------ late telemetry after a verdict
@pytest.mark.django_db
class TestLateTelemetry:
    def test_the_tutor_turning_up_after_a_teacher_no_show_opens_a_dispute(self, lesson):
        Booking.objects.filter(pk=lesson.pk).update(status=S.TEACHER_NO_SHOW)
        join(lesson, tutor())
        lesson.refresh_from_db()
        assert lesson.status == S.DISPUTED and DisputeCase.objects.filter(booking=lesson).exists()

    def test_the_student_turning_up_after_a_teacher_no_show_does_not(self, lesson):
        Booking.objects.filter(pk=lesson.pk).update(status=S.TEACHER_NO_SHOW)
        join(lesson, pupil(lesson))
        lesson.refresh_from_db()
        assert lesson.status == S.TEACHER_NO_SHOW and not DisputeCase.objects.exists()
        assert rows(lesson, participant_email=lesson.student.email).exists()      # still recorded

    def test_the_student_turning_up_after_a_student_no_show_opens_a_dispute(self, lesson):
        Booking.objects.filter(pk=lesson.pk).update(status=S.STUDENT_NO_SHOW)
        join(lesson, pupil(lesson))
        lesson.refresh_from_db()
        assert lesson.status == S.DISPUTED and DisputeCase.objects.filter(booking=lesson).exists()

    def test_the_tutor_after_a_student_no_show_does_not(self, lesson):
        Booking.objects.filter(pk=lesson.pk).update(status=S.STUDENT_NO_SHOW)
        join(lesson, tutor())
        lesson.refresh_from_db()
        assert lesson.status == S.STUDENT_NO_SHOW

    def test_a_stranger_after_any_verdict_does_not(self, lesson):
        for verdict in (S.TEACHER_NO_SHOW, S.STUDENT_NO_SHOW):
            Booking.objects.filter(pk=lesson.pk).update(status=verdict)
            join(lesson, {'id': '', 'user_id': 'x', 'participant_uuid': 'x-' + verdict, 'email': 'who@else.test'})
            lesson.refresh_from_db()
            assert lesson.status == verdict
        assert not DisputeCase.objects.exists()


# ------------------------------------------------------------------ robustness
@pytest.mark.django_db
class TestBadPayloads:
    @pytest.mark.parametrize('payload', [[], 'x', None, {'object': []}, {'object': 'x'}, {'object': {'id': MEETING, 'participant': 'x'}},
                                         {'object': {'id': MEETING, 'participant': []}}])
    def test_odd_shapes_are_acknowledged_not_500(self, lesson, payload):
        raw = json.dumps({'event': 'meeting.participant_joined', 'payload': payload}).encode()
        res = APIClient().post('/api/v1/integrations/zoom/webhook/', data=raw, content_type='application/json', **generate_zoom_headers(raw))
        assert res.status_code in (200, 400)
        lesson.refresh_from_db()
        assert lesson.status == S.CONFIRMED

    def test_unknown_meeting_is_ignored(self, lesson):
        res = send('meeting.participant_joined', tutor(), meeting_id='000')
        assert res.json()['status'] == 'ignored'

    def test_unrelated_events_are_acknowledged(self, lesson):
        assert send('meeting.chat_message_sent').status_code == 200
        assert not rows(lesson).exists()


# ------------------------------------------------------------------ creating the meeting
class TestCreateMeeting:
    def test_a_zoom_rejection_is_an_error_not_a_none(self, settings):
        # Slice Z1: the error names the HTTP status only, never Zoom's body (no provider text in errors or logs).
        settings.ZOOM_ACCOUNT_ID, settings.ZOOM_CLIENT_ID, settings.ZOOM_CLIENT_SECRET = 'acc', 'cid', 'sec'
        resp = MagicMock(status_code=400, text='{"code":300,"message":"bad start_time"}')
        with patch.object(zoom_client, 'get_access_token', return_value='tok'), patch('apps.integrations.zoom.requests.post', return_value=resp):
            with pytest.raises(ZoomError, match='HTTP 400') as err:
                zoom_client.create_meeting('t', '2026-10-05T09:00:00Z')
        assert 'bad start_time' not in str(err.value) and err.value.status == 400
