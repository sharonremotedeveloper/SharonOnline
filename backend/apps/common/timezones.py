"""
IANA timezone helpers (T2). One definition of "a real timezone" for save-time validation and slot generation.

`zoneinfo.ZoneInfo(key)` alone is too lenient (it will load any file under the tz database path, e.g. `localtime`, or a
differently cased name on a case-insensitive filesystem), so a key must also be in `zoneinfo.available_timezones()`.
"""
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones


# Names a system tz directory can contain that are not IANA zones. `available_timezones()` is platform dependent: Linux
# lists these, Windows (tzdata package) does not (ERR-194).
_NOT_ZONES = frozenset({'localtime', 'posixrules', 'Factory'})
_NOT_ZONE_PREFIXES = ('posix/', 'right/')


@lru_cache(maxsize=1)
def _known() -> frozenset:
    return frozenset(name for name in available_timezones()
                     if name not in _NOT_ZONES and not name.startswith(_NOT_ZONE_PREFIXES))


def is_valid_timezone(name) -> bool:
    return isinstance(name, str) and name in _known()


def get_zone(name) -> ZoneInfo:
    """The ZoneInfo for a valid IANA key; raises ValueError for anything else (never falls back to another zone)."""
    if not is_valid_timezone(name):
        raise ValueError('not an IANA timezone')
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:     # listed but unloadable: a broken tz install
        raise ValueError('timezone data unavailable') from exc
