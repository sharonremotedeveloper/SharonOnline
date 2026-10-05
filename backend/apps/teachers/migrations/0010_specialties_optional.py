"""
T1c: `TeacherProfile.specialties` may be empty (`blank=True`). A tutor created at signup has no tags yet, and the Django admin
form rejected `[]` (ERR-158). No database change (blank is form/validation metadata only); kept apart from the 0009 data step.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teachers', '0009_backfill_teacher_profiles'),
    ]

    operations = [
        migrations.AlterField(
            model_name='teacherprofile',
            name='specialties',
            field=models.JSONField(blank=True, default=list,
                                   help_text="List of tags: ['FreeTalk', 'Business English', 'Daily News', 'TOEIC']"),
        ),
    ]
