"""Slice V4 contract (docs/PHASE_11_12_TASK_ASSIGNMENTS.md section 3, seam 2): attendance for Video SDK lessons.

The Video SDK has no Zoom meeting id. A lesson is an SDK lesson when the SDK is configured and the booking has no
`zoom_meeting_id` (`bookings/services/video_provider.py::uses_video_sdk`). Evidence is `AttendanceAudit` rows (teacher /
student classification, join/leave times); V4 only WRITES that evidence and implements the live-session probe
`attendance_probe.probe_video_session(booking)`. These tests fix the VERDICT semantics and are the acceptance test for V4:
they must pass unchanged once V4 is built. Money-safety rules (F0):

1. Silence is never a no-show: no evidence + unknown probe defers, and the lesson is DISPUTED at its end.
2. A tutor no-show needs positive evidence: the student joined, AND the SDK probe says the tutor's session never started.
   Both absent is never a tutor no-show (a human decides).
3. Tutor evidence wins over any probe; >= LESSON_DELIVERED_MIN_TEACHER_MINUTES of tutor dwell completes the lesson.
4. A confirmed SDK lesson provisions no Zoom Meetings room (the zoom step is SKIPPED, not DONE or FAILED).
"""
import itertools
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.bookings.models import AttendanceAudit, Booking, BookingStatusChange
from apps.bookings.services import attendance_probe
from apps.bookings.tasks import audit_attendance_and_noshows_task
from apps.integrations.tasks import dispatch_booking_fulfillment
from apps.integrations.zoom import zoom_client
from apps.payments.models import CreditBundle, FulfillmentDispatch, RefundRequest
from apps.teachers.models import TeacherStrike
from payment_helpers import lesson

S = Booking.Status
_ids = itertools.count(1)


def sdk_lesson(teacher, student, *, started_min_ago=12, status=S.CONFIRMED):
    b = lesson(teacher, student, -started_min_ago, status=status)
    assert not b.zoom_meeting_id
    return b


def evidence(booking, who, *, join_min, leave_min=None):
    """One SDK join session of `who` ('teacher'|'student'), offsets in minutes from the lesson start."""
    user = booking.teacher.user if who == 'teacher' else booking.student
    return AttendanceAudit.objects.create(
        booking=booking, participant_email=user.email, classification=who, identity='video_sdk',
        zoom_session_id=f'sdk-{next(_ids)}',
        join_time_utc=booking.start_time_utc + timedelta(minutes=join_min),
        leave_time_utc=None if leave_min is None else booking.start_time_utc + timedelta(minutes=leave_min))


def probe_returns(value):
    return mock.patch.object(attendance_probe, 'probe_video_session', return_value=value)


def nothing_a_no_show_does(booking):
    assert not TeacherStrike.objects.filter(booking=booking).exists()
    assert not RefundRequest.objects.filter(booking=booking).exists()
    assert not CreditBundle.objects.filter(user=booking.student).exists()
    assert not BookingStatusChange.objects.filter(booking=booking, to_status=S.TEACHER_NO_SHOW).exists()


