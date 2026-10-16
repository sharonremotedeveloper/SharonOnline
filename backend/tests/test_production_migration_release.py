"""Safety contract for the production migration release entrypoint."""

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "run_production_migrations.py"
SPEC = importlib.util.spec_from_file_location("production_migration_release", SCRIPT)
RELEASE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RELEASE)


VALID_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "DATABASE_URL_UNPOOLED": "postgresql://migration:secret@ep-direct.neon.tech:5432/sharon",
}


def test_release_requires_production_settings_and_direct_url():
    with pytest.raises(RuntimeError, match="DJANGO_SETTINGS_MODULE"):
        RELEASE.validate_environment({"DATABASE_URL_UNPOOLED": VALID_ENV["DATABASE_URL_UNPOOLED"]})

    with pytest.raises(RuntimeError, match="DATABASE_URL_UNPOOLED"):
        RELEASE.validate_environment({"DJANGO_SETTINGS_MODULE": VALID_ENV["DJANGO_SETTINGS_MODULE"]})


def test_release_rejects_local_database_targets():
    env = {**VALID_ENV, "DATABASE_URL_UNPOOLED": "postgresql://user:pass@localhost:5432/db"}
    with pytest.raises(RuntimeError, match="local or Docker"):
        RELEASE.validate_environment(env)


def test_release_commands_are_fixed_and_never_fake_or_syncdb():
    assert RELEASE.command_for("plan")[1:] == ["manage.py", "migrate", "--plan"]
    assert RELEASE.command_for("apply")[1:] == ["manage.py", "migrate", "--noinput"]
    assert "--fake" not in RELEASE.command_for("apply")
    assert "--run-syncdb" not in RELEASE.command_for("apply")


def test_redacted_target_never_includes_credentials():
    target = RELEASE.redacted_target(VALID_ENV["DATABASE_URL_UNPOOLED"])
    assert target == "postgresql://ep-direct.neon.tech:5432/sharon"
    assert "secret" not in target
