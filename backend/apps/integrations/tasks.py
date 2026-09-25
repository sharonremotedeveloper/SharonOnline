from celery import shared_task
from apps.bookings.models import Booking
from .zoom import zoom_client
from .google_calendar import sync_booking_to_teacher_gcal
from .email import send_booking_confirmation_email
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def dispatch_booking_fulfillment(self, booking_id: str):
    """
    Asynchronous Celery task that executes upon payment confirmation:
    1. Provisions a dedicated 25-minute Zoom meeting room via Server-to-Server OAuth 2.0.
    2. Syncs the confirmed lesson into the teacher's connected Google Calendar.
    3. Generates the standard .ics calendar invite and emails it to the student via Resend.
    """
    try:
        booking = Booking.objects.get(id=booking_id)
    except Booking.DoesNotExist:
        logger.error(f"Cannot fulfill booking: ID {booking_id} does not exist.")
        return False

    # 1. Provision Zoom Meeting
    if not booking.zoom_meeting_id:
        try:
            topic = f"Sharon ESL: {booking.student.first_name or booking.student.username} with {booking.teacher.user.first_name or booking.teacher.user.username}"
            zoom_data = zoom_client.create_meeting(
                topic=topic,
                start_time_iso=booking.start_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
                duration_minutes=25
            )
            booking.zoom_meeting_id = zoom_data['meeting_id']
            booking.zoom_join_url = zoom_data['join_url']
            booking.zoom_start_url = zoom_data['start_url']
            booking.zoom_password = zoom_data.get('password', '')
            booking.save()
            logger.info(f"Zoom meeting provisioned successfully for booking={booking_id}: ID={booking.zoom_meeting_id}")
        except Exception as exc:
            logger.error(f"Error provisioning Zoom room for booking {booking_id}: {exc}")
            raise self.retry(exc=exc)

    # 2. Sync to Teacher Google Calendar
    try:
        sync_booking_to_teacher_gcal(booking)
    except Exception as exc:
        logger.warning(f"Google Calendar sync warning for booking {booking_id}: {exc}")

    # 3. Send Transactional Confirmation Email with .ics Invite
    try:
        send_booking_confirmation_email(booking)
    except Exception as exc:
        logger.warning(f"Email dispatch warning for booking {booking_id}: {exc}")

    return True
