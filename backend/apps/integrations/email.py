import os
import requests
from icalendar import Calendar, Event
import logging

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """The provider refused or could not be reached; callers (Celery tasks) retry."""


def send_email(to: str, subject: str, html: str, text: str = '') -> None:
    """
    Generic transactional send through Resend. Raises EmailDeliveryError on failure (never swallows it).
    Without a real key (dev/test) it logs instead of sending; the body (which holds links) is only logged when DEBUG.
    """
    from django.conf import settings
    api_key = os.environ.get('RESEND_API_KEY')
    if not api_key or api_key.startswith('re_dev'):
        logger.info("[DEV EMAIL MOCK] to=%s subject=%r%s", to, subject, f"\n{text}" if (settings.DEBUG and text) else "")
        return
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": os.environ.get('DEFAULT_FROM_EMAIL', 'Sharon ESL <bookings@sharonesl.com>'),
                  "to": [to], "subject": subject, "html": html, **({"text": text} if text else {})},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise EmailDeliveryError(str(exc)) from exc
    if resp.status_code >= 300:
        raise EmailDeliveryError(f"Resend returned {resp.status_code}")

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

def send_booking_confirmation_email(booking):
    """
    Sends transactional confirmation email with attached .ics calendar file via Resend API.
    """
    api_key = os.environ.get('RESEND_API_KEY')
    if not api_key or api_key.startswith('re_dev'):
        logger.info(f"[DEV EMAIL MOCK] Booking confirmation email dispatched for booking={booking.id} to student={booking.student.email}")
        return True

    ics_bytes = generate_ics_content(booking)
    import base64
    ics_base64 = base64.b64encode(ics_bytes).decode()

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "from": os.environ.get('DEFAULT_FROM_EMAIL', 'Sharon ESL <bookings@sharonesl.com>'),
        "to": [booking.student.email],
        "subject": f"Confirmed: Your English Lesson on Sharon ESL ({booking.start_time_utc.strftime('%Y-%m-%d %H:%M UTC')})",
        "html": f"""
        <h2>Your Lesson is Confirmed!</h2>
        <p>Hi {booking.student.first_name or booking.student.username},</p>
        <p>Your 25-minute lesson with <strong>{booking.teacher.user.first_name or booking.teacher.user.username}</strong> is locked in.</p>
        <p><strong>Time:</strong> {booking.start_time_utc.strftime('%Y-%m-%d %H:%M UTC')}</p>
        <p><a href="{booking.zoom_join_url}" style="background-color: #0D4440; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px;">Launch Classroom (Zoom)</a></p>
        <p>We've attached your calendar invite (.ics). See you in class!</p>
        """,
        "attachments": [
            {
                "filename": "lesson-invite.ics",
                "content": ics_base64
            }
        ]
    }

    resp = requests.post(url, headers=headers, json=data, timeout=10)
    if resp.status_code == 200:
        logger.info(f"Resend email sent successfully for booking={booking.id}")
        return True
    logger.error(f"Resend email error: {resp.text}")
    return False
