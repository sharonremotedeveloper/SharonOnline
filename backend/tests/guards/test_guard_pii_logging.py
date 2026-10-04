"""
Guard (d): no obvious PII or secrets interpolated into log messages.

Plan §5: logs carry ids and error types only. Deliberately conservative (few false positives): a logging call
(`logger.info(...)`, `log.error(...)`, `logging.warning(...)`) is flagged when its message is an f-string, a `%`-format or a
`.format()` that interpolates an expression whose NAME mentions email / token / password / phone / secret, or when such
an expression is passed as a lazy `%s` argument, concatenated (`'x' + user.email`) or put in `extra={...}`.
`user.email`, `access_token`, `payload['password']`, `clientSecret`, `phone_number` are caught; `booking.id`,
`type(exc).__name__`, `token_count`, `password_reset_sent` are not: names are split into words (snake_case and camelCase)
and only the LAST word (or the last two, for `phone_number` / `email_address`) decides. Logger receivers: `logger`, `log`,
`logging`, any name or attribute ending in `logger` / `_log` (`self.logger`, `audit_logger`, `self._log`).

How to shrink: log an id instead of the value, then lower the file's count here.
"""
import ast
import re

from guards._scan import parse, ratchet_errors, scan, src

LOGGER_NAMES = {'logger', 'log', 'logging', '_log', '_logger', 'LOGGER'}
LEVELS = {'debug', 'info', 'warning', 'warn', 'error', 'exception', 'critical', 'log'}
PII_WORDS = {'email', 'emails', 'token', 'tokens', 'password', 'passwords', 'passwd', 'pwd', 'phone', 'secret', 'secrets'}
PII_PAIRS = {('phone', 'number'), ('email', 'address'), ('mobile', 'number')}


def _words(identifier):
    snake = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', identifier).lower()
    return [w for w in re.split(r'[^a-z0-9]+', snake) if w]


def is_pii_name(identifier):
    words = _words(identifier)
    return bool(words) and (words[-1] in PII_WORDS or tuple(words[-2:]) in PII_PAIRS)
# Baseline 2026-10-04: {file: number of logging calls with PII}. Only ever lower these numbers.
ALLOWLIST = {
    'bookings/tasks.py': 5,                       # reminder / late-alert logs print e-mail addresses (N2a moves them)
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
    return any(is_pii_name(word) for word in _names(expr))


def _interpolated(message):
    """Expressions interpolated into the message itself (f-string, %-format, .format(), + concatenation)."""
    if isinstance(message, ast.JoinedStr):
        return [v.value for v in message.values if isinstance(v, ast.FormattedValue)]
    if isinstance(message, ast.BinOp) and isinstance(message.op, ast.Mod):
        right = message.right
        return list(right.elts) if isinstance(right, ast.Tuple) else [right]
    if isinstance(message, ast.BinOp) and isinstance(message.op, ast.Add):
        return [part for side in (message.left, message.right)
                for part in (_interpolated(side) if isinstance(side, (ast.BinOp, ast.JoinedStr)) else [side])
                if not isinstance(part, ast.Constant)]
    if isinstance(message, ast.Call) and isinstance(message.func, ast.Attribute) and message.func.attr == 'format':
        return list(message.args) + [kw.value for kw in message.keywords]
    return []


def _extra(node):
    """Values (and PII-named keys) of `extra={...}`; a non-literal `extra=` expression is checked as a whole."""
    value = next((kw.value for kw in node.keywords if kw.arg == 'extra'), None)
    if value is None:
        return []
    if isinstance(value, ast.Dict):
        keys = [k for k in value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str) and is_pii_name(k.value)]
        return list(value.values) + keys
    return [value]


def _is_logger(receiver):
    name = receiver.id if isinstance(receiver, ast.Name) else receiver.attr if isinstance(receiver, ast.Attribute) else ''
    return name in LOGGER_NAMES or name.lower().endswith(('logger', '_log'))


def _is_logging_call(node):
    func = node.func
    return isinstance(func, ast.Attribute) and func.attr in LEVELS and _is_logger(func.value)


def pii_log_calls(path):
    hits = []
    for node in ast.walk(parse(path)):
        if not (isinstance(node, ast.Call) and _is_logging_call(node) and node.args):
            continue
        args = node.args[1:] if node.func.attr == 'log' else node.args       # log(level, msg, ...)
        if not args:
            continue
        message, lazy = args[0], args[1:]
        suspects = [e for e in _interpolated(message) + list(lazy) + _extra(node)
                    if (isinstance(e, ast.Constant) and is_pii_name(str(e.value))) or _mentions_pii(e)]
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


def test_detector_catches_extra_concatenation_and_attribute_loggers(tmp_path):
    """QA review item 6."""
    bad = tmp_path / 'bad.py'
    bad.write_text(
        "logger.info('sent', extra={'to': user.email})\n"
        "logger.info('sent to ' + user.email)\n"
        "self.logger.warning('token %s', refresh_token)\n"
        "self._log.error(f'{payload[\"password\"]}')\n"
        "audit_logger.info('%s', phone_number)\n"
        "log.info('%s', data.get('clientSecret'))\n",
        encoding='utf-8')
    assert len(pii_log_calls(bad)) == 6


def test_detector_matches_word_segments_not_substrings(tmp_path):
    ok = tmp_path / 'ok.py'
    ok.write_text(
        "logger.info('used %s tokens', token_count)\n"
        "logger.info(f'{emailed_at} {password_reset_sent}')\n"
        "catalog.info(user.email)\n"                                      # not a logger
        "logger.info('x', extra={'booking': booking.id})\n",
        encoding='utf-8')
    assert pii_log_calls(ok) == []


def test_detector_ignores_ids_and_error_types(tmp_path):
    ok = tmp_path / 'ok.py'
    ok.write_text(
        "logger.info('booking=%s', booking.id)\n"
        "logger.error(f'failed for {booking.pk}: {type(exc).__name__}')\n"
        "logger.warning('Zoom OAuth token request failed')\n"          # the word is in the literal text, not interpolated
        "print(f'{user.email}')\n",
        encoding='utf-8')
    assert pii_log_calls(ok) == []
