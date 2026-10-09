"""D5 (docs/DAILY_CO_MIGRATION_PLAN.md): Daily.co is the only video provider; drop the Zoom columns and the Zoom host-link audit."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('bookings', '0017_r1_retention_index')]

    operations = [
        migrations.DeleteModel(name='HostLinkIssue'),
        migrations.RemoveField(model_name='booking', name='zoom_meeting_id'),
        migrations.RemoveField(model_name='booking', name='zoom_join_url'),
        migrations.RemoveField(model_name='booking', name='zoom_start_url'),
        migrations.RemoveField(model_name='booking', name='zoom_password'),
        migrations.RemoveField(model_name='booking', name='zoom_host_user_id'),
        migrations.RemoveField(model_name='attendanceaudit', name='zoom_user_id'),
        migrations.RemoveField(model_name='attendanceaudit', name='registrant_id'),
        migrations.RemoveField(model_name='attendanceaudit', name='host_id'),
        migrations.RemoveConstraint(model_name='attendanceaudit', name='uniq_attendance_session_per_booking'),
        migrations.RenameField(model_name='attendanceaudit', old_name='zoom_session_id', new_name='session_id'),
        migrations.AddConstraint(
            model_name='attendanceaudit',
            constraint=models.UniqueConstraint(
                condition=models.Q(('session_id', ''), _negated=True), fields=('booking', 'session_id'),
                name='uniq_attendance_session_per_booking'),
        ),
    ]
