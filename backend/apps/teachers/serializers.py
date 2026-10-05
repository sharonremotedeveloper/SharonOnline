from rest_framework import serializers
from .models import TeacherProfile, TeacherAvailability, TeacherDateOverride, TeacherTimeOff
from .services import availability as rules
from apps.users.serializers import UserSerializer


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

class TeacherDetailSerializer(TeacherListSerializer):
    availabilities = TeacherAvailabilitySerializer(many=True, read_only=True)
    timezone = serializers.CharField(source='user.timezone', read_only=True)

    class Meta(TeacherListSerializer.Meta):
        fields = TeacherListSerializer.Meta.fields + (
            'bio', 'intro_video_url', 'timezone', 'availabilities'
        )

