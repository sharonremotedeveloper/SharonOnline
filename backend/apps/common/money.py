"""Money at the API boundary: exact strings, never floats (Task 10.1a)."""
from decimal import Decimal

from apps.payments.services.pricing import quantize_money


def money_str(amount, currency: str = 'ZAR') -> str:
    """Exact string in the currency's minor unit, e.g. '162.00' (JPY: '1350')."""
    return str(quantize_money(Decimal(str(amount or 0)), currency))
