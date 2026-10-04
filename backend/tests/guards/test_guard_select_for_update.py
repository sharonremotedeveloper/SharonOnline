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


SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _chain(node):
    """(method calls of one queryset chain, outermost first, and the chain's root node): a.b().c() -> ([c, b], a)."""
    calls = []
    while True:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            calls.append(node)
            node = node.func.value
        elif isinstance(node, ast.Attribute):
            node = node.value
        else:
            return calls, node


def _unsafe(call):
    """select_for_update() whose `of=` is missing or does not name 'self' (e.g. of=('teacher',))."""
    if call.func.attr != 'select_for_update':
        return False
    of = next((kw.value for kw in call.keywords if kw.arg == 'of'), None)
    return of is None or not any(isinstance(n, ast.Constant) and n.value == 'self' for n in ast.walk(of))


def _scope_nodes(scope):
    """Nodes of one scope (module or function), not descending into nested functions / classes."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, SCOPES):
            stack.extend(ast.iter_child_nodes(node))


def _scope_hits(scope, parent, flagged):
    """
    Chains in one scope, following one level of variables inside the same scope:
    `qs = X.objects.select_related(...)` then `qs.select_for_update()` (or the other way round) counts as one chain.
    """
    nodes = list(_scope_nodes(scope))
    variables = {}                                   # name -> (has select_related, unsafe select_for_update calls)
    for node in sorted((n for n in nodes if isinstance(n, ast.Assign)), key=lambda n: n.lineno):
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            calls, root = _chain(node.value)
            related, unsafe = variables.get(getattr(root, 'id', None), (False, []))
            variables[node.targets[0].id] = (related or any(c.func.attr == 'select_related' for c in calls),
                                             unsafe + [c for c in calls if _unsafe(c)])
    for node in nodes:
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        up = parent.get(node)
        if isinstance(up, ast.Attribute) and up.value is node:
            continue                                   # not the top of its chain
        calls, root = _chain(node)
        related, unsafe = variables.get(getattr(root, 'id', None), (False, []))
        related = related or any(c.func.attr == 'select_related' for c in calls)
        if related:
            for call in unsafe + [c for c in calls if _unsafe(c)]:
                flagged.setdefault(id(call), f'{call.lineno}: {src(call.func)[:90]}')


def unsafe_lock_joins(path):
    tree = parse(path)
    parent = parents(tree)
    flagged = {}
    for scope in [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))]:
        _scope_hits(scope, parent, flagged)
    return list(flagged.values())


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


def test_detector_requires_self_inside_of_and_follows_a_split_chain(tmp_path):
    """QA review item 4: `of=` without 'self', and a queryset built in one statement and locked in the next."""
    bad = tmp_path / 'bad.py'
    bad.write_text(
        "a = Booking.objects.select_for_update(of=('teacher',)).select_related('teacher').get(pk=1)\n"
        "def f():\n"
        "    qs = Booking.objects.select_related('teacher')\n"
        "    return qs.select_for_update().get(pk=1)\n"
        "def g():\n"
        "    locked = Booking.objects.select_for_update().filter(pk=1)\n"
        "    return locked.select_related('teacher').first()\n",
        encoding='utf-8')
    assert len(unsafe_lock_joins(bad)) == 3


def test_detector_split_chain_with_of_self_is_fine(tmp_path):
    ok = tmp_path / 'ok.py'
    ok.write_text(
        "def f():\n"
        "    qs = Booking.objects.select_related('teacher')\n"
        "    return qs.select_for_update(of=('self',)).get(pk=1)\n"
        "def g():\n"
        "    qs = Booking.objects.select_related('teacher')\n"
        "def h():\n"
        "    return qs.select_for_update().get(pk=1)\n",                # different function: not followed
        encoding='utf-8')
    assert unsafe_lock_joins(ok) == []


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
