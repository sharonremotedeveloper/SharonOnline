"""
T+10 attendance adjudication with a tri-state Zoom probe (Slice F0; docs/ZOOM_ATTENDANCE.md, docs/SETTLEMENT_PATHS.md).

A teacher no-show refunds the student, grants a bonus credit and strikes the tutor, so it must only follow positive evidence
that the room was open and the tutor never came:

* `probe_meeting` answers `started | not_started | unknown`. Only Zoom's own `waiting` is `not_started`; a non-200, a
  timeout, an auth failure, any exception or an unexpected payload is `unknown`.
* `unknown` defers: nothing changes, the next beat run (60 s) probes again until the lesson window ends; a lesson still
  without a verdict at its end goes to DISPUTED (`dispute_without_verdict`), never to a no-show.
* A lesson with no Zoom meeting id cannot have been attended, so it is never scored a no-show: DISPUTED + an open
  DisputeCase at T+10 instead.
* `probe_t10_candidates` does the HTTP calls with no database lock and no task lock held, bounded by
  ATTENDANCE_PROBE_BUDGET_SECONDS. `adjudicate_t10` then locks each booking, re-checks its status and meeting id, and applies.
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
from apps.integrations.zoom import zoom_client
from apps.payments.services.credits import grant_credit
from apps.payments.services.funding import funding_for_settlement
from apps.teachers.models import TeacherStrike
from apps.teachers.strikes import add_strike

logger = logging.getLogger(__name__)

S = Booking.Status
STARTED, NOT_STARTED, UNKNOWN = 'started', 'not_started', 'unknown'
ACTOR = 'system:attendance_audit'
LIVE = (S.CONFIRMED, S.IN_PROGRESS)


def probe_meeting(meeting_id: str) -> str:
    """Ask Zoom whether the meeting is running. Anything but a clear answer is UNKNOWN (defer), never 'absent'."""
    try:
        payload = zoom_client.get_meeting_status(meeting_id)
    except Exception as exc:    # timeout / auth / HTTP / parse failure: we do not know, so we must not judge
        logger.warning('Zoom probe failed: meeting=%s error=%s', meeting_id, type(exc).__name__)
        return UNKNOWN
    status = payload.get('status') if isinstance(payload, dict) else None
    if status == 'started':
        return STARTED
    if status == 'waiting':
        return NOT_STARTED
    logger.warning('Zoom probe inconclusive: meeting=%s', meeting_id)
    return UNKNOWN


def _t10_candidates(now):
    return (Booking.objects.filter(status__in=LIVE, start_time_utc__lte=now - timedelta(minutes=10), end_time_utc__gt=now)
            .select_related('teacher__user', 'student'))


def probe_t10_candidates(now) -> dict:
    """Phase 1, no locks held: probe every confirmed lesson past T+10 whose tutor has not been seen. {booking_id: (meeting, result)}"""
    deadline = time.monotonic() + settings.ATTENDANCE_PROBE_BUDGET_SECONDS
    probes = {}
    for booking in _t10_candidates(now):
        if booking.status != S.CONFIRMED or not booking.zoom_meeting_id:
            continue
        if present_with_disconnect_grace(booking, TEACHER, now):
            continue
        if time.monotonic() >= deadline:
            logger.warning('Zoom probe budget exhausted, deferring: booking=%s', booking.id)
            probes[booking.id] = (booking.zoom_meeting_id, UNKNOWN)
            continue
        probes[booking.id] = (booking.zoom_meeting_id, probe_meeting(booking.zoom_meeting_id))
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
        if not booking.zoom_meeting_id:
            dispute_without_verdict(booking, 'no Zoom meeting provisioned: no no-show verdict is possible')
            results['disputed_without_verdict'] = results.get('disputed_without_verdict', 0) + 1
            return
        outcome = probe[1] if probe and probe[0] == booking.zoom_meeting_id else UNKNOWN
        if outcome == UNKNOWN:
            logger.warning('No-show verdict deferred (Zoom status unknown): booking=%s', booking.id)
            results['probe_deferred'] = results.get('probe_deferred', 0) + 1
            return
        if outcome == NOT_STARTED:
            apply_teacher_no_show(booking)
            results['teacher_no_shows'] += 1
            return
        _record_probe_presence(booking)
    if not student_present:
        transition_booking(booking, S.STUDENT_NO_SHOW, actor=ACTOR, reason='student absent at T+10m, teacher present')
        results['student_no_shows'] += 1
        logger.info('[NO-SHOW] Student absent at T+10m: booking=%s', booking.id)


def _record_probe_presence(booking) -> None:
    """Zoom says the room is running: the tutor (host link) is in, so no tutor no-show."""
    AttendanceAudit.objects.get_or_create(
        booking=booking, zoom_session_id='active_zoom_probe',
        defaults={'participant_email': booking.teacher.user.email, 'classification': AttendanceAudit.Classification.TEACHER,
                  'identity': 'active_zoom_probe', 'join_time_utc': booking.start_time_utc,
                  'raw_payload': {'source': 'active_zoom_probe'}})
    transition_booking(booking, S.IN_PROGRESS, actor='system:zoom_probe',
                       reason='active Zoom meeting detected before no-show verdict')
    logger.warning('[ACTIVE ZOOM PROBE GUARD] Active meeting detected, no-show prevented: booking=%s', booking.id)


def apply_teacher_no_show(booking) -> None:
    """TEACHER_NO_SHOW with its consequences (D-6): strike, gateway refund of the captured amount, 1 bonus credit."""
    from apps.payments.models import CreditBundle, RefundRequest
    from apps.payments.services.ledger_service import record_compensation_entry
    from apps.payments.services.refunds import request_refund

    transition_booking(booking, S.TEACHER_NO_SHOW, actor=ACTOR, reason='teacher absent at T+10m (Zoom room not started)')
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
    logger.error('[NO-SHOW] Teacher absent at T+10m: booking=%s; student refunded and given 1 bonus credit', booking.id)


def end_of_window_reason(booking) -> str:
    """Why a lesson that is still CONFIRMED at its end never got a verdict (it is disputed, never scored)."""
    if not booking.zoom_meeting_id:
        return 'no attendance verdict before the lesson ended: no Zoom meeting provisioned'
    return 'no attendance verdict before the lesson ended: Zoom probe unresolved'


def dispute_without_verdict(booking, reason: str) -> None:
    """Human-visible state for a lesson we cannot judge: DISPUTED + an open DisputeCase. No refund, strike or credit."""
    result = transition_booking(booking, S.DISPUTED, actor=ACTOR, reason=reason)
    DisputeCase.objects.get_or_create(booking=booking, defaults={
        'student': booking.student, 'teacher': booking.teacher, 'status': DisputeCase.Status.OPEN,
        'student_statement': f'Automated: {reason}.',
        'teacher_statement': '',
        'admin_notes': 'No attendance verdict was possible (Slice F0). Nothing was refunded, credited or struck: '
                       'decide from the attendance records and the Zoom account.'})
    if result.changed:
        # TODO(N1a): admin notification through notify(); the open DisputeCase is the durable work item meanwhile.
        logger.error('[ADMIN ALERT] Lesson disputed without an attendance verdict: booking=%s', booking.id)
