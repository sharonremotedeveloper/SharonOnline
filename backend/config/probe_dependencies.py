"""One-shot dependency probe; never prints URLs, secrets, or query errors."""

import os
import sys

import dj_database_url
import psycopg2
from redis import Redis

from config.database import production_database_config
from config.redis import normalize_redis_url


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return 1
    production = os.environ.get("DJANGO_SETTINGS_MODULE") == "config.settings.production"
    config = (production_database_config(database_url) if production
              else dj_database_url.parse(database_url))
    params = {"dbname": config["NAME"], **config.get("OPTIONS", {})}
    for key, param in (("USER", "user"), ("PASSWORD", "password"),
                       ("HOST", "host"), ("PORT", "port")):
        if config[key]:
            params[param] = config[key]
    # One dictionary avoids duplicate keyword arguments if the URL already
    # supplies connect_timeout or other libpq options.
    params["connect_timeout"] = 2
    conn = psycopg2.connect(**params)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                return 1
    finally:
        conn.close()

    redis_url = os.environ.get("REDIS_URL", "")
    if production and not redis_url:
        return 1
    if redis_url:
        client = Redis.from_url(normalize_redis_url(redis_url), socket_connect_timeout=1, socket_timeout=1)
        try:
            if not client.ping():
                return 1
        finally:
            client.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(1)
