from typing import Optional
from rest_framework import serializers
from .models import Booking, LessonMemo
from apps.teachers.models import TeacherProfile
from apps.materials.models import Material
from apps.teachers.serializers import TeacherListSerializer
from apps.users.serializers import UserSerializer
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from django.conf import settings
from .services.holds import hold_expires_at
from django.utils.dateparse import parse_datetime

class LessonMemoSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonMemo
        fields = ('id', 'booking', 'teacher', 'student', 'feedback_text', 'vocabulary_words', 'pronunciation_notes',
                  'grammar_notes', 'homework', 'submitted_at')
        read_only_fields = ('id', 'booking', 'teacher', 'student', 'submitted_at')

MAX_NOTE_LENGTH = 5000
MAX_VOCAB_WORDS = 30
VOCAB_LIMITS = {'word': 128, 'definition': 1000, 'phonetic': 128, 'part_of_speech': 64}  # word/phonetic/pos mirror StudentFlashcard columns


class LessonMemoInputSerializer(serializers.Serializer):
    """
    What a tutor may submit after a lesson. Unknown keys (e.g. the UI's `booking_id`, `next_steps`) are ignored.
    (DRF's CharField already rejects NUL characters - PostgreSQL cannot store them; the vocabulary items are checked by hand.)
    """
    feedback_text = serializers.CharField(max_length=MAX_NOTE_LENGTH)
    vocabulary_words = serializers.ListField(child=serializers.JSONField(), required=False, default=list, max_length=MAX_VOCAB_WORDS)
    pronunciation_notes = serializers.CharField(max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True, default='')
    grammar_notes = serializers.CharField(max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True, default='')
    homework = serializers.CharField(max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True, default='')

    def validate_vocabulary_words(self, items):
        """Normalise to [{word, definition, phonetic, part_of_speech}], one entry per word (case-insensitive)."""
        cleaned, seen = [], set()
        for n, item in enumerate(items, start=1):
            entry = {'word': item} if isinstance(item, str) else item
            if not isinstance(entry, dict):
                raise serializers.ValidationError(f'Item {n}: expected a word or an object with a "word".')
            fields = {}
            for key, limit in VOCAB_LIMITS.items():
                value = entry.get(key, '')
                value = '' if value is None else value
                if not isinstance(value, str):
                    raise serializers.ValidationError(f'Item {n}: "{key}" must be text.')
                value = value.strip()
                if len(value) > limit:
                    raise serializers.ValidationError(f'Item {n}: "{key}" is longer than {limit} characters.')
                if '\x00' in value:
                    raise serializers.ValidationError(f'Item {n}: "{key}" contains a null character.')
                fields[key] = value
            if not fields['word']:
                raise serializers.ValidationError(f'Item {n}: "word" is required.')
            if fields['word'].casefold() in seen:
                continue
            seen.add(fields['word'].casefold())
            cleaned.append(fields)
        return cleaned


class BookingStudentSerializer(serializers.Serializer):
    """Minimal student view embedded in a booking. Contact details are only for the student themselves/staff."""
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()
    first_name = serializers.CharField()
    timezone = serializers.CharField()
    country = serializers.CharField()

    def get_full_name(self, obj) -> str:
        return obj.get_full_name() or obj.username

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        viewer = getattr(request, 'user', None)
        if viewer is not None and viewer.is_authenticated and (viewer.id == instance.id or viewer.is_staff or getattr(viewer, 'role', '') == 'admin'):
            data['email'] = instance.email
        return data


