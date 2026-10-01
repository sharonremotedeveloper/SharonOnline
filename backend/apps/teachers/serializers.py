from rest_framework import serializers
from .models import TeacherProfile, TeacherAvailability
from apps.users.serializers import UserSerializer

class TeacherAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherAvailability
        fields = ('id', 'day_of_week', 'start_time', 'end_time', 'is_active')

class TeacherListSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source='user.id', read_only=True)
    full_name = serializers.SerializerMethodField()
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    country = serializers.CharField(source='user.country', read_only=True)
    avatar_url = serializers.CharField(source='resolved_avatar_url', read_only=True)
    intro_audio_url = serializers.CharField(source='resolved_intro_audio_url', read_only=True)

    class Meta:
        model = TeacherProfile
        fields = (
            'id', 'user_id', 'full_name', 'first_name', 'last_name', 'headline',
            'accent', 'intro_video_thumbnail', 'avatar_url', 'intro_audio_url',
            'rating_avg', 'rating_count', 'price_per_25min_usd', 'specialties',
            'country', 'is_verified'
        )

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

class TeacherDetailSerializer(TeacherListSerializer):
    availabilities = TeacherAvailabilitySerializer(many=True, read_only=True)
    timezone = serializers.CharField(source='user.timezone', read_only=True)

    class Meta(TeacherListSerializer.Meta):
        fields = TeacherListSerializer.Meta.fields + (
            'bio', 'intro_video_url', 'timezone', 'availabilities'
        )

