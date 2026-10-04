from rest_framework import serializers
from .models import TeacherProfile, TeacherAvailability
from apps.users.serializers import UserSerializer

class TeacherAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherAvailability
        fields = ('id', 'day_of_week', 'start_time', 'end_time', 'is_active')


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

