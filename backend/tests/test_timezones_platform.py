"""
ERR-194: `zoneinfo.available_timezones()` is platform dependent. On Linux system tz directories it also lists names that are
not IANA zones (`localtime` = "whatever this server's zone is", `posixrules`, `Factory`, `posix/...`, `right/...`), so the
T2 validator accepted `localtime` on CI while it rejected it on Windows. The rule must not depend on the platform.
"""
import pytest

from apps.common import timezones

LINUX_STYLE_LISTING = frozenset({
    'UTC', 'Africa/Johannesburg', 'Europe/Berlin', 'Asia/Tokyo',
    'localtime', 'posixrules', 'Factory', 'posix/Europe/Berlin', 'right/Europe/Berlin',
})


@pytest.fixture
def linux_listing(monkeypatch):
    monkeypatch.setattr(timezones, 'available_timezones', lambda: set(LINUX_STYLE_LISTING))
    timezones._known.cache_clear()
    yield
    timezones._known.cache_clear()


@pytest.mark.parametrize('name', ['localtime', 'posixrules', 'Factory', 'posix/Europe/Berlin', 'right/Europe/Berlin'])
def test_system_directory_artifacts_are_not_timezones(linux_listing, name):
    assert timezones.is_valid_timezone(name) is False
    with pytest.raises(ValueError):
        timezones.get_zone(name)


@pytest.mark.parametrize('name', ['UTC', 'Africa/Johannesburg', 'Europe/Berlin', 'Asia/Tokyo'])
def test_real_zones_still_validate(linux_listing, name):
    assert timezones.is_valid_timezone(name) is True
    assert timezones.get_zone(name).key == name
