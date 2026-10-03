from rest_framework.throttling import ScopedRateThrottle


class WritesOnlyScopedThrottle(ScopedRateThrottle):
    """
    Rate-limits only changes (POST / PATCH / PUT / DELETE). The payout-settings endpoint re-checks the user's password on every
    change, so without this a stolen session could guess it at the default 300 requests a minute. Reading the masked
    settings is not limited here.
    """

    def allow_request(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return super().allow_request(request, view)
