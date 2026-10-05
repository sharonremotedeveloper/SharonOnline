import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def wipe_legacy_calendar_tokens(apps, schema_editor):
    apps.get_model('users', 'User').objects.exclude(google_calendar_token__isnull=True).update(google_calendar_token=None)


class Migration(migrations.Migration):
    dependencies = [('integrations', '0001_eskom_status_and_notifications'), ('users', '0001_initial')]
    operations = [
        migrations.CreateModel(
            name='CalendarCredential',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('refresh_token_enc', models.TextField()), ('scopes', models.JSONField(blank=True, default=list)),
                ('connected_at', models.DateTimeField(auto_now_add=True)), ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('block_busy', models.BooleanField(default=True)), ('last_error', models.CharField(blank=True, max_length=255)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='calendar_credential', to=settings.AUTH_USER_MODEL)),
            ],
            options={'indexes': [models.Index(fields=['revoked_at', 'user'], name='integration_revoked_3fd39f_idx')]},
        ),
        migrations.RunPython(wipe_legacy_calendar_tokens, migrations.RunPython.noop),
    ]
