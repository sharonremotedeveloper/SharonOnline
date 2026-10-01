import os
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage

class MediaR2Storage(S3Boto3Storage):
    """
    Cloudflare R2 storage backend with $0 egress fees.
    Configured specifically for S3-compatible R2 storage:
    - No AWS ACLs (R2 does not support x-amz-acl headers)
    - s3v4 signature version
    - Direct custom domain mapping (CLOUDFLARE_R2_PUBLIC_DOMAIN) for zero egress public CDN delivery
    """
    default_acl = None
    file_overwrite = False
    signature_version = 's3v4'
    querystring_auth = False
    
    def __init__(self, *args, **kwargs):
        account_id = getattr(settings, 'CLOUDFLARE_R2_ACCOUNT_ID', None)
        if account_id:
            kwargs.setdefault('endpoint_url', f"https://{account_id}.r2.cloudflarestorage.com")
        
        access_key = getattr(settings, 'CLOUDFLARE_R2_ACCESS_KEY_ID', None)
        if access_key:
            kwargs.setdefault('access_key', access_key)
            
        secret_key = getattr(settings, 'CLOUDFLARE_R2_SECRET_ACCESS_KEY', None)
        if secret_key:
            kwargs.setdefault('secret_key', secret_key)
            
        bucket_name = getattr(settings, 'CLOUDFLARE_R2_BUCKET_NAME', None)
        if bucket_name:
            kwargs.setdefault('bucket_name', bucket_name)
            
        public_domain = getattr(settings, 'CLOUDFLARE_R2_PUBLIC_DOMAIN', None)
        if public_domain:
            domain = public_domain.replace('https://', '').replace('http://', '').rstrip('/')
            kwargs.setdefault('custom_domain', domain)
            
        super().__init__(*args, **kwargs)


class PrivateMediaR2Storage(S3Boto3Storage):
    """
    Secure Cloudflare R2 storage backend for private assets (e.g. TEFL certificates, passport/ID vetting files).
    Assets are not publicly accessible and require time-limited presigned URLs (querystring_auth=True).
    """
    default_acl = None
    file_overwrite = False
    signature_version = 's3v4'
    querystring_auth = True
    querystring_expire = 900  # 15 minutes TTL
    
    def __init__(self, *args, **kwargs):
        account_id = getattr(settings, 'CLOUDFLARE_R2_ACCOUNT_ID', None)
        if account_id:
            kwargs.setdefault('endpoint_url', f"https://{account_id}.r2.cloudflarestorage.com")
        
        access_key = getattr(settings, 'CLOUDFLARE_R2_ACCESS_KEY_ID', None)
        if access_key:
            kwargs.setdefault('access_key', access_key)
            
        secret_key = getattr(settings, 'CLOUDFLARE_R2_SECRET_ACCESS_KEY', None)
        if secret_key:
            kwargs.setdefault('secret_key', secret_key)
            
        bucket_name = getattr(settings, 'CLOUDFLARE_R2_BUCKET_NAME', None)
        if bucket_name:
            kwargs.setdefault('bucket_name', bucket_name)
            
        super().__init__(*args, **kwargs)
