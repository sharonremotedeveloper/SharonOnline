from django.contrib import admin
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
            'fields': ('role', 'country', 'timezone', 'phone_number', 'google_calendar_token')
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
