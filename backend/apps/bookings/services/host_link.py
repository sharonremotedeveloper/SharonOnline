"""
Fresh Zoom host link for the classroom (Slice Z1; docs/ZOOM_ATTENDANCE.md "Host link").

The host start link embeds a ZAK that expires (about 2 h for a regular user; to verify in the sandbox), so it is never stored
or e-mailed or put in a calendar event. The booking's tutor (or staff) asks for it when the classroom opens and gets a link
fetched from Zoom (`GET /meetings/{id}`) at that moment.

Access: the booking's own tutor and platform staff (role admin / is_staff / superuser). The booking's student gets 403 (they
know the lesson exists; the host link is not theirs); anybody else gets 404 (the booking's existence is not revealed).
Staff opening the room as host count as the host in attendance (the `host_id` rule in docs/ZOOM_ATTENDANCE.md): staff do this
only to rescue a lesson, never routinely.

Logs carry booking / user / meeting ids only, never the link.
"""
import logging

from apps.bookings.models import Booking
from apps.common import clock
from apps.integrations.zoom import ZoomError, ZoomNotFound, zoom_client

logger = logging.getLogger(__name__)

LIVE = (Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS)


class HostLinkError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code, self.code, self.message = status_code, code, message


def is_staff(user) -> bool:
    return bool(getattr(user, 'role', None) == 'admin' or user.is_staff or user.is_superuser)


def _authorised_booking(booking_id, user) -> Booking:
    booking = Booking.objects.select_related('teacher').filter(pk=booking_id).first()
    if booking is None:
        raise HostLinkError(404, 'not_found', 'Booking not found.')
    if booking.teacher.user_id == user.pk or is_staff(user):
        return booking
    if booking.student_id == user.pk:
        raise HostLinkError(403, 'host_only', 'Only the tutor of this lesson can start it as host.')
    raise HostLinkError(404, 'not_found', 'Booking not found.')


def fresh_host_link(booking_id, user) -> dict:
    """{'meeting_id', 'start_url'} straight from Zoom, or HostLinkError (404/403/409/502)."""
    booking = _authorised_booking(booking_id, user)
    if booking.status not in LIVE:
        raise HostLinkError(409, 'not_live', 'This lesson is not scheduled to take place.')
    if not booking.zoom_meeting_id:
        raise HostLinkError(409, 'no_meeting', 'The Zoom room for this lesson is not ready yet.')
    if clock.now() >= booking.end_time_utc:
        raise HostLinkError(409, 'lesson_ended', 'This lesson has ended.')
    try:
        start_url = zoom_client.get_start_url(booking.zoom_meeting_id)
    except ZoomNotFound:
        logger.error('[ADMIN ALERT] Zoom has no meeting for a live lesson: booking=%s meeting=%s',
                     booking.pk, booking.zoom_meeting_id)
        raise HostLinkError(409, 'meeting_missing', 'The Zoom room for this lesson no longer exists.') from None
    except ZoomError as exc:
        logger.warning('Host link unavailable: booking=%s error=%s status=%s', booking.pk, type(exc).__name__, exc.status)
        raise HostLinkError(502, 'zoom_unavailable', 'Zoom is not answering right now. Please try again.') from None
    logger.info('Host link issued: booking=%s user=%s meeting=%s', booking.pk, user.pk, booking.zoom_meeting_id)
    return {'meeting_id': booking.zoom_meeting_id, 'start_url': start_url}
