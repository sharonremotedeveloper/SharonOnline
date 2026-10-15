"""Atomic, identity-safe throttle extensions for high-risk endpoints."""

import hashlib
import hmac
import logging
import time

from django.conf import settings
from django.core.cache import cache
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError
from rest_framework.exceptions import APIException
from rest_framework.throttling import AnonRateThrottle
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.throttling import UserRateThrottle


logger = logging.getLogger("security.rate_limit")

ABUSE_COUNTER_TTL_SECONDS = 300
ABUSE_ESCALATION_THRESHOLD = 5

# These endpoints are public, read-only catalog surfaces whose underlying
# queries are intentionally bounded. If Redis is unavailable, serving them is
# safer than converting a cheap browse into an outage. Every other scoped
# throttle, including unknown future scopes, fails closed below.
THROTTLE_FAIL_OPEN_SCOPES = frozenset({
    'public_default_read',
    'public_teacher_directory',
    'public_teacher_detail',
    'public_materials_directory',
    'public_materials_detail',
    'credit_pack_list',
})

# Keep the security-sensitive policy visible next to the fail-open allowlist.
# The implementation still defaults unknown scopes to fail-closed so a new
# state-changing or sensitive endpoint cannot silently inherit fail-open.
THROTTLE_FAIL_CLOSED_SCOPES = frozenset({
    'public_slots', 'public_teacher_availability', 'booking_write', 'purchase_status', 'financial_read',
    'financial_export', 'financial_document', 'private_asset', 'lesson_write',
    'student_write', 'student_refund_read', 'crm_write', 'refund_write',
    'teacher_settings', 'integration_write', 'integration_callback',
    'admin_read', 'admin_refund_read', 'admin_write',
})

_CACHE_FAILURES = (
    RedisError,
    RedisConnectionError,
    RedisTimeoutError,
    ConnectionError,
    TimeoutError,
    OSError,
)


class ThrottleBackendUnavailable(APIException):
    """Controlled response when a fail-closed throttle cannot consult Redis."""

    status_code = 503
    default_detail = 'Rate limiting is temporarily unavailable. Please retry shortly.'
    default_code = 'rate_limit_unavailable'


def _failure_policy(scope: str) -> str:
    if scope in THROTTLE_FAIL_OPEN_SCOPES:
        return 'fail_open'
    if scope in THROTTLE_FAIL_CLOSED_SCOPES:
        return 'fail_closed'
    return 'fail_closed'


def _handle_cache_failure(scope: str, exc: Exception) -> bool:
    """Log only safe failure metadata and return whether enforcement may continue."""
    policy = _failure_policy(scope)
    logger.warning(
        'rate_limit.cache_unavailable scope=%s policy=%s error_type=%s',
        scope,
        policy,
        type(exc).__name__,
    )
    if policy == 'fail_closed':
        raise ThrottleBackendUnavailable() from exc
    return True


class ResilientThrottleMixin:
    """Apply the Redis outage policy around DRF's standard throttle algorithm."""

    def _failure_scope(self, request, view) -> str:
        explicit_scope = getattr(view, 'throttle_scope', None)
        if explicit_scope:
            return explicit_scope
        # The anonymous default is used by public safe-method reads. Keep
        # those browse paths available during a Redis outage; anonymous writes
        # and authenticated defaults remain fail-closed.
        if getattr(self, 'scope', None) == 'anon' and request.method in ('GET', 'HEAD', 'OPTIONS'):
            return 'public_default_read'
        return getattr(self, 'scope', None) or self.__class__.__name__

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except _CACHE_FAILURES as exc:
            if _handle_cache_failure(self._failure_scope(request, view), exc):
                return True
            return False


class ResilientSimpleRateThrottle(ResilientThrottleMixin, SimpleRateThrottle):
    """Base for custom identity throttles that still use DRF's cache algorithm."""


class ResilientScopedRateThrottle(ResilientThrottleMixin, ScopedRateThrottle):
    """ScopedRateThrottle with controlled Redis outage behavior."""


class ResilientAnonRateThrottle(ResilientThrottleMixin, AnonRateThrottle):
    """Default anonymous throttle with public-read fail-open behavior only."""


class ResilientUserRateThrottle(ResilientThrottleMixin, UserRateThrottle):
    """Default authenticated-user throttle that fails closed on Redis outage."""


def _increment_counter(key: str, timeout: int, limit: int) -> int:
    """Increment a fixed-window counter with an expiry-race retry."""
    try:
        if cache.add(key, 1, timeout=timeout):
            return 1
        return cache.incr(key)
    except (ValueError, TypeError):
        # A key can expire between add and incr on a non-Redis test backend.
        try:
            if cache.add(key, 1, timeout=timeout):
                return 1
        except (ValueError, TypeError):
            return limit + 1
        # Fail closed for the request if the backend cannot establish a count.
        return limit + 1


