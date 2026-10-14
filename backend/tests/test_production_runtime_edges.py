from importlib import import_module
from wsgiref.util import setup_testing_defaults
import pytest

from config.redis import normalize_redis_url
from config import health


def test_wsgi_delegates_non_health_requests_to_django_application(monkeypatch):
    monkeypatch.setenv('DJANGO_SETTINGS_MODULE', 'config.settings.local')
    wsgi = import_module('config.wsgi')
    calls = []

    def fake_application(environ, start_response):
        calls.append(environ['PATH_INFO'])
        return [b'django']

    monkeypatch.setattr(wsgi, 'django_application', fake_application)
    result = wsgi.railway_health_probe_application({'PATH_INFO': '/api/ready/'}, object())

    assert result == [b'django']
    assert calls == ['/api/ready/']


def test_wsgi_keeps_railway_liveness_independent_from_readiness(monkeypatch):
    monkeypatch.setenv('DJANGO_SETTINGS_MODULE', 'config.settings.local')
    wsgi = import_module('config.wsgi')
    calls = []

    def fake_application(environ, start_response):
        calls.append(environ['PATH_INFO'])
        return [b'django']

    def start_response(status, headers):
        assert status == '200 OK'

    monkeypatch.setattr(wsgi, 'django_application', fake_application)
    body = b''.join(wsgi.railway_health_probe_application({'PATH_INFO': '/api/health/'}, start_response))

    assert b'"status":"healthy"' in body
    assert calls == []


@pytest.mark.django_db
def test_wsgi_readiness_reaches_django_and_returns_503(monkeypatch):
    monkeypatch.setenv('DJANGO_SETTINGS_MODULE', 'config.settings.local')
    wsgi = import_module('config.wsgi')
    monkeypatch.setattr(health, 'check_dependencies', lambda: False)
    environ = {}
    setup_testing_defaults(environ)
    environ['PATH_INFO'] = '/api/ready/'
    environ['HTTP_HOST'] = 'testserver'
    statuses = []

    body = b''.join(wsgi.railway_health_probe_application(
        environ, lambda status, headers: statuses.append(status)))

    assert statuses == ['503 Service Unavailable']
    assert b'"status": "unavailable"' in body


def test_production_rediss_url_gets_explicit_certificate_policy(monkeypatch):
    assert normalize_redis_url('rediss://default:secret@upstash.example:6379') == (
        'rediss://default:secret@upstash.example:6379?ssl_cert_reqs=required'
    )
    assert normalize_redis_url('rediss://default:secret@upstash.example:6379?ssl_cert_reqs=none') == (
        'rediss://default:secret@upstash.example:6379?ssl_cert_reqs=required'
    )
