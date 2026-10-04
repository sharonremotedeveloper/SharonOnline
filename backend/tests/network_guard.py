"""
No-network guard for the test suite (Q0). Installed by the autouse `no_network` fixture in conftest.py.

Blocks `socket.socket.connect` / `connect_ex` and `socket.getaddrinfo` for anything that is not local, so no test can reach
Zoom, Resend, Google, PayPal, PayFast or R2 by accident (use the fakes in tests/fakes.py instead). Allowed:
  * Unix sockets, localhost / 127.0.0.0/8 / ::1 (the Postgres and Redis CI jobs use 127.0.0.1);
  * the hosts named in DATABASE_URL / REDIS_URL / REDIS_TEST_URL (e.g. `db` / `redis` under docker compose), plus the
    addresses they resolve to.
Opt out per test with `@pytest.mark.allow_network`.

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


def _guarded_connect(self, address):
    if self.family == getattr(socket, 'AF_UNIX', object()) or is_local(address):
        return ORIGINAL_CONNECT(self, address)
    raise NetworkBlocked(f'Test tried to connect to {address!r}; use tests/fakes.py or mark it allow_network')


def _guarded_connect_ex(self, address):
    if self.family == getattr(socket, 'AF_UNIX', object()) or is_local(address):
        return ORIGINAL_CONNECT_EX(self, address)
    raise NetworkBlocked(f'Test tried to connect to {address!r}; use tests/fakes.py or mark it allow_network')


def _guarded_getaddrinfo(host, *args, **kwargs):
    name = host.decode() if isinstance(host, bytes) else (host or '')
    if not _host_allowed(name):
        raise NetworkBlocked(f'Test tried to resolve {name!r}; use tests/fakes.py or mark it allow_network')
    results = ORIGINAL_GETADDRINFO(host, *args, **kwargs)
    if name.lower() in _service_hosts():
        _resolved_service_ips.update(str(info[4][0]).lower() for info in results)
    return results


def install(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', _guarded_connect)
    monkeypatch.setattr(socket.socket, 'connect_ex', _guarded_connect_ex)
    monkeypatch.setattr(socket, 'getaddrinfo', _guarded_getaddrinfo)
