from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

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
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Platform Role & Regional Settings', {
            'fields': ('role', 'country', 'timezone', 'phone_number')
        }),
    )
