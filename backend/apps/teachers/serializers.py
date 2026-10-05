from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.money import money_str
from apps.payments.services.pricing import PriceNotConfigured, lesson_price
from .models import TeacherProfile, TeacherAvailability, TeacherDateOverride, TeacherTimeOff
from .profile import VETTED_FIELDS, WRITABLE_FIELDS
from .services import availability as rules

_CATALOG_USD = '_t1c_catalog_usd'      # serializer-context cache key: one catalog read per response

# OpenAPI for the deprecated public price (T1c, plan §3.1): kept in the contract for one release so generated clients and
# the TS type stay compatible, but it is the platform catalog price, never the old per-tutor column.
DEPRECATED_PRICE_SCHEMA = {
    'type': 'string', 'format': 'decimal', 'nullable': True, 'deprecated': True,
    'description': 'Deprecated. USD catalog price only. Do not display; use `/payments/lesson-prices/` for the student\'s '
                   'currency. null when no USD price is configured.',
}


class TeacherAvailabilitySerializer(serializers.ModelSerializer):
    """One weekly window in the tutor's local clock. Validated against the tutor in `context['teacher']` (absent = read-only use)."""
    day_of_week = serializers.IntegerField(min_value=0, max_value=6, help_text='0=Monday ... 6=Sunday')

    class Meta:
        model = TeacherAvailability
        fields = ('id', 'day_of_week', 'start_time', 'end_time', 'is_active')

    def validate(self, attrs):
        teacher = self.context.get('teacher')
        if teacher is None:
            return attrs
        current = self.instance

        def pick(name, default=None):
            return attrs[name] if name in attrs else (getattr(current, name) if current else default)
        start, end, day, active = pick('start_time'), pick('end_time'), pick('day_of_week'), pick('is_active', True)
        # Only a payload that sets the hours (or re-activates the row) is judged on them, so a legacy row with bad hours can
        # still be deactivated (T2 QA MINOR-6).
        if current is None or {'start_time', 'end_time'} & attrs.keys() or attrs.get('is_active') is True:
            errors = rules.window_errors(start, end)
            if errors:
                raise serializers.ValidationError(errors)
        if current is None:
            rules.check_row_limit(teacher)
        if active:
            rules.check_no_overlap(teacher, day, start, end, exclude_id=current.pk if current else None)
        return attrs


class AvailabilityUpdateSerializer(TeacherAvailabilitySerializer):
    acknowledge_conflicts = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta(TeacherAvailabilitySerializer.Meta):
        fields = TeacherAvailabilitySerializer.Meta.fields + ('acknowledge_conflicts',)


class AvailabilityRowSerializer(serializers.Serializer):
    day_of_week = serializers.IntegerField(min_value=0, max_value=6)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        errors = rules.window_errors(attrs['start_time'], attrs['end_time'])
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class AvailabilityMatrixSerializer(serializers.Serializer):
    rows = AvailabilityRowSerializer(many=True, allow_empty=True)
    acknowledge_conflicts = serializers.BooleanField(required=False, default=False)

    def validate_rows(self, rows):
        return rules.validate_matrix(rows)


class ConflictSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField()
    start_time_utc = serializers.CharField(help_text='ISO 8601 UTC')
    end_time_utc = serializers.CharField(help_text='ISO 8601 UTC')


class ConflictErrorSerializer(serializers.Serializer):
    """409 body: nothing was changed. Resend with acknowledge_conflicts=true to apply it anyway."""
    code = serializers.CharField()
    detail = serializers.CharField()
    conflicts = ConflictSerializer(many=True)


class AvailabilityChangeSerializer(serializers.Serializer):
    availability = TeacherAvailabilitySerializer()
    conflicts = ConflictSerializer(many=True)


class AvailabilityReplaceResultSerializer(serializers.Serializer):
    rows = TeacherAvailabilitySerializer(many=True)
    conflicts = ConflictSerializer(many=True)


class DeletedSerializer(serializers.Serializer):
    deleted = serializers.BooleanField()
    conflicts = ConflictSerializer(many=True)


class TeacherTimeOffSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherTimeOff
        fields = ('id', 'start_utc', 'end_utc', 'reason')


class TimeOffCreateSerializer(TeacherTimeOffSerializer):
    acknowledge_conflicts = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta(TeacherTimeOffSerializer.Meta):
        fields = TeacherTimeOffSerializer.Meta.fields + ('acknowledge_conflicts',)

    def validate(self, attrs):
        return rules.validate_time_off(attrs)


class TimeOffResultSerializer(serializers.Serializer):
    time_off = TeacherTimeOffSerializer()
    conflicts = ConflictSerializer(many=True)


class TeacherDateOverrideSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherDateOverride
        fields = ('id', 'date', 'kind', 'start_time', 'end_time', 'reason')


class DateOverrideCreateSerializer(TeacherDateOverrideSerializer):
    acknowledge_conflicts = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta(TeacherDateOverrideSerializer.Meta):
        fields = TeacherDateOverrideSerializer.Meta.fields + ('acknowledge_conflicts',)

    def validate(self, attrs):
        return rules.validate_override(attrs, self.context['teacher'])


