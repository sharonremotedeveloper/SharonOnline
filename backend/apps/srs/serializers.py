from rest_framework import serializers
from apps.common.timezones import get_zone
from apps.srs.models import StudentFlashcard
from apps.bookings.models import Booking, LessonMemo

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
    memo = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            'id', 'booking_reference', 'teacher',
            'start_time_utc', 'end_time_utc',
            'local_date', 'local_start_time', 'local_end_time',
            'viewer_timezone', 'material_title', 'material_cefr',
            'material_slug', 'status', 'memo', 'review'
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
        return self._local_start(obj).strftime('%b %d, %Y')

    def get_local_start_time(self, obj):
        return self._local_start(obj).strftime('%H:%M')

    def get_local_end_time(self, obj):
        return self._local_end(obj).strftime('%H:%M')

    def get_viewer_timezone(self, obj):
        return obj.student.timezone

    def _student_zone(self, obj):
        return get_zone(obj.student.timezone)

    def _local_start(self, obj):
        return obj.start_time_utc.astimezone(self._student_zone(obj))

    def _local_end(self, obj):
        return obj.end_time_utc.astimezone(self._student_zone(obj))

    def get_material_title(self, obj):
        return obj.material.title if obj.material else None

    def get_material_cefr(self, obj):
        return obj.material.cefr_level if obj.material else None

    def get_material_slug(self, obj):
        return obj.material.slug if obj.material else None

    def get_memo(self, obj):
        if not hasattr(obj, 'memo') or not obj.memo:
            return None
        memo = obj.memo
        return {
            'id': str(memo.id),
            'feedback_text': memo.feedback_text,
            'vocabulary_words': memo.vocabulary_words,
            'pronunciation_notes': memo.pronunciation_notes,
            'grammar_notes': memo.grammar_notes,
            'homework': memo.homework,
            'submitted_at': memo.submitted_at.isoformat()
        }

    def get_review(self, obj):
        if obj.student_rating is None:
            return None
        return {
            'rating': obj.student_rating,
            'tags': obj.student_review_tags,      # what the student actually picked; the written text stays staff-only
            'submitted_at': (obj.reviewed_at or obj.updated_at).isoformat()
        }
