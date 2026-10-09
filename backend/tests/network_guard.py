"""
No-network guard for the test suite (Q0). Installed by the autouse `no_network` fixture in conftest.py.

Blocks `socket.socket.connect` / `connect_ex` and `socket.getaddrinfo` for anything that is not local, so no test can reach
Daily, Resend, Google, PayPal, PayFast or R2 by accident (use the fakes in tests/fakes.py instead). Allowed:
  * Unix sockets, localhost / 127.0.0.0/8 / ::1 (the Postgres and Redis CI jobs use 127.0.0.1);
  * the hosts named in DATABASE_URL / REDIS_URL / REDIS_TEST_URL (e.g. `db` / `redis` under docker compose), plus the
    addresses they resolve to.
Opt out per test with `@pytest.mark.allow_network`. `gethostbyname` / `gethostbyname_ex` are guarded too.

Every blocked attempt is recorded; the fixture FAILS the test at teardown if any happened, so an attempt that application
code swallowed (`except Exception`) still fails loudly. A test that provokes a block on purpose calls `consume()`.

`NetworkBlocked` deliberately is NOT an OSError: requests/urllib3 would wrap an OSError into a ConnectionError that
production code treats as a transient provider failure, hiding the fact that a test tried to go online.
"""
import ipaddress
import os
import socket
from urllib.parse import urlparse

ORIGINAL_CONNECT = socket.socket.connect
ORIGINAL_CONNECT_EX = socket.socket.connect_ex
ORIGINAL_GETADDRINFO = socket.getaddrinfo
ORIGINAL_GETHOSTBYNAME = socket.gethostbyname
ORIGINAL_GETHOSTBYNAME_EX = socket.gethostbyname_ex

LOCAL_NAMES = {'localhost', 'localhost.localdomain', 'ip6-localhost', ''}
SERVICE_URL_ENV = ('DATABASE_URL', 'REDIS_URL', 'REDIS_TEST_URL')


class NetworkBlocked(RuntimeError):
    """A test tried to open a real network connection."""


def _service_hosts():
    hosts = set()
    for name in SERVICE_URL_ENV:
        host = urlparse(os.environ.get(name, '') or '').hostname
        if host:
            hosts.add(host.lower())
    return hosts


_resolved_service_ips = set()


def _is_loopback(host):
    try:
        return ipaddress.ip_address(host.split('%', 1)[0]).is_loopback
    except ValueError:
        return False


def _host_allowed(host):
    host = (host or '').lower()
    return host in LOCAL_NAMES or host.endswith('.localhost') or _is_loopback(host) or host in _service_hosts() \
        or host in _resolved_service_ips


def is_local(address):
    """True for a Unix socket path or an (host, port[, ...]) tuple pointing at an allowed host."""
    if isinstance(address, (str, bytes)):
        return True                                   # AF_UNIX path
    if isinstance(address, tuple) and address:
        host = address[0]
        return _host_allowed(host.decode() if isinstance(host, bytes) else str(host))
    return False


# Every blocked attempt of the current test. Application code may swallow NetworkBlocked (`except Exception`), so the
# `no_network` fixture fails the test at teardown when this is not empty (tests that provoke a block call consume()).
_attempts = []


def _block(what):
    message = f'Test tried to {what}; use tests/fakes.py or mark it allow_network'
    _attempts.append(message)
    raise NetworkBlocked(message)


def consume():
    """Return and clear the blocked attempts recorded so far (for tests that trigger a block on purpose)."""
    taken = list(_attempts)
    _attempts.clear()
    return taken


def teardown_error():
    """The failure message for the fixture's teardown, or None when no attempt was blocked."""
    if not _attempts:
        return None
    return 'Blocked network access (possibly swallowed by application code):\n  ' + '\n  '.join(_attempts)


def _guarded_connect(self, address):
    if self.family == getattr(socket, 'AF_UNIX', object()) or is_local(address):
        return ORIGINAL_CONNECT(self, address)
    _block(f'connect to {address!r}')


def _guarded_connect_ex(self, address):
    if self.family == getattr(socket, 'AF_UNIX', object()) or is_local(address):
        return ORIGINAL_CONNECT_EX(self, address)
    _block(f'connect to {address!r}')


def _name(host):
    return host.decode() if isinstance(host, bytes) else (host or '')


def _guarded_getaddrinfo(host, *args, **kwargs):
    name = _name(host)
    if not _host_allowed(name):
        _block(f'resolve {name!r}')
    results = ORIGINAL_GETADDRINFO(host, *args, **kwargs)
    if name.lower() in _service_hosts():
        _resolved_service_ips.update(str(info[4][0]).lower() for info in results)
    return results


def _guarded_gethostbyname(host):
    if not _host_allowed(_name(host)):
        _block(f'resolve {_name(host)!r}')
    return ORIGINAL_GETHOSTBYNAME(host)


def _guarded_gethostbyname_ex(host):
    if not _host_allowed(_name(host)):
        _block(f'resolve {_name(host)!r}')
    return ORIGINAL_GETHOSTBYNAME_EX(host)


def install(monkeypatch):
    _attempts.clear()
    monkeypatch.setattr(socket.socket, 'connect', _guarded_connect)
    monkeypatch.setattr(socket.socket, 'connect_ex', _guarded_connect_ex)
    monkeypatch.setattr(socket, 'getaddrinfo', _guarded_getaddrinfo)
    monkeypatch.setattr(socket, 'gethostbyname', _guarded_gethostbyname)
    monkeypatch.setattr(socket, 'gethostbyname_ex', _guarded_gethostbyname_ex)
