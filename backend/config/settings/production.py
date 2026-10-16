from .base import *
import os
from config.redis import normalize_redis_url
from config.database import production_database_config

DEBUG = False
# Production must never permit free test bookings, even if an environment variable is copied accidentally.
TEST_BOOKINGS_ENABLED = False
# The only production route to a no-payment booking is TEST_BOOKING_ALLOWED_EMAILS (both parties listed, payments off).

from .guard import validate_production_settings

validate_production_settings()

# Production Neon PostgreSQL
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable must be set in production")

DATABASES = {
    'default': production_database_config(DATABASE_URL)
}

# Production Upstash Redis
REDIS_URL = os.environ.get('REDIS_URL')
if not REDIS_URL:
    raise ValueError("REDIS_URL environment variable must be set in production")

# redis-py 8 / Kombu require an explicit certificate policy for ``rediss://``
# URLs. Upstash's generated URL omits the query parameter, so normalize it at
# the production boundary while retaining TLS and requiring certificate
# validation by default.
if REDIS_URL.lower().startswith('rediss://'):
    REDIS_URL = normalize_redis_url(REDIS_URL)

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
    }
}

# Security Headers
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
# Railway probes the container health endpoint over plain HTTP during rollout.
# Keep HTTPS enforcement for every application route while allowing this
# non-sensitive liveness response to be used by the platform healthcheck.
SECURE_REDIRECT_EXEMPT = [r'^api/health/$']
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
