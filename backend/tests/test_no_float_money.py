"""Task 10.1a: money is Decimal in code and an exact string at the API boundary."""
import re
from decimal import Decimal
from pathlib import Path

import pytest

from apps.common.money import money_str

APPS = Path(__file__).resolve().parent.parent / 'apps'
MONEY_MODULES = [
    'payments/services', 'payments/views.py', 'admin_api/views.py', 'admin_api/serializers.py',
    'bookings/serializers.py',
]


def test_money_str_is_exact():
    assert money_str(Decimal('0.1') + Decimal('0.2'), 'USD') == '0.30'
    assert money_str(Decimal('1350.5'), 'JPY') == '1351'
    assert money_str(None) == '0.00'
    assert money_str(Decimal('12345678901.235'), 'ZAR') == '12345678901.24'


def test_no_float_calls_in_money_modules():
    offenders = []
    for rel in MONEY_MODULES:
        path = APPS / rel
        files = [path] if path.is_file() else sorted(path.rglob('*.py'))
        for f in files:
            for n, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
                if re.search(r'\bfloat\(|[^\w.]\d+\.\d+\s*\*|\*\s*\d+\.\d+', line) and 'float-ok' not in line:
                    offenders.append(f'{f.relative_to(APPS)}:{n}: {line.strip()}')
    assert not offenders, 'float money found:\n' + '\n'.join(offenders)
