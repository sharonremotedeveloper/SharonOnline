"""Zoom attendance: who a participant is, and how join / leave / start / end events become AttendanceAudit rows (Task 9.8).

Everything downstream (no-show verdicts, the 20-minute completion rule, escrow release, disputes) trusts
`AttendanceAudit.participant_email`, so the only way a row gets a real account e-mail is through `classify()`:

* tutor   - Zoom reports the platform host account (`participant.id == host_id`): that is whoever opened the host (start)
            link, which only the tutor is given. Or a *signed-in* Zoom account (non-empty `participant.id`) whose
            verified e-mail is the tutor's. A guest who merely TYPES the tutor's e-mail is not the tutor.
* student - the e-mail they joined with matches the booking's student (the join link is not personal, so this is the
            best identity available until registrant links are used; see docs/ZOOM_ATTENDANCE.md).
* nobody else is the student: unrecognised participants are stored (evidence) with an empty e-mail, so they can neither
  satisfy attendance nor trigger a dispute.

Events are idempotent: a row is keyed by the Zoom join session, and retries only fill in what is missing.
Callers hold the booking row lock (the webhook view does).
"""
import logging
from datetime import timedelta, timezone as dt_timezone

import dateutil.parser
from django.utils import timezone

from apps.admin_api.models import DisputeCase
from apps.bookings.models import AttendanceAudit, Booking
from apps.bookings.services.state_machine import transition_booking

logger = logging.getLogger(__name__)
S = Booking.Status
ACTOR = 'system:zoom_webhook'

TEACHER, STUDENT = 'teacher', 'student'
STARTED = 'meeting_started'      # presence-only row from meeting.started; carries no minutes


def classify(booking, meeting_obj: dict, participant: dict):
    """-> (role, account_email, identity). role is None when the participant cannot be tied to this lesson."""
    account_id = str(participant.get('id') or '').strip()          # Zoom account id; empty for guests
    host_id = str(meeting_obj.get('host_id') or '').strip()
    email = (participant.get('email') or '').strip().lower()
    teacher = booking.teacher.user
    if account_id and host_id and account_id == host_id:
        return TEACHER, teacher.email, 'host'
    if account_id and email and email == teacher.email.strip().lower():
        return TEACHER, teacher.email, 'account_email'
    if email and email == booking.student.email.strip().lower():
        return STUDENT, booking.student.email, 'email'
    return None, '', 'unmatched'


def parse_time(raw, fallback):
    """Zoom's timestamp as an aware datetime; anything unusable falls back (and is logged) instead of failing the webhook."""
    if not raw:
        return fallback
    try:
        value = dateutil.parser.isoparse(str(raw))
    except (ValueError, OverflowError):
        logger.warning("[ZOOM ATTENDANCE] Unparseable time %r; using fallback", raw)
        return fallback
    return value.replace(tzinfo=dt_timezone.utc) if timezone.is_naive(value) else value


