"""The shared ratchet: new offenders fail, and an allowlist that is larger than reality fails too (it only shrinks)."""
from guards._scan import app_files, ratchet_errors


def test_clean_tree_passes():
    assert ratchet_errors({}, {}) == []
    assert ratchet_errors({'a.py': ['1: x']}, {'a.py': 1}) == []


def test_new_file_and_extra_site_fail():
    assert 'NEW offender' in ratchet_errors({'b.py': ['1: x']}, {})[0]
    assert 'NEW offender' in ratchet_errors({'a.py': ['1: x', '2: y']}, {'a.py': 1})[0]


def test_fixed_site_forces_the_allowlist_down():
    errors = ratchet_errors({'a.py': ['1: x']}, {'a.py': 2, 'gone.py': 1})
    assert len(errors) == 2 and all('lower the number' in e for e in errors)


def test_migrations_are_skipped_unless_asked(tmp_path):
    (tmp_path / 'x' / 'migrations').mkdir(parents=True)
    (tmp_path / 'x' / 'migrations' / '0001_initial.py').write_text('', encoding='utf-8')
    (tmp_path / 'x' / 'models.py').write_text('', encoding='utf-8')
    assert [p.name for p in app_files(tmp_path)] == ['models.py']
    assert len(list(app_files(tmp_path, include_migrations=True))) == 2
