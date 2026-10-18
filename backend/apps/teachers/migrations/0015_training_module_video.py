"""Wave 2: optional YouTube video on a training module. Expand-only: the column has a database default, so the previous API
release (which does not know the column) can still insert rows while a new release rolls out."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teachers', '0014_t5a_application'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainingmodule',
            name='video_youtube_id',
            field=models.CharField(blank=True, db_default='', default='', help_text='Optional YouTube video (the 11-character id only; set through teachers/training.py::parse_youtube_id).', max_length=11),
        ),
    ]
