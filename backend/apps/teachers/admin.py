from django.contrib import admin
from .models import TeacherProfile, TeacherAvailability

class TeacherAvailabilityInline(admin.TabularInline):
    model = TeacherAvailability
    extra = 1

@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('get_name', 'accent', 'price_per_25min_usd', 'rating_avg', 'rating_count', 'is_verified', 'is_active', 'created_at')
    list_filter = ('accent', 'is_verified', 'is_active')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'headline', 'bio')
    inlines = [TeacherAvailabilityInline]

    def get_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
    get_name.short_description = 'Teacher'

@admin.register(TeacherAvailability)
class TeacherAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'day_of_week', 'start_time', 'end_time', 'is_active')
    list_filter = ('day_of_week', 'is_active')
