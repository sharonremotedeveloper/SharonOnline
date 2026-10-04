import os
import requests
import logging

logger = logging.getLogger(__name__)

def sync_booking_to_teacher_gcal(booking) -> str:
    """
    Inserts a confirmed booking onto the teacher's connected Google Calendar via Google Calendar API v3.
    Returns the Google Calendar event ID if successful. It does NOT save the booking: the caller stores the id under the
    booking's row lock (bookings/services/fulfillment.py), so a stale instance can never overwrite a cancel or a reschedule.
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
            logger.info(f"Successfully synced to Google Calendar event_id={event_id}")
            return event_id
        else:
            logger.warning(f"Google Calendar sync error: {resp.text}")
    except Exception as e:
        logger.error(f"Failed to communicate with Google Calendar API: {e}")

    return ""


def delete_teacher_gcal_event(user, event_id: str) -> bool:
    """Remove a lesson from the tutor's Google Calendar (lesson cancelled or moved). Returns False when there was nothing to do."""
    token = user.google_calendar_token
    access_token = token.get('access_token') if token else None
    if not (event_id and access_token):
        return False
    resp = requests.delete(f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                           headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    if resp.status_code in (200, 204, 404, 410):       # already gone counts as done
        return True
    raise RuntimeError(f"Google Calendar refused to delete event {event_id}: HTTP {resp.status_code}")
