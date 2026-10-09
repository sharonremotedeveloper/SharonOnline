from .base import *
import dj_database_url
import os

DEBUG = True

DAILY_API_KEY = os.environ.get('DAILY_API_KEY', '')
DAILY_DOMAIN = os.environ.get('DAILY_DOMAIN', '') or 'local.daily.co'
DAILY_WEBHOOK_SECRET = os.environ.get('DAILY_WEBHOOK_SECRET', '')
# No Daily key: local runs get simulated rooms and tokens. Production (base) never does.
DAILY_SIMULATE_WITHOUT_CREDENTIALS = os.environ.get(
    'DAILY_SIMULATE_WITHOUT_CREDENTIALS', 'false' if DAILY_API_KEY else 'true').lower() in ('1', 'true', 'yes')

# Without credentials, local/test runs simulate external services (R2, Google Calendar, uploads). Production (base) never does.
SIMULATE_WITHOUT_CREDENTIALS = True

# Database: Uses DATABASE_URL if configured, otherwise falls back gracefully to SQLite for local lightweight development
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Celery & Redis
# Empty by default so plain `runserver` works with SQLite + an in-process cache and no Redis (every request touches
# the cache for throttling). Docker compose / a real Redis opts in by setting REDIS_URL explicitly.
REDIS_URL = os.environ.get('REDIS_URL', '')
CELERY_BROKER_URL = REDIS_URL or 'memory://'
CELERY_RESULT_BACKEND = REDIS_URL or 'cache+memory://'

# Caching Configuration
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
    }
} if 'redis' in REDIS_URL else {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# Allow all CORS in local debug if needed
CORS_ALLOW_ALL_ORIGINS = True

# No broker configured => no worker exists to run queued tasks (account e-mails, fulfilment...). Run them inline instead of
# silently queueing them into an in-process memory broker nobody reads. Docker / real Redis keeps normal async behaviour.
if not REDIS_URL:
    CELERY_TASK_ALWAYS_EAGER = True

# EMAIL_BACKEND_MODE=console prints each e-mail here (local + docker compose, which uses these settings). Set only in this
# module, never in base.py, so a non-local deployment in console mode fails loudly instead of printing links to stdout.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# E-mail send results (provider ids / error codes only) in the runserver console. With EMAIL_BACKEND_MODE=console the
# messages themselves (including reset / verify links) are printed by Django's console mail backend, not the log.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'apps.integrations.email': {'handlers': ['console'], 'level': 'INFO'},
        'apps.integrations.services.email': {'handlers': ['console'], 'level': 'INFO'},
    },
}
