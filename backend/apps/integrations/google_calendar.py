import os
import requests
import logging

logger = logging.getLogger(__name__)

def sync_booking_to_teacher_gcal(booking) -> str:
    """
    Inserts a confirmed booking onto the teacher's connected Google Calendar via Google Calendar API v3.
    Returns the Google Calendar event ID if successful.
    """
    teacher_token = booking.teacher.user.google_calendar_token
    if not teacher_token:
        logger.info(f"Teacher {booking.teacher.user.username} does not have Google Calendar connected. Skipping sync.")
        return ""

    access_token = teacher_token.get('access_token')
    if not access_token:
        return ""

    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    event_body = {
        "summary": f"Sharon ESL: Lesson with {booking.student.first_name or booking.student.username}",
        "description": f"25-minute lesson.\n\nHost Zoom URL: {booking.zoom_start_url or booking.zoom_join_url}",
        "start": {
            "dateTime": booking.start_time_utc.isoformat(),
            "timeZone": "UTC"
        },
        "end": {
            "dateTime": booking.end_time_utc.isoformat(),
            "timeZone": "UTC"
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 10},
                {"method": "email", "minutes": 30}
            ]
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=event_body, timeout=10)
        if resp.status_code in [200, 201]:
            event_id = resp.json().get('id', '')
            booking.teacher_gcal_event_id = event_id
            booking.save(update_fields=['teacher_gcal_event_id'])
            logger.info(f"Successfully synced to Google Calendar event_id={event_id}")
            return event_id
        else:
            logger.warning(f"Google Calendar sync error: {resp.text}")
    except Exception as e:
        logger.error(f"Failed to communicate with Google Calendar API: {e}")

    return ""
