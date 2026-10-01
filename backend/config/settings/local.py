from .base import *
import dj_database_url
import os

DEBUG = True

# Dev-only constant so local webhook tests/tools can sign payloads. Production refuses to boot without a real one.
ZOOM_WEBHOOK_SECRET_TOKEN = os.environ.get('ZOOM_WEBHOOK_SECRET_TOKEN') or 'local-dev-zoom-webhook-secret'

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
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

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
