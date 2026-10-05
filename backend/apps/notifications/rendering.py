"""Helpers for notification renderers (slice N1a). HTML goes through `render_html` (every value escaped)."""
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.integrations.services.email import render_html  # noqa: F401  (re-exported for kind modules)

MAX_LINE = 200
_WHITESPACE = re.compile(r'[\r\n\t\x0b\x0c]+')
_TIME_FORMAT = '%a %d %b %Y, %H:%M'


def one_line(value) -> str:
    """Subjects and titles: no CR/LF (no header injection), single spaces, at most 200 characters."""
    flat = _WHITESPACE.sub(' ', str(value or ''))
    return re.sub(r' {2,}', ' ', flat).strip()[:MAX_LINE]


def recipient_zone(user):
    """The recipient's IANA zone, or None when it is blank or invalid (the caller then shows UTC with a label)."""
    name = (getattr(user, 'timezone', '') or '').strip()
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def local_time(when, user) -> str:
    """`when` (aware, UTC) in the recipient's zone; blank/invalid zone -> UTC with a visible label."""
    zone = recipient_zone(user)
    if zone is None:
        return f'{when.astimezone(ZoneInfo("UTC")).strftime(_TIME_FORMAT)} UTC (time zone not set in your profile)'
    return f'{when.astimezone(zone).strftime(_TIME_FORMAT)} ({zone.key})'


def first_name(user) -> str:
    return one_line(getattr(user, 'first_name', '') or '') or 'there'
