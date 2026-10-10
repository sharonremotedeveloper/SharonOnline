from django.contrib import admin
from .models import AttendanceAudit, Booking, BookingStatusChange, LessonMemo, VideoTrial


@admin.register(VideoTrial)
class VideoTrialAdmin(admin.ModelAdmin):
    list_display = ('id', 'teacher', 'student', 'opens_at', 'closes_at', 'enabled', 'created_by')
    list_filter = ('enabled',)
    search_fields = ('teacher__username', 'student__username')
    readonly_fields = ('id', 'created_by', 'created_at')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.full_clean()
        super().save_model(request, obj, form, change)

class LessonMemoInline(admin.StackedInline):
    model = LessonMemo
    extra = 0

class StatusChangeInline(admin.TabularInline):
    """Append-only audit trail (read-only)."""
    model = BookingStatusChange
    extra = 0
    can_delete = False
    readonly_fields = ('from_status', 'to_status', 'actor', 'reason', 'created_at')
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'teacher', 'student', 'status', 'start_time_utc', 'created_at')
    list_filter = ('status', 'start_time_utc')
    search_fields = ('teacher__user__username', 'student__username')
    # `status` is changed only through services.state_machine.transition_booking (validated + audited), never by form edit.
    readonly_fields = ('status', 'student_rating', 'student_review', 'student_review_tags', 'reviewed_at', 'created_at', 'updated_at')
    inlines = [LessonMemoInline, StatusChangeInline]

@admin.register(LessonMemo)
class LessonMemoAdmin(admin.ModelAdmin):
    list_display = ('booking', 'teacher', 'student', 'submitted_at')
    search_fields = ('teacher__user__username', 'student__username', 'feedback_text')


@admin.register(AttendanceAudit)
class AttendanceAuditAdmin(admin.ModelAdmin):
    list_display = ('booking', 'classification', 'participant_email', 'participant_id',
                    'join_time_utc', 'leave_time_utc', 'total_minutes')
    list_filter = ('classification', 'identity')
    search_fields = ('booking__id', 'participant_email', 'participant_id')
    readonly_fields = tuple(field.name for field in AttendanceAudit._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
