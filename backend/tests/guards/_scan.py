"""
Shared helpers for the guard tests (Q0, docs/QUALITY_GATES.md).

Every guard follows the same ratchet:
  * a detector turns one source file into a list of offending sites;
  * `ratchet_errors(found, allowlist)` compares the per-file counts with the baseline allowlist;
  * a file that is not on the allowlist, or that has MORE sites than allowed, fails (a new offender);
  * a file with FEWER sites than allowed also fails, with a message asking you to lower the number (the allowlist can only
    shrink, so a fixed site can never silently come back).

Allowlists are keyed by file and count (not line numbers) so unrelated edits that move code do not break the guards.
"""
import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
APPS = BACKEND / 'apps'


def app_files(root=APPS, *, include_migrations=False, pattern='*.py'):
    """Every Python source file under `root` (migrations excluded unless asked)."""
    for path in sorted(Path(root).rglob(pattern)):
        if not include_migrations and 'migrations' in path.parts:
            continue
        if '__pycache__' in path.parts:
            continue
        yield path


def rel(path, root=APPS):
    return Path(path).relative_to(root).as_posix()


def _display(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(BACKEND).as_posix()
    except ValueError:
        return path.as_posix()


def parse(path):
    """AST of a source file (a UTF-8 BOM is accepted); a SyntaxError names the file relative to backend/."""
    name = _display(path)
    try:
        return ast.parse(Path(path).read_text(encoding='utf-8-sig'), filename=name)
    except SyntaxError as exc:
        raise SyntaxError(f'guard scan cannot parse {name}: {exc.msg}', (name, exc.lineno, exc.offset, exc.text)) from exc


def src(node):
    return ast.unparse(node)


def parents(tree):
    """Map child node -> parent node."""
    out = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[child] = node
    return out


def scan(detector, root=APPS, files=None, **kw):
    """{relative path: [site descriptions]} for every file where `detector(path)` found something."""
    found = {}
    for path in (files if files is not None else app_files(root, **kw)):
        sites = detector(path)
        if sites:
            found[rel(path, root)] = sites
    return found


def ratchet_errors(found, allowlist):
    """Human-readable problems: new offenders (fail) and stale allowlist entries (fail: shrink the allowlist)."""
    errors = []
    for path, sites in sorted(found.items()):
        allowed = allowlist.get(path, 0)
        if len(sites) > allowed:
            errors.append(f'NEW offender(s) in {path} ({len(sites)} found, {allowed} allowed):\n    ' + '\n    '.join(sites))
    for path, allowed in sorted(allowlist.items()):
        actual = len(found.get(path, []))
        if actual < allowed:
            errors.append(f'{path}: allowlist says {allowed} but only {actual} remain - lower the number (allowlists only shrink)')
    return errors
