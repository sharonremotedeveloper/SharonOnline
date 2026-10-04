"""
Guard (c): every outbound HTTP call through `requests` / `httpx` passes `timeout=`.

A call without a timeout can hang a Celery worker (or a request thread) forever on a stuck provider. Covers module-level
calls (`requests.post(...)`, `httpx.get(...)`) and `requests.request(...)`; `**kwargs` forwarding is reported too, because
the scan cannot see whether a timeout is inside.

How to shrink: add `timeout=` to a listed call, then lower its count here.
"""
import ast

from guards._scan import parse, ratchet_errors, scan, src

CLIENT_MODULES = {'requests', 'httpx'}
VERBS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'request', 'stream'}
# Baseline 2026-10-04: {file: number of calls without timeout=}. Only ever lower these numbers.
ALLOWLIST = {}


def calls_without_timeout(path):
    hits = []
    for node in ast.walk(parse(path)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        receiver = node.func.value
        if not (isinstance(receiver, ast.Name) and receiver.id in CLIENT_MODULES and node.func.attr in VERBS):
            continue
        has_timeout = any(kw.arg == 'timeout' for kw in node.keywords)
        if not has_timeout:
            hits.append(f'{node.lineno}: {src(node.func)}(...)')
    return hits


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
