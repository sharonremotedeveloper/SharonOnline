"""
Guard (h): `.env.example` documents every environment variable that `config/settings/` reads.

An operator only learns a setting exists from `.env.example`; a key read in settings but missing there is an undocumented
production knob. Reads recognised: `os.environ.get('X')`, `os.environ['X']`, `os.getenv('X')`, `env.get('X')` / `env['X']`
(the production guard's injected mapping) and the local helpers `_env_bool('X')` / `_int('X')`. A key counts as listed when
`.env.example` has a line `X=...` or a commented example `# X=...`.

How to shrink: add the key (with a comment and a safe default) to `.env.example`, then delete it from ALLOWLIST.
"""
import ast
import re

from guards._scan import BACKEND, parse, src

SETTINGS_DIR = BACKEND / 'config' / 'settings'
ENV_EXAMPLE = BACKEND.parent / '.env.example'
READ_FUNCS = {'os.environ.get', 'os.getenv', 'environ.get', 'env.get', '_env_bool', '_int'}
MAPPINGS = {'os.environ', 'environ', 'env'}
KEY = re.compile(r'^[A-Z][A-Z0-9_]+$')
# Baseline 2026-10-04: keys read in settings but not yet in .env.example. Only ever remove entries.
ALLOWLIST = {
    'BEHIND_NO_PROXY', 'SUPPORT_TO_EMAIL', 'LESSON_DELIVERED_MIN_TEACHER_MINUTES', 'PAYPAL_CAPTURE_CONFIRMS',
    # cancellation / reschedule / strike policy (Task 9.6)
    'STUDENT_FREE_CANCEL_HOURS', 'RESCHEDULE_MIN_NOTICE_HOURS', 'RESCHEDULE_MAX_PER_BOOKING',
    'TUTOR_CANCEL_NO_PENALTY_HOURS', 'TUTOR_EARLY_CANCELS_PER_30D', 'TUTOR_CANCEL_BONUS_CREDITS', 'STRIKE_LIMIT',
    'STRIKE_WINDOW_DAYS', 'CREDIT_EXPIRY_DAYS_REFUND', 'CREDIT_EXPIRY_DAYS_BONUS', 'CREDIT_EXPIRY_DAYS_BUNDLE',
    # refund worker tuning (Task 10.7)
    'REFUND_MAX_ATTEMPTS', 'REFUND_TRANSIENT_WINDOW_HOURS', 'REFUND_ATTEMPT_LEASE_MINUTES', 'REFUND_MANUAL_ALERT_AFTER_HOURS',
    'REFUND_REPLAY_WINDOW_DAYS', 'REFUND_SWEEP_LIMIT', 'REFUND_SWEEP_BUDGET_SECONDS', 'REFUND_POLL_INTERVAL_MINUTES',
    'REFUND_FIRST_ATTEMPT_DELAY_MINUTES',
}


def env_keys_read(path):
    keys = set()
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.Call) and node.args and src(node.func) in READ_FUNCS:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and KEY.match(first.value):
                keys.add(first.value)
        elif isinstance(node, ast.Subscript) and src(node.value) in MAPPINGS:
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str) and KEY.match(node.slice.value):
                keys.add(node.slice.value)
    return keys


def documented_keys(text):
    return {m.group(1) for m in re.finditer(r'^\s*#?\s*([A-Z][A-Z0-9_]+)=', text, re.MULTILINE)}


def _missing():
    read = set().union(*(env_keys_read(p) for p in sorted(SETTINGS_DIR.glob('*.py'))))
    return read - documented_keys(ENV_EXAMPLE.read_text(encoding='utf-8'))


def test_env_example_lists_every_setting_read_from_the_environment():
    missing = _missing()
    new = sorted(missing - ALLOWLIST)
    stale = sorted(ALLOWLIST - missing)
    assert not new, f'Add these keys to .env.example: {new}'
    assert not stale, f'These keys are documented now - remove them from ALLOWLIST: {stale}'


def test_detector(tmp_path):
    settings = tmp_path / 'base.py'
    settings.write_text(
        "A = os.environ.get('ALPHA', '1')\n"
        "B = os.environ['BRAVO']\n"
        "C = os.getenv('CHARLIE')\n"
        "D = _env_bool('DELTA', True)\n"
        "def v(env=os.environ):\n    return env.get('ECHO'), env['FOXTROT'], _int('GOLF')\n"
        "X = os.environ.get(name)\n",                       # dynamic names are out of reach
        encoding='utf-8')
    assert env_keys_read(settings) == {'ALPHA', 'BRAVO', 'CHARLIE', 'DELTA', 'ECHO', 'FOXTROT', 'GOLF'}
    assert documented_keys('ALPHA=1\n# BRAVO=x\n  CHARLIE=\nnot a key\n# see DELTA=1 inline\n') == {'ALPHA', 'BRAVO', 'CHARLIE'}
