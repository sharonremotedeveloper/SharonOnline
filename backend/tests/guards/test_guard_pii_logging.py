"""
Guard (d): no obvious PII or secrets interpolated into log messages.

Plan §5: logs carry ids and error types only. Deliberately conservative (few false positives): a logging call
(`logger.info(...)`, `log.error(...)`, `logging.warning(...)`) is flagged when its message is an f-string, a `%`-format or a
`.format()` that interpolates an expression whose NAME mentions email / token / password / phone / secret, or when such
an expression is passed as a lazy `%s` argument. `user.email`, `access_token`, `payload['password']` are caught;
`booking.id` and `type(exc).__name__` are not.

How to shrink: log an id instead of the value, then lower the file's count here.
"""
import ast
import re

from guards._scan import parse, ratchet_errors, scan, src

LOGGER_NAMES = {'logger', 'log', 'logging', '_log', '_logger', 'LOGGER'}
LEVELS = {'debug', 'info', 'warning', 'warn', 'error', 'exception', 'critical', 'log'}
PII = re.compile(r'e_?mail|token|password|passwd|phone|secret', re.IGNORECASE)
# Baseline 2026-10-04: {file: number of logging calls with PII}. Only ever lower these numbers.
ALLOWLIST = {
    'bookings/tasks.py': 5,                       # reminder / late-alert logs print e-mail addresses (N2a moves them)
    'integrations/email.py': 1,                   # dev-mock confirmation log (N1c rewrites send_email)
    'integrations/services/attendance.py': 2,     # Zoom participant e-mail in attendance logs
}


def _names(expr):
    """Identifier-ish words of an expression: attribute names, variable names and constant subscripts."""
    words = []
    for node in ast.walk(expr):
        if isinstance(node, ast.Name):
            words.append(node.id)
        elif isinstance(node, ast.Attribute):
            words.append(node.attr)
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            words.append(node.slice.value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'get' and node.args \
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            words.append(node.args[0].value)
    return words


def _mentions_pii(expr):
    return any(PII.search(word) for word in _names(expr))


def _interpolated(message):
    """Expressions interpolated into the message itself (f-string, %-format, .format())."""
    if isinstance(message, ast.JoinedStr):
        return [v.value for v in message.values if isinstance(v, ast.FormattedValue)]
    if isinstance(message, ast.BinOp) and isinstance(message.op, ast.Mod):
        right = message.right
        return list(right.elts) if isinstance(right, ast.Tuple) else [right]
    if isinstance(message, ast.Call) and isinstance(message.func, ast.Attribute) and message.func.attr == 'format':
        return list(message.args) + [kw.value for kw in message.keywords]
    return []


def _is_logging_call(node):
    func = node.func
    return (isinstance(func, ast.Attribute) and func.attr in LEVELS and isinstance(func.value, ast.Name)
            and func.value.id in LOGGER_NAMES)


def pii_log_calls(path):
    hits = []
    for node in ast.walk(parse(path)):
        if not (isinstance(node, ast.Call) and _is_logging_call(node) and node.args):
            continue
        args = node.args[1:] if node.func.attr == 'log' else node.args       # log(level, msg, ...)
        if not args:
            continue
        message, lazy = args[0], args[1:]
        suspects = [e for e in _interpolated(message) + list(lazy) if _mentions_pii(e)]
        if suspects:
            hits.append(f'{node.lineno}: {src(node.func)}(... {", ".join(src(s)[:40] for s in suspects)} ...)')
    return hits


def test_no_pii_in_log_messages():
    errors = ratchet_errors(scan(pii_log_calls), ALLOWLIST)
    assert not errors, 'Log ids and error types, never e-mails/tokens/passwords/phones/secrets:\n' + '\n'.join(errors)


def test_detector(tmp_path):
    bad = tmp_path / 'bad.py'
    bad.write_text(
        "logger.info(f'sent to {user.email}')\n"
        "logger.warning('token %s', access_token)\n"
        "logging.error('pw %s' % payload['password'])\n"
        "log.debug('{}'.format(user.phone_number))\n"
        "logger.log(logging.INFO, 'x %s', data.get('client_secret'))\n",
        encoding='utf-8')
    assert len(pii_log_calls(bad)) == 5


def test_detector_ignores_ids_and_error_types(tmp_path):
    ok = tmp_path / 'ok.py'
    ok.write_text(
        "logger.info('booking=%s', booking.id)\n"
        "logger.error(f'failed for {booking.pk}: {type(exc).__name__}')\n"
        "logger.warning('Zoom OAuth token request failed')\n"          # the word is in the literal text, not interpolated
        "print(f'{user.email}')\n",
        encoding='utf-8')
    assert pii_log_calls(ok) == []
