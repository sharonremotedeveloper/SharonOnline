"""
T3b: quarantine -> verified material asset (PDF worksheet or audio clip), the admin twin of `teachers/assets.py`.

The admin uploads to the private quarantine prefix `incoming/{admin id}/`; this commit checks the object is still the one
whose ETag the admin saw, that its bytes really are the declared format, then copies it to a random permanent key in the
public bucket and removes the quarantine copy once the database change has committed.
"""
import logging
import uuid

from botocore.exceptions import ClientError
from django.db import transaction

from apps.common import r2_client
from apps.common.upload_policy import MB

from .models import Material

logger = logging.getLogger(__name__)

PDF, AUDIO = 'pdf', 'audio'
KINDS = (PDF, AUDIO)
MAX_BYTES = {PDF: 25 * MB, AUDIO: 25 * MB}

# declared content type -> (file extension, which kind it may be attached as)
CONTENT_TYPES = {
    'application/pdf': ('.pdf', PDF),
    'audio/mpeg': ('.mp3', AUDIO),
    'audio/ogg': ('.ogg', AUDIO),
    'audio/wav': ('.wav', AUDIO),
}
_FIELDS = {PDF: 'pdf_file', AUDIO: 'audio_snippet_file'}


class AssetRejected(ValueError):
    """The upload is not acceptable (the admin can fix it): a 400, never a 500."""


def bytes_match(content_type: str, prefix: bytes) -> bool:
    """Magic bytes of the declared type (not just any known type: an OGG labelled audio/mpeg is rejected)."""
    if content_type == 'application/pdf':
        return prefix.startswith(b'%PDF-')
    if content_type == 'audio/mpeg':
        return prefix.startswith(b'ID3') or (len(prefix) >= 2 and prefix[0] == 0xFF and prefix[1] & 0xE0 == 0xE0)
    if content_type == 'audio/ogg':
        return prefix.startswith(b'OggS')
    if content_type == 'audio/wav':
        return len(prefix) >= 12 and prefix[:4] == b'RIFF' and prefix[8:12] == b'WAVE'
    return False


def _storage_error(exc: ClientError) -> AssetRejected:
    code = str(exc.response.get('Error', {}).get('Code', ''))
    if code in {'404', 'NoSuchKey', 'NotFound'}:
        return AssetRejected('The uploaded file was not found. Upload it again.')
    if code in {'412', 'PreconditionFailed'}:
        return AssetRejected('The uploaded file changed before it was committed.')
    raise exc


def _verify_quarantined(actor, kind: str, quarantine_key: str, expected_etag: str) -> tuple[str, str, str]:
    """Every check before anything is copied: (etag header as stored, content type, file extension)."""
    if kind not in KINDS:
        raise AssetRejected('Unsupported asset kind.')
    if '..' in quarantine_key or not quarantine_key.startswith(f'incoming/{actor.pk}/'):
        raise AssetRejected('The file is not in your upload quarantine.')
    try:
        metadata = r2_client.head_object(quarantine_key, private=True)
    except ClientError as exc:
        raise _storage_error(exc) from exc
    if metadata is None:
        raise RuntimeError('Asset storage is unavailable.')
    etag_header = str(metadata.get('ETag') or '')
    if expected_etag and etag_header.strip('"') != expected_etag.strip('"'):
        raise AssetRejected('The uploaded file changed before it was committed.')
    content_type = str(metadata.get('ContentType') or '').split(';', 1)[0].strip().lower()
    size = int(metadata.get('ContentLength') or 0)
    extension, allowed_kind = CONTENT_TYPES.get(content_type, ('', None))
    if allowed_kind != kind:
        raise AssetRejected(f'A {content_type or "file of unknown type"} cannot be attached as {kind}.')
    if not 0 < size <= MAX_BYTES[kind]:
        raise AssetRejected('The file is empty or larger than the allowed size.')
    try:
        prefix = r2_client.read_object_prefix(quarantine_key, etag=etag_header, private=True) or b''
    except ClientError as exc:
        raise _storage_error(exc) from exc
    if not bytes_match(content_type, prefix):
        raise AssetRejected('The file contents do not match its declared type.')
    return etag_header, content_type, extension


def commit_material_asset(material: Material, *, actor, kind: str, quarantine_key: str, expected_etag: str = ''):
    etag_header, content_type, extension = _verify_quarantined(actor, kind, quarantine_key, expected_etag)

    final_key = f'materials/{material.pk}/{kind}-{uuid.uuid4().hex}{extension}'
    try:
        r2_client.copy_object(quarantine_key, final_key, etag=etag_header, private=False, source_private=True)
    except ClientError as exc:
        raise _storage_error(exc) from exc
    try:
        with transaction.atomic():
            row = Material.objects.select_for_update().get(pk=material.pk)
            field = _FIELDS[kind]
            previous = getattr(row, field).name
            getattr(row, field).name = final_key
            row.save(update_fields=[field, 'updated_at'])
    except Exception:
        _delete_quietly(final_key, private=False)
        raise
    # Storage has no rollback: the quarantine copy (and the replaced object) go only once the change is durable.
    transaction.on_commit(lambda: _delete_quietly(quarantine_key, private=True))
    if previous and previous.startswith(f'materials/{material.pk}/'):
        transaction.on_commit(lambda: _delete_quietly(previous, private=False))
    material.refresh_from_db()
    return final_key, etag_header.strip('"'), content_type


def _delete_quietly(key: str, *, private: bool) -> None:
    """Cleanup of an object nobody references. A failure leaves an orphan (lifecycle rules reap quarantine), never a 500."""
    try:
        r2_client.delete_object(key, private=private)
    except Exception:
        logger.exception('Could not delete orphaned storage object %s', key)
