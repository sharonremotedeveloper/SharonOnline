from django.contrib import admin
from .models import Booking, LessonMemo

class LessonMemoInline(admin.StackedInline):
    model = LessonMemo
    extra = 0

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'teacher', 'student', 'status', 'start_time_utc', 'zoom_meeting_id', 'created_at')
    list_filter = ('status', 'start_time_utc')
    search_fields = ('teacher__user__username', 'student__username', 'zoom_meeting_id')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [LessonMemoInline]

@admin.register(LessonMemo)
class LessonMemoAdmin(admin.ModelAdmin):
    list_display = ('booking', 'teacher', 'student', 'submitted_at')
    search_fields = ('teacher__user__username', 'student__username', 'feedback_text')
