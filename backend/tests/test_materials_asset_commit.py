"""Slice T3b: an admin attaches a PDF worksheet or audio clip to a material through the quarantine commit."""
import pytest
from rest_framework.test import APIClient

from apps.materials.models import Material

pytestmark = pytest.mark.django_db

PDF = b'%PDF-1.7\n%worksheet bytes'
MP3 = b'ID3\x04\x00\x00\x00\x00\x00\x00audio'
OGG = b'OggS\x00\x02\x00\x00audio'
WAV = b'RIFF\x24\x00\x00\x00WAVEfmt '


@pytest.fixture
def buckets(settings, fake_r2):
    settings.CLOUDFLARE_R2_PRIVATE_BUCKET_NAME = 'private-assets'
    settings.CLOUDFLARE_R2_BUCKET_NAME = 'public-assets'
    return fake_r2


@pytest.fixture
def material(db):
    return Material.objects.create(title='Cafe talk', slug='cafe-talk', category='freetalk', cefr_level='A2')


def _url(material):
    return f'/api/v1/materials/{material.id}/assets/commit/'


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def _quarantine(buckets, admin, body, content_type, name='upload.bin'):
    key = f'incoming/{admin.id}/{name}'
    etag = buckets.put_object(Bucket='private-assets', Key=key, Body=body, ContentType=content_type)['ETag']
    return key, etag


def _commit(client, material, **payload):
    return client.post(_url(material), payload, format='json')


class TestCommit:
    def test_pdf_is_copied_to_permanent_storage_and_attached(self, admin_user, material, buckets,
                                                             django_capture_on_commit_callbacks):
        key, etag = _quarantine(buckets, admin_user, PDF, 'application/pdf')
        with django_capture_on_commit_callbacks(execute=True):
            response = _commit(_client(admin_user), material, kind='pdf', key=key, etag=etag)
        assert response.status_code == 200, response.content
        material.refresh_from_db()
        assert material.pdf_file.name.startswith(f'materials/{material.id}/')
        assert material.pdf_file.name.endswith('.pdf')
        assert buckets.objects[('public-assets', material.pdf_file.name)]['body'] == PDF
        assert ('private-assets', key) not in buckets.objects            # quarantine copy is removed after commit
        assert response.json()['key'] == material.pdf_file.name

    @pytest.mark.parametrize('body,content_type', [(MP3, 'audio/mpeg'), (OGG, 'audio/ogg'), (WAV, 'audio/wav')])
    def test_audio_formats_are_accepted(self, admin_user, material, buckets, body, content_type):
        key, etag = _quarantine(buckets, admin_user, body, content_type)
        response = _commit(_client(admin_user), material, kind='audio', key=key, etag=etag)
        assert response.status_code == 200, response.content
        material.refresh_from_db()
        assert material.audio_snippet_file.name.startswith(f'materials/{material.id}/')

    def test_replacing_an_asset_removes_the_previous_object(self, admin_user, material, buckets,
                                                            django_capture_on_commit_callbacks):
        client = _client(admin_user)
        first, etag1 = _quarantine(buckets, admin_user, PDF, 'application/pdf', 'a.pdf')
        with django_capture_on_commit_callbacks(execute=True):
            _commit(client, material, kind='pdf', key=first, etag=etag1)
        material.refresh_from_db()
        old_key = material.pdf_file.name
        second, etag2 = _quarantine(buckets, admin_user, PDF + b'v2', 'application/pdf', 'b.pdf')
        with django_capture_on_commit_callbacks(execute=True):
            _commit(client, material, kind='pdf', key=second, etag=etag2)
        material.refresh_from_db()
        assert material.pdf_file.name != old_key
        assert ('public-assets', old_key) not in buckets.objects


