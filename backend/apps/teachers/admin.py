from django.contrib import admin
from .models import TeacherProfile, TeacherAvailability

class TeacherAvailabilityInline(admin.TabularInline):
    model = TeacherAvailability
    extra = 1

@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('get_name', 'accent', 'price_per_25min_usd', 'rating_avg', 'rating_count', 'has_audio', 'has_certificate', 'is_verified', 'is_active', 'created_at')
    list_filter = ('accent', 'is_verified', 'is_active', 'has_inverter_backup')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'headline', 'bio')
    inlines = [TeacherAvailabilityInline]
    fieldsets = (
        ('User & Core Profile', {
            'fields': ('user', 'headline', 'accent', 'bio', 'specialties', 'price_per_25min_usd')
        }),
        ('Quality & Verification', {
            'fields': ('is_verified', 'is_active', 'rating_avg', 'rating_count', 'sla_strikes')
        }),
        ('Eskom Grid Resilience', {
            'fields': ('eskom_area_id', 'has_inverter_backup')
        }),
        ('Cloudflare Media Assets ($0 Egress)', {
            'fields': (
                'avatar_image', 'avatar_url',
                'intro_audio_file', 'intro_audio_url',
                'intro_video_url', 'intro_video_thumbnail',
                'tefl_certificate_file', 'tefl_certificate_url'
            ),
            'description': 'Public audio snippets, profile avatars, and private TEFL certificates managed in Cloudflare R2.'
        }),
    )

    def get_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
    get_name.short_description = 'Teacher'

    def has_audio(self, obj):
        return bool(obj.intro_audio_file or obj.intro_audio_url)
    has_audio.boolean = True
    has_audio.short_description = "Audio"

    def has_certificate(self, obj):
        return bool(obj.tefl_certificate_file or obj.tefl_certificate_url)
    has_certificate.boolean = True
    has_certificate.short_description = "TEFL"


@admin.register(TeacherAvailability)
class TeacherAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'day_of_week', 'start_time', 'end_time', 'is_active')
    list_filter = ('day_of_week', 'is_active')
