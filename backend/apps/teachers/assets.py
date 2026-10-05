"""T3 quarantine -> verified tutor asset commits."""

import logging
import uuid
from functools import wraps
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common import r2_client
from apps.common.upload_policy import policy_for_key
from .models import PrivateAssetAccessAudit, TeacherAsset, TeacherProfile

logger = logging.getLogger(__name__)

MAGIC = {
    'image/jpeg': (b'\xff\xd8\xff',), 'image/png': (b'\x89PNG\r\n\x1a\n',),
    'image/webp': (b'RIFF',), 'application/pdf': (b'%PDF-',),
    'audio/mpeg': (b'ID3', b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'),
    'audio/mp4': (b'ftyp',), 'audio/wav': (b'RIFF',), 'audio/webm': (b'\x1a\x45\xdf\xa3',),
    'video/mp4': (b'ftyp',), 'video/webm': (b'\x1a\x45\xdf\xa3',),
}

KIND_TYPES = {
    TeacherAsset.Kind.AVATAR: {'image/jpeg', 'image/png', 'image/webp'},
    TeacherAsset.Kind.ACCENT_AUDIO: {'audio/mpeg', 'audio/mp4', 'audio/wav', 'audio/webm'},
    TeacherAsset.Kind.TEFL_CERTIFICATE: {'application/pdf', 'image/jpeg', 'image/png'},
    TeacherAsset.Kind.INTRO_VIDEO: {'video/mp4', 'video/webm'},
    TeacherAsset.Kind.IDENTITY_DOCUMENT: {'application/pdf', 'image/jpeg', 'image/png'},
}


def _matches(kind, content_type, prefix):
    if content_type not in KIND_TYPES[kind] or len(prefix) < 4:
        return False
    if content_type == 'image/webp':
        return len(prefix) >= 12 and prefix[:4] == b'RIFF' and prefix[8:12] == b'WEBP'
    if content_type == 'audio/wav':
        return len(prefix) >= 12 and prefix[:4] == b'RIFF' and prefix[8:12] == b'WAVE'
    if content_type in {'audio/mp4', 'video/mp4'}:
        return len(prefix) >= 8 and prefix[4:8] == b'ftyp'
    return any(prefix.startswith(magic) for magic in MAGIC[content_type])


def _private(kind):
    return kind in {TeacherAsset.Kind.TEFL_CERTIFICATE, TeacherAsset.Kind.IDENTITY_DOCUMENT}


def _cleanup_copied_objects_on_error(func):
    """Storage has no transaction rollback; remove committed copies if DB work fails."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        copied = []
        try:
            return func(*args, _copied_objects=copied, **kwargs)
        except Exception:
            for object_key, private in copied:
                try:
                    r2_client.delete_object(object_key, private=private)
                except Exception:
                    logger.exception('Failed to clean up copied tutor asset after database rollback.')
            raise
    return wrapped


@_cleanup_copied_objects_on_error
@transaction.atomic
def commit_asset(teacher, *, actor, kind, quarantine_key, expected_etag='', _copied_objects=None):  # noqa: C901 - ordered integrity gate
    if kind not in KIND_TYPES:
        raise ValueError('Unsupported asset kind.')
    if not quarantine_key.startswith(f'incoming/{teacher.user_id}/'):
        raise ValueError('Asset is not in the tutor quarantine prefix.')
    if teacher.status not in {TeacherProfile.Status.APPLIED, TeacherProfile.Status.CHANGES_REQUESTED,
                              TeacherProfile.Status.APPROVED}:
        raise ValueError('Assets cannot be submitted in the current tutor status.')

    private = _private(kind)
    local_mode = getattr(settings, 'DEBUG', False) or getattr(settings, 'ZOOM_SIMULATE_WITHOUT_CREDENTIALS', False)
    if private and not local_mode and not getattr(settings, 'CLOUDFLARE_R2_PRIVATE_BUCKET_NAME', ''):
        raise RuntimeError('A separate private R2 bucket is required for vetting assets.')
    metadata = r2_client.head_object(quarantine_key, private=True)
    if metadata is None:
        if not local_mode:
            raise RuntimeError('Private asset storage is unavailable.')
        metadata = {'ETag': expected_etag or 'local', 'ContentType': 'application/octet-stream', 'ContentLength': 0}
    etag_header = str(metadata.get('ETag', '') or '')
    etag = etag_header.strip('"')
    content_type = str(metadata.get('ContentType') or '').split(';', 1)[0].lower()
    size = int(metadata.get('ContentLength') or 0)
    if expected_etag and etag != expected_etag.strip('"'):
        raise ValueError('The uploaded asset changed before commit.')
    policy = policy_for_key('incoming/')
    if policy and size and (content_type not in policy[0] or size > policy[1]):
        raise ValueError('The uploaded asset violates the quarantine size or content-type policy.')
    prefix = r2_client.read_object_prefix(quarantine_key, etag=etag_header, private=True) or b''
    if metadata.get('ContentLength', 0) and not _matches(kind, content_type, prefix):
        raise ValueError('The uploaded bytes do not match the declared content type.')
    if not metadata.get('ContentLength', 0) and not local_mode:
        raise ValueError('Storage did not return object metadata.')

    same = TeacherAsset.objects.filter(teacher=teacher, kind=kind, etag=etag).first()
    if same:
        return same
    old = TeacherAsset.objects.filter(teacher=teacher, kind=kind, replaced_at__isnull=True).first()
    suffix = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'application/pdf': '.pdf'}.get(content_type, '')
    final_key = f'private/vetting/{teacher.user_id}/{kind}/{uuid.uuid4().hex}{suffix}' if private else f'teachers/{kind}/{teacher.user_id}/{uuid.uuid4().hex}{suffix}'
    if metadata.get('ContentLength'):
        r2_client.copy_object(quarantine_key, final_key, etag=etag_header, private=private, source_private=True)
        _copied_objects.append((final_key, private))
        # Do not delete the quarantine object until the DB transaction commits. If it rolls back,
        # the cleanup wrapper removes the copied final object and leaves the upload retryable.
        transaction.on_commit(lambda: r2_client.delete_object(quarantine_key, private=True))

    if old:
        old.replaced_at = timezone.now()
        old.save(update_fields=['replaced_at'])
    asset = TeacherAsset.objects.create(teacher=teacher, kind=kind, object_key=final_key,
                                        quarantine_key=quarantine_key, etag=etag,
                                        content_type=content_type or 'application/octet-stream', size_bytes=size)
    _apply_profile_asset(teacher, asset)
    if teacher.status == TeacherProfile.Status.APPROVED:
        from .profile import revet_after_vetted_change
        revet_after_vetted_change(teacher, actor=actor, fields=[kind])
    return asset


def _apply_profile_asset(teacher, asset):
    field = {
        TeacherAsset.Kind.AVATAR: 'avatar_url',
        TeacherAsset.Kind.ACCENT_AUDIO: 'intro_audio_url',
        TeacherAsset.Kind.INTRO_VIDEO: 'intro_video_url',
        # Private vetting documents are only exposed through the audited
        # download endpoint; never publish an expiring URL in the profile.
        TeacherAsset.Kind.TEFL_CERTIFICATE: None,
        TeacherAsset.Kind.IDENTITY_DOCUMENT: None,
    }[asset.kind]
    if field:
        value = r2_client.generate_presigned_download_url(asset.object_key, private=_private(asset.kind)) if _private(asset.kind) else r2_client.get_public_r2_url(asset.object_key)
        setattr(teacher, field, value)
        teacher.save(update_fields=[field, 'updated_at'])


def audit_private_access(actor, teacher, object_key):
    return PrivateAssetAccessAudit.objects.create(actor=actor, teacher=teacher, object_key=object_key)
