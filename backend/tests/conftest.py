import pytest
from apps.users.models import User
from apps.teachers.models import TeacherProfile, TeacherAvailability
from datetime import datetime, time, timedelta, timezone as dt_timezone

import fakes
import network_guard

@pytest.fixture(autouse=True)
def test_environment_settings(settings):
    """
    Configures isolated in-memory cache and eager Celery execution
    so tests execute immediately in milliseconds without external Redis dependencies.
    """
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'isolated-test-cache',
        }
    }
    from django.core.cache import cache
    cache.clear()  # throttle counters / locks must not leak between tests
    settings.CELERY_TASK_ALWAYS_EAGER = True
    # A developer .env may select the real refund router; no test may reach a payment gateway by accident.
    settings.REFUND_GATEWAY_BACKEND = 'apps.payments.services.refund_gateways.ManualSandboxRefundGateway'
    # Same for e-mail (slice N1c): a developer .env with a real RESEND_API_KEY must never make a test send real mail.
    # Console mode hands every message to Django's test mail backend (`django.core.mail.outbox`).
    settings.EMAIL_BACKEND_MODE = 'console'
    # A developer .env must never make a test call Daily: default to simulated rooms (no key). Tests that need the
    # HTTP contract use `fake_daily`; tests of an unconfigured Daily blank DAILY_DOMAIN.
    settings.DAILY_API_KEY = ''
    settings.DAILY_DOMAIN = 'test.daily.co'
    settings.DAILY_SIMULATE_WITHOUT_CREDENTIALS = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.CELERY_BROKER_URL = 'memory://'
    settings.CELERY_RESULT_BACKEND = 'cache+memory://'
    # Password strength is a production concern, not what these tests exercise. The
    # production hasher made each fixture user cost several seconds and turned the
    # full regression gate into an hour-long run.
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

@pytest.fixture
def teacher_user(db):
    user = User.objects.create_user(
        username="test_tutor",
        email="tutor@test.com",
        password="password123",
        role=User.Role.TEACHER,
        country="ZA",
        timezone="Africa/Johannesburg"
    )
    profile = TeacherProfile.objects.create(
        user=user,
        headline="TEFL Tutor",
        accent=TeacherProfile.Accent.SOUTH_AFRICAN,
        price_per_25min_usd=9.00,
        status=TeacherProfile.Status.APPROVED,      # is_verified / is_active are generated from it (T1a)
    )
    # Give availability on Monday from 09:00 to 12:00 SAST
    TeacherAvailability.objects.create(
        teacher=profile,
        day_of_week=0, # Monday
        start_time=time(9, 0),
        end_time=time(12, 0),
        is_active=True
    )
    return profile

@pytest.fixture
def student_user(db):
    return User.objects.create_user(
        username="test_student",
        email="student@test.com",
        password="password123",
        role=User.Role.STUDENT,
        country="JP",
        timezone="Asia/Tokyo"
    )

@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="test_admin",
        email="admin@test.com",
        password="password123",
        role=User.Role.ADMIN,
        is_staff=True,
        is_superuser=True,
        country="ZA",
        timezone="Africa/Johannesburg"
    )



@pytest.fixture(autouse=True)
def fake_paypal_orders(monkeypatch, settings):
    """No test talks to PayPal: checkout order creation is stubbed (tests of the real client mock `requests`)."""
    settings.PAYPAL_CLIENT_ID = settings.PAYPAL_CLIENT_ID or 'test-client-id'
    settings.PAYPAL_CLIENT_SECRET = settings.PAYPAL_CLIENT_SECRET or 'test-client-secret'
    calls = []

    def fake_create(tx, description):
        calls.append({'reference': tx.merchant_reference, 'amount': tx.amount, 'currency': tx.currency,
                      'description': description})
        tx.gateway_order_id = f'ORDER-{tx.merchant_reference}'
        tx.save(update_fields=['gateway_order_id', 'updated_at'])
        return tx.gateway_order_id

    monkeypatch.setattr('apps.payments.views.create_checkout_order', fake_create, raising=False)
    return calls


# ------------------------------------------------------------------ Q0 quality infrastructure (docs/QUALITY_GATES.md)
@pytest.fixture(autouse=True)
def no_network(request, monkeypatch):
    """No test opens a real outbound connection (localhost / CI service hosts are allowed). Opt out: @pytest.mark.allow_network."""
    if request.node.get_closest_marker('allow_network') is not None:
        yield
        return
    network_guard.install(monkeypatch)
    yield
    error = network_guard.teardown_error()
    network_guard.consume()
    if error:
        pytest.fail(error, pytrace=False)          # also catches attempts the code under test swallowed


class FrozenClock:
    """Controls apps.common.clock.now() for one test."""

    def __init__(self, start):
        self.now = start

    def set(self, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('frozen_clock needs an aware datetime (all timestamps are UTC)')
        self.now = value

    def advance(self, **delta):
        self.now = self.now + timedelta(**delta)
        return self.now

    def __call__(self):
        return self.now


@pytest.fixture
def frozen_clock(monkeypatch):
    """Freeze apps.common.clock.now() at a fixed instant (`.set(dt)`, `.advance(minutes=5)`); restored after the test."""
    from apps.common import clock
    fake = FrozenClock(datetime(2026, 1, 5, 9, 0, tzinfo=dt_timezone.utc))
    monkeypatch.setattr(clock, '_override', fake)
    return fake


@pytest.fixture
def fake_resend(monkeypatch):
    return fakes.FakeResend().install(monkeypatch)


@pytest.fixture
def fake_daily(monkeypatch):
    return fakes.FakeDaily().install(monkeypatch)


@pytest.fixture
def fake_google(monkeypatch):
    return fakes.FakeGoogle().install(monkeypatch)


@pytest.fixture
def fake_r2(monkeypatch):
    return fakes.FakeR2().install(monkeypatch)


@pytest.fixture
def resend(settings, monkeypatch):
    """Slice N1c: Resend mode with a fake key and a recording `requests.post` in the unified sender (no network).
    `.calls` records each post, `.response` / `.raises` control the answer (FakeResponse from test_send_email)."""
    from types import SimpleNamespace

    from apps.integrations.services import email as svc
    from test_send_email import FakeResponse
    settings.EMAIL_BACKEND_MODE = 'resend'
    settings.RESEND_API_KEY = 're_test_not_a_real_key'
    settings.DEFAULT_FROM_EMAIL = 'Sharon ESL <bookings@sharonesl.com>'
    state = SimpleNamespace(calls=[], response=FakeResponse(200, {'id': 'msg_123'}), raises=None)

    def fake_post(url, **kwargs):
        state.calls.append(SimpleNamespace(url=url, **kwargs))
        if state.raises is not None:
            raise state.raises
        return state.response

    monkeypatch.setattr(svc.requests, 'post', fake_post)
    return state
