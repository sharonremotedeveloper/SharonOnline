"""
Which Zoom user hosts a lesson meeting (Slice Z1; docs/ZOOM_ATTENDANCE.md "Host allocation").

Today every lesson is hosted by one user, settings.ZOOM_HOST_USER_ID (default 'me' = the account owning the S2S app). One
licensed host can run ONE meeting at a time, so two concurrent lessons collide: **launch blocker pending D-9** (a host pool,
e.g. one licence per ~3 concurrent tutors with alternative hosts). D-9 replaces `pick_host` with an allocation over the
pool; callers already store the answer in `Booking.zoom_host_user_id`, so the probe, deletion and host-link paths need no
change.
"""
from django.conf import settings


class HostPicker:
    def pick_host(self, booking) -> str:
        """The Zoom user id (or e-mail, or 'me') the booking's meeting is created under."""
        return (getattr(settings, 'ZOOM_HOST_USER_ID', '') or 'me').strip() or 'me'


host_picker = HostPicker()
