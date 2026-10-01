from rest_framework import serializers
from apps.teachers.models import TeacherProfile
from apps.bookings.models import Booking, AttendanceAudit
from apps.admin_api.models import DisputeCase, PayoutBatch
from apps.users.models import User

class AdminTelemetrySerializer(serializers.Serializer):
    gmv_today_usd = serializers.FloatField()
    gmv_month_usd = serializers.FloatField()
    active_zoom_sessions_count = serializers.IntegerField()
    open_disputes_count = serializers.IntegerField()
    pending_vetting_count = serializers.IntegerField()
    escrow_liability_usd = serializers.FloatField()
    escrow_liability_zar = serializers.FloatField()
    total_students_count = serializers.IntegerField()
    total_teachers_count = serializers.IntegerField()


class PendingTeacherApplicationSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source='user.email')
    country = serializers.CharField(source='user.country')
    accent = serializers.CharField(source='get_accent_display')
    video_url = serializers.CharField(source='intro_video_url')
    tefl_certificate_url = serializers.SerializerMethodField()
    eskom_area = serializers.SerializerMethodField()
    has_inverter = serializers.SerializerMethodField()
    applied_at = serializers.DateTimeField(source='created_at')
    status = serializers.SerializerMethodField()

    class Meta:
        model = TeacherProfile
        fields = [
            'id', 'full_name', 'email', 'country', 'accent', 'bio',
            'specialties', 'video_url', 'tefl_certificate_url',
            'eskom_area', 'has_inverter', 'applied_at', 'status'
        ]

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_tefl_certificate_url(self, obj):
        if hasattr(obj, 'resolved_tefl_certificate_url'):
            return obj.resolved_tefl_certificate_url
        return getattr(obj, 'tefl_certificate_url', '')


    def get_eskom_area(self, obj):
        return getattr(obj, 'eskom_area', 'City of Johannesburg Block 3')

    def get_has_inverter(self, obj):
        return getattr(obj, 'has_inverter_backup', True)

    def get_status(self, obj):
        if obj.is_verified:
            return 'approved'
        if not obj.is_active:
            return 'rejected'
        return 'pending'


class VerifyTeacherActionSerializer(serializers.Serializer):
    is_verified = serializers.BooleanField()
    rejection_reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class LiveSessionRadarSerializer(serializers.ModelSerializer):
    booking_ref = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()
    material_title = serializers.SerializerMethodField()
    elapsed_minutes = serializers.SerializerMethodField()
    student_joined_at = serializers.SerializerMethodField()
    teacher_joined_at = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            'id', 'booking_ref', 'teacher_name', 'student_name',
            'material_title', 'start_time_utc', 'elapsed_minutes',
            'student_joined_at', 'teacher_joined_at', 'zoom_meeting_id', 'status'
        ]

    def get_booking_ref(self, obj):
        return f"BK-{str(obj.id)[:6].upper()}"

    def get_teacher_name(self, obj):
        return obj.teacher.user.get_full_name() or obj.teacher.user.username

    def get_student_name(self, obj):
        return obj.student.get_full_name() or obj.student.username

    def get_material_title(self, obj):
        return obj.material.title if obj.material else "Free Conversation & Fluency"

    def get_elapsed_minutes(self, obj):
        from django.utils import timezone
        diff = timezone.now() - obj.start_time_utc
        return max(0, int(diff.total_seconds() // 60))

    def get_student_joined_at(self, obj):
        audit = obj.attendance_audits.filter(participant_email=obj.student.email).first()
        return audit.join_time_utc.isoformat() if audit else None

    def get_teacher_joined_at(self, obj):
        audit = obj.attendance_audits.filter(participant_email=obj.teacher.user.email).first()
        return audit.join_time_utc.isoformat() if audit else None


class DisputeCaseSerializer(serializers.ModelSerializer):
    booking_ref = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    lesson_date = serializers.SerializerMethodField()
    amount_usd = serializers.SerializerMethodField()
    amount_zar = serializers.SerializerMethodField()
    zoom_telemetry = serializers.SerializerMethodField()

    class Meta:
        model = DisputeCase
        fields = [
            'id', 'booking_ref', 'student_name', 'teacher_name',
            'lesson_date', 'amount_usd', 'amount_zar',
            'student_statement', 'teacher_statement',
            'zoom_telemetry', 'status', 'resolution', 'admin_notes'
        ]

    def get_booking_ref(self, obj):
        return f"BK-{str(obj.booking.id)[:6].upper()}"

    def get_student_name(self, obj):
        return obj.student.get_full_name() or obj.student.username

    def get_teacher_name(self, obj):
        return obj.teacher.user.get_full_name() or obj.teacher.user.username

    def get_lesson_date(self, obj):
        return obj.booking.start_time_utc.strftime('%Y-%m-%d %H:%M UTC')

    def get_amount_usd(self, obj):
        return float(obj.teacher.price_per_25min_usd)

    def get_amount_zar(self, obj):
        return round(float(obj.teacher.price_per_25min_usd) * 18.75, 2)

    def get_zoom_telemetry(self, obj):
        student_audit = obj.booking.attendance_audits.filter(participant_email=obj.student.email).first()
        teacher_audit = obj.booking.attendance_audits.filter(participant_email=obj.teacher.user.email).first()
        return {
            'student_dwell_minutes': student_audit.total_minutes if student_audit else 0,
            'teacher_dwell_minutes': teacher_audit.total_minutes if teacher_audit else 0,
            'call_connected': bool(student_audit and teacher_audit),
            'interrupted_reason': "Tutor socket disconnect" if (obj.booking.status == 'interrupted_power') else None
        }


class ResolveDisputeSerializer(serializers.Serializer):
    resolution = serializers.ChoiceField(choices=DisputeCase.Resolution.choices)
    admin_notes = serializers.CharField(required=False, allow_blank=True, default="")


class FinanceEscrowItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    booking_ref = serializers.CharField()
    student_name = serializers.CharField()
    teacher_name = serializers.CharField()
    lesson_date = serializers.CharField()
    amount_usd = serializers.FloatField()
    amount_zar = serializers.FloatField()
    platform_fee_usd = serializers.FloatField()
    teacher_net_zar = serializers.FloatField()
    escrow_status = serializers.CharField()
    release_date = serializers.CharField()


class PayoutBatchItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    teacher_id = serializers.CharField()
    teacher_name = serializers.CharField()
    bank_name = serializers.CharField()
    account_number_masked = serializers.CharField()
    branch_code = serializers.CharField()
    cleared_lessons_count = serializers.IntegerField()
    payout_amount_zar = serializers.FloatField()
    status = serializers.CharField()
