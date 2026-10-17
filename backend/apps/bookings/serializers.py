from typing import Optional
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from apps.common.contact_guard import validate_no_off_platform_contact
from .models import Booking, LessonMemo
from .services.reviews import REVIEW_TAGS
from apps.teachers.serializers import TeacherListSerializer
from apps.users.serializers import UserSerializer
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from django.conf import settings
from .services.holds import hold_expires_at
from apps.payments.services.pricing import lesson_price
from apps.common.money import money_str
from django.utils.dateparse import parse_datetime

MAX_NOTE_LENGTH = 5000
MAX_VOCAB_WORDS = 30
VOCAB_LIMITS = {'word': 128, 'definition': 1000, 'phonetic': 128, 'part_of_speech': 64}  # word/phonetic/pos mirror StudentFlashcard columns


class LessonMemoSerializer(serializers.ModelSerializer):
    feedback_text = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=False,
        validators=[validate_no_off_platform_contact]
    )
    general_feedback = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=False,
        validators=[validate_no_off_platform_contact]
    )
    pronunciation_notes = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True, default='',
        validators=[validate_no_off_platform_contact]
    )
    grammar_notes = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True, default='',
        validators=[validate_no_off_platform_contact]
    )
    grammar_corrections = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True,
        validators=[validate_no_off_platform_contact]
    )
    homework = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True, default='',
        validators=[validate_no_off_platform_contact]
    )
    homework_assigned = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True,
        validators=[validate_no_off_platform_contact]
    )
    next_lesson_recommendation = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True, default='',
        validators=[validate_no_off_platform_contact]
    )

    class Meta:
        model = LessonMemo
        fields = (
            'id', 'booking', 'teacher', 'student', 'feedback_text', 'general_feedback',
            'vocabulary_words', 'pronunciation_notes', 'grammar_notes', 'grammar_corrections',
            'homework', 'homework_assigned', 'next_lesson_recommendation', 'submitted_at'
        )
        read_only_fields = ('id', 'booking', 'teacher', 'student', 'submitted_at')

    def validate_feedback_text(self, val):
        if val: validate_no_off_platform_contact(val)
        return val

    def validate_general_feedback(self, val):
        if val: validate_no_off_platform_contact(val)
        return val

    def validate_pronunciation_notes(self, val):
        if val: validate_no_off_platform_contact(val)
        return val

    def validate_grammar_notes(self, val):
        if val: validate_no_off_platform_contact(val)
        return val

    def validate_grammar_corrections(self, val):
        if val: validate_no_off_platform_contact(val)
        return val

    def validate_homework(self, val):
        if val: validate_no_off_platform_contact(val)
        return val

    def validate_homework_assigned(self, val):
        if val: validate_no_off_platform_contact(val)
        return val

    def validate_next_lesson_recommendation(self, val):
        if val: validate_no_off_platform_contact(val)
        return val

    def validate(self, attrs):
        if not attrs.get('feedback_text') and not attrs.get('general_feedback'):
            raise serializers.ValidationError({'feedback_text': ['This field is required.']})
        if not attrs.get('feedback_text') and attrs.get('general_feedback'):
            attrs['feedback_text'] = attrs['general_feedback']
        elif attrs.get('feedback_text') and not attrs.get('general_feedback'):
            attrs['general_feedback'] = attrs['feedback_text']

        if not attrs.get('homework') and attrs.get('homework_assigned'):
            attrs['homework'] = attrs['homework_assigned']
        elif attrs.get('homework') and not attrs.get('homework_assigned'):
            attrs['homework_assigned'] = attrs['homework']

        if not attrs.get('grammar_notes') and attrs.get('grammar_corrections'):
            attrs['grammar_notes'] = attrs['grammar_corrections']
        elif attrs.get('grammar_notes') and not attrs.get('grammar_corrections'):
            attrs['grammar_corrections'] = attrs['grammar_notes']

        return attrs

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['general_feedback'] = ret.get('feedback_text', '')
        ret['homework_assigned'] = ret.get('homework', '')
        ret['grammar_corrections'] = ret.get('grammar_notes', '')
        ret['next_lesson_recommendation'] = getattr(instance, 'next_lesson_recommendation', '')
        return ret

    def create(self, validated_data):
        validated_data.pop('general_feedback', None)
        validated_data.pop('homework_assigned', None)
        validated_data.pop('grammar_corrections', None)
        validated_data.pop('next_lesson_recommendation', None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop('general_feedback', None)
        validated_data.pop('homework_assigned', None)
        validated_data.pop('grammar_corrections', None)
        validated_data.pop('next_lesson_recommendation', None)
        return super().update(instance, validated_data)


class LessonMemoInputSerializer(serializers.Serializer):
    """
    What a tutor may submit after a lesson. Supports canonical model field names
    and descriptive aliases with contact-guard sanitization.
    """
    feedback_text = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False,
        validators=[validate_no_off_platform_contact]
    )
    vocabulary_words = serializers.ListField(
        child=serializers.JSONField(), required=False, default=list, max_length=MAX_VOCAB_WORDS
    )
    pronunciation_notes = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True, default='',
        validators=[validate_no_off_platform_contact]
    )
    grammar_notes = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True, default='',
        validators=[validate_no_off_platform_contact]
    )
    homework = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True, default='',
        validators=[validate_no_off_platform_contact]
    )

    # Descriptive field aliases (R2 specification)
    general_feedback = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False,
        validators=[validate_no_off_platform_contact]
    )
    grammar_corrections = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True,
        validators=[validate_no_off_platform_contact]
    )
    homework_assigned = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True,
        validators=[validate_no_off_platform_contact]
    )
    next_lesson_recommendation = serializers.CharField(
        max_length=MAX_NOTE_LENGTH, required=False, allow_blank=True, default='',
        validators=[validate_no_off_platform_contact]
    )

    def validate_feedback_text(self, val):
        if val:
            validate_no_off_platform_contact(val)
        return val

    def validate_general_feedback(self, val):
        if val:
            validate_no_off_platform_contact(val)
        return val

    def validate_pronunciation_notes(self, val):
        if val:
            validate_no_off_platform_contact(val)
        return val

    def validate_grammar_notes(self, val):
        if val:
            validate_no_off_platform_contact(val)
        return val

    def validate_grammar_corrections(self, val):
        if val:
            validate_no_off_platform_contact(val)
        return val

    def validate_homework(self, val):
        if val:
            validate_no_off_platform_contact(val)
        return val

    def validate_homework_assigned(self, val):
        if val:
            validate_no_off_platform_contact(val)
        return val

    def validate_next_lesson_recommendation(self, val):
        if val:
            validate_no_off_platform_contact(val)
        return val

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

    def validate(self, attrs):
        # 1. Require feedback_text or general_feedback
        if not attrs.get('feedback_text') and not attrs.get('general_feedback'):
            raise serializers.ValidationError({'feedback_text': ['This field is required.']})

        # 2. Reconcile feedback aliases
        if not attrs.get('feedback_text') and attrs.get('general_feedback'):
            attrs['feedback_text'] = attrs['general_feedback']
        elif attrs.get('feedback_text') and not attrs.get('general_feedback'):
            attrs['general_feedback'] = attrs['feedback_text']

        # 3. Reconcile homework aliases
        if not attrs.get('homework') and attrs.get('homework_assigned'):
            attrs['homework'] = attrs['homework_assigned']
        elif attrs.get('homework') and not attrs.get('homework_assigned'):
            attrs['homework_assigned'] = attrs['homework']

        # 4. Reconcile grammar aliases
        if not attrs.get('grammar_notes') and attrs.get('grammar_corrections'):
            attrs['grammar_notes'] = attrs['grammar_corrections']
        elif attrs.get('grammar_notes') and not attrs.get('grammar_corrections'):
            attrs['grammar_corrections'] = attrs['grammar_notes']

        # Ensure canonical fields have their defaults if omitted
        if 'pronunciation_notes' not in attrs:
            attrs['pronunciation_notes'] = ''
        if 'grammar_notes' not in attrs:
            attrs['grammar_notes'] = ''
        if 'homework' not in attrs:
            attrs['homework'] = ''
        if 'vocabulary_words' not in attrs:
            attrs['vocabulary_words'] = []

        return attrs


