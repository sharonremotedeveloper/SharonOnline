import boto3
from botocore.config import Config
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def get_r2_client():
    """
    Returns an initialized S3/R2 boto3 client configured with Cloudflare R2 endpoint and credentials.
    Returns None if credentials are not configured.
    """
    account_id = getattr(settings, 'CLOUDFLARE_R2_ACCOUNT_ID', None)
    access_key = getattr(settings, 'CLOUDFLARE_R2_ACCESS_KEY_ID', None)
    secret_key = getattr(settings, 'CLOUDFLARE_R2_SECRET_ACCESS_KEY', None)

    if not (account_id and access_key and secret_key):
        return None

    return boto3.client(
        's3',
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name='auto',
        config=Config(signature_version='s3v4')
    )

def _bucket(private=False):
    if private:
        return getattr(settings, 'CLOUDFLARE_R2_PRIVATE_BUCKET_NAME', '') or getattr(settings, 'CLOUDFLARE_R2_BUCKET_NAME', 'esl-platform-assets')
    return getattr(settings, 'CLOUDFLARE_R2_BUCKET_NAME', 'esl-platform-assets')


def _client_or_fail(operation):
    client = get_r2_client()
    local_mode = getattr(settings, 'DEBUG', False) or getattr(settings, 'SIMULATE_WITHOUT_CREDENTIALS', False)
    if client is None and not local_mode:
        raise RuntimeError(f'Cloudflare R2 is unavailable for {operation}.')
    return client


def generate_presigned_download_url(object_key: str, expires_in: int = 900, *, private=False) -> str:
    """
    Generates a secure, time-limited GET presigned URL for private vetting assets
    (e.g. TEFL certificates, identity documents).
    Defaults to 15-minute (900s) expiry.
    Falls back gracefully to local media URL if R2 is not active.
    """
    client = _client_or_fail('download')
    bucket_name = _bucket(private)

    if not client:
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        return f"{media_url.rstrip('/')}/{object_key.lstrip('/')}"

    try:
        url = client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': object_key
            },
            ExpiresIn=expires_in
        )
        return url
    except Exception as e:
        logger.error(f"Failed to generate presigned R2 download URL for {object_key}: {e}")
        if not (getattr(settings, 'DEBUG', False) or getattr(settings, 'SIMULATE_WITHOUT_CREDENTIALS', False)):
            raise RuntimeError('Cloudflare R2 refused the download URL.') from e
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        return f"{media_url.rstrip('/')}/{object_key.lstrip('/')}"

def generate_presigned_upload_url(object_key: str, content_type: str = None, expires_in: int = 900, content_length: int = None, *, private=False) -> dict:
    """
    Generates a direct PUT presigned upload URL enabling client-side direct uploads
    to Cloudflare R2 with zero backend compute overhead.
    """
    client = _client_or_fail('upload')
    bucket_name = _bucket(private)

    if not client:
        return {
            'upload_url': f"/api/v1/upload/{object_key}",
            'fields': {},
            'expires_in': expires_in
        }

    params = {
        'Bucket': bucket_name,
        'Key': object_key
    }
    if content_type:
        params['ContentType'] = content_type
    if content_length is not None:
        # Signed header: R2 rejects any upload whose Content-Length differs, enforcing the size cap.
        params['ContentLength'] = int(content_length)

    try:
        url = client.generate_presigned_url(
            'put_object',
            Params=params,
            ExpiresIn=expires_in
        )
        return {
            'upload_url': url,
            'key': object_key,
            'expires_in': expires_in
        }
    except Exception as e:
        logger.error(f"Failed to generate presigned R2 upload URL for {object_key}: {e}")
        if not (getattr(settings, 'DEBUG', False) or getattr(settings, 'SIMULATE_WITHOUT_CREDENTIALS', False)):
            raise RuntimeError('Cloudflare R2 refused the upload URL.') from e
        return {
            'upload_url': f"/api/v1/upload/{object_key}",
            'error': str(e)
        }

def get_public_r2_url(object_key: str) -> str:
    """
    Returns the public CDN URL for public assets (curriculum PDFs, teacher accent snippets, avatars).
    Falls back to MEDIA_URL when R2 credentials are not configured.
    """
    account_id = getattr(settings, 'CLOUDFLARE_R2_ACCOUNT_ID', None)
    access_key = getattr(settings, 'CLOUDFLARE_R2_ACCESS_KEY_ID', None)
    public_domain = getattr(settings, 'CLOUDFLARE_R2_PUBLIC_DOMAIN', None)

    if account_id and access_key and public_domain:
        domain = public_domain.rstrip('/')
        if not domain.startswith('http://') and not domain.startswith('https://'):
            domain = f"https://{domain}"
        return f"{domain}/{object_key.lstrip('/')}"
    media_url = getattr(settings, 'MEDIA_URL', '/media/')
    return f"{media_url.rstrip('/')}/{object_key.lstrip('/')}"


def head_object(object_key: str, *, private=False):
    client = _client_or_fail('head')
    if not client:
        return None
    return client.head_object(Bucket=_bucket(private), Key=object_key)


def read_object_prefix(object_key: str, *, etag: str, private=False, size=64):
    client = _client_or_fail('read')
    if not client:
        return None
    response = client.get_object(Bucket=_bucket(private), Key=object_key, Range=f'bytes=0-{size - 1}', IfMatch=etag)
    body = response['Body']
    return body.read(size)


def copy_object(source_key: str, destination_key: str, *, etag: str, private=False, source_private=None):
    client = _client_or_fail('copy')
    if not client:
        return None
    if source_private is None:
        source_private = private
    return client.copy_object(Bucket=_bucket(private), Key=destination_key,
                              CopySource={'Bucket': _bucket(source_private), 'Key': source_key},
                              CopySourceIfMatch=etag)


def delete_object(object_key: str, *, private=False):
    client = _client_or_fail('delete')
    if not client:
        return None
    return client.delete_object(Bucket=_bucket(private), Key=object_key)


