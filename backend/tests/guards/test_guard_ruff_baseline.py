"""
The ruff baseline (backend/ruff.toml `[lint.extend-per-file-ignores]`) can only shrink.

Runs ruff WITHOUT the baseline (isolated mode, same rules and the permanent policy ignores) and checks:
  * every baseline entry (file, code) still matches at least one real violation (a fixed one must be deleted from the list);
  * no violation exists outside the baseline (the same verdict as the blocking CI `ruff check .` job);
  * the baseline never grows past its 2026-10-04 size;
  * for C901 and every S / B code the NUMBER of violations per (file, code) is pinned in RUFF_COUNTS: a file-level ignore
    would otherwise hide a second complex function or a second security finding in a file that already had one. A count
    that goes up fails ("NEW"); a count that goes down fails until RUFF_COUNTS is lowered (the same ratchet as the guards).
    F codes (unused imports / variables) stay per-file.
Skipped when the ruff binary is not installed (it is in requirements-dev.txt; CI installs it).
"""
import json
import shutil
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path

import pytest

from guards._scan import BACKEND

RUFF_TOML = BACKEND / 'ruff.toml'
BASELINE_MAX_PAIRS = 68          # (file, code) pairs: 69 on 2026-10-04, 68 after T1a; lower it whenever you remove entries
# Baseline 2026-10-04: violations per (file, code) for the counted codes (42 violations, 26 pairs). Only ever lower.
RUFF_COUNTS = {
    ('apps/admin_api/views.py', 'C901'): 1,
    ('apps/bookings/services/rescheduling.py', 'B904'): 1,
    ('apps/bookings/services/rescheduling.py', 'C901'): 1,
    ('apps/bookings/services/reservation.py', 'C901'): 1,
    ('apps/bookings/tasks.py', 'C901'): 1,
    ('apps/integrations/tasks.py', 'B904'): 4,
    ('apps/integrations/views.py', 'C901'): 1,
    ('apps/materials/models.py', 'S110'): 2,
    ('apps/payments/gateways/payfast.py', 'S324'): 2,
    ('apps/payments/gateways/paypal.py', 'S105'): 1,
    ('apps/payments/services/credits.py', 'C901'): 1,
    ('apps/payments/services/grace.py', 'C901'): 2,
    ('apps/payments/services/ledger_service.py', 'C901'): 1,
    ('apps/payments/services/refunds.py', 'C901'): 1,
    ('apps/payments/services/webhook_handler.py', 'C901'): 1,
    ('apps/payments/views.py', 'C901'): 3,
    ('apps/teachers/models.py', 'S110'): 3,
    ('apps/users/serializers.py', 'B904'): 3,
    ('apps/users/tasks.py', 'B904'): 1,
    ('apps/users/tasks.py', 'S105'): 1,
    ('config/settings/guard.py', 'C901'): 1,
    ('config/settings/guard.py', 'S104'): 1,
    ('config/settings/guard.py', 'S105'): 1,
    ('tests/test_fx_rates.py', 'B017'): 3,
    ('tests/test_payment_verification.py', 'S324'): 3,
    ('tests/test_refund_deploy_check.py', 'S603'): 1,
}


def counted(code):
    return code == 'C901' or code[0] in 'SB'


def count_ratchet_errors(actual, baseline):
    """actual / baseline: {(file, code): n} for counted codes. Up = new violation; down = lower the baseline."""
    errors = []
    for key in sorted(set(actual) | set(baseline)):
        have, allowed = actual.get(key, 0), baseline.get(key, 0)
        if have > allowed:
            errors.append(f'NEW {key[1]} in {key[0]}: {have} found, {allowed} allowed (fix it; never raise the count)')
        elif have < allowed:
            errors.append(f'{key[1]} in {key[0]}: RUFF_COUNTS says {allowed} but only {have} remain - lower the number')
    return errors


def _ruff():
    exe = 'ruff.exe' if sys.platform == 'win32' else 'ruff'
    local = Path(sys.executable).parent / exe
    return str(local) if local.exists() else shutil.which('ruff')


def _inline_table(mapping):
    return '{' + ', '.join(f'{json.dumps(k)} = {json.dumps(v)}' for k, v in mapping.items()) + '}'


def _config():
    return tomllib.loads(RUFF_TOML.read_text(encoding='utf-8'))['lint']


def _violations_without_baseline(ruff):
    lint = _config()
    cmd = [ruff, 'check', '.', '--isolated', '--no-cache', '--exit-zero', '--output-format', 'json',
           '--config', f"lint.select = {json.dumps(lint['select'])}",
           '--config', f"lint.mccabe.max-complexity = {lint['mccabe']['max-complexity']}",
           '--config', f"lint.per-file-ignores = {_inline_table(lint['per-file-ignores'])}",
           '--config', f'extend-exclude = {json.dumps(["venv", "staticfiles", "media"])}']
    result = subprocess.run(cmd, cwd=BACKEND, capture_output=True, text=True, check=True)  # noqa: S603 - fixed argv
    return Counter((Path(v['filename']).resolve().relative_to(BACKEND).as_posix(), v['code']) for v in json.loads(result.stdout))


def test_count_ratchet_catches_a_second_violation_of_a_baselined_code():
    """QA review MAJOR 3: a per-file ignore hid a NEW C901/S/B violation in a file that already had one."""
    baseline = {('apps/x.py', 'C901'): 1, ('apps/x.py', 'S105'): 2}
    assert count_ratchet_errors({('apps/x.py', 'C901'): 1, ('apps/x.py', 'S105'): 2}, baseline) == []
    up = count_ratchet_errors({('apps/x.py', 'C901'): 2, ('apps/x.py', 'S105'): 2}, baseline)
    assert len(up) == 1 and 'C901' in up[0] and 'NEW' in up[0]
    down = count_ratchet_errors({('apps/x.py', 'C901'): 1, ('apps/x.py', 'S105'): 1}, baseline)
    assert len(down) == 1 and 'lower' in down[0]
    gone = count_ratchet_errors({('apps/x.py', 'S105'): 2}, baseline)
    assert len(gone) == 1 and 'lower' in gone[0]
    assert counted('C901') and counted('S324') and counted('B904') and not counted('F401')


def test_ruff_baseline_only_shrinks():
    ruff = _ruff()
    if not ruff:
        pytest.skip('ruff is not installed (pip install -r requirements-dev.txt)')
    baseline = {(path, code) for path, codes in _config()['extend-per-file-ignores'].items() for code in codes}
    counts = _violations_without_baseline(ruff)
    actual = set(counts)
    stale = sorted(baseline - actual)
    new = sorted(actual - baseline)
    assert not new, f'New ruff violations (fix them; never add them to the baseline): {new}'
    assert not stale, f'Fixed - delete these from [lint.extend-per-file-ignores] in ruff.toml: {stale}'
    assert len(baseline) <= BASELINE_MAX_PAIRS, 'The ruff baseline grew; only remove entries from it'
    errors = count_ratchet_errors({key: n for key, n in counts.items() if counted(key[1])}, RUFF_COUNTS)
    assert not errors, 'Counted ruff codes (C901, S*, B*):\n' + '\n'.join(errors)
