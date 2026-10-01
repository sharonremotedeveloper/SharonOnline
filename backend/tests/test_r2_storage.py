import pytest
from unittest.mock import patch, MagicMock
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

from apps.users.models import User
from apps.teachers.models import TeacherProfile
from apps.materials.models import Material
from apps.materials.serializers import MaterialListSerializer, MaterialDetailSerializer
from apps.teachers.serializers import TeacherListSerializer, TeacherDetailSerializer
from apps.admin_api.serializers import PendingTeacherApplicationSerializer
from apps.common.storage import MediaR2Storage, PrivateMediaR2Storage
from apps.common.r2_client import (
    get_r2_client,
    generate_presigned_download_url,
    generate_presigned_upload_url,
    get_public_r2_url
)


@pytest.mark.django_db
class TestCloudflareR2StorageIntegration:
    """
    Task 6.4: Cloudflare R2 Asset Storage Integration Test Suite ($0 Egress)
    """

    def test_media_r2_storage_configuration(self):
        """Verify MediaR2Storage uses strict S3v4, no ACLs, and public custom domain."""
        with override_settings(
            CLOUDFLARE_R2_ACCOUNT_ID="test-acc-123",
            CLOUDFLARE_R2_ACCESS_KEY_ID="test-key-id",
            CLOUDFLARE_R2_SECRET_ACCESS_KEY="test-secret-key",
            CLOUDFLARE_R2_BUCKET_NAME="esl-platform-assets",
            CLOUDFLARE_R2_PUBLIC_DOMAIN="https://assets.sharonesl.com"
        ):
            storage = MediaR2Storage()
            assert storage.default_acl is None, "R2 must not use S3 ACL headers"
            assert storage.signature_version == "s3v4"
            assert storage.querystring_auth is False
            assert storage.custom_domain == "assets.sharonesl.com"
            assert storage.endpoint_url == "https://test-acc-123.r2.cloudflarestorage.com"
            assert storage.bucket_name == "esl-platform-assets"

    def test_private_media_r2_storage_configuration(self):
        """Verify PrivateMediaR2Storage enables 15-minute presigned queries for private assets."""
        with override_settings(
            CLOUDFLARE_R2_ACCOUNT_ID="test-acc-123",
            CLOUDFLARE_R2_ACCESS_KEY_ID="test-key-id",
            CLOUDFLARE_R2_SECRET_ACCESS_KEY="test-secret-key",
            CLOUDFLARE_R2_BUCKET_NAME="esl-platform-assets"
        ):
            private_storage = PrivateMediaR2Storage()
            assert private_storage.default_acl is None
            assert private_storage.signature_version == "s3v4"
            assert private_storage.querystring_auth is True
            assert private_storage.querystring_expire == 900

    def test_local_fallback_when_r2_unconfigured(self):
        """Verify zero-drift fallback when R2 credentials are missing."""
        with override_settings(
            CLOUDFLARE_R2_ACCOUNT_ID=None,
            CLOUDFLARE_R2_ACCESS_KEY_ID=None,
            CLOUDFLARE_R2_SECRET_ACCESS_KEY=None,
            MEDIA_URL="/media/"
        ):
            client = get_r2_client()
            assert client is None

            download_url = generate_presigned_download_url("private/cert.pdf")
            assert download_url == "/media/private/cert.pdf"

            public_url = get_public_r2_url("materials/pdfs/lesson-1.pdf")
            assert "/media/materials/pdfs/lesson-1.pdf" in public_url

    def test_r2_presigned_urls_with_mock_client(self):
        """Verify boto3 S3 client generates compliant presigned URLs with custom parameters."""
        mock_boto_client = MagicMock()
        mock_boto_client.generate_presigned_url.side_effect = lambda op, Params, ExpiresIn: (
            f"https://test-acc.r2.cloudflarestorage.com/{Params['Bucket']}/{Params['Key']}?op={op}&exp={ExpiresIn}"
        )

        with patch("apps.common.r2_client.get_r2_client", return_value=mock_boto_client):
            with override_settings(
                CLOUDFLARE_R2_ACCOUNT_ID="test-acc",
                CLOUDFLARE_R2_ACCESS_KEY_ID="key",
                CLOUDFLARE_R2_SECRET_ACCESS_KEY="secret",
                CLOUDFLARE_R2_BUCKET_NAME="esl-platform-assets",
                CLOUDFLARE_R2_PUBLIC_DOMAIN="https://assets.sharonesl.com"
            ):
                # Test download presigned URL
                down_url = generate_presigned_download_url("private/vetting/certs/teacher-1.pdf", expires_in=600)
                assert "op=get_object" in down_url
                assert "exp=600" in down_url
                assert "esl-platform-assets/private/vetting/certs/teacher-1.pdf" in down_url

                # Test upload presigned URL
                up_res = generate_presigned_upload_url("teachers/audio/tutor-123_accent.mp3", content_type="audio/mpeg")
                assert "upload_url" in up_res
                assert "op=put_object" in up_res["upload_url"]

                # Test public CDN URL
                pub_url = get_public_r2_url("materials/pdfs/business-english-01.pdf")
                assert pub_url == "https://assets.sharonesl.com/materials/pdfs/business-english-01.pdf"

    def test_material_model_and_serializer_resolution(self):
        """Verify Material model resolves R2 PDF and audio URLs across list and detail serializers."""
        # Case 1: Direct URL fallback
        mat1 = Material.objects.create(
            title="Everyday Small Talk in Tokyo",
            slug="everyday-small-talk-tokyo",
            category=Material.Category.DAILY_NEWS,
            cefr_level=Material.CEFRLevel.B1,
            pdf_file_url="https://assets.sharonesl.com/materials/pdfs/everyday-small-talk.pdf",
            audio_snippet_url="https://assets.sharonesl.com/materials/audio/everyday-small-talk.mp3"
        )
        assert mat1.resolved_pdf_url == "https://assets.sharonesl.com/materials/pdfs/everyday-small-talk.pdf"
        assert mat1.resolved_audio_url == "https://assets.sharonesl.com/materials/audio/everyday-small-talk.mp3"

        serializer1 = MaterialListSerializer(mat1)
        assert serializer1.data['pdf_file_url'] == "https://assets.sharonesl.com/materials/pdfs/everyday-small-talk.pdf"
        assert serializer1.data['audio_snippet_url'] == "https://assets.sharonesl.com/materials/audio/everyday-small-talk.mp3"

        # Case 2: Uploaded file override
        uploaded_pdf = SimpleUploadedFile("lesson_worksheet.pdf", b"%PDF-1.4 dummy binary content", content_type="application/pdf")
        mat2 = Material.objects.create(
            title="Business Negotiations in London",
            slug="business-negotiations-london",
            category=Material.Category.BUSINESS,
            cefr_level=Material.CEFRLevel.C1,
            pdf_file=uploaded_pdf
        )
        assert "lesson_worksheet" in mat2.resolved_pdf_url
        serializer2 = MaterialDetailSerializer(mat2)
        assert "lesson_worksheet" in serializer2.data['pdf_file_url']

    def test_teacher_profile_model_and_serializer_resolution(self):
        """Verify TeacherProfile resolves avatar, accent audio, and TEFL certificate URLs."""
        user = User.objects.create_user(
            username="sharon_tutor",
            email="sharon@example.com",
            role="teacher",
            first_name="Sharon",
            last_name="Tutor",
            country="ZA",
            timezone="Africa/Johannesburg"
        )

        uploaded_audio = SimpleUploadedFile("intro_accent.mp3", b"ID3 fake audio bytes", content_type="audio/mpeg")
        teacher = TeacherProfile.objects.create(
            user=user,
            accent=TeacherProfile.Accent.SOUTH_AFRICAN,
            avatar_url="https://assets.sharonesl.com/teachers/avatars/sharon.jpg",
            intro_audio_file=uploaded_audio,
            tefl_certificate_url="https://assets.sharonesl.com/private/vetting/certs/sharon_tefl.pdf",
            is_verified=True
        )

        assert teacher.resolved_avatar_url == "https://assets.sharonesl.com/teachers/avatars/sharon.jpg"
        assert "intro_accent" in teacher.resolved_intro_audio_url
        assert teacher.resolved_tefl_certificate_url == "https://assets.sharonesl.com/private/vetting/certs/sharon_tefl.pdf"

        # Check TeacherListSerializer
        list_data = TeacherListSerializer(teacher).data
        assert list_data['avatar_url'] == "https://assets.sharonesl.com/teachers/avatars/sharon.jpg"
        assert "intro_accent" in list_data['intro_audio_url']

        # Check PendingTeacherApplicationSerializer
        app_data = PendingTeacherApplicationSerializer(teacher).data
        assert app_data['tefl_certificate_url'] == "https://assets.sharonesl.com/private/vetting/certs/sharon_tefl.pdf"
        assert app_data['status'] == "approved"

    def test_r2_presigned_url_api_endpoint_rbac(self):
        """Verify POST /api/v1/integrations/storage/presigned-url/ and /r2/presigned-url/ enforce auth, path traversal, and RBAC."""
        client = APIClient()

        # Unauthenticated request
        res = client.post('/api/v1/integrations/storage/presigned-url/', {'key': 'test.pdf', 'action': 'upload'})
        assert res.status_code == 401

        # Student user
        student = User.objects.create_user(username="test_student", email="student@test.com", role="student")
        teacher_user = User.objects.create_user(username="tutor_bob", email="bob@test.com", role="teacher")
        client.force_authenticate(user=student)

        # Path traversal attack defense
        res_traversal = client.post('/api/v1/integrations/storage/presigned-url/', {
            'action': 'upload',
            'key': f'../secret.txt'
        })
        assert res_traversal.status_code == 400

        # Student trying to upload to unauthorized teacher prefix -> 403 Forbidden
        res_forbidden = client.post('/api/v1/integrations/storage/presigned-url/', {
            'action': 'upload',
            'key': 'teachers/audio/unauthorized_upload.mp3'
        })
        assert res_forbidden.status_code == 403

        # Student uploading to own avatar namespace -> 200 OK
        res_ok = client.post('/api/v1/integrations/storage/presigned-url/', {
            'action': 'upload',
            'key': f'students/avatars/{student.id}/photo.jpg',
            'content_type': 'image/jpeg'
        })
        assert res_ok.status_code == 200
        assert 'upload_url' in res_ok.data
        assert 'public_cdn_url' in res_ok.data

        # Student attempting to download teacher private TEFL cert -> 403 Forbidden
        res_leak = client.post('/api/v1/integrations/storage/presigned-url/', {
            'action': 'download',
            'key': f'private/vetting/certificates/{teacher_user.id}/celta_cert.pdf'
        })
        assert res_leak.status_code == 403

        # Teacher requesting own private vetting cert download -> 200 OK
        client.force_authenticate(user=teacher_user)
        res_own_cert = client.post('/api/v1/integrations/r2/presigned-url/', {
            'action': 'download',
            'key': f'private/vetting/certificates/{teacher_user.id}/celta_cert.pdf'
        })
        assert res_own_cert.status_code == 200
        assert 'download_url' in res_own_cert.data

        # Admin staff user -> full access to any prefix (upload & private download)
        admin = User.objects.create_superuser(username="admin_user", email="admin@test.com", role="admin")
        client.force_authenticate(user=admin)

        res_admin_upload = client.post('/api/v1/integrations/storage/presigned-url/', {
            'action': 'upload',
            'key': 'materials/pdfs/brand-new-lesson.pdf',
            'content_type': 'application/pdf'
        })
        assert res_admin_upload.status_code == 200
        assert 'upload_url' in res_admin_upload.data

        res_admin_download = client.post('/api/v1/integrations/storage/presigned-url/', {
            'action': 'download',
            'key': f'private/vetting/certificates/{teacher_user.id}/celta_cert.pdf'
        })
        assert res_admin_download.status_code == 200
        assert 'download_url' in res_admin_download.data

