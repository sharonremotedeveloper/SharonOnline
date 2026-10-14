"""Production database connection policy shared by Django and readiness."""

import dj_database_url


def production_database_config(database_url):
    config = dj_database_url.parse(database_url, conn_max_age=600)
    options = config.setdefault("OPTIONS", {})
    # ssl_require=True in dj-database-url overwrites an explicit verify-ca or
    # verify-full URL option with the weaker `require` mode. Preserve the
    # configured policy, while upgrading weak or missing modes to `require`.
    # This preserves the old production floor even for legacy URLs that
    # explicitly say `prefer` or `disable`.
    sslmode = options.get("sslmode") or "require"
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        sslmode = "require"
    options["sslmode"] = sslmode
    return config
