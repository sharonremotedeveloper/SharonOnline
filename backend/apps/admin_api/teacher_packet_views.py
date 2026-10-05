"""
GET /api/v1/admin/teachers/<id>/review-packet/ (slice T4a): everything a reviewer needs on one tutor, staff only.

Upload fingerprints (kind, etag, type, size) but never storage keys or URLs: documents open only through the audited
download endpoint. The rubric criteria and minimum come from `teachers/rubric.py`. Scores appear only here, never to the tutor.
"""
from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from apps.admin_api.teacher_review_views import _ERROR, _StaffThrottled
from apps.teachers import rubric as rubric_rules
from apps.teachers.models import TeacherApplication, TeacherAsset, TeacherProfile, TeacherStatusChange

HISTORY_LIMIT = 50


class PacketAssetSerializer(serializers.Serializer):
    kind = serializers.CharField()
    etag = serializers.CharField(help_text='Send these back in `reviewed_assets` when approving.')
    content_type = serializers.CharField()
    size_bytes = serializers.IntegerField()
    uploaded_at = serializers.DateTimeField()


class PacketHistorySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    from_status = serializers.CharField(allow_blank=True)
    to_status = serializers.CharField()
    actor = serializers.CharField()
    reason = serializers.CharField(allow_blank=True)
    scores = serializers.DictField(child=serializers.IntegerField(), allow_null=True)
    requested_changes = serializers.ListField(child=serializers.CharField())
    created_at = serializers.DateTimeField()


class PacketApplicationSerializer(serializers.Serializer):
    speed_test_download_mbps = serializers.DecimalField(max_digits=7, decimal_places=1, allow_null=True)
    speed_test_upload_mbps = serializers.DecimalField(max_digits=7, decimal_places=1, allow_null=True)
    speed_test_at = serializers.DateTimeField(allow_null=True)
    power_backup_confirmed = serializers.BooleanField()
    declaration_accepted_at = serializers.DateTimeField(allow_null=True)
    submitted_at = serializers.DateTimeField(allow_null=True)


class ReviewPacketSerializer(serializers.Serializer):
    teacher_id = serializers.UUIDField()
    full_name = serializers.CharField()
    status = serializers.CharField()
    headline = serializers.CharField(allow_blank=True)
    bio = serializers.CharField(allow_blank=True)
    accent = serializers.CharField(allow_blank=True)
    specialties = serializers.ListField(child=serializers.CharField())
    sla_strikes = serializers.IntegerField()
    criteria = serializers.ListField(child=serializers.CharField(), help_text='The rubric criteria, in order.')
    min_score = serializers.IntegerField(help_text='Approval needs every criterion at or above this score.')
    required_asset_kinds = serializers.ListField(child=serializers.CharField())
    assets = PacketAssetSerializer(many=True)
    history = PacketHistorySerializer(many=True)
    application = PacketApplicationSerializer(allow_null=True, help_text='What the tutor reported in the funnel (T5a).')


@extend_schema(responses={200: ReviewPacketSerializer, 404: _ERROR},
               description='Reviewer packet for one tutor (staff only). Scores are never shown to the tutor.')
class TeacherReviewPacketView(_StaffThrottled):
    def get(self, request, pk):
        teacher = TeacherProfile.objects.select_related('user').filter(pk=pk).first()
        if teacher is None:
            return Response({'error': 'Tutor not found.', 'code': 'not_found'}, status=404)
        assets = TeacherAsset.objects.filter(teacher=teacher, replaced_at__isnull=True).order_by('kind')
        history = TeacherStatusChange.objects.filter(teacher=teacher).order_by('-created_at')[:HISTORY_LIMIT]
        app = TeacherApplication.objects.filter(teacher=teacher).first()
        return Response(ReviewPacketSerializer({
            'application': None if app is None else {
                'speed_test_download_mbps': app.speed_test_download_mbps, 'speed_test_upload_mbps': app.speed_test_upload_mbps,
                'speed_test_at': app.speed_test_at, 'power_backup_confirmed': app.power_backup_confirmed_at is not None,
                'declaration_accepted_at': app.declaration_accepted_at, 'submitted_at': app.submitted_at},
            'teacher_id': teacher.pk, 'full_name': teacher.user.get_full_name() or teacher.user.username,
            'status': teacher.status, 'headline': teacher.headline, 'bio': teacher.bio, 'accent': teacher.accent,
            'specialties': teacher.specialties or [], 'sla_strikes': teacher.sla_strikes,
            'criteria': list(rubric_rules.CRITERIA), 'min_score': rubric_rules.min_score(),
            'required_asset_kinds': list(getattr(settings, 'VETTING_REQUIRED_ASSET_KINDS', ())),
            'assets': [{'kind': a.kind, 'etag': a.etag, 'content_type': a.content_type, 'size_bytes': a.size_bytes,
                        'uploaded_at': a.created_at} for a in assets],
            'history': [{'id': c.id, 'from_status': c.from_status, 'to_status': c.to_status, 'actor': c.actor,
                         'reason': c.reason, 'scores': (c.rubric or {}).get('scores'),
                         'requested_changes': (c.rubric or {}).get('requested_changes', []),
                         'created_at': c.created_at} for c in history],
        }).data)
