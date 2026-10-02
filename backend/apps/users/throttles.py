import hashlib

from rest_framework.throttling import SimpleRateThrottle


class _HashedBodyFieldThrottle(SimpleRateThrottle):
    """Throttle per value of one body field (hashed), independent of client IP, so a distributed attack on one target is still limited."""
    field = ''

    def get_cache_key(self, request, view):
        raw = request.data.get(self.field, '') if hasattr(request.data, 'get') else ''
        value = str(raw).strip().lower()
        if not value:
            return None
        ident = hashlib.sha256(value.encode('utf-8')).hexdigest()
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class LoginUsernameThrottle(_HashedBodyFieldThrottle):
    """Login attempts per submitted username-or-email."""
    scope = 'login_user'
    field = 'username'


class PasswordResetEmailThrottle(_HashedBodyFieldThrottle):
    """Reset e-mails per address: stops mail-bombing one inbox from many IPs."""
    scope = 'password_reset_email'
    field = 'email'
