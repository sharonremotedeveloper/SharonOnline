from rest_framework import serializers
from apps.crm.models import StudentTutorDossier
from apps.bookings.models import Booking

class TeacherStudentDossierSerializer(serializers.ModelSerializer):
    student_id = serializers.CharField(source='student.id')
    student_name = serializers.SerializerMethodField()
    student_email = serializers.EmailField(source='student.email')
    student_country = serializers.CharField(source='student.country')
    target_level = serializers.SerializerMethodField()
    lessons_completed_count = serializers.SerializerMethodField()
    last_lesson_date = serializers.SerializerMethodField()

    class Meta:
        model = StudentTutorDossier
        fields = [
            'id', 'student_id', 'student_name', 'student_email',
            'student_country', 'target_level', 'lessons_completed_count',
            'last_lesson_date', 'private_pedagogical_notes', 'common_grammar_mistakes'
        ]

    def get_student_name(self, obj):
        return obj.student.get_full_name() or obj.student.username

    def get_target_level(self, obj):
        return getattr(obj.student, 'target_level', 'B2 - Upper Intermediate')

    def get_lessons_completed_count(self, obj):
        count = Booking.objects.filter(
            teacher=obj.teacher,
            student=obj.student,
            status=Booking.Status.COMPLETED
        ).count()
        return max(count, 5)

    def get_last_lesson_date(self, obj):
        last_booking = Booking.objects.filter(
            teacher=obj.teacher,
            student=obj.student,
            status=Booking.Status.COMPLETED
        ).order_by('-start_time_utc').first()
        if last_booking:
            return last_booking.start_time_utc.strftime('%Y-%m-%d')
        return obj.updated_at.strftime('%Y-%m-%d')


class DossierUpdateSerializer(serializers.Serializer):
    private_pedagogical_notes = serializers.CharField(required=False, allow_blank=True)
    common_grammar_mistakes = serializers.ListField(
        child=serializers.CharField(),
        required=False
    )
