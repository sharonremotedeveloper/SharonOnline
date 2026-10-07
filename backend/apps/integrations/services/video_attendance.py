"""Video SDK attendance telemetry and evidence writer (Decision D-9, Slice V4).

Ingests Zoom Video SDK events (session.user_joined, session.user_left, session.started,
session.ended) into AttendanceAudit rows with identity='video_sdk'.

Core Invariants (F0 & ZOOM_ATTENDANCE.md):
- Evidence writer only: never transitions bookings to TEACHER_NO_SHOW or STUDENT_NO_SHOW directly.
- Classification is strictly 'teacher', 'student', or 'unknown' by matching user_identity (UUID).
- Unmatched participants receive classification='unknown' with empty email so they cannot satisfy attendance.
- Tutor joining moves CONFIRMED bookings to IN_PROGRESS.
- Re-joins and out-of-order events converge idempotently without double-counting minutes.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
import logging
from typing import Optional, Tuple
import dateutil.parser
from django.utils import timezone

from apps.admin_api.models import DisputeCase
from apps.bookings.models import AttendanceAudit, Booking
from apps.bookings.services.state_machine import transition_booking

logger = logging.getLogger(__name__)

S = Booking.Status
ACTOR = 'system:video_sdk_webhook'
TEACHER, STUDENT, UNKNOWN = 'teacher', 'student', 'unknown'
IDENTITY = 'video_sdk'
STARTED_SESSION = 'session_started'


def classify_video_participant(booking: Booking, user_identity: Optional[str]) -> Tuple[str, str, str]:
    """Classify participant by user_identity UUID matching booking tutor or student.

    Returns (role, email, identity).
    If identity matches neither, returns ('unknown', '', 'video_sdk').
    """
    uid = str(user_identity or '').strip().lower()
    if not uid:
        return UNKNOWN, '', IDENTITY

    teacher_user = getattr(booking.teacher, 'user', None) if hasattr(booking, 'teacher') else None
    teacher_id = str(teacher_user.id).lower() if teacher_user else ''
    student_id = str(booking.student_id).lower()

    if teacher_id and uid == teacher_id:
        return TEACHER, teacher_user.email, IDENTITY
    if student_id and uid == student_id:
        return STUDENT, booking.student.email, IDENTITY

    return UNKNOWN, '', IDENTITY


def parse_video_time(raw, fallback: datetime) -> datetime:
    """Parse timestamp into UTC aware datetime, falling back to provided default."""
    if not raw:
        return fallback
    if isinstance(raw, (int, float)):
        # Support epoch seconds or milliseconds
        ts = raw / 1000.0 if raw > 1e11 else float(raw)
        try:
            return datetime.fromtimestamp(ts, tz=dt_timezone.utc)
        except (ValueError, OverflowError):
            return fallback
    try:
        dt = dateutil.parser.isoparse(str(raw))
        return dt.replace(tzinfo=dt_timezone.utc) if timezone.is_naive(dt) else dt
    except (ValueError, OverflowError):
        logger.warning("[VIDEO SDK ATTENDANCE] Unparseable time %r; using fallback", raw)
        return fallback


def _minutes(join: Optional[datetime], leave: Optional[datetime], *, lower=None, upper=None) -> int:
    if not join:
        return 0
    join = max(join, lower) if lower else join
    leave = min(leave, upper) if leave and upper else leave
    if not leave or leave < join:
        return 0
    return int((leave - join).total_seconds() // 60)


def _video_session_key(session_id: str, participant_id: str, user_identity: str) -> str:
    key_body = f"{session_id or 'session'}:{participant_id or user_identity or 'guest'}"
    return f"sdk-{key_body}"[:96]


def _fill_video_row(
    row: AttendanceAudit,
    *,
    join: Optional[datetime] = None,
    leave: Optional[datetime] = None,
    user_id: str = '',
    event_id: str = '',
) -> None:
    """Update row idempotently and recompute total_minutes."""
    if join and not row.join_time_utc:
        row.join_time_utc = join
    if leave and not row.leave_time_utc:
        row.leave_time_utc = leave
    if user_id and not row.zoom_user_id:
        row.zoom_user_id = user_id[:64]
    if event_id and event_id not in row.event_ids:
        row.event_ids = [*row.event_ids, event_id]
    row.total_minutes = _minutes(
        row.join_time_utc,
        row.leave_time_utc,
    )
    row.save()


def _get_or_create_video_row(
    booking: Booking,
    key: str,
    role: str,
    email: str,
    identity: str,
    participant_data: dict,
    *,
    join: Optional[datetime] = None,
    leave: Optional[datetime] = None,
    event_id: str = '',
) -> AttendanceAudit:
    user_id = str(participant_data.get('user_id') or participant_data.get('id') or '')[:64]
    user_identity = str(participant_data.get('user_identity') or participant_data.get('user_key') or '')[:128]

    row = AttendanceAudit.objects.filter(booking=booking, zoom_session_id=key).first() if key else None

    # Handle rejoins: if the first session was already closed and this join is later, mint new key
    if row and join and row.leave_time_utc and join > row.leave_time_utc:
        key = f"{key}@{int(join.timestamp())}"[:96]
        row = AttendanceAudit.objects.filter(booking=booking, zoom_session_id=key).first()

    # Handle leave for a session whose initial row was closed but later session remains open
    if row and leave and row.leave_time_utc:
        later = (
            AttendanceAudit.objects.filter(
                booking=booking,
                zoom_session_id__startswith=f"{key}@",
                leave_time_utc__isnull=True,
            )
            .order_by('-join_time_utc')
            .first()
        )
        row = later or row

    if row is None:
        row = AttendanceAudit(
            booking=booking,
            participant_email=email,
            identity=identity,
            classification=role,
            zoom_session_id=key,
            zoom_user_id=user_id,
            participant_id=user_identity,
            registrant_id='',
            host_id='',
            event_ids=[event_id] if event_id else [],
            raw_payload=participant_data,
        )
    elif row.classification == UNKNOWN and role != UNKNOWN:
        row.classification = role
        row.participant_email = email
        row.identity = identity

    _fill_video_row(row, join=join, leave=leave, user_id=user_id, event_id=event_id)
    return row


def _quarantine_if_contradicted(
    booking: Booking,
    role: str,
    what: str,
    evidence_email: str,
    detail: str,
) -> None:
    """Quarantine to DISPUTED if telemetry contradicts a previous no-show verdict."""
    contradicts = (
        (booking.status == S.TEACHER_NO_SHOW and role == TEACHER)
        or (booking.status == S.STUDENT_NO_SHOW and role == STUDENT)
    )
    if not contradicts:
        return

    verdict = booking.status
    logger.warning(
        "[LATE VIDEO TELEMETRY HAZARD] Booking %s is %s but %s telemetry for role %s arrived; quarantining to DISPUTED.",
        booking.id,
        verdict,
        what,
        role,
    )
    transition_booking(
        booking,
        S.DISPUTED,
        actor=ACTOR,
        reason=f"late {what} Video SDK telemetry after {verdict} verdict",
    )
    DisputeCase.objects.get_or_create(
        booking=booking,
        defaults={
            "student": booking.student,
            "teacher": booking.teacher,
            "student_statement": f"Automated Alert: Late Video SDK attendance telemetry received after {verdict} adjudication.",
            "teacher_statement": f"Telemetry proof: Participant {evidence_email} {detail}.",
            "status": DisputeCase.Status.OPEN,
            "admin_notes": "Late Video SDK webhook arrived post-adjudication. Quarantined for admin manual arbitration.",
        },
    )


def _tutor_present(booking: Booking, who: str) -> None:
    if booking.status == S.CONFIRMED:
        transition_booking(
            booking,
            S.IN_PROGRESS,
            actor=ACTOR,
            reason=f"tutor {who} joined Video SDK classroom",
        )


def on_video_user_joined(
    booking: Booking,
    obj_data: dict,
    now: datetime,
    event_id: str = '',
) -> AttendanceAudit:
    """Process session.user_joined event."""
    participant = obj_data.get('participant') if isinstance(obj_data.get('participant'), dict) else obj_data
    user_identity = participant.get('user_identity') or obj_data.get('user_identity')
    session_id = str(obj_data.get('session_id') or obj_data.get('id') or '')
    user_id = str(participant.get('user_id') or participant.get('id') or '')

    role, email, identity = classify_video_participant(booking, user_identity)
    raw_join = participant.get('join_time') or obj_data.get('start_time')
    join_time = min(parse_video_time(raw_join, now), now + timedelta(minutes=5))

    key = _video_session_key(session_id, user_id, str(user_identity or ''))
    row = _get_or_create_video_row(
        booking,
        key,
        role,
        email,
        identity,
        participant,
        join=join_time,
        event_id=event_id,
    )

    if role == TEACHER:
        _tutor_present(booking, email)

    _quarantine_if_contradicted(booking, role, 'join', email, f"joined at {join_time.isoformat()}")
    return row


def on_video_user_left(
    booking: Booking,
    obj_data: dict,
    now: datetime,
    event_id: str = '',
) -> AttendanceAudit:
    """Process session.user_left event."""
    participant = obj_data.get('participant') if isinstance(obj_data.get('participant'), dict) else obj_data
    user_identity = participant.get('user_identity') or obj_data.get('user_identity')
    session_id = str(obj_data.get('session_id') or obj_data.get('id') or '')
    user_id = str(participant.get('user_id') or participant.get('id') or '')

    role, email, identity = classify_video_participant(booking, user_identity)
    raw_leave = participant.get('leave_time') or obj_data.get('end_time')
    leave_time = parse_video_time(raw_leave, now)

    key = _video_session_key(session_id, user_id, str(user_identity or ''))
    row = _get_or_create_video_row(
        booking,
        key,
        role,
        email,
        identity,
        participant,
        leave=leave_time,
        event_id=event_id,
    )

    logger.info(
        "[VIDEO SDK ATTENDANCE] Participant (%s) left booking %s after %sm",
        role,
        booking.id,
        row.total_minutes,
    )
    _quarantine_if_contradicted(booking, role, 'leave', email, f"logged {row.total_minutes}m")
    return row


def on_video_session_started(
    booking: Booking,
    obj_data: dict,
    now: datetime,
    event_id: str = '',
) -> Optional[AttendanceAudit]:
    """Process session.started event."""
    session_id = str(obj_data.get('session_id') or obj_data.get('id') or '')
    start_time = parse_video_time(obj_data.get('start_time'), now)

    # Check if a teacher row already exists
    teacher_row = (
        AttendanceAudit.objects.filter(booking=booking, classification=TEACHER)
        .order_by('-join_time_utc')
        .first()
    )
    if teacher_row is None:
        teacher_user = getattr(booking.teacher, 'user', None) if hasattr(booking, 'teacher') else None
        if teacher_user:
            row = AttendanceAudit.objects.create(
                booking=booking,
                participant_email=teacher_user.email,
                identity=IDENTITY,
                classification=TEACHER,
                zoom_session_id=f"sdk-{session_id or 'started'}:{STARTED_SESSION}"[:96],
                join_time_utc=start_time,
                event_ids=[event_id] if event_id else [],
                raw_payload=obj_data,
            )
            _tutor_present(booking, teacher_user.email)
            return row
    else:
        _fill_video_row(teacher_row, event_id=event_id)
        return teacher_row
    return None


def on_video_session_ended(
    booking: Booking,
    obj_data: dict,
    now: datetime,
    event_id: str = '',
) -> None:
    """Process session.ended event by closing open sessions at end_time."""
    end_time = parse_video_time(obj_data.get('end_time'), now)
    for row in AttendanceAudit.objects.filter(booking=booking, leave_time_utc__isnull=True):
        _fill_video_row(
            row,
            leave=max(end_time, row.join_time_utc) if row.join_time_utc else end_time,
            event_id=event_id,
        )
