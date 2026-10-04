"""
Copy-based mutation helper (Q0, docs/QUALITY_GATES.md). Proves a test actually guards a line:

    python scripts/mutate.py --file apps/bookings/services/holds.py --line 42 --find "<=" --replace "<" \
        --test tests/test_booking_holds.py [--test tests/other.py::test_x]

1. Refuses to run unless `git status --porcelain` is empty (so the restore can never clobber someone's edits and a crash
   leaves an obvious one-file diff).
2. Copies the file to a temp backup, replaces the FIRST occurrence of --find on --line only (bytes; line endings kept).
3. Runs pytest on the given node ids with bytecode writing disabled (a stale mutant .pyc can never outlive the run).
4. ALWAYS restores the original bytes and timestamps from the backup (finally block) and verifies the restore by hash.

Exit codes: 0 = KILLED (the tests failed on the mutant), 1 = SURVIVED (they passed: the line is not guarded),
2 = refused / bad arguments / pytest could not run (no verdict; collection errors and "no tests ran" are not kills).
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KILLED, SURVIVED, ERROR = 0, 1, 2


def _fail(message):
    print(f'mutate: {message}', file=sys.stderr)
    return ERROR


def tree_is_clean(directory):
    result = subprocess.run(['git', 'status', '--porcelain'], cwd=directory, capture_output=True, text=True)
    if result.returncode != 0:
        return False, f'not a git checkout ({result.stderr.strip()})'
    return result.stdout.strip() == '', result.stdout.strip()


def mutate_line(original: bytes, line_no: int, find: str, replace: str) -> bytes:
    lines = original.splitlines(keepends=True)
    if not 1 <= line_no <= len(lines):
        raise ValueError(f'line {line_no} is outside the file (1..{len(lines)})')
    needle, repl = find.encode('utf-8'), replace.encode('utf-8')
    if needle not in lines[line_no - 1]:
        raise ValueError(f'{find!r} not found on line {line_no}: {lines[line_no - 1].decode("utf-8", "replace").rstrip()}')
    lines[line_no - 1] = lines[line_no - 1].replace(needle, repl, 1)
    return b''.join(lines)


def run_tests(python, tests, cwd):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    cmd = [python, '-m', 'pytest', '-q', '-x', '-p', 'no:cacheprovider', *tests]
    return subprocess.run(cmd, cwd=cwd, env=env).returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description='Apply one textual mutant, run tests, restore the file.')
    parser.add_argument('--file', required=True, help='source file to mutate (relative to the current directory)')
    parser.add_argument('--line', required=True, type=int, help='1-based line number')
    parser.add_argument('--find', required=True, help='text to replace (first occurrence on that line)')
    parser.add_argument('--replace', required=True, help='replacement text')
    parser.add_argument('--test', required=True, action='append', help='pytest node id (repeatable)')
    parser.add_argument('--python', default=sys.executable, help='interpreter for pytest (default: this one)')
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    target = (cwd / args.file).resolve()
    if not target.is_file():
        return _fail(f'{args.file} does not exist')
    clean, detail = tree_is_clean(target.parent)
    if not clean:
        return _fail(f'refusing to run: the working tree is not clean (commit or stash first):\n{detail}')

    original = target.read_bytes()
    try:
        mutant = mutate_line(original, args.line, args.find, args.replace)
    except ValueError as exc:
        return _fail(str(exc))

    fd, backup = tempfile.mkstemp(prefix='mutate-', suffix=target.suffix)
    os.close(fd)
    shutil.copy2(target, backup)
    print(f'mutant: {args.file}:{args.line}  {args.find!r} -> {args.replace!r}')
    try:
        target.write_bytes(mutant)
        code = run_tests(args.python, args.test, cwd)
    finally:
        shutil.copy2(backup, target)
        os.unlink(backup)
    restored = hashlib.sha256(target.read_bytes()).hexdigest() == hashlib.sha256(original).hexdigest()
    print(f'restored: {"ok (byte-identical)" if restored else "MISMATCH"}')
    if not restored:
        return _fail(f'{args.file} was not restored byte-for-byte; check `git diff`')
    if code == 0:
        print('SURVIVED: the tests passed on the mutant')
        return SURVIVED
    if code == 1:
        print('KILLED: the tests failed on the mutant')
        return KILLED
    return _fail(f'no verdict: pytest exited with {code} (collection error, usage error or no tests ran)')


if __name__ == '__main__':
    sys.exit(main())
