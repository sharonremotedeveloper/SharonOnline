"""
T+10 attendance adjudication with a tri-state room probe (Slice F0, V4 contract; docs/SETTLEMENT_PATHS.md).

A teacher no-show refunds the student, grants a bonus credit and strikes the tutor, so it must only follow positive evidence
that the room was open and the tutor never came:

* `probe_room` asks Daily's presence API who is in the lesson room and answers `started | not_started | unknown`. Only a
  clear answer from Daily is `started` (the tutor is in the room) or `not_started` (the roster is readable and the tutor is
  not in it). A non-200, a timeout, an unconfigured or simulated client, a missing room or any exception is `unknown`.
* A tutor no-show needs BOTH the student's own join (evidence that the room was open) AND `not_started`. Anything less
  defers: nothing changes, the next beat run (60 s) probes again until the lesson window ends; a lesson still without a
  verdict at its end goes to DISPUTED (`dispute_without_verdict`), never to a no-show.
* `probe_t10_candidates` does the HTTP calls with no database lock and no task lock held, bounded by
  ATTENDANCE_PROBE_BUDGET_SECONDS. `adjudicate_t10` then locks each booking, re-checks its status and applies.
"""
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.db import transaction

from apps.admin_api.models import DisputeCase
from apps.bookings.models import AttendanceAudit, Booking
from apps.bookings.services.state_machine import transition_booking
from apps.integrations.services.attendance import STUDENT, TEACHER, present_with_disconnect_grace
from apps.integrations.services.daily import DailyClient, is_daily_configured
from apps.notifications.alerts import alert_staff
from apps.payments.services.credits import grant_credit
from apps.payments.services.funding import funding_for_settlement
from apps.teachers.models import TeacherStrike
from apps.teachers.strikes import add_strike

logger = logging.getLogger(__name__)

S = Booking.Status
STARTED, NOT_STARTED, UNKNOWN = 'started', 'not_started', 'unknown'
ACTOR = 'system:attendance_audit'
ROOM = 'room'
LIVE = (S.CONFIRMED, S.IN_PROGRESS)


def probe_room(booking) -> str:
    """Ask Daily whether the tutor is in the lesson room. Anything but a clear answer is UNKNOWN (defer), never 'absent'."""
    teacher_user = getattr(getattr(booking, 'teacher', None), 'user', None)
    if teacher_user is None or not is_daily_configured():
        return UNKNOWN
    state, roster = DailyClient().get_room_presence(f'lesson-{booking.id}')
    if state != 'ok':
        return UNKNOWN
    tutor_id = str(teacher_user.id).lower()
    in_room = any(str(p.get('userId') or p.get('user_id') or '').lower() == tutor_id for p in roster if isinstance(p, dict))
    return STARTED if in_room else NOT_STARTED


def _safe_probe(booking) -> str:
    try:
        return probe_room(booking)
    except Exception as exc:    # timeout / auth / HTTP / parse failure: no clear answer, no verdict
        logger.warning('Room probe failed: booking=%s error=%s', booking.id, type(exc).__name__)
        return UNKNOWN


def _t10_candidates(now):
    return (Booking.objects.filter(status__in=LIVE, start_time_utc__lte=now - timedelta(minutes=10), end_time_utc__gt=now)
            .select_related('teacher__user', 'student'))


def probe_t10_candidates(now) -> dict:
    """Phase 1, no locks held: probe every confirmed lesson past T+10 whose tutor has not been seen. {booking_id: (ROOM, result)}"""
    deadline = time.monotonic() + settings.ATTENDANCE_PROBE_BUDGET_SECONDS
    probes = {}
    for booking in _t10_candidates(now):
        if booking.status != S.CONFIRMED:
            continue
        if present_with_disconnect_grace(booking, TEACHER, now):
            continue
        # A tutor no-show needs the student's own join as evidence that the room was open (V4 contract).
        if not present_with_disconnect_grace(booking, STUDENT, now):
            continue
        if time.monotonic() >= deadline:
            logger.warning('Room probe budget exhausted, deferring: booking=%s', booking.id)
            probes[booking.id] = (ROOM, UNKNOWN)
            continue
        probes[booking.id] = (ROOM, _safe_probe(booking))
    return probes


def adjudicate_t10(now, probes: dict, results: dict) -> None:
    """Phase 2: per booking, row lock + status re-check, then the verdict."""
    for candidate_id in list(_t10_candidates(now).values_list('id', flat=True)):
        with transaction.atomic():
            booking = (Booking.objects.select_for_update(of=('self',)).select_related('teacher__user', 'student')
                       .filter(id=candidate_id).first())
            if booking is None or booking.status not in LIVE:
                continue
            _verdict(booking, probes.get(booking.id), now, results)


def _verdict(booking, probe, now, results) -> None:
    teacher_present = present_with_disconnect_grace(booking, TEACHER, now)
    student_present = present_with_disconnect_grace(booking, STUDENT, now)
    if booking.status == S.IN_PROGRESS and not teacher_present:
        return    # inconsistent data (room open, no tutor record): the end-of-lesson check disputes it
    if not teacher_present:
        _room_verdict(booking, probe, student_present, results)
        return
    if not student_present:
        transition_booking(booking, S.STUDENT_NO_SHOW, actor=ACTOR, reason='student absent at T+10m, teacher present')
        results['student_no_shows'] += 1
        from apps.notifications.service import booking_key, notify
        notify(booking.teacher.user, 'student_no_show', key=booking_key('student-no-show', booking, 'teacher'),
               payload={'booking_id': str(booking.id)}, booking=booking)
        notify(booking.student, 'student_no_show', key=booking_key('student-no-show', booking, 'student'),
               payload={'booking_id': str(booking.id)}, booking=booking)
        logger.info('[NO-SHOW] Student absent at T+10m: booking=%s', booking.id)


