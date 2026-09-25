from rest_framework import serializers
from .models import Booking, LessonMemo
from apps.teachers.models import TeacherProfile
from apps.materials.models import Material
from apps.teachers.serializers import TeacherListSerializer
from apps.users.serializers import UserSerializer
from datetime import timedelta
from django.utils.dateparse import parse_datetime

class LessonMemoSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonMemo
        fields = ('id', 'booking', 'teacher', 'student', 'feedback_text', 'vocabulary_words', 'pronunciation_notes', 'homework', 'submitted_at')
        read_only_fields = ('id', 'booking', 'teacher', 'student', 'submitted_at')

class BookingDetailSerializer(serializers.ModelSerializer):
    teacher = TeacherListSerializer(read_only=True)
    student = UserSerializer(read_only=True)
    memo = LessonMemoSerializer(read_only=True)
    zoom_url = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = (
            'id', 'teacher', 'student', 'material', 'status',
            'start_time_utc', 'end_time_utc', 'zoom_url', 'zoom_password',
            'student_rating', 'student_review', 'memo', 'created_at'
        )

    def get_zoom_url(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return ""
        # Return host start URL for the assigned teacher, join URL for student
        if request.user == obj.teacher.user:
            return obj.zoom_start_url or obj.zoom_join_url
        return obj.zoom_join_url

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
