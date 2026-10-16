"""Run the Django production migration release as a separately gated job.

The application uses Railway/Neon pooled ``DATABASE_URL`` for normal traffic.
Migrations must use Neon's direct/unpooled connection instead.  This entrypoint
deliberately accepts no Django migration arguments so a Railway one-shot
release cannot accidentally receive ``--fake``, ``--run-syncdb``, or a partial
migration target.

Preview the command without applying migrations::

    DJANGO_SETTINGS_MODULE=config.settings.production \
    DATABASE_URL_UNPOOLED=postgresql://... \
    python scripts/run_production_migrations.py --plan

Apply only from an explicitly approved one-shot release::

    DJANGO_SETTINGS_MODULE=config.settings.production \
    DATABASE_URL_UNPOOLED=postgresql://... \
    PRODUCTION_MIGRATION_APPROVED=true \
    python scripts/run_production_migrations.py --apply

This script does not create a backup, alter provider infrastructure, or decide
whether a migration is safe for production.  The release owner must review the
plan for expand/contract compatibility before setting the approval variable.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


BACKEND_DIR = Path(__file__).resolve().parents[1]
# 0.0.0.0 is included to reject Docker/local bind targets in release config.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "db"}  # noqa: S104
APPROVED_VALUES = {"1", "true", "yes"}


def validate_environment(env: dict[str, str] | None = None) -> str:
    """Validate the release-only settings and return the direct DB URL."""

    env = env or os.environ
    if env.get("DJANGO_SETTINGS_MODULE") != "config.settings.production":
        raise RuntimeError(
            "DJANGO_SETTINGS_MODULE must equal config.settings.production"
        )

    database_url = (env.get("DATABASE_URL_UNPOOLED") or "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL_UNPOOLED is required for migrations")

    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RuntimeError("DATABASE_URL_UNPOOLED must be a PostgreSQL URL")
    if parsed.hostname.lower() in LOCAL_HOSTS:
        raise RuntimeError(
            "DATABASE_URL_UNPOOLED must not target a local or Docker database"
        )
    return database_url


def command_for(mode: str) -> list[str]:
    """Return the only management command this release supports."""

    if mode == "plan":
        return [sys.executable, "manage.py", "migrate", "--plan"]
    if mode == "apply":
        return [sys.executable, "manage.py", "migrate", "--noinput"]
    raise ValueError(f"unsupported migration mode: {mode}")


def redacted_target(database_url: str) -> str:
    parsed = urlsplit(database_url)
    host = parsed.hostname or "unknown"
    port = f":{parsed.port}" if parsed.port else ""
    database = parsed.path.lstrip("/") or "unknown"
    return f"{parsed.scheme}://{host}{port}/{database}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="show pending migrations only")
    mode.add_argument("--apply", action="store_true", help="apply all pending migrations")
    args = parser.parse_args(argv)

    try:
        database_url = validate_environment()
    except RuntimeError as exc:
        parser.error(str(exc))

    if args.apply and os.environ.get("PRODUCTION_MIGRATION_APPROVED", "").lower() not in APPROVED_VALUES:
        parser.error(
            "--apply requires PRODUCTION_MIGRATION_APPROVED=true (or 1/yes)"
        )

    child_env = os.environ.copy()
    # production.py intentionally reads DATABASE_URL for Django's connection;
    # this release maps it to the explicitly supplied direct/unpooled URL.
    child_env["DATABASE_URL"] = database_url
    child_env["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
    command = command_for("apply" if args.apply else "plan")
    print(f"production migration {'apply' if args.apply else 'plan'}: {redacted_target(database_url)}")
    return subprocess.call(command, cwd=BACKEND_DIR, env=child_env)  # noqa: S603


if __name__ == "__main__":
    raise SystemExit(main())
