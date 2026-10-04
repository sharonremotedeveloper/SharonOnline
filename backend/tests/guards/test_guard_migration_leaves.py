"""
Guard (g): one migration leaf per app.

Parallel slices each add migrations (numbers are reserved at dispatch, plan §4); two branches that both add `000N` to the same
app merge cleanly in git but leave Django with two leaves ("Conflicting migrations detected"). This catches the fork in the
unit suite instead of at deploy time. Fix with `manage.py makemigrations --merge` (or renumber before merging). No allowlist.
"""
from django.db.migrations.graph import MigrationGraph
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.migration import Migration


def test_every_app_has_exactly_one_migration_leaf():
    conflicts = MigrationLoader(None, ignore_no_migrations=True).detect_conflicts()
    assert conflicts == {}, f'Forked migration history (run makemigrations --merge): {conflicts}'


def test_detector_sees_a_forked_app():
    loader = MigrationLoader(None, ignore_no_migrations=True, load=False)
    loader.graph = MigrationGraph()
    for name in ('0001_initial', '0002_a', '0002_b'):
        loader.graph.add_node(('demo', name), Migration(name, 'demo'))
    loader.graph.add_dependency('demo.0002_a', ('demo', '0002_a'), ('demo', '0001_initial'))
    loader.graph.add_dependency('demo.0002_b', ('demo', '0002_b'), ('demo', '0001_initial'))
    assert loader.detect_conflicts() == {'demo': ['0002_a', '0002_b']}