def _room_verdict(booking, probe, student_present, results) -> None:
    """Tutor absent at T+10. A no-show needs BOTH the student's join and Daily's own word that the tutor is not in the room;
    anything less defers, and the lesson-end check disputes it (V4 contract, F0 semantics)."""
    outcome = probe[1] if probe and probe[0] == ROOM else UNKNOWN
    if outcome == STARTED:
        _record_probe_presence(booking)
        return
    if outcome == NOT_STARTED and student_present:
        apply_teacher_no_show(booking)
        results['teacher_no_shows'] += 1
        return
    logger.warning('No-show verdict deferred (room evidence insufficient): booking=%s', booking.id)
    results['probe_deferred'] = results.get('probe_deferred', 0) + 1


def _record_probe_presence(booking) -> None:
    """Daily says the tutor is in the room, but no join webhook arrived: record that evidence and start the lesson."""
    AttendanceAudit.objects.get_or_create(
        booking=booking, session_id='active_room_probe',
        defaults={'participant_email': booking.teacher.user.email, 'classification': AttendanceAudit.Classification.TEACHER,
                  'identity': 'probe', 'join_time_utc': booking.start_time_utc,
                  'raw_payload': {'source': 'active_room_probe'}})
    transition_booking(booking, S.IN_PROGRESS, actor='system:room_probe',
                       reason='tutor present in the room (presence probe) before no-show verdict')
    logger.warning('[ACTIVE ROOM PROBE GUARD] Tutor present in room, no-show prevented: booking=%s', booking.id)


def apply_teacher_no_show(booking) -> None:
    """TEACHER_NO_SHOW with its consequences (D-6): strike, gateway refund of the captured amount, 1 bonus credit."""
    from apps.notifications.service import booking_key, notify
    from apps.payments.models import CreditBundle, RefundRequest
    from apps.payments.services.ledger_service import record_compensation_entry
    from apps.payments.services.refunds import request_refund

    transition_booking(booking, S.TEACHER_NO_SHOW, actor=ACTOR, reason='teacher absent at T+10m (classroom not entered)')
    add_strike(booking.teacher, TeacherStrike.Kind.NO_SHOW, booking=booking)
    funding = funding_for_settlement(booking, context='teacher_no_show_restitution')
    if funding is None:
        logger.error('Teacher no-show restitution stopped: booking=%s missing funding', booking.id)
        return
    request_refund(booking, RefundRequest.Reason.TEACHER_NO_SHOW)
    grant_credit(booking.student, source=CreditBundle.Source.BONUS, pack_name='Teacher no-show apology',
                 unit_amount=funding.captured_amount, currency=funding.currency, fx_rate_to_zar=funding.fx_rate_to_zar,
                 fx_source=funding.fx_source, booking=booking, idempotency_key=f'teacher-no-show-bonus:{booking.id}')
    record_compensation_entry(user=booking.student, booking=booking, amount_usd=funding.captured_amount,
                              currency=funding.currency, fx_rate_to_zar=funding.fx_rate_to_zar,
                              fx_source=funding.fx_source, reason='Teacher no-show bonus compensation')
    notify(booking.student, 'teacher_no_show', key=booking_key('teacher-no-show', booking, 'student'),
           payload={'booking_id': str(booking.id)}, booking=booking)
    notify(booking.teacher.user, 'teacher_no_show', key=booking_key('teacher-no-show', booking, 'teacher'),
           payload={'booking_id': str(booking.id)}, booking=booking)
    logger.error('[NO-SHOW] Teacher absent at T+10m: booking=%s; student refunded and given 1 bonus credit', booking.id)


def end_of_window_reason(booking) -> str:
    """Why a lesson that is still CONFIRMED at its end never got a verdict (it is disputed, never scored)."""
    return 'no attendance verdict before the lesson ended: room evidence insufficient'


def dispute_without_verdict(booking, reason: str) -> None:
    """Human-visible state for a lesson we cannot judge: DISPUTED + an open DisputeCase. No refund, strike or credit."""
    result = transition_booking(booking, S.DISPUTED, actor=ACTOR, reason=reason)
    note = (f'{reason}. No attendance verdict was possible (Slice F0). Nothing was refunded, credited or struck: '
            'decide from the attendance records and the Daily room.')
    case, created = DisputeCase.objects.select_for_update().get_or_create(booking=booking, defaults={
        'student': booking.student, 'teacher': booking.teacher, 'status': DisputeCase.Status.OPEN,
        'student_statement': f'Automated: {reason}.', 'teacher_statement': '', 'admin_notes': note})
    if not created and case.status != DisputeCase.Status.OPEN:
        # One case per booking (OneToOne): an earlier, resolved case is reopened as the work item, its history kept.
        case.status, case.resolution, case.resolved_at = DisputeCase.Status.OPEN, None, None
        case.admin_notes = f'{case.admin_notes}\n[reopened] {note}'.strip()
        case.save(update_fields=['status', 'resolution', 'resolved_at', 'admin_notes'])
    if result.changed:
        # Staff alert through notify() (slice N1a); the open DisputeCase stays the durable work item.
        logger.error('[ADMIN ALERT] Lesson disputed without an attendance verdict: booking=%s', booking.id)
        alert_staff('lesson_disputed_without_verdict',
                    key=f'admin:disputed-no-verdict:{booking.id}:{booking.reschedule_count}',
                    payload={'booking_id': str(booking.id)})
