"""
Guard (c): every outbound HTTP call through `requests` / `httpx` passes `timeout=`.

A call without a timeout can hang a Celery worker (or a request thread) forever on a stuck provider. Covers module-level
calls (`requests.post(...)`, `httpx.get(...)`) and `requests.request(...)`, module aliases (`import requests as r`) and
imported verbs (`from requests import post`); `timeout=None` counts as no timeout; `**kwargs` forwarding is reported too,
because the scan cannot see whether a timeout is inside.

How to shrink: add `timeout=` to a listed call, then lower its count here.
"""
import ast

from guards._scan import parse, ratchet_errors, scan, src

CLIENT_MODULES = {'requests', 'httpx'}
VERBS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'request', 'stream'}
# Baseline 2026-10-04: {file: number of calls without timeout=}. Only ever lower these numbers.
ALLOWLIST = {}


def _aliases(tree):
    """Names bound to the client modules (`import requests as r`) and to their verbs (`from requests import post as p`)."""
    modules, functions = set(CLIENT_MODULES), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.asname or a.name for a in node.names if a.name in CLIENT_MODULES}
        elif isinstance(node, ast.ImportFrom) and node.module in CLIENT_MODULES:
            functions |= {a.asname or a.name for a in node.names if a.name in VERBS}
    return modules, functions


def _is_client_call(node, modules, functions):
    func = node.func
    if isinstance(func, ast.Attribute):
        return isinstance(func.value, ast.Name) and func.value.id in modules and func.attr in VERBS
    return isinstance(func, ast.Name) and func.id in functions


def _has_real_timeout(node):
    timeout = next((kw.value for kw in node.keywords if kw.arg == 'timeout'), None)
    return timeout is not None and not (isinstance(timeout, ast.Constant) and timeout.value is None)


def calls_without_timeout(path):
    tree = parse(path)
    modules, functions = _aliases(tree)
    return [f'{node.lineno}: {src(node.func)}(...)' for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _is_client_call(node, modules, functions) and not _has_real_timeout(node)]


def test_outbound_http_calls_always_pass_a_timeout():
    errors = ratchet_errors(scan(calls_without_timeout), ALLOWLIST)
    assert not errors, 'Pass timeout= to every requests/httpx call:\n' + '\n'.join(errors)


def test_detector(tmp_path):
    bad = tmp_path / 'bad.py'
    bad.write_text(
        "requests.post(url, json={})\n"
        "httpx.get(url)\n"
        "requests.request('GET', url, **kw)\n"
        "requests.get(url, timeout=10)\n"                 # fine
        "refund_requests.filter(x=1)\n"                    # not the HTTP client
        "session.get(url)\n",                              # sessions are out of scope (none exist today)
        encoding='utf-8')
    assert len(calls_without_timeout(bad)) == 3


def test_detector_resolves_aliases_and_rejects_timeout_none(tmp_path):
    """QA review item 5."""
    bad = tmp_path / 'bad.py'
    bad.write_text(
        "import requests as r\n"
        "import httpx as hx\n"
        "from requests import post, get as fetch\n"
        "r.post(url)\n"
        "hx.get(url)\n"
        "post(url, json={})\n"
        "fetch(url)\n"
        "requests.get(url, timeout=None)\n"
        "fetch(url, timeout=5)\n",                         # fine
        encoding='utf-8')
    assert len(calls_without_timeout(bad)) == 5


def test_detector_ignores_unrelated_bare_names(tmp_path):
    ok = tmp_path / 'ok.py'
    ok.write_text("def post(x):\n    return x\npost(1)\nget(2)\n", encoding='utf-8')
    assert calls_without_timeout(ok) == []
