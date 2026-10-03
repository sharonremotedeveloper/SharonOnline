"""Admin-maintained FX table for EUR and JPY (Task 10.1d). Checkout stamps the rate on the transaction; capture reuses it."""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from apps.payments.models import FxRate

MAX_STEP = Decimal('0.10')      # a new rate more than 10 % away from the previous one needs explicit confirmation
RATE_PLACES = Decimal('0.000001')


class FxRateUnavailable(LookupError):
    """No effective rate exists for the currency."""


class FxRateStale(LookupError):
    """The newest effective rate is older than FX_RATE_MAX_AGE_HOURS."""


class FxRateSanityError(ValueError):
    """The new rate moves too far from the previous one (typo guard)."""


def max_age() -> timedelta:
    return timedelta(hours=int(getattr(settings, 'FX_RATE_MAX_AGE_HOURS', 24)))


def latest_row(currency: str, now=None):
    now = now or timezone.now()
    return FxRate.objects.filter(currency=currency.upper(), valid_from__lte=now).order_by('-valid_from', '-id').first()


def current_rate(currency: str, now=None) -> FxRate:
    """The rate to quote a new checkout in `currency`; refuses a missing or stale one rather than guessing."""
    now = now or timezone.now()
    row = latest_row(currency, now)
    if row is None:
        raise FxRateUnavailable(f'No FX rate has been entered for {currency.upper()}.')
    if now - row.valid_from > max_age():
        raise FxRateStale(f'The {currency.upper()} rate is older than {max_age()} (set {row.valid_from:%Y-%m-%d %H:%M} UTC).')
    return row


def record_rate(currency: str, rate, *, set_by, confirm: bool = False, source: str = 'manual', valid_from=None) -> FxRate:
    currency = currency.upper()
    if currency not in FxRate.SUPPORTED:
        raise ValueError(f'FX table rates exist for {FxRate.SUPPORTED} only, not {currency!r}.')
    rate = Decimal(str(rate)).quantize(RATE_PLACES)
    if rate <= 0:
        raise ValueError('An FX rate must be positive.')
    previous = latest_row(currency)
    if previous is not None and not confirm:
        move = abs(rate - previous.rate_to_zar) / previous.rate_to_zar
        if move > MAX_STEP:
            raise FxRateSanityError(
                f'{currency} {rate} is {move:.0%} away from the previous {previous.rate_to_zar}; confirm to save it.')
    return FxRate.objects.create(currency=currency, rate_to_zar=rate, source=source,
                                 valid_from=valid_from or timezone.now(), set_by=set_by)


def fx_source_label(row: FxRate) -> str:
    return f'fx_rate_table:{row.pk}'
