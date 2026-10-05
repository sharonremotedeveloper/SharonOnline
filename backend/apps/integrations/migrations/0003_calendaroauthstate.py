from django.db import migrations, models
import django.conf
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('integrations', '0002_g1_calendar_t3_access_audit')]

    operations = [migrations.CreateModel(
        name='CalendarOAuthState',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('state_hash', models.CharField(max_length=64, unique=True)),
            ('expires_at', models.DateTimeField()),
            ('used_at', models.DateTimeField(blank=True, null=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=django.conf.settings.AUTH_USER_MODEL)),
        ],
        options={'indexes': [models.Index(fields=['user', 'expires_at'], name='gcal_state_user_exp_idx')]},
    )]
