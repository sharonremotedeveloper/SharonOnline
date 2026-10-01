"""Per-prefix upload policy for presigned R2 uploads (content-type allowlist + size cap)."""
MB = 1024 * 1024
IMAGES = frozenset({'image/jpeg', 'image/png', 'image/webp'})
AUDIO = frozenset({'audio/mpeg', 'audio/mp4', 'audio/wav', 'audio/webm'})
DOCS = frozenset({'application/pdf'})

# (key prefix, allowed content types, max bytes) - first match wins
UPLOAD_POLICIES = (
    ('teachers/avatars/', IMAGES, 5 * MB),
    ('students/avatars/', IMAGES, 5 * MB),
    ('teachers/audio/', AUDIO, 10 * MB),
    ('private/vetting/', DOCS | {'image/jpeg', 'image/png'}, 10 * MB),
    ('materials/', DOCS | AUDIO | IMAGES, 25 * MB),
)

MIN_EXPIRES, MAX_EXPIRES = 60, 900


def policy_for_key(key: str):
    for prefix, types, max_bytes in UPLOAD_POLICIES:
        if key.startswith(prefix):
            return types, max_bytes
    return None


def clamp_expires(value, default=900) -> int:
    try:
        value = int(value)
    except (ValueError, TypeError):
        return default
    return max(MIN_EXPIRES, min(value, MAX_EXPIRES))
