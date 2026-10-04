"""E-mail helpers built on the one sender, `apps.integrations.services.email.send_email` (slice N1c).

`send_email` here is the older raising interface the Celery tasks use (account mails, refunds, alerts, Eskom, cancellations):
it delegates to the service and raises `EmailDeliveryError` for anything but `sent`, so those tasks keep retrying exactly as
before. N4 moves them onto `notify()`; see docs/slices/N1c.md for the inventory.
"""
import logging

from icalendar import Calendar, Event

from .services import email as email_service
from .services.email import Attachment, render_html

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Not sent, but worth retrying (`in_flight` / `retryable`); `.result` is the `EmailResult` when there is one."""

    def __init__(self, message: str = '', result=None):
        super().__init__(message)
        self.result = result


class EmailPermanentError(EmailDeliveryError):
    """Not sent and retrying cannot help (`failed`: 4xx validation/auth, not configured). Celery callers do not retry it."""


def raise_for_result(result, label: str) -> None:
    """Raise the right error for a result that is not `sent`. The message holds status and code only (no address)."""
    if result.ok:
        return
    error = EmailPermanentError if result.status == email_service.FAILED else EmailDeliveryError
    raise error(f'{label} {result.status} ({result.error_code})', result=result)


def log_permanent_failure(task_name: str, ref_id, exc: EmailPermanentError) -> None:
    """One line for a human: which task and record, and the provider's short code. Never the address or body."""
    code = exc.result.error_code if exc.result is not None else ''
    logger.error('email.permanent_failure task=%s ref=%s error_code=%s (not retried)', task_name, ref_id, code)


def send_email(to: str, subject: str, html: str, text: str = '') -> None:
    """Raising wrapper over the unified sender: `EmailPermanentError` for `failed`, `EmailDeliveryError` otherwise."""
    raise_for_result(email_service.send_email(to, subject, html, text), 'e-mail')


def generate_ics_content(booking) -> bytes:
    """
    Generates standard RFC 5545 .ics calendar data for the 25-minute lesson.
    """
    cal = Calendar()
    cal.add('prodid', '-//Sharon ESL Marketplace//sharonesl.com//EN')
    cal.add('version', '2.0')

    event = Event()
    event.add('summary', f"English Lesson: {booking.student.first_name or booking.student.username} & {booking.teacher.user.first_name or booking.teacher.user.username}")
    event.add('dtstart', booking.start_time_utc)
    event.add('dtend', booking.end_time_utc)
    event.add('description', f"Your 25-minute 1-on-1 English lesson on Sharon ESL.\n\nJoin Zoom Link: {booking.zoom_join_url}\nMeeting Password: {booking.zoom_password}")
    event.add('location', booking.zoom_join_url)
    event.add('status', 'CONFIRMED')

    cal.add_component(event)
    return cal.to_ical()


_CONFIRMATION_HTML = (
    '<h2>Your Lesson is Confirmed!</h2>'
    '<p>Hi {student},</p>'
    '<p>Your 25-minute lesson with <strong>{tutor}</strong> is locked in.</p>'
    '<p><strong>Time:</strong> {when}</p>'
    '<p><a href="{join_url}" style="background-color: #0D4440; color: white; padding: 10px 20px; '
    'text-decoration: none; border-radius: 6px;">Launch Classroom (Zoom)</a></p>'
    "<p>We've attached your calendar invite (.ics). See you in class!</p>"
)


def booking_confirmation_key(booking) -> str:
    """Resend idempotency key: one confirmation per booking generation (a reschedule bumps `reschedule_count`)."""
    return f'booking-confirmed:{booking.id}:{booking.reschedule_count}:student'


def build_booking_confirmation(booking):
    """(subject, html, text) for the student's confirmation; every interpolated value is escaped."""
    when = booking.start_time_utc.strftime('%Y-%m-%d %H:%M UTC')
    student = booking.student.first_name or booking.student.username
    tutor = booking.teacher.user.first_name or booking.teacher.user.username
    join_url = booking.zoom_join_url or ''
    subject = f'Confirmed: Your English Lesson on Sharon ESL ({when})'
    html = render_html(_CONFIRMATION_HTML, student=student, tutor=tutor, when=when, join_url=join_url)
    text = (f'Hi {student},\n\nYour 25-minute lesson with {tutor} is locked in.\nTime: {when}\n'
            f'Join: {join_url}\n\nYour calendar invite (.ics) is attached. See you in class!')
    return subject, html, text


def send_booking_confirmation_email(booking):
    """
    Sends the student's confirmation with the .ics invite through the unified sender. Returns the `EmailResult`;
    raises `EmailPermanentError` for `failed` and `EmailDeliveryError` for `in_flight` / `retryable`, so the fulfilment
    task (F0) can stop on the first and retry the second (before N1c a provider error returned False and the step was
    marked done anyway).
    """
    subject, html, text = build_booking_confirmation(booking)
    invite = Attachment('lesson-invite.ics', generate_ics_content(booking), 'text/calendar')
    result = email_service.send_email(booking.student.email, subject, html, text,
                                      idempotency_key=booking_confirmation_key(booking), attachments=[invite],
                                      tags={'kind': 'booking_confirmed'})
    raise_for_result(result, 'booking confirmation')
    logger.info('Booking confirmation e-mail sent for booking=%s provider_id=%s', booking.id, result.provider_message_id)
    return result
