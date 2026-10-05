from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import StudentProfile, SupportInquiry, User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'role', 'country', 'timezone', 'is_staff', 'created_at')
    list_filter = ('role', 'is_staff', 'is_active', 'country')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-created_at',)

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Platform Role & Regional Settings', {
            'fields': ('role', 'country', 'timezone', 'phone_number')
        }),
        ('Booking block (clear this field to let the student book again)', {
            'fields': ('booking_blocked_reason',)
        }),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Platform Role & Regional Settings', {
            'fields': ('role', 'country', 'timezone', 'phone_number')
        }),
    )

    def save_model(self, request, obj, form, change):
        """T2: staff may change a tutor's timezone, but are told when it strands confirmed lessons (the API asks the tutor to acknowledge)."""
        if change and 'timezone' in form.changed_data and getattr(obj, 'teacher_profile', None) is not None:
            from apps.common.timezones import get_zone
            from apps.teachers.services.availability import conflicts_for
            conflicts = conflicts_for(obj.teacher_profile, zone=get_zone(obj.timezone))
            if conflicts:
                self.message_user(request, f'{len(conflicts)} confirmed lesson(s) of this tutor now fall outside their weekly hours; '
                                           'they stay booked: ask the tutor to teach or cancel them.', level=messages.WARNING)
        super().save_model(request, obj, form, change)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'target_level', 'updated_at')
    search_fields = ('user__username', 'user__email', 'learning_goals')


@admin.register(SupportInquiry)
class SupportInquiryAdmin(admin.ModelAdmin):
    list_display = ('subject', 'sender_email', 'sender_type', 'status', 'delivery_state', 'delivery_attempts', 'created_at')
    list_filter = ('status', 'delivery_state', 'sender_type')
    search_fields = ('sender_name', 'sender_email', 'subject', 'message')
    readonly_fields = ('id', 'delivery_attempts', 'last_delivery_error', 'delivered_at', 'created_at', 'updated_at')
