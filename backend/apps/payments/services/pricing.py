"""Platform lesson price catalog (Task 10.1, D-1): flat price per currency, Decimal only, JPY with 0 decimals."""
from decimal import Decimal, ROUND_HALF_UP

from apps.payments.models import LessonPrice

CURRENCY_EXPONENT = {'USD': 2, 'EUR': 2, 'ZAR': 2, 'JPY': 0}


class PriceNotConfigured(LookupError):
    pass


def quantize_money(amount, currency: str) -> Decimal:
    """Round to the currency's minor unit (JPY: whole yen)."""
    try:
        exponent = CURRENCY_EXPONENT[currency.upper()]
    except KeyError:
        raise ValueError(f'Unsupported currency: {currency}') from None
    return Decimal(str(amount)).quantize(Decimal(1).scaleb(-exponent), ROUND_HALF_UP)


def lesson_price(currency: str) -> Decimal:
    """The active flat price of one lesson in `currency`; raises PriceNotConfigured rather than inventing one."""
    currency = currency.upper()
    row = LessonPrice.objects.filter(currency=currency, is_active=True).first()
    if row is None:
        raise PriceNotConfigured(f'No active lesson price for {currency}.')
    return quantize_money(row.amount, currency)


def usd_to_zar_rate() -> Decimal:
    """ZAR valuation of one USD, derived from the two catalog prices (replaces the old ZAR_PER_USD setting)."""
    return (lesson_price('ZAR') / lesson_price('USD')).quantize(Decimal('0.000001'), ROUND_HALF_UP)