def _hmac_identity(value: str) -> str:
    """Return a short keyed digest; raw identity values never enter cache keys or logs."""
    secret = str(getattr(settings, "SECRET_KEY", "")).encode("utf-8")
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def _request_target(request) -> str:
    resolver = getattr(request, "resolver_match", None)
    route = getattr(resolver, "url_name", None) or "unknown"
    kwargs = getattr(resolver, "kwargs", {}) or {}
    target = "|".join(f"{key}={kwargs[key]}" for key in sorted(kwargs))
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        target = f"user={getattr(user, 'pk', 'unknown')}|{target}"
    return _hmac_identity(f"{route}|{target}")


def _record_abuse_event(request, scope: str, ip_identity: str, count: int) -> None:
    """Count repeated denials for a short window and emit one bounded escalation event."""
    ip_hash = _hmac_identity(ip_identity)
    target_hash = _request_target(request)
    counter_key = f"abuse:rate-limit:{scope}:{ip_hash}:{target_hash}"
    try:
        if cache.add(counter_key, 1, timeout=ABUSE_COUNTER_TTL_SECONDS):
            abuse_count = 1
        else:
            abuse_count = cache.incr(counter_key)
    except _CACHE_FAILURES as exc:
        # Abuse telemetry is best-effort and must never turn an existing 429
        # into a 500 or expose backend details.
        logger.warning(
            'rate_limit.abuse_counter_unavailable scope=%s error_type=%s',
            scope,
            type(exc).__name__,
        )
        return
    except (ValueError, TypeError):
        # A cache race/unsupported increment must not turn a throttle denial into a 500.
        abuse_count = max(1, count)

    if abuse_count < ABUSE_ESCALATION_THRESHOLD:
        return

    marker_key = f"{counter_key}:escalated"
    try:
        marked = cache.add(marker_key, 1, timeout=ABUSE_COUNTER_TTL_SECONDS)
    except _CACHE_FAILURES as exc:
        logger.warning(
            'rate_limit.abuse_marker_unavailable scope=%s error_type=%s',
            scope,
            type(exc).__name__,
        )
        return
    except (ValueError, TypeError) as exc:
        logger.warning(
            'rate_limit.abuse_marker_unavailable scope=%s error_type=%s',
            scope,
            type(exc).__name__,
        )
        return
    if marked:
        logger.error(
            "[ADMIN ALERT] rate_limit.abuse_escalated scope=%s ip_hash=%s target_hash=%s count_bucket=%s",
            scope,
            ip_hash,
            target_hash,
            ABUSE_ESCALATION_THRESHOLD,
        )


class ObservedScopedRateThrottle(SimpleRateThrottle):
    """Atomic fixed-window throttle across IP and authenticated-user identities.

    Public requests use the IP dimension. Authenticated requests must satisfy
    both the IP and user buckets, preventing either identity dimension from
    bypassing the other. Cache ``add``/``incr`` operations are atomic on the
    configured Redis backend; this intentionally uses fixed windows rather than
    DRF's non-atomic rolling-list implementation.
    """

    def __init__(self):
        # DRF constructs throttle classes before it passes the view instance to
        # allow_request. Resolve the scope there instead of in SimpleRateThrottle
        # __init__, which would otherwise raise ImproperlyConfigured.
        self.rate = None
        self.num_requests = None
        self.duration = None
        self.history = []
        self._wait = None

    def _identities(self, request):
        yield "ip", self.get_ident(request)
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False) and getattr(user, "pk", None) is not None:
            yield "user", f"user:{user.pk}"

    def _rate_for(self, scope: str, dimension: str):
        return self.THROTTLE_RATES.get(f"{scope}_{dimension}") or self.THROTTLE_RATES.get(scope)

    def wait(self):
        return getattr(self, "_wait", None)

    def allow_request(self, request, view):
        self.scope = getattr(view, "throttle_scope", None)
        self._wait = None
        if not self.scope:
            return True

        now = time.time()
        denied = False
        denial_count = 0
        for dimension, identity in self._identities(request):
            rate = self._rate_for(self.scope, dimension)
            if not rate or identity is None:
                continue
            num_requests, duration = self.parse_rate(rate)
            if not num_requests or not duration:
                continue
            bucket = int(now // duration)
            key = f"throttle:{self.scope}:{dimension}:{_hmac_identity(str(identity))}:{bucket}"
            try:
                count = _increment_counter(key, max(2, int(duration) + 1), num_requests)
            except _CACHE_FAILURES as exc:
                # Cheap catalog reads continue without Redis; sensitive and
                # state-changing scopes return a controlled 503.
                if _handle_cache_failure(self.scope, exc):
                    continue

            if count > num_requests:
                denied = True
                denial_count = max(denial_count, count)
                self._wait = max(self._wait or 0, (bucket + 1) * duration - now)

        if denied:
            _record_abuse_event(request, self.scope, self.get_ident(request), denial_count)
            return False
        return True
