"""Q0: `apps/common/clock.py` is the one seam new code reads the time through; `frozen_clock` freezes it."""
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.utils import timezone

from apps.common import clock
from apps.common.clock import now as imported_now


def test_now_is_aware_utc_and_current():
    before = timezone.now()
    value = clock.now()
    assert value.tzinfo is not None
    assert before <= value <= timezone.now()


def test_frozen_clock_freezes_and_advances(frozen_clock):
    start = datetime(2026, 3, 29, 0, 30, tzinfo=dt_timezone.utc)
    frozen_clock.set(start)
    assert clock.now() == start
    assert imported_now() == start                      # `from apps.common.clock import now` sees the freeze too
    frozen_clock.advance(minutes=25)
    assert clock.now() == start + timedelta(minutes=25)


def test_frozen_clock_starts_at_a_fixed_instant(frozen_clock):
    assert clock.now() == frozen_clock.now
    assert clock.now() == clock.now()                   # it does not tick on its own


def test_frozen_clock_rejects_naive_datetimes(frozen_clock):
    with pytest.raises(ValueError):
        frozen_clock.set(datetime(2026, 1, 1, 12, 0))


def test_clock_is_live_again_after_the_fixture():
    # Runs after the frozen tests above: nothing leaked.
    assert abs(clock.now() - timezone.now()) < timedelta(seconds=5)
