"""Production Redis URL normalization shared by Celery and Django cache."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_redis_url(redis_url: str) -> str:
    """Require an explicit TLS certificate policy for ``rediss://`` URLs."""

    if not redis_url.lower().startswith("rediss://"):
        return redis_url
    parts = urlsplit(redis_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["ssl_cert_reqs"] = "required"
    return urlunsplit(parts._replace(query=urlencode(query)))
