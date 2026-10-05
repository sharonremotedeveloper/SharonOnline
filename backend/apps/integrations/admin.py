from django.contrib import admin

from .models import EskomAreaStatus, EskomNotificationAttempt, CalendarCredential
from apps.teachers.models import PrivateAssetAccessAudit


@admin.register(CalendarCredential)
class CalendarCredentialAdmin(admin.ModelAdmin):
    list_display = ('user', 'connected_at', 'revoked_at', 'block_busy', 'last_error')
    readonly_fields = ('user', 'refresh_token_enc', 'scopes', 'connected_at', 'revoked_at', 'last_error')


@admin.register(PrivateAssetAccessAudit)
class PrivateAssetAccessAuditAdmin(admin.ModelAdmin):
    list_display = ('actor', 'teacher', 'object_key', 'action', 'created_at')
    readonly_fields = tuple(field.name for field in PrivateAssetAccessAudit._meta.fields)


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

