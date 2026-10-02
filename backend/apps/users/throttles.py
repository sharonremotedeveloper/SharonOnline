import hashlib

from rest_framework.throttling import SimpleRateThrottle


class LoginUsernameThrottle(SimpleRateThrottle):
    """Throttle login attempts per submitted username, independent of client IP."""
    scope = 'login_user'

    def get_cache_key(self, request, view):
        raw = request.data.get('username', '') if hasattr(request.data, 'get') else ''
        username = str(raw).strip().lower()
        if not username:
            return None
        ident = hashlib.sha256(username.encode('utf-8')).hexdigest()
        return self.cache_format % {'scope': self.scope, 'ident': ident}
