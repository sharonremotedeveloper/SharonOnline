import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')

django_application = get_wsgi_application()


def railway_health_probe_application(environ, start_response):
    """Serve Railway's liveness probe before Django validates the Host header.

    Railway can probe a service through an internal host that is not one of the
    public names in DJANGO_ALLOWED_HOSTS. Keep this exception limited to the
    non-sensitive liveness path; all application routes still use Django's
    normal host, CSRF, and security middleware.
    """
    if environ.get("PATH_INFO") == "/api/health/":
        body = b'{"status":"healthy","service":"esl_backend","version":"1.0.0"}'
        start_response(
            "200 OK",
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [body]
    return django_application(environ, start_response)


application = railway_health_probe_application
