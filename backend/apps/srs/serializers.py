from rest_framework import serializers
from apps.srs.models import StudentFlashcard
from apps.bookings.models import Booking, LessonMemo
from apps.users.models import User

class StudentFlashcardSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentFlashcard
        fields = [
            'id', 'word', 'phonetic', 'part_of_speech',
            'definition', 'example_sentence', 'lesson_source',
            'mastery', 'review_count', 'next_review_due'
        ]


class FlashcardMasteryUpdateSerializer(serializers.Serializer):
    grade = serializers.ChoiceField(choices=['again', 'good', 'easy'])


class StudentLessonItemSerializer(serializers.ModelSerializer):
    booking_reference = serializers.SerializerMethodField()
    teacher = serializers.SerializerMethodField()
    local_date = serializers.SerializerMethodField()
    local_start_time = serializers.SerializerMethodField()
    local_end_time = serializers.SerializerMethodField()
    viewer_timezone = serializers.SerializerMethodField()
    material_title = serializers.SerializerMethodField()
    material_cefr = serializers.SerializerMethodField()
    material_slug = serializers.SerializerMethodField()
    zoom_url = serializers.CharField(source='zoom_join_url', allow_blank=True)
    memo = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            'id', 'booking_reference', 'teacher',
            'start_time_utc', 'end_time_utc',
            'local_date', 'local_start_time', 'local_end_time',
            'viewer_timezone', 'material_title', 'material_cefr',
            'material_slug', 'status', 'zoom_url', 'memo', 'review'
        ]

    def get_booking_reference(self, obj):
        return f"BK-{str(obj.id)[:6].upper()}"

    def get_teacher(self, obj):
        return {
            'id': str(obj.teacher.id),
            'name': obj.teacher.user.get_full_name() or obj.teacher.user.username,
            'avatar': obj.teacher.avatar_url or "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=400&q=80",
            'accent': obj.teacher.get_accent_display()
        }

    def get_local_date(self, obj):
        return obj.start_time_utc.strftime('%b %d, %Y')

    def get_local_start_time(self, obj):
        return obj.start_time_utc.strftime('%H:%M')

    def get_local_end_time(self, obj):
        return obj.end_time_utc.strftime('%H:%M')

    def get_viewer_timezone(self, obj):
        return obj.student.timezone or "Asia/Tokyo"

    def get_material_title(self, obj):
        return obj.material.title if obj.material else "FreeTalk & Topic Discussion"

    def get_material_cefr(self, obj):
        return obj.material.cefr_level if obj.material else "B2"

    def get_material_slug(self, obj):
        return obj.material.slug if obj.material else "freetalk-discussion"

    def get_memo(self, obj):
        if not hasattr(obj, 'memo') or not obj.memo:
            return None
        memo = obj.memo
        return {
            'id': str(memo.id),
            'feedback_text': memo.feedback_text,
            'vocabulary_words': memo.vocabulary_words,
            'pronunciation_notes': memo.pronunciation_notes,
            'grammar_notes': memo.homework or "Focus on natural conversational phrasing.",
            'homework': memo.homework,
            'submitted_at': memo.submitted_at.isoformat()
        }

    def get_review(self, obj):
        if obj.student_rating is None:
            return None
        return {
            'rating': obj.student_rating,
            'tags': ["Clear Pronunciation", "Great Corrections", "Patience"],
            'submitted_at': obj.updated_at.isoformat()
        }


class SubmitLessonReviewSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    tags = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    private_notes = serializers.CharField(required=False, allow_blank=True, default="")


class StudentProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    target_level = serializers.CharField(required=False, allow_blank=True)
    learning_goals = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            'id', 'full_name', 'email', 'country', 'timezone',
            'target_level', 'learning_goals'
        ]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username