def _minutes(join, leave) -> int:
    if not (join and leave) or leave < join:
        return 0
    return int((leave - join).total_seconds() // 60)


def _session_key(participant: dict) -> str:
    return str(participant.get('user_id') or participant.get('participant_uuid') or '').strip()[:96]


def _fill(row, *, join=None, leave=None, user_id=''):
    """Apply only what the row does not already know, so retries and out-of-order delivery converge on the same result."""
    if join and not row.join_time_utc:
        row.join_time_utc = join
    if leave and not row.leave_time_utc:
        row.leave_time_utc = leave
    if user_id and not row.zoom_user_id:
        row.zoom_user_id = user_id
    row.total_minutes = _minutes(row.join_time_utc, row.leave_time_utc)
    row.save()


def _session_row(booking, key, email, identity, participant, *, join=None, leave=None):
    """The row for this Zoom join session, created if it is new."""
    user_id = str(participant.get('user_id') or participant.get('id') or '')[:64]
    row = AttendanceAudit.objects.filter(booking=booking, zoom_session_id=key).first() if key else None
    if row and join and row.leave_time_utc and join > row.leave_time_utc:
        # Same Zoom id, but this join is after the earlier session ended: the participant came back.
        key = f"{key}@{int(join.timestamp())}"[:96]
        row = AttendanceAudit.objects.filter(booking=booking, zoom_session_id=key).first()
    if row and leave and row.leave_time_utc:
        # A leave for a Zoom id whose first session is already closed belongs to a later session of the same id, if one is open.
        later = (AttendanceAudit.objects.filter(booking=booking, zoom_session_id__startswith=f"{key}@", leave_time_utc__isnull=True)
                 .order_by('-join_time_utc').first())
        row = later or row
    if row is None and not key and leave and email:
        # No Zoom id on the event at all: close the identified participant's open session.
        row = (AttendanceAudit.objects.filter(booking=booking, participant_email=email, leave_time_utc__isnull=True)
               .order_by('-join_time_utc').first())
    if row is None:
        row = AttendanceAudit(booking=booking, participant_email=email, identity=identity, zoom_session_id=key,
                              zoom_user_id=user_id, raw_payload=participant)
    _fill(row, join=join, leave=leave, user_id=user_id)
    return row


def _quarantine_if_contradicted(booking, role, what, evidence_email, detail):
    """A no-show verdict is contradicted only by the party it blamed: tutor telemetry after TEACHER_NO_SHOW, student telemetry after STUDENT_NO_SHOW."""
    contradicts = (booking.status == S.TEACHER_NO_SHOW and role == TEACHER) or (booking.status == S.STUDENT_NO_SHOW and role == STUDENT)
    if not contradicts:
        return
    verdict = booking.status
    logger.warning("[LATE WEBHOOK HAZARD] Booking %s is %s but %s telemetry for %s arrived; quarantining to DISPUTED.",
                   booking.id, verdict, what, evidence_email)
    transition_booking(booking, S.DISPUTED, actor=ACTOR, reason=f'late {what} telemetry after {verdict} verdict')
    DisputeCase.objects.get_or_create(
        booking=booking,
        defaults={
            "student": booking.student,
            "teacher": booking.teacher,
            "student_statement": f"Automated Alert: Late Zoom attendance telemetry received after {verdict} adjudication.",
            "teacher_statement": f"Telemetry proof: Participant {evidence_email} {detail}.",
            "status": DisputeCase.Status.OPEN,
            "admin_notes": "Late webhook arrived post-adjudication. Quarantined for admin manual arbitration.",
        },
    )


def _tutor_present(booking, who):
    """The tutor being in the room is what makes a lesson 'under way' (a student alone does not)."""
    if booking.status == S.CONFIRMED:
        transition_booking(booking, S.IN_PROGRESS, actor=ACTOR, reason=f'{who} joined')


def on_participant_joined(booking, meeting_obj, participant, now):
    role, email, identity = classify(booking, meeting_obj, participant)
    join = min(parse_time(participant.get('join_time'), now), now + timedelta(minutes=5))
    _session_row(booking, _session_key(participant), email, identity, participant, join=join)
    if role == TEACHER:
        _tutor_present(booking, email)
    _quarantine_if_contradicted(booking, role, 'join', email, f"joined at {join.isoformat()}")


def on_participant_left(booking, meeting_obj, participant, now):
    role, email, identity = classify(booking, meeting_obj, participant)
    leave = parse_time(participant.get('leave_time'), now)
    row = _session_row(booking, _session_key(participant), email, identity, participant, leave=leave)
    logger.info("[ZOOM ATTENDANCE] %s left booking %s after %sm", email or 'unmatched participant', booking.id, row.total_minutes)
    _quarantine_if_contradicted(booking, role, 'leave', email, f"logged {row.total_minutes}m")


def on_meeting_started(booking, meeting_obj, now):
    """The host opened the room: the tutor is there even if their participant_joined event is late or lost."""
    teacher = booking.teacher.user
    if not AttendanceAudit.objects.filter(booking=booking, participant_email=teacher.email).exists():
        AttendanceAudit.objects.create(
            booking=booking, participant_email=teacher.email, identity=STARTED, zoom_session_id=STARTED,
            join_time_utc=parse_time(meeting_obj.get('start_time'), now), raw_payload={'event': 'meeting.started'})
    _tutor_present(booking, teacher.email)
    _quarantine_if_contradicted(booking, TEACHER, 'start', teacher.email, "started the meeting")


def on_meeting_ended(booking, meeting_obj, now):
    """Close every still-open session at Zoom's own end time (ours is only the fallback)."""
    end = parse_time(meeting_obj.get('end_time'), now)
    for row in AttendanceAudit.objects.filter(booking=booking, leave_time_utc__isnull=True).exclude(identity=STARTED):
        _fill(row, leave=max(end, row.join_time_utc) if row.join_time_utc else end)
