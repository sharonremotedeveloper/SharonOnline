"""Which video technology serves a lesson (D-9, Zoom Video SDK direction).

A lesson is an SDK lesson when the Video SDK is configured and the booking has no Zoom Meetings room. Lessons that already
have a `zoom_meeting_id` (booked before the switch, or while the SDK was unconfigured) stay on the legacy Meetings path
until slice V5 retires it. No stored flag: the rule is derived, so a configuration change cannot orphan a lesson.
"""
from apps.integrations.services.video_sdk import is_video_sdk_configured


def uses_video_sdk(booking) -> bool:
    return not booking.zoom_meeting_id and is_video_sdk_configured()
