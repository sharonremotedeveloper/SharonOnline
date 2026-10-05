"""Live-session probe for Video SDK lessons (slice V4 implements `probe_session`; this file is the seam).

Contract (tests/test_v4_attendance_contract.py), mirroring the Meetings probe in `attendance_probe.py`:
    STARTED      the SDK session `lesson-<booking id>` is live AND the tutor is in it
    NOT_STARTED  Zoom positively reports that no tutor ever joined a session for this lesson
    UNKNOWN      anything else: an error, a timeout, missing credentials, an unexpected payload, no way to tell

Only an explicit answer may be returned as STARTED / NOT_STARTED; the safe default is UNKNOWN (it defers the verdict and a
lesson still unresolved at its end goes to DISPUTED, never to a no-show).
"""
UNKNOWN = 'unknown'


def probe_session(booking) -> str:
    """Placeholder until V4: no way to ask Zoom yet, so the answer is always UNKNOWN."""
    return UNKNOWN
