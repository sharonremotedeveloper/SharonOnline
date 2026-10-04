"""
The ruff baseline (backend/ruff.toml `[lint.extend-per-file-ignores]`) can only shrink.

Runs ruff WITHOUT the baseline (isolated mode, same rules and the permanent policy ignores) and checks:
  * every baseline entry (file, code) still matches at least one real violation (a fixed one must be deleted from the list);
  * no violation exists outside the baseline (the same verdict as the blocking CI `ruff check .` job);
  * the baseline never grows past its 2026-10-04 size.
Skipped when the ruff binary is not installed (it is in requirements-dev.txt; CI installs it).
"""
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from guards._scan import BACKEND

RUFF_TOML = BACKEND / 'ruff.toml'
BASELINE_MAX_PAIRS = 69          # (file, code) pairs on 2026-10-04; lower it whenever you remove entries


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
    return {(Path(v['filename']).resolve().relative_to(BACKEND).as_posix(), v['code']) for v in json.loads(result.stdout)}


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
    actual = _violations_without_baseline(ruff)
    stale = sorted(baseline - actual)
    new = sorted(actual - baseline)
    assert not new, f'New ruff violations (fix them; never add them to the baseline): {new}'
    assert not stale, f'Fixed - delete these from [lint.extend-per-file-ignores] in ruff.toml: {stale}'
    assert len(baseline) <= BASELINE_MAX_PAIRS, 'The ruff baseline grew; only remove entries from it'
