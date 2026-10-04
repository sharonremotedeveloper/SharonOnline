from django.contrib import admin
from .models import TeacherProfile, TeacherAvailability, TeacherStatusChange

class TeacherAvailabilityInline(admin.TabularInline):
    model = TeacherAvailability
    extra = 1


class TeacherStatusChangeInline(admin.TabularInline):
    """The tutor's status history, read only (append-only audit rows written by teachers/vetting.py)."""
    model = TeacherStatusChange
    fk_name = 'teacher'
    extra = 0
    can_delete = False
    fields = readonly_fields = ('created_at', 'from_status', 'to_status', 'actor', 'reason')

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('get_name', 'accent', 'price_per_25min_usd', 'rating_avg', 'rating_count', 'has_audio', 'has_certificate', 'status', 'is_verified', 'is_active', 'created_at')
    list_filter = ('status', 'accent', 'has_inverter_backup')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'headline', 'bio')
    inlines = [TeacherAvailabilityInline, TeacherStatusChangeInline]
    # Status changes only through teachers/vetting.py (docs/TUTOR_STATUS_MACHINE.md); the flags are generated from it.
    readonly_fields = ('status', 'is_verified', 'is_active', 'training_completed_at', 'sla_strikes')
    fieldsets = (
        ('User & Core Profile', {
            'fields': ('user', 'headline', 'accent', 'bio', 'specialties', 'price_per_25min_usd')
        }),
        ('Quality & Verification', {
            'fields': ('status', 'is_verified', 'is_active', 'training_completed_at', 'rating_avg', 'rating_count', 'sla_strikes')
        }),
        ('Eskom Grid Resilience', {
            'fields': ('eskom_area_id', 'has_inverter_backup', 'has_lte_failover')
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


@admin.register(TeacherStatusChange)
class TeacherStatusChangeAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'teacher', 'from_status', 'to_status', 'actor')
    list_filter = ('to_status',)
    search_fields = ('teacher__user__username', 'actor')
    readonly_fields = [f.name for f in TeacherStatusChange._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TeacherAvailability)
class TeacherAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'day_of_week', 'start_time', 'end_time', 'is_active')
    list_filter = ('day_of_week', 'is_active')