class BookingDetailSerializer(serializers.ModelSerializer):
    teacher = TeacherListSerializer(read_only=True)
    student = BookingStudentSerializer(read_only=True)
    memo = LessonMemoSerializer(read_only=True)
    zoom_url = serializers.SerializerMethodField()
    zoom_join_url = serializers.SerializerMethodField()
    zoom_start_url = serializers.SerializerMethodField()
    booking_reference = serializers.SerializerMethodField()
    price_usd = serializers.SerializerMethodField()
    price_zar = serializers.SerializerMethodField()
    lock_expires_at = serializers.SerializerMethodField()
    material_slug = serializers.SerializerMethodField()
    material_title = serializers.SerializerMethodField()
    local_date = serializers.SerializerMethodField()
    local_start_time = serializers.SerializerMethodField()
    local_end_time = serializers.SerializerMethodField()
    viewer_timezone = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = (
            'id', 'booking_reference', 'teacher', 'student', 'material', 'material_slug', 'material_title', 'status',
            'start_time_utc', 'end_time_utc', 'local_date', 'local_start_time', 'local_end_time', 'viewer_timezone',
            'price_usd', 'price_zar', 'lock_expires_at',
            'zoom_url', 'zoom_join_url', 'zoom_start_url', 'zoom_meeting_id', 'zoom_password',
            'student_rating', 'student_review', 'memo', 'created_at'
        )

    def _viewer(self):
        request = self.context.get('request')
        return getattr(request, 'user', None) if request else None

    def _is_host(self, obj):
        viewer = self._viewer()
        return bool(viewer and viewer.is_authenticated and viewer == obj.teacher.user)

    def get_zoom_url(self, obj) -> str:
        viewer = self._viewer()
        if not viewer or not viewer.is_authenticated:
            return ""
        # Return host start URL for the assigned teacher, join URL for student
        if self._is_host(obj):
            return obj.zoom_start_url or obj.zoom_join_url
        return obj.zoom_join_url

    def get_zoom_join_url(self, obj) -> str:
        return obj.zoom_join_url if self._viewer() and self._viewer().is_authenticated else ""

    def get_zoom_start_url(self, obj) -> str:
        # The host link grants control of the meeting: ONLY the booking's own tutor ever receives it.
        return obj.zoom_start_url if self._is_host(obj) else ""

    def get_booking_reference(self, obj) -> str:
        return f"BK-{str(obj.id).split('-')[0].upper()}"

    def _price_usd(self, obj):
        return Decimal(str(obj.teacher.price_per_25min_usd)).quantize(Decimal('0.01'), ROUND_HALF_UP)

    def get_price_usd(self, obj) -> float:
        return float(self._price_usd(obj))

    def get_price_zar(self, obj) -> float:
        return float((self._price_usd(obj) * Decimal(str(settings.ZAR_PER_USD))).quantize(Decimal('0.01'), ROUND_HALF_UP))

    def get_lock_expires_at(self, obj) -> Optional[str]:
        if obj.status != Booking.Status.PENDING_PAYMENT:
            return None
        return hold_expires_at(obj).isoformat()

    def get_material_slug(self, obj) -> Optional[str]:
        return obj.material.slug if obj.material_id else None

    def get_material_title(self, obj) -> Optional[str]:
        return obj.material.title if obj.material_id else None

    def _viewer_tz(self):
        request = self.context.get('request')
        name = (request.query_params.get('tz') if request else None) or getattr(self._viewer(), 'timezone', None) or 'UTC'
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            return ZoneInfo('UTC')

    def get_viewer_timezone(self, obj) -> str:
        return self._viewer_tz().key

    def get_local_date(self, obj) -> str:
        return obj.start_time_utc.astimezone(self._viewer_tz()).strftime("%Y-%m-%d")

    def get_local_start_time(self, obj) -> str:
        return obj.start_time_utc.astimezone(self._viewer_tz()).strftime("%H:%M")

    def get_local_end_time(self, obj) -> str:
        return obj.end_time_utc.astimezone(self._viewer_tz()).strftime("%H:%M")

class ReserveSlotRequestSerializer(serializers.Serializer):
    teacher_id = serializers.UUIDField(required=True)
    start_time_utc = serializers.DateTimeField(required=True)

class BookingCreateSerializer(serializers.ModelSerializer):
    teacher_id = serializers.UUIDField(write_only=True)
    material_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Booking
        fields = ('id', 'teacher_id', 'material_id', 'start_time_utc', 'status')
        read_only_fields = ('id', 'status')

    def create(self, validated_data):
        teacher_id = validated_data.pop('teacher_id')
        material_id = validated_data.pop('material_id', None)
        start_time_utc = validated_data['start_time_utc']
        end_time_utc = start_time_utc + timedelta(minutes=25)

        teacher = TeacherProfile.objects.get(id=teacher_id)
        material = Material.objects.get(id=material_id) if material_id else None
        student = self.context['request'].user

        booking = Booking.objects.create(
            teacher=teacher,
            student=student,
            material=material,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
            status=Booking.Status.PENDING_PAYMENT
        )
        return booking

class ReviewSubmitSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5, required=True)
    review = serializers.CharField(required=False, allow_blank=True)
