"""
Guard (e): `apps/integrations/` never fails silently.

Two shapes hide provider failures: an exception handler whose whole body is `pass`, and `return ""` (an empty string that
callers cannot tell apart from "no data"; e.g. a failed Zoom OAuth used to fall back to a fabricated meeting). Slices F0/Z1/
N1c/G1 replace them with typed errors.

How to shrink: raise a typed error (or return an explicit result object) instead, then lower the file's count here.
"""
import ast

from guards._scan import APPS, app_files, parse, ratchet_errors, scan

INTEGRATIONS = APPS / 'integrations'
# Baseline 2026-10-04: {file (relative to apps/): number of silent failures}. Only ever lower these numbers.
ALLOWLIST = {
    'integrations/google_calendar.py': 1,         # explicit "not connected" result (G1 rewrites)
}                                                 # zoom.py: 0 since Z1 (no-credentials token call raises)


def silent_failures(path):
    hits = []
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.ExceptHandler) and all(isinstance(stmt, ast.Pass) for stmt in node.body):
            hits.append(f'{node.lineno}: except ...: pass')
        elif isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) and node.value.value == '':
            hits.append(f'{node.lineno}: return ""')
    return hits


def test_integrations_never_swallow_errors_or_return_empty_strings():
    errors = ratchet_errors(scan(silent_failures, APPS, files=list(app_files(INTEGRATIONS))), ALLOWLIST)
    assert not errors, 'Raise a typed error instead of `except: pass` / `return ""` in integrations:\n' + '\n'.join(errors)


def test_detector(tmp_path):
    bad = tmp_path / 'bad.py'
    bad.write_text(
        "def f():\n"
        "    try:\n        g()\n    except Exception:\n        pass\n"
        "    try:\n        g()\n    except:\n        pass\n"
        "    return ''\n"
        "def h():\n    return \"\"\n",
        encoding='utf-8')
    assert len(silent_failures(bad)) == 4


def test_detector_ignores_handled_errors(tmp_path):
    ok = tmp_path / 'ok.py'
    ok.write_text(
        "def f():\n"
        "    try:\n        g()\n    except ValueError:\n        logger.warning('x')\n        raise\n"
        "    return None\n",
        encoding='utf-8')
    assert silent_failures(ok) == []