class BookingStudentSerializer(serializers.Serializer):
    """Minimal student view embedded in a booking. Contact details are only for the student themselves/staff."""
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()
    first_name = serializers.CharField()
    timezone = serializers.CharField()
    country = serializers.CharField()
    # Optional in the contract because tutors must not receive the student's e-mail.
    email = serializers.EmailField(required=False)
    target_level = serializers.SerializerMethodField()
    learning_goals = serializers.SerializerMethodField()

    def get_full_name(self, obj) -> str:
        return obj.get_full_name() or obj.username

    def get_target_level(self, obj) -> str:
        profile = getattr(obj, 'student_profile', None)
        return profile.target_level if profile else ''

    def get_learning_goals(self, obj) -> str:
        profile = getattr(obj, 'student_profile', None)
        return profile.learning_goals if profile else ''

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        viewer = getattr(request, 'user', None)
        if viewer is not None and viewer.is_authenticated and (viewer.id == instance.id or viewer.is_staff or getattr(viewer, 'role', '') == 'admin'):
            data['email'] = instance.email
        else:
            data.pop('email', None)
        return data


class BookingDetailSerializer(serializers.ModelSerializer):
    teacher = TeacherListSerializer(read_only=True)
    student = BookingStudentSerializer(read_only=True)
    memo = LessonMemoSerializer(read_only=True, allow_null=True)
    # Conditionally omitted outside staff responses, so it cannot be required in the public contract.
    student_review = serializers.CharField(required=False)
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
            'student_rating', 'student_review', 'memo', 'created_at',
            'cancelled_at', 'reschedule_count', 'original_start_time_utc',
        )
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        viewer = self._viewer()
        # The student's written review is private to staff: not to the tutor it is about, nor to anyone else.
        if not (viewer and viewer.is_authenticated and viewer.is_staff):
            data.pop('student_review', None)
        return data

    def _viewer(self):
        request = self.context.get('request')
        return getattr(request, 'user', None) if request else None

    def get_booking_reference(self, obj) -> str:
        return f"BK-{str(obj.id).split('-')[0].upper()}"

    # D-1: the platform's flat catalog price, not the tutor's. Exact Decimals; floats only at the JSON boundary.
    def get_price_usd(self, obj) -> str:
        return money_str(lesson_price('USD'), 'USD')

    def get_price_zar(self, obj) -> str:
        return money_str(lesson_price('ZAR'), 'ZAR')

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
        # Validation only: BookingListCreateView.create() reserves through services/reservation.py (hold + bookable tutor).
        # The old body here created a booking without either (slice T1b review nit); it was never reachable.
        raise NotImplementedError('Bookings are created by bookings.services.reservation.reserve_slot.')

class ReviewInputSerializer(serializers.Serializer):
    """A student's review. `review` is the legacy name of `private_notes` (older clients)."""
    rating = serializers.IntegerField(min_value=1, max_value=5)
    tags = serializers.ListField(child=serializers.ChoiceField(choices=REVIEW_TAGS), required=False, default=list, max_length=len(REVIEW_TAGS))
    private_notes = serializers.CharField(max_length=2000, required=False, allow_blank=True, default='')
    review = serializers.CharField(max_length=2000, required=False, allow_blank=True, default='', write_only=True)

    def validate_tags(self, tags):
        return list(dict.fromkeys(tags))  # drop repeats, keep order

    def validate(self, attrs):
        attrs['notes'] = attrs.get('private_notes') or attrs.get('review') or ''
        return attrs
