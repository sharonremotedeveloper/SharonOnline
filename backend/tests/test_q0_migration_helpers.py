"""Q0: migration-test helper (tests/migration_helpers.py) smoke test on an existing migration (users 0005 adds a column)."""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader

from migration_helpers import latest_targets, migrate_and_build

BEFORE = [('users', '0004_supportinquiry_category_and_more')]
AFTER = [('users', '0005_grace_failure_runbook')]


@pytest.mark.django_db(transaction=True)
def test_rows_built_on_the_old_schema_survive_the_forward_migration():
    def build(old_apps):
        User = old_apps.get_model('users', 'User')
        assert 'booking_blocked_reason' not in {f.name for f in User._meta.get_fields()}
        User.objects.create(username='historical', email='h@example.test', password='!')

    def verify(new_apps):
        return new_apps.get_model('users', 'User').objects.get(username='historical').booking_blocked_reason

    assert migrate_and_build(BEFORE, AFTER, build, verify) == ''


@pytest.mark.django_db(transaction=True)
def test_the_database_is_back_on_the_latest_migrations_afterwards():
    executor = MigrationExecutor(connection)
    assert executor.migration_plan(latest_targets()) == []


def test_latest_targets_are_one_leaf_per_app():
    targets = latest_targets()
    apps = [app for app, _ in targets]
    assert len(apps) == len(set(apps)) and 'users' in apps
    assert set(targets) == set(MigrationLoader(None, ignore_no_migrations=True).graph.leaf_nodes())
