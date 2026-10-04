"""
Migration-test helper (Q0): test a data migration against rows built with the historical models.

    @pytest.mark.django_db(transaction=True)          # schema changes cannot run inside the per-test transaction
    def test_backfill(...):
        def build(old_apps):
            Teacher = old_apps.get_model('teachers', 'TeacherProfile')
            ...create rows on the OLD schema...
        def verify(new_apps):
            return new_apps.get_model('teachers', 'TeacherProfile').objects.get(...).status
        assert migrate_and_build([('teachers', '0004_x')], [('teachers', '0005_y')], build, verify) == 'approved'

`migrate_and_build` migrates the test database back to `before`, calls `build(apps)` with the historical app registry,
migrates forward to `after` and calls `verify(apps)` at that state. The database is ALWAYS migrated back to the latest
leaf of every app afterwards (also when the test fails), so later tests see the normal schema. Use the Postgres job
(`@pytest.mark.postgres`) for the populated-DB check plan §5 asks for; SQLite runs it too.
"""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader


def latest_targets():
    """One (app, migration) leaf per app: the state `migrate` with no arguments reaches."""
    return sorted(MigrationLoader(None, ignore_no_migrations=True).graph.leaf_nodes())


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor


def apps_at(targets):
    """The historical app registry at `targets` (does not touch the database)."""
    return MigrationExecutor(connection).loader.project_state(targets).apps


def migrate_and_build(before, after, build=None, verify=None):
    """
    Migrate to `before`, `build(old_apps)`, migrate to `after`, `verify(new_apps)` (while the database is still at `after`),
    then restore the latest schema. Returns `verify`'s result (or the `after` registry when no `verify` is given; only safe
    to query when `after` is already the latest state of the apps involved).
    """
    try:
        _migrate(before)
        if build is not None:
            build(apps_at(before))
        _migrate(after)
        new_apps = apps_at(after)
        return verify(new_apps) if verify is not None else new_apps
    finally:
        _migrate(latest_targets())
