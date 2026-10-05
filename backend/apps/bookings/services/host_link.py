"""
Fresh Zoom host link for the classroom (Slice Z1; docs/ZOOM_ATTENDANCE.md "Host link").

The host start link embeds a ZAK that expires (about 2 h for a regular user; to verify in the sandbox), so it is never stored
or e-mailed or put in a calendar event. The booking's tutor (or staff) asks for it when the classroom opens and gets a link
fetched from Zoom (`GET /meetings/{id}`) at that moment.

Access: the booking's own tutor and platform staff (role admin / is_staff / superuser). The booking's student gets 403 (they
know the lesson exists; the host link is not theirs); anybody else gets 404 (the booking's existence is not revealed).
Window: from `ZOOM_HOST_LINK_OPEN_MINUTES_BEFORE` (15) minutes before the start until the lesson ends (409 `too_early`).

Staff hosting (QA #3): whoever opens the host link IS the host, and the attendance rule credits the host as the tutor, so a
staff-issued link would show an absent tutor as present. Every link issued to staff who are not the tutor therefore writes a
`HostLinkIssue` row (who, when) that holds the lesson's escrow release until an admin reviews it
(`review_host_link_issues`; `settlement.attendance_verified_for_release`).

Logs carry booking / user / meeting ids only, never the link.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone as dj_timezone

from apps.bookings.models import Booking, HostLinkIssue
from apps.common import clock
from apps.integrations.zoom import ZoomError, ZoomNotFound, zoom_client
logger = logging.getLogger(__name__)

LIVE = (Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS)


class HostLinkError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


class ReviewRefused(Exception):
    """The reviewer may not clear this hold (not an admin, or reviewing their own link)."""


def can_review(user) -> bool:
    """Who may clear a staff-host hold in Django admin: active, `is_staff`, and superuser or role admin. The SAME predicate
    decides who may obtain a staff host link at all (QA re-review #2), so a row is never created by someone who cannot reach
    the admin screen and a non-admin staff member cannot start a lesson as host."""
    return bool(user.is_active and user.is_staff and (user.is_superuser or getattr(user, 'role', None) == 'admin'))


def _authorised_booking(booking_id, user) -> Booking:
    booking = Booking.objects.select_related('teacher').filter(pk=booking_id).first()
    if booking is None:
        raise HostLinkError(404, 'not_found', 'Booking not found.')
    if booking.teacher.user_id == user.pk or can_review(user):
        return booking
    if booking.student_id == user.pk:
        raise HostLinkError(403, 'host_only', 'Only the tutor of this lesson can start it as host.')
    raise HostLinkError(404, 'not_found', 'Booking not found.')


def _check_open(booking: Booking) -> None:
    if booking.status not in LIVE:
        raise HostLinkError(409, 'not_live', 'This lesson is not scheduled to take place.')
    if not booking.zoom_meeting_id:
        raise HostLinkError(409, 'no_meeting', 'The Zoom room for this lesson is not ready yet.')
    now = clock.now()
    if now >= booking.end_time_utc:
        raise HostLinkError(409, 'lesson_ended', 'This lesson has ended.')
    opens = booking.start_time_utc - timedelta(minutes=settings.ZOOM_HOST_LINK_OPEN_MINUTES_BEFORE)
    if now < opens:
        raise HostLinkError(409, 'too_early', 'The classroom opens shortly before the lesson starts.')


def _fetch(booking: Booking, user) -> str:
    try:
        return zoom_client.get_start_url(booking.zoom_meeting_id)
    except ZoomNotFound:
        logger.error('[ADMIN ALERT] Zoom has no meeting for a live lesson: booking=%s meeting=%s',
                     booking.pk, booking.zoom_meeting_id)
        raise HostLinkError(409, 'meeting_missing', 'The Zoom room for this lesson no longer exists.') from None
    except ZoomError as exc:
        logger.warning('Host link unavailable: booking=%s error=%s status=%s', booking.pk, type(exc).__name__, exc.status)
    except Exception as exc:    # anything unexpected (cache, parsing, ...) is still a structured answer, never a bare 500
        logger.error('Host link failed unexpectedly: booking=%s user=%s error=%s', booking.pk, user.pk, type(exc).__name__)
    raise HostLinkError(502, 'zoom_unavailable', 'Zoom is not answering right now. Please try again.')


def fresh_host_link(booking_id, user) -> dict:
    """{'meeting_id', 'start_url'} straight from Zoom, or HostLinkError (404/403/409/502)."""
    booking = _authorised_booking(booking_id, user)
    _check_open(booking)
    start_url = _fetch(booking, user)
    if booking.teacher.user_id != user.pk:      # staff, not the tutor: audited, and the lesson's escrow waits for a review
        HostLinkIssue.objects.create(booking=booking, issued_by=user)
        logger.warning('Host link issued to STAFF (attendance review required): booking=%s user=%s', booking.pk, user.pk)
    logger.info('Host link issued: booking=%s user=%s meeting=%s', booking.pk, user.pk, booking.zoom_meeting_id)
    return {'meeting_id': booking.zoom_meeting_id, 'start_url': start_url}


def review_host_link_issues(queryset, reviewer) -> int:
    """Stamp still-open audit rows as reviewed (the tutor's real attendance was checked). Returns how many were open.

    Refuses (`ReviewRefused`, nothing changed) when `reviewer` cannot review, or when ANY open selected row was issued to the
    reviewer themselves (a superuser may: with one admin on the platform nobody else could clear the hold)."""
    if not can_review(reviewer):
        raise ReviewRefused('not allowed to review host-link audit rows')
    open_rows = queryset.filter(reviewed_at__isnull=True)
    if not reviewer.is_superuser and open_rows.filter(issued_by=reviewer).exists():
        raise ReviewRefused('a host link cannot be reviewed by the person it was issued to')
    return open_rows.update(reviewed_at=dj_timezone.now(), reviewed_by=reviewer)
