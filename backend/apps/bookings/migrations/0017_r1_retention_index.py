from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('bookings', '0016_hostlinkissue')]
    operations = [migrations.AddIndex(
        model_name='attendanceaudit',
        index=models.Index(fields=['created_at', 'id'], name='attendance_created_id_idx'),
    )]
