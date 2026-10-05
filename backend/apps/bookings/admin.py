from django.contrib import admin
from .models import AttendanceAudit, Booking, BookingStatusChange, HostLinkIssue, LessonMemo
from .services.host_link import review_host_link_issues

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


@admin.register(HostLinkIssue)
class HostLinkIssueAdmin(admin.ModelAdmin):
    """Staff-hosted lessons waiting for an attendance review (escrow is held until reviewed). Read-only audit rows."""
    list_display = ('booking', 'issued_by', 'created_at', 'reviewed_at', 'reviewed_by')
    list_filter = (('reviewed_at', admin.EmptyFieldListFilter),)
    search_fields = ('booking__id',)
    readonly_fields = ('booking', 'issued_by', 'created_at', 'reviewed_at', 'reviewed_by')
    actions = ['mark_reviewed']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description='Mark reviewed (the tutor\'s attendance was checked; releases the escrow hold)')
    def mark_reviewed(self, request, queryset):
        count = review_host_link_issues(queryset, request.user)
        self.message_user(request, f'{count} host-link audit row(s) marked reviewed.')


@admin.register(AttendanceAudit)
class AttendanceAuditAdmin(admin.ModelAdmin):
    list_display = ('booking', 'classification', 'participant_email', 'participant_id', 'registrant_id',
                    'join_time_utc', 'leave_time_utc', 'total_minutes')
    list_filter = ('classification', 'identity')
    search_fields = ('booking__id', 'participant_email', 'participant_id', 'registrant_id', 'host_id')
    readonly_fields = tuple(field.name for field in AttendanceAudit._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
