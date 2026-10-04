"""
Guard (b): `select_for_update()` combined with `select_related(...)` must say `of=('self',)`.

PostgreSQL refuses FOR UPDATE on the nullable side of an outer join ("FOR UPDATE cannot be applied to the nullable side of
an outer join"), and even across a non-null join it would lock the related rows too (wrong lock order, needless
contention). SQLite ignores row locks, so only this source scan (and the Postgres CI job) can see it. This scan covers the
whole `apps/` tree and supersedes the PaymentTransaction-only scan from Task 10.7 (test_refund_final_review.py).

How to shrink: add `of=('self',)` to a listed site (and prove it on the Postgres job), then lower its count here.
"""
import ast
import functools

from guards._scan import APPS, parents, parse, ratchet_errors, scan, src

# Baseline 2026-10-04: {file: number of select_for_update() + select_related() chains without of=('self',)}.
ALLOWLIST = {
    'integrations/views.py': 1,
    'payments/services/credits.py': 3,
    'payments/services/grace.py': 3,
    'payments/services/webhook_handler.py': 2,
}


def _chain_calls(node):
    """The method calls of one queryset chain, outermost first: a.b().c().d() -> [d, c, b]."""
    calls = []
    while True:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            calls.append(node)
            node = node.func.value
        elif isinstance(node, ast.Attribute):
            node = node.value
        else:
            return calls


def unsafe_lock_joins(path):
    tree = parse(path)
    parent = parents(tree)
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        up = parent.get(node)
        if isinstance(up, ast.Attribute) and up.value is node:
            continue                                   # not the top of its chain
        calls = _chain_calls(node)
        names = [c.func.attr for c in calls]
        if 'select_related' not in names:
            continue
        for call in calls:
            if call.func.attr == 'select_for_update' and not any(kw.arg == 'of' for kw in call.keywords):
                hits.append(f'{call.lineno}: {src(call.func)[:90]}')
    return hits


@functools.lru_cache(maxsize=1)
def _tree_hits():
    return scan(unsafe_lock_joins)


def test_row_locks_with_select_related_use_of_self():
    errors = ratchet_errors(_tree_hits(), ALLOWLIST)
    assert not errors, "select_for_update() + select_related() needs of=('self',):\n" + '\n'.join(errors)


def test_payment_transaction_locks_are_never_allowlisted():
    """Task 10.7 rule kept at zero tolerance: PaymentTransaction.booking / .credit_purchase are nullable."""
    bad = [f'{path}:{site}' for path, sites in _tree_hits().items() for site in sites if 'PaymentTransaction' in site]
    assert not bad, "select_for_update() + select_related() on PaymentTransaction without of=('self',): " + ', '.join(bad)


def test_detector_catches_both_orders_and_multiline_chains(tmp_path):
    bad = tmp_path / 'bad.py'
    bad.write_text(
        "a = Booking.objects.select_for_update().select_related('teacher').get(pk=1)\n"
        "b = Booking.objects.select_related('teacher').select_for_update(skip_locked=True).first()\n"
        "c = (PaymentTransaction.objects\n"
        "     .select_for_update()\n"
        "     .filter(x=1)\n"
        "     .select_related('booking')\n"
        "     .get())\n",
        encoding='utf-8')
    assert len(unsafe_lock_joins(bad)) == 3


def test_detector_accepts_of_self_and_plain_locks(tmp_path):
    ok = tmp_path / 'ok.py'
    ok.write_text(
        "a = Booking.objects.select_for_update(of=('self',)).select_related('teacher').get(pk=1)\n"
        "b = Booking.objects.select_for_update().get(pk=1)\n"
        "c = Booking.objects.select_related('teacher').get(pk=1)\n",
        encoding='utf-8')
    assert unsafe_lock_joins(ok) == []


def test_ratchet_fails_when_a_new_site_appears_in_an_allowlisted_file(tmp_path):
    (tmp_path / 'payments' / 'services').mkdir(parents=True)
    original = (APPS / 'payments' / 'services' / 'credits.py').read_text(encoding='utf-8')
    mutant = original + "\n\ndef _mutant():\n    return Booking.objects.select_for_update().select_related('x').get()\n"
    (tmp_path / 'payments' / 'services' / 'credits.py').write_text(mutant, encoding='utf-8')
    errors = ratchet_errors(scan(unsafe_lock_joins, tmp_path), {'payments/services/credits.py': 3})
    assert errors and 'NEW offender' in errors[0]
