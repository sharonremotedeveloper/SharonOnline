import pytest

from config.database import production_database_config


@pytest.mark.parametrize("mode", ["require", "verify-ca", "verify-full"])
def test_production_db_preserves_explicit_tls_mode(mode):
    config = production_database_config(f"postgresql://user:password@db.example/test?sslmode={mode}")

    assert config["OPTIONS"]["sslmode"] == mode
    assert config["CONN_MAX_AGE"] == 600


def test_production_db_requires_tls_by_default():
    config = production_database_config("postgresql://user:password@db.example/test")

    assert config["OPTIONS"]["sslmode"] == "require"


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer"])
def test_production_db_upgrades_weak_tls_mode(mode):
    config = production_database_config(f"postgresql://user:password@db.example/test?sslmode={mode}")

    assert config["OPTIONS"]["sslmode"] == "require"
