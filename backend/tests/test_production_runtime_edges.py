from importlib import import_module

from config.redis import normalize_redis_url


def test_wsgi_delegates_non_health_requests_to_django_application(monkeypatch):
    monkeypatch.setenv('DJANGO_SETTINGS_MODULE', 'config.settings.local')
    wsgi = import_module('config.wsgi')
    calls = []

    def fake_application(environ, start_response):
        calls.append(environ['PATH_INFO'])
        return [b'django']

    monkeypatch.setattr(wsgi, 'django_application', fake_application)
    result = wsgi.railway_health_probe_application({'PATH_INFO': '/'}, object())

    assert result == [b'django']
    assert calls == ['/']


def test_production_rediss_url_gets_explicit_certificate_policy(monkeypatch):
    assert normalize_redis_url('rediss://default:secret@upstash.example:6379') == (
        'rediss://default:secret@upstash.example:6379?ssl_cert_reqs=required'
    )
