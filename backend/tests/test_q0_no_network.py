"""Q0: the autouse no-network fixture blocks real outbound sockets; localhost and the `allow_network` marker are exempt."""
import socket

import pytest
import requests

import network_guard


def test_outbound_connect_is_blocked():
    with pytest.raises(network_guard.NetworkBlocked):
        socket.create_connection(('203.0.113.10', 443), timeout=1)    # TEST-NET-3, never routable


def test_dns_for_remote_hosts_is_blocked():
    with pytest.raises(network_guard.NetworkBlocked):
        socket.getaddrinfo('api.zoom.us', 443)


def test_requests_cannot_reach_the_internet_and_the_error_is_not_swallowed_as_a_network_error():
    with pytest.raises(network_guard.NetworkBlocked):
        requests.get('https://api.resend.com/emails', timeout=1)
    assert not issubclass(network_guard.NetworkBlocked, OSError)      # requests/urllib3 would wrap an OSError as transient


def test_localhost_still_works():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    try:
        client = socket.create_connection(server.getsockname(), timeout=2)
        client.close()
        assert socket.getaddrinfo('localhost', 80)
    finally:
        server.close()


@pytest.mark.allow_network
def test_allow_network_marker_restores_real_sockets():
    assert socket.socket.connect is network_guard.ORIGINAL_CONNECT
    assert socket.getaddrinfo is network_guard.ORIGINAL_GETADDRINFO


def test_is_local_address():
    assert network_guard.is_local(('127.0.0.1', 5432)) and network_guard.is_local(('::1', 6379, 0, 0))
    assert network_guard.is_local(('localhost', 6379)) and network_guard.is_local('/run/postgresql/.s.PGSQL.5432')
    assert not network_guard.is_local(('10.0.0.5', 5432)) and not network_guard.is_local(('example.com', 80))