class TestRejections:
    def test_etag_mismatch_is_rejected_and_nothing_is_attached(self, admin_user, material, buckets):
        key, _etag = _quarantine(buckets, admin_user, PDF, 'application/pdf')
        response = _commit(_client(admin_user), material, kind='pdf', key=key, etag='"0000"')
        assert response.status_code == 400
        material.refresh_from_db()
        assert not material.pdf_file
        assert ('private-assets', key) in buckets.objects
        assert not [k for k in buckets.objects if k[0] == 'public-assets']

    def test_the_object_changing_after_the_etag_was_read_is_rejected(self, admin_user, material, buckets):
        key, etag = _quarantine(buckets, admin_user, PDF, 'application/pdf')
        buckets.put_object(Bucket='private-assets', Key=key, Body=PDF + b'swapped', ContentType='application/pdf')
        assert _commit(_client(admin_user), material, kind='pdf', key=key, etag=etag).status_code == 400

    @pytest.mark.parametrize('kind,body,content_type', [
        ('pdf', b'not really a pdf', 'application/pdf'),
        ('pdf', b'MZ\x90\x00 executable', 'application/pdf'),
        ('audio', b'plain text pretending', 'audio/mpeg'),
        ('audio', OGG, 'audio/mpeg'),            # declared type and bytes disagree
        ('audio', PDF, 'audio/wav'),
    ])
    def test_corrupted_or_mislabelled_magic_bytes_are_rejected(self, admin_user, material, buckets, kind, body, content_type):
        key, etag = _quarantine(buckets, admin_user, body, content_type)
        response = _commit(_client(admin_user), material, kind=kind, key=key, etag=etag)
        assert response.status_code == 400
        assert not [k for k in buckets.objects if k[0] == 'public-assets']

    def test_a_pdf_cannot_be_committed_as_audio_nor_audio_as_a_pdf(self, admin_user, material, buckets):
        key, etag = _quarantine(buckets, admin_user, PDF, 'application/pdf')
        assert _commit(_client(admin_user), material, kind='audio', key=key, etag=etag).status_code == 400
        key, etag = _quarantine(buckets, admin_user, MP3, 'audio/mpeg', 'b.mp3')
        assert _commit(_client(admin_user), material, kind='pdf', key=key, etag=etag).status_code == 400

    def test_a_key_outside_the_admins_own_quarantine_prefix_is_rejected(self, admin_user, teacher_user, material, buckets):
        key = f'incoming/{teacher_user.user_id}/x.pdf'
        etag = buckets.put_object(Bucket='private-assets', Key=key, Body=PDF, ContentType='application/pdf')['ETag']
        assert _commit(_client(admin_user), material, kind='pdf', key=key, etag=etag).status_code == 400
        assert _commit(_client(admin_user), material, kind='pdf', key='teachers/avatar/x.pdf', etag=etag).status_code == 400
        assert _commit(_client(admin_user), material, kind='pdf', key=f'incoming/{admin_user.id}/../x.pdf',
                       etag=etag).status_code == 400

    def test_a_missing_upload_is_a_client_error_not_a_500(self, admin_user, material, buckets):
        key = f'incoming/{admin_user.id}/never-uploaded.pdf'
        assert _commit(_client(admin_user), material, kind='pdf', key=key).status_code == 400

    def test_oversize_uploads_are_rejected(self, admin_user, material, buckets, settings):
        key, etag = _quarantine(buckets, admin_user, PDF + b'0' * 64, 'application/pdf')
        from apps.materials import assets
        assets_limit = assets.MAX_BYTES['pdf']
        assert assets_limit > 0
        original = assets.MAX_BYTES['pdf']
        assets.MAX_BYTES['pdf'] = 32
        try:
            assert _commit(_client(admin_user), material, kind='pdf', key=key, etag=etag).status_code == 400
        finally:
            assets.MAX_BYTES['pdf'] = original


class TestAccess:
    def test_only_admins_may_commit(self, student_user, teacher_user, material, buckets):
        for user in (student_user, teacher_user.user):
            assert _commit(_client(user), material, kind='pdf', key='incoming/x/y.pdf').status_code == 403
        assert APIClient().post(_url(material), {}, format='json').status_code == 401

    def test_unknown_material_is_404(self, admin_user, buckets):
        response = _client(admin_user).post('/api/v1/materials/00000000-0000-0000-0000-000000000000/assets/commit/',
                                            {'kind': 'pdf', 'key': f'incoming/{admin_user.id}/a.pdf'}, format='json')
        assert response.status_code == 404

    def test_invalid_kind_is_rejected(self, admin_user, material, buckets):
        assert _commit(_client(admin_user), material, kind='video', key=f'incoming/{admin_user.id}/a.mp4').status_code == 400

    def test_storage_outage_is_a_503_and_leaves_the_material_unchanged(self, admin_user, material, buckets, monkeypatch):
        key, etag = _quarantine(buckets, admin_user, PDF, 'application/pdf')
        from apps.common import r2_client

        def boom(*a, **k):
            raise RuntimeError('Cloudflare R2 is unavailable for head.')

        monkeypatch.setattr(r2_client, 'head_object', boom)
        assert _commit(_client(admin_user), material, kind='pdf', key=key, etag=etag).status_code == 503
        material.refresh_from_db()
        assert not material.pdf_file
