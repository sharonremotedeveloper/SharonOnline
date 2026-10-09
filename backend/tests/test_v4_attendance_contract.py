"""Slice V4 contract (docs/PHASE_11_12_TASK_ASSIGNMENTS.md section 3, seam 2): attendance verdicts for in-browser classroom lessons.

Ported for D5 (Daily.co is the only provider): "Video SDK" became "Daily" and the probe is `attendance_probe.probe_room`;
every assertion keeps its V4 meaning. Evidence is `AttendanceAudit` rows (teacher / student classification, join/leave
times) written by the Daily webhook; the verdict logic reads them and the room probe. These tests fix the VERDICT semantics
and are the acceptance test for attendance. Money-safety rules (F0):

1. Silence is never a no-show: no evidence + unknown probe defers, and the lesson is DISPUTED at its end.
2. A tutor no-show needs positive evidence: the student joined, AND the room probe says the tutor never came.
   Both absent is never a tutor no-show (a human decides).
3. Tutor evidence wins over any probe; >= LESSON_DELIVERED_MIN_TEACHER_MINUTES of tutor dwell completes the lesson.
4. A confirmed lesson provisions its Daily room (the room step is DONE), and nothing else.
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
from apps.payments.models import CreditBundle, FulfillmentDispatch, RefundRequest
from apps.teachers.models import TeacherStrike
from payment_helpers import lesson

S = Booking.Status
_ids = itertools.count(1)


def room_lesson(teacher, student, *, started_min_ago=12, status=S.CONFIRMED):
    return lesson(teacher, student, -started_min_ago, status=status)


def evidence(booking, who, *, join_min, leave_min=None):
    """One join session of `who` ('teacher'|'student'), offsets in minutes from the lesson start."""
    user = booking.teacher.user if who == 'teacher' else booking.student
    return AttendanceAudit.objects.create(
        booking=booking, participant_email=user.email, classification=who, identity='daily',
        session_id=f'daily-{next(_ids)}',
        join_time_utc=booking.start_time_utc + timedelta(minutes=join_min),
        leave_time_utc=None if leave_min is None else booking.start_time_utc + timedelta(minutes=leave_min))


def probe_returns(value):
    return mock.patch.object(attendance_probe, 'probe_room', return_value=value)


def nothing_a_no_show_does(booking):
    assert not TeacherStrike.objects.filter(booking=booking).exists()
    assert not RefundRequest.objects.filter(booking=booking).exists()
    assert not CreditBundle.objects.filter(user=booking.student).exists()
    assert not BookingStatusChange.objects.filter(booking=booking, to_status=S.TEACHER_NO_SHOW).exists()


@pytest.mark.django_db
class TestRoomLessonVerdicts:
    def test_no_evidence_and_unknown_probe_defers_then_disputes_at_the_end(self, teacher_user, student_user):
        b = room_lesson(teacher_user, student_user)
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

    def test_both_absent_is_never_a_tutor_no_show_even_if_the_probe_says_not_started(self, teacher_user, student_user):
        b = room_lesson(teacher_user, student_user)
        with probe_returns(attendance_probe.NOT_STARTED):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED
        nothing_a_no_show_does(b)

    def test_student_joined_tutor_never_started_is_a_tutor_no_show(self, teacher_user, student_user):
        b = room_lesson(teacher_user, student_user)
        evidence(b, 'student', join_min=1)
        with probe_returns(attendance_probe.NOT_STARTED):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.TEACHER_NO_SHOW
        assert TeacherStrike.objects.filter(booking=b).exists()
        assert RefundRequest.objects.filter(booking=b).exists()

    @pytest.mark.parametrize('probe_value', [attendance_probe.UNKNOWN, None])
    def test_student_joined_but_probe_unknown_never_scores_the_tutor(self, teacher_user, student_user, probe_value):
        b = room_lesson(teacher_user, student_user)
        evidence(b, 'student', join_min=1)
        with probe_returns(probe_value if probe_value else attendance_probe.UNKNOWN):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED
        nothing_a_no_show_does(b)

    def test_a_probe_that_raises_is_unknown_not_absence(self, teacher_user, student_user):
        b = room_lesson(teacher_user, student_user)
        evidence(b, 'student', join_min=1)
        with mock.patch.object(attendance_probe, 'probe_room', side_effect=RuntimeError('daily 500')):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED
        nothing_a_no_show_does(b)

    def test_live_session_with_the_tutor_in_it_prevents_a_no_show(self, teacher_user, student_user):
        b = room_lesson(teacher_user, student_user)
        evidence(b, 'student', join_min=1)
        with probe_returns(attendance_probe.STARTED):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.IN_PROGRESS
        nothing_a_no_show_does(b)

    def test_tutor_evidence_beats_the_probe(self, teacher_user, student_user):
        b = room_lesson(teacher_user, student_user)
        evidence(b, 'teacher', join_min=2)
        evidence(b, 'student', join_min=3)
        with probe_returns(attendance_probe.NOT_STARTED) as probe:
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.CONFIRMED
        probe.assert_not_called()
        nothing_a_no_show_does(b)

    def test_tutor_present_student_absent_is_a_student_no_show(self, teacher_user, student_user):
        b = room_lesson(teacher_user, student_user)
        evidence(b, 'teacher', join_min=1)
        with probe_returns(attendance_probe.UNKNOWN):
            audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.STUDENT_NO_SHOW
        nothing_a_no_show_does(b)

    def test_twenty_minutes_of_tutor_dwell_completes_the_lesson(self, teacher_user, student_user):
        b = room_lesson(teacher_user, student_user, started_min_ago=30, status=S.IN_PROGRESS)
        Booking.objects.filter(pk=b.pk).update(end_time_utc=timezone.now() - timedelta(minutes=1))
        evidence(b, 'teacher', join_min=0, leave_min=24)
        evidence(b, 'student', join_min=0, leave_min=24)
        audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.COMPLETED_PENDING_MEMO

    def test_less_than_twenty_minutes_of_tutor_dwell_is_disputed_not_completed(self, teacher_user, student_user):
        b = room_lesson(teacher_user, student_user, started_min_ago=30, status=S.IN_PROGRESS)
        Booking.objects.filter(pk=b.pk).update(end_time_utc=timezone.now() - timedelta(minutes=1))
        evidence(b, 'teacher', join_min=0, leave_min=10)
        audit_attendance_and_noshows_task()
        b.refresh_from_db()
        assert b.status == S.DISPUTED
        nothing_a_no_show_does(b)


@pytest.mark.django_db
class TestFulfilmentProvisionsTheDailyRoom:
    def test_a_confirmed_lesson_gets_its_room_and_nothing_is_stored_on_the_booking(self, teacher_user, student_user, fake_daily):
        b = lesson(teacher_user, student_user, 30 * 60, status=S.CONFIRMED)
        assert dispatch_booking_fulfillment(str(b.id)) is True
        assert fake_daily.created == [f'lesson-{b.id}']
        d = FulfillmentDispatch.objects.get(booking=b)
        assert d.room_state == FulfillmentDispatch.StepState.DONE
        assert d.status == FulfillmentDispatch.Status.SUCCEEDED
