"""
Q0: scripts/mutate.py, the copy-based mutation helper. Exercised on a throwaway git repo in tmp_path (never on real source):
it refuses a dirty tree, mutates exactly one line, reports KILLED / SURVIVED and restores the file byte-for-byte.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

MUTATE = Path(__file__).resolve().parents[1] / 'scripts' / 'mutate.py'
SOURCE = b'def add(a, b):\r\n    return a + b\r\n\r\n\r\ndef sub(a, b):\r\n    return a - b\r\n'
TEST = (b'import os\nfrom calc import add\n\n\ndef test_add():\n'
        b'    observe = os.environ.get("OBSERVE_PATH")\n'
        b'    if observe:\n'
        b'        open(observe, "wb").write(open("calc.py", "rb").read())\n'
        b'    assert add(2, 3) == 5\n')


def _git(repo, *args):
    subprocess.run(['git', '-c', 'user.email=q0@example.test', '-c', 'user.name=Q0', *args], cwd=repo, check=True,
                   capture_output=True)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / 'repo'
    path.mkdir()
    (path / 'calc.py').write_bytes(SOURCE)
    (path / 'test_calc.py').write_bytes(TEST)
    (path / 'pytest.ini').write_text('[pytest]\naddopts = -p no:django -p no:cacheprovider\n', encoding='utf-8')
    (path / '.gitattributes').write_text('* -text\n', encoding='utf-8')     # keep CRLF bytes exactly as written
    _git(path, 'init', '-q')
    _git(path, 'add', '-A')
    _git(path, 'commit', '-q', '-m', 'init')
    return path


def run(repo, *args, observe=None):
    env = {k: v for k, v in os.environ.items() if k != 'DJANGO_SETTINGS_MODULE'}
    if observe:
        env['OBSERVE_PATH'] = str(observe)
    return subprocess.run([sys.executable, str(MUTATE), *args], cwd=repo, env=env, capture_output=True, text=True,
                          timeout=120)


def test_a_killed_mutant_is_reported_and_the_file_restored(repo, tmp_path):
    observed = tmp_path / 'observed.py'
    result = run(repo, '--file', 'calc.py', '--line', '2', '--find', '+', '--replace', '-', '--test', 'test_calc.py',
                 observe=observed)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'KILLED' in result.stdout
    assert 'backup: ' in result.stdout                     # QA item 9: where to recover from if the process is killed
    assert (repo / 'calc.py').read_bytes() == SOURCE
    # exactly one line changed during the run, line endings untouched
    assert observed.read_bytes() == SOURCE.replace(b'return a + b', b'return a - b')


def test_a_surviving_mutant_is_reported_and_the_file_restored(repo):
    result = run(repo, '--file', 'calc.py', '--line', '6', '--find', 'a - b', '--replace', 'a + b', '--test', 'test_calc.py')
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'SURVIVED' in result.stdout
    assert (repo / 'calc.py').read_bytes() == SOURCE


def test_a_dirty_tree_is_refused_without_touching_anything(repo):
    (repo / 'scratch.txt').write_text('uncommitted', encoding='utf-8')
    result = run(repo, '--file', 'calc.py', '--line', '2', '--find', '+', '--replace', '-', '--test', 'test_calc.py')
    assert result.returncode == 2
    assert 'refus' in (result.stdout + result.stderr).lower()
    assert (repo / 'calc.py').read_bytes() == SOURCE


def test_a_mutant_that_does_not_compile_is_refused(repo):
    """ERR-120: a shell that drops quotes produced `return "` - a SyntaxError is not a kill."""
    result = run(repo, '--file', 'calc.py', '--line', '2', '--find', 'a + b', '--replace', '"', '--test', 'test_calc.py')
    assert result.returncode == 2
    assert 'does not compile' in result.stdout + result.stderr
    assert (repo / 'calc.py').read_bytes() == SOURCE


def test_text_not_on_the_line_is_an_error_not_a_mutation(repo):
    result = run(repo, '--file', 'calc.py', '--line', '1', '--find', 'a + b', '--replace', 'a - b', '--test', 'test_calc.py')
    assert result.returncode == 2
    assert 'not found on line 1' in result.stdout + result.stderr
    assert (repo / 'calc.py').read_bytes() == SOURCE
    assert subprocess.run(['git', 'status', '--porcelain'], cwd=repo, capture_output=True, text=True).stdout == ''
