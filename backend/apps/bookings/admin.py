from django.contrib import admin
from .models import Booking, BookingStatusChange, LessonMemo

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
    list_display = ('id', 'teacher', 'student', 'status', 'start_time_utc', 'zoom_meeting_id', 'created_at')
    list_filter = ('status', 'start_time_utc')
    search_fields = ('teacher__user__username', 'student__username', 'zoom_meeting_id')
    # `status` is changed only through services.state_machine.transition_booking (validated + audited), never by form edit.
    readonly_fields = ('status', 'student_rating', 'student_review', 'student_review_tags', 'reviewed_at', 'created_at', 'updated_at')
    inlines = [LessonMemoInline, StatusChangeInline]

@admin.register(LessonMemo)
class LessonMemoAdmin(admin.ModelAdmin):
    list_display = ('booking', 'teacher', 'student', 'submitted_at')
    search_fields = ('teacher__user__username', 'student__username', 'feedback_text')
