from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.notifications'
    verbose_name = 'Notifications'

    def ready(self):
        # Kind modules register their templates on import. Later slices add their module here (N2a-c, N4).
        from apps.notifications import builtin_kinds  # noqa: F401
        from apps.notifications import domain_kinds   # noqa: F401
