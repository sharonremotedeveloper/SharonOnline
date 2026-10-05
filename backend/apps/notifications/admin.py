from django.contrib import admin
from django.core.exceptions import PermissionDenied

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Read-only delivery view (docs/RUNBOOK_NOTIFICATIONS.md). FAILED rows can be re-sent after a human review."""
    list_display = ('id', 'kind', 'user', 'email_state', 'email_attempts', 'email_last_error', 'created_at',
                    'email_sent_at')
    list_filter = ('email_state', 'kind', 'in_app')
    search_fields = ('id', 'idempotency_key', 'provider_message_id')
    exclude = ('rendered_html',)        # bodies are not browsed in the list; the runbook works with ids and codes
    actions = ['resend_failed']

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in Notification._meta.fields if f.name != 'rendered_html']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_resend_permission(self, request):
        user = request.user
        return bool(user.is_active and user.is_staff and (user.is_superuser or getattr(user, 'role', None) == 'admin'))

    @admin.action(description='Re-send FAILED e-mails (after checking they were not delivered)', permissions=['resend'])
    def resend_failed(self, request, queryset):
        if not self.has_resend_permission(request):
            raise PermissionDenied
        from apps.notifications.delivery import requeue_failed
        requeued = requeue_failed(queryset, actor=request.user)     # one log line per row with the actor id
        self.message_user(request, f'{len(requeued)} notification(s) re-queued; rows that were not FAILED were left unchanged.')
