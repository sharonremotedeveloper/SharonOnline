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
BASELINE_MAX_PAIRS = 68          # (file, code) pairs: 69 on 2026-10-04, 68 after T1a; lower it whenever you remove entries


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
