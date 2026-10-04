"""
The one place new code reads the current time (plan §5: "clock seam, no `datetime.now()` in new code").

    from apps.common import clock
    deadline = clock.now() + timedelta(hours=24)

Tests freeze it with the `frozen_clock` fixture (tests/conftest.py). `from apps.common.clock import now` works too: the
freeze is applied inside `now()`, not by replacing the function. Existing code still calls `django.utils.timezone.now()`
and is not migrated here; Phase 11/12 slices use this seam for new code.
"""
from datetime import datetime
from typing import Callable, Optional

from django.utils import timezone

# Test hook only: the `frozen_clock` fixture sets this (via monkeypatch) and it is restored after each test.
_override: Optional[Callable[[], datetime]] = None


def now() -> datetime:
    """The current time as an aware UTC datetime."""
    if _override is not None:
        return _override()
    return timezone.now()