@pytest.mark.django_db
class TestSdkLessonVerdicts:
    def test_no_evidence_and_unknown_probe_defers_then_disputes_at_the_end(self, video_sdk_on, teacher_user, student_user):
        b = sdk_lesson(teacher_user, student_user)
        with probe_returns(attendance_probe.UNKNOWN):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED                                  # deferred, not judged and not disputed yet
        nothing_a_no_show_does(b)
        Booking.objects.filter(pk=b.pk).update(start_time_utc=timezone.now() - timedelta(minutes=30),
                                               end_time_utc=timezone.now() - timedelta(minutes=5))
        with probe_returns(attendance_probe.UNKNOWN):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.DISPUTED
        nothing_a_no_show_does(b)

    def test_both_absent_is_never_a_tutor_no_show_even_if_the_probe_says_not_started(self, video_sdk_on, teacher_user,
                                                                                    student_user):
        b = sdk_lesson(teacher_user, student_user)
        with probe_returns(attendance_probe.NOT_STARTED):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED
        nothing_a_no_show_does(b)

    def test_student_joined_tutor_never_started_is_a_tutor_no_show(self, video_sdk_on, teacher_user, student_user):
        b = sdk_lesson(teacher_user, student_user)
        evidence(b, 'student', join_min=1)
        with probe_returns(attendance_probe.NOT_STARTED):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.TEACHER_NO_SHOW
        assert TeacherStrike.objects.filter(booking=b).exists()
        assert RefundRequest.objects.filter(booking=b).exists()

    @pytest.mark.parametrize('probe_value', [attendance_probe.UNKNOWN, None])
    def test_student_joined_but_probe_unknown_never_scores_the_tutor(self, video_sdk_on, teacher_user, student_user,
                                                                     probe_value):
        b = sdk_lesson(teacher_user, student_user)
        evidence(b, 'student', join_min=1)
        with probe_returns(probe_value if probe_value else attendance_probe.UNKNOWN):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED
        nothing_a_no_show_does(b)

    def test_a_probe_that_raises_is_unknown_not_absence(self, video_sdk_on, teacher_user, student_user):
        b = sdk_lesson(teacher_user, student_user)
        evidence(b, 'student', join_min=1)
        with mock.patch.object(attendance_probe, 'probe_video_session', side_effect=RuntimeError('zoom 500')):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED
        nothing_a_no_show_does(b)

    def test_live_session_with_the_tutor_in_it_prevents_a_no_show(self, video_sdk_on, teacher_user, student_user):
        b = sdk_lesson(teacher_user, student_user)
        evidence(b, 'student', join_min=1)
        with probe_returns(attendance_probe.STARTED):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.IN_PROGRESS
        nothing_a_no_show_does(b)

    def test_tutor_evidence_beats_the_probe(self, video_sdk_on, teacher_user, student_user):
        b = sdk_lesson(teacher_user, student_user)
        evidence(b, 'teacher', join_min=2)
        evidence(b, 'student', join_min=3)
        with probe_returns(attendance_probe.NOT_STARTED) as probe:
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED
        probe.assert_not_called()
        nothing_a_no_show_does(b)

    def test_tutor_present_student_absent_is_a_student_no_show(self, video_sdk_on, teacher_user, student_user):
        b = sdk_lesson(teacher_user, student_user)
        evidence(b, 'teacher', join_min=1)
        with probe_returns(attendance_probe.UNKNOWN):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.STUDENT_NO_SHOW
        nothing_a_no_show_does(b)

    def test_twenty_minutes_of_tutor_dwell_completes_the_lesson(self, video_sdk_on, teacher_user, student_user):
        b = sdk_lesson(teacher_user, student_user, started_min_ago=30, status=S.IN_PROGRESS)
        Booking.objects.filter(pk=b.pk).update(end_time_utc=timezone.now() - timedelta(minutes=1))
        evidence(b, 'teacher', join_min=0, leave_min=24)
        evidence(b, 'student', join_min=0, leave_min=24)
        audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.COMPLETED_PENDING_MEMO

    def test_less_than_twenty_minutes_of_tutor_dwell_is_disputed_not_completed(self, video_sdk_on, teacher_user,
                                                                               student_user):
        b = sdk_lesson(teacher_user, student_user, started_min_ago=30, status=S.IN_PROGRESS)
        Booking.objects.filter(pk=b.pk).update(end_time_utc=timezone.now() - timedelta(minutes=1))
        evidence(b, 'teacher', join_min=0, leave_min=10)
        audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.DISPUTED
        nothing_a_no_show_does(b)


@pytest.mark.django_db
class TestLegacyMeetingsPathIsUntouched:
    def test_without_sdk_credentials_a_lesson_with_no_meeting_still_goes_to_disputed(self, teacher_user, student_user):
        b = sdk_lesson(teacher_user, student_user)            # video_sdk_on NOT requested: the SDK is unconfigured
        audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.DISPUTED

    def test_a_lesson_that_already_has_a_meeting_stays_on_the_meetings_path(self, video_sdk_on, teacher_user, student_user):
        b = sdk_lesson(teacher_user, student_user)
        Booking.objects.filter(pk=b.pk).update(zoom_meeting_id='5550001112')
        with mock.patch.object(zoom_client, 'get_meeting_status', return_value={'status': 'waiting'}), \
                mock.patch.object(zoom_client, 'get_past_instances', return_value=[]), \
                probe_returns(attendance_probe.UNKNOWN) as sdk_probe:
            audit_attendance_and_noshows_task()
        sdk_probe.assert_not_called()


@pytest.mark.django_db
class TestFulfilmentProvisionsNoMeetingsRoom:
    def test_confirmed_sdk_lesson_skips_the_zoom_step_and_creates_no_meeting(self, video_sdk_on, teacher_user, student_user):
        b = lesson(teacher_user, student_user, 30 * 60, status=S.CONFIRMED)
        with mock.patch.object(zoom_client, 'create_meeting') as create:
            assert dispatch_booking_fulfillment(str(b.id)) is True
        create.assert_not_called()
        d = FulfillmentDispatch.objects.get(booking=b)
        assert d.zoom_state == FulfillmentDispatch.StepState.SKIPPED
        assert d.status == FulfillmentDispatch.Status.SUCCEEDED
        b.refresh_from_db()
        assert not b.zoom_meeting_id