class DateOverrideResultSerializer(serializers.Serializer):
    override = TeacherDateOverrideSerializer()
    conflicts = ConflictSerializer(many=True)


class PowerBackupSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherProfile
        fields = ('has_inverter_backup', 'has_lte_failover')

class TeacherListSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source='user.id', read_only=True)
    full_name = serializers.SerializerMethodField()
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    country = serializers.CharField(source='user.country', read_only=True)
    avatar_url = serializers.CharField(source='resolved_avatar_url', read_only=True)
    intro_audio_url = serializers.CharField(source='resolved_intro_audio_url', read_only=True)
    # Generated from status (teachers/vetting.py); never writable through an API.
    is_verified = serializers.BooleanField(read_only=True)
    price_per_25min_usd = serializers.SerializerMethodField()

    class Meta:
        model = TeacherProfile
        fields = (
            'id', 'user_id', 'full_name', 'first_name', 'last_name', 'headline',
            'accent', 'intro_video_thumbnail', 'avatar_url', 'intro_audio_url',
            'rating_avg', 'rating_count', 'price_per_25min_usd', 'specialties',
            'country', 'is_verified'
        )

    def get_full_name(self, obj) -> str:
        return obj.user.get_full_name() or obj.user.username

    @extend_schema_field(DEPRECATED_PRICE_SCHEMA)
    def get_price_per_25min_usd(self, obj):
        context = self.context
        if _CATALOG_USD not in context:
            try:
                context[_CATALOG_USD] = money_str(lesson_price('USD'), 'USD')
            except PriceNotConfigured:
                context[_CATALOG_USD] = None
        return context[_CATALOG_USD]

class TeacherDetailSerializer(TeacherListSerializer):
    availabilities = TeacherAvailabilitySerializer(many=True, read_only=True)
    timezone = serializers.CharField(source='user.timezone', read_only=True)

    class Meta(TeacherListSerializer.Meta):
        fields = TeacherListSerializer.Meta.fields + (
            'bio', 'intro_video_url', 'timezone', 'availabilities'
        )


SPECIALTY_MAX_ITEMS, SPECIALTY_MAX_LENGTH, BIO_MAX_LENGTH = 10, 40, 5000


class _TagField(serializers.CharField):
    # A specialty tag: a real string (DRF's CharField would turn 1 into '1').

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail('invalid')
        return super().to_internal_value(data)


class TeacherOwnProfileSerializer(serializers.ModelSerializer):
    # `GET|PATCH /teachers/me/` (T1c). Only WRITABLE_FIELDS are accepted; any other key (vetted, service-owned, staff-owned,
    # unknown) is a 400 naming the field, never silently ignored. Private document locations are never returned.
    # (Comments, not a docstring, so nothing internal is published in the OpenAPI file.)
    headline = serializers.CharField(max_length=255, allow_blank=True, required=False)
    bio = serializers.CharField(max_length=BIO_MAX_LENGTH, allow_blank=True, required=False, trim_whitespace=True)
    specialties = serializers.ListField(
        child=_TagField(max_length=SPECIALTY_MAX_LENGTH, allow_blank=False),
        max_length=SPECIALTY_MAX_ITEMS, allow_empty=True, required=False)
    is_verified = serializers.BooleanField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    avatar_url = serializers.CharField(source='resolved_avatar_url', read_only=True)
    intro_audio_url = serializers.CharField(source='resolved_intro_audio_url', read_only=True)
    has_tefl_certificate = serializers.SerializerMethodField()

    class Meta:
        model = TeacherProfile
        fields = (
            'id', 'status', 'is_verified', 'is_active', 'headline', 'bio', 'specialties', 'accent', 'intro_video_url',
            'intro_video_thumbnail', 'avatar_url', 'intro_audio_url', 'has_tefl_certificate', 'eskom_area_id',
            'has_inverter_backup', 'has_lte_failover', 'rating_avg', 'rating_count', 'sla_strikes',
            'training_completed_at', 'created_at', 'updated_at',
        )
        read_only_fields = tuple(name for name in fields if name not in WRITABLE_FIELDS)

    def get_has_tefl_certificate(self, obj) -> bool:
        return bool(obj.tefl_certificate_file or obj.tefl_certificate_url)

    def to_internal_value(self, data):
        if hasattr(data, 'keys'):
            errors = {}
            for key in data.keys():
                if key in WRITABLE_FIELDS:
                    continue
                errors[key] = [('This field is reviewed by vetting and changes only through the upload flow.'
                                if key in VETTED_FIELDS else 'This field cannot be changed here.')]
            if errors:
                raise serializers.ValidationError(errors)
        return super().to_internal_value(data)

    def validate_specialties(self, value):
        cleaned = []                       # each tag is already trimmed and non-blank (_TagField)
        for tag in value:
            if tag not in cleaned:
                cleaned.append(tag)
        return cleaned
