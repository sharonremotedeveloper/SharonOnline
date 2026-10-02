from pathlib import Path
from datetime import timedelta
import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-dev-key-change-in-production-esl-marketplace-2026')

DEBUG = False

# Zoom webhook HMAC secret. Never derived from SECRET_KEY; production requires it explicitly.
ZOOM_WEBHOOK_SECRET_TOKEN = os.environ.get('ZOOM_WEBHOOK_SECRET_TOKEN', '')
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()
]

ALLOWED_HOSTS = [host.strip() for host in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0,backend').split(',')]

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-Party Apps
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'storages',

    # Local Domain Apps
    'apps.users',
    'apps.teachers',
    'apps.bookings',
    'apps.payments',
    'apps.materials',
    'apps.integrations',
    'apps.admin_api',
    'apps.crm',
    'apps.srs',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization - Strict UTC Standard
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    # Secure by default: public endpoints must opt in with permission_classes = [AllowAny].
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '300/min',
        # Scoped (views opt in with throttle_classes=[ScopedRateThrottle] + throttle_scope)
        'login': '5/min',
        'login_user': '10/hour',  # per submitted username, so a distributed attack on one account is still limited
        'register': '5/hour',
        'upload': '30/hour',
        'checkout': '20/hour',
        'reserve': '30/min',
        'password_reset': '5/hour',          # per IP; plus 3/hour per target address (PasswordResetEmailThrottle)
        'password_reset_email': '3/hour',
        'password_reset_confirm': '10/hour',
        'password_change': '10/hour',
        'email_verify': '5/hour',
        'email_verify_confirm': '20/hour',
        'webhook': '120/min',
    },
    # Number of trusted reverse proxies in front of Django. 0 = ignore X-Forwarded-For entirely (REMOTE_ADDR only).
    # NEVER map 0 to None: DRF treats None as "trust the whole client-supplied X-Forwarded-For header", which lets
    # an attacker rotate the header to bypass every IP throttle.
    'NUM_PROXIES': int(os.environ.get('THROTTLE_NUM_PROXIES', '0')),
}

# Account e-mails (Task 8.5). Links are always built from FRONTEND_BASE_URL, never from the request Host header.
FRONTEND_BASE_URL = os.environ.get('FRONTEND_BASE_URL', 'http://localhost:3000')
PASSWORD_RESET_TIMEOUT = 60 * 60  # seconds; reset links are single-use AND short-lived
EMAIL_VERIFY_MAX_AGE = 3 * 24 * 60 * 60

# SimpleJWT Authentication
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),  # safe now: the Next.js proxy refreshes transparently (Task 8.4)
    'REFRESH_TOKEN_LIFETIME': timedelta(days=14),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Celery Configuration
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

from config.celery_schedule import CELERY_BEAT_SCHEDULE, CELERY_TASK_ROUTES
CELERY_BEAT_SCHEDULE = CELERY_BEAT_SCHEDULE
CELERY_TASK_ROUTES = CELERY_TASK_ROUTES

# CORS Settings
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True

# Cloudflare R2 & Media Storage Configuration ($0 Egress)
CLOUDFLARE_R2_ACCOUNT_ID = os.environ.get('CLOUDFLARE_R2_ACCOUNT_ID')
CLOUDFLARE_R2_ACCESS_KEY_ID = os.environ.get('CLOUDFLARE_R2_ACCESS_KEY_ID')
CLOUDFLARE_R2_SECRET_ACCESS_KEY = os.environ.get('CLOUDFLARE_R2_SECRET_ACCESS_KEY')
CLOUDFLARE_R2_BUCKET_NAME = os.environ.get('CLOUDFLARE_R2_BUCKET_NAME', 'esl-platform-assets')
CLOUDFLARE_R2_PUBLIC_DOMAIN = os.environ.get('CLOUDFLARE_R2_PUBLIC_DOMAIN', 'https://assets.sharonesl.com')

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

if CLOUDFLARE_R2_ACCOUNT_ID and CLOUDFLARE_R2_ACCESS_KEY_ID and CLOUDFLARE_R2_SECRET_ACCESS_KEY:
    DEFAULT_FILE_STORAGE = 'apps.common.storage.MediaR2Storage'
    STORAGES = {
        'default': {
            'BACKEND': 'apps.common.storage.MediaR2Storage',
        },
        'private': {
            'BACKEND': 'apps.common.storage.PrivateMediaR2Storage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        }
    }
else:
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'private': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        }
    }


# Payment gateways. Production guard (config/settings/guard.py) rejects unsafe values.
def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes')

PAYFAST_MERCHANT_ID = os.environ.get('PAYFAST_MERCHANT_ID', '')
PAYFAST_MERCHANT_KEY = os.environ.get('PAYFAST_MERCHANT_KEY', '')
PAYFAST_PASSPHRASE = os.environ.get('PAYFAST_PASSPHRASE', '')
PAYFAST_SANDBOX = _env_bool('PAYFAST_SANDBOX', True)
PAYFAST_SKIP_IP_CHECK = _env_bool('PAYFAST_SKIP_IP_CHECK', False)
PAYFAST_TRUSTED_PROXY_COUNT = int(os.environ.get('PAYFAST_TRUSTED_PROXY_COUNT', '0'))
PAYFAST_NOTIFY_URL = os.environ.get('PAYFAST_NOTIFY_URL', '')
# Extra source-IP ranges allowed for ITNs (comma-separated CIDRs). Copy PayFast's currently published ranges here;
# DNS resolution of PayFast's hosts is used in addition.
PAYFAST_EXTRA_ALLOWED_CIDRS = [c.strip() for c in os.environ.get('PAYFAST_EXTRA_ALLOWED_CIDRS', '').split(',') if c.strip()]
# D-1: retail price is platform-set per currency. Until the price table exists (Phase 10),
# ZAR = USD price x this configurable rate.
ZAR_PER_USD = float(os.environ.get('ZAR_PER_USD', '18.0'))

PAYPAL_CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID', '')
PAYPAL_CLIENT_SECRET = os.environ.get('PAYPAL_CLIENT_SECRET', '')
PAYPAL_MODE = os.environ.get('PAYPAL_MODE', 'sandbox')
PAYPAL_WEBHOOK_ID = os.environ.get('PAYPAL_WEBHOOK_ID', '')
