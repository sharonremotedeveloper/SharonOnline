from django.contrib import admin

from .models import EskomAreaStatus, EskomNotificationAttempt


@admin.register(EskomAreaStatus)
class EskomAreaStatusAdmin(admin.ModelAdmin):
    list_display = ('area_id', 'area_name', 'stage', 'provider_status', 'provider_retrieved_at', 'fresh_until')
    readonly_fields = ('updated_at',)
    search_fields = ('area_id', 'area_name')


@admin.register(EskomNotificationAttempt)
class EskomNotificationAttemptAdmin(admin.ModelAdmin):
    list_display = ('booking', 'recipient', 'state', 'attempts', 'sent_at', 'created_at')
    readonly_fields = ('idempotency_key', 'created_at', 'updated_at')
    list_filter = ('state',)

