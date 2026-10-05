# T2 (PRP 11.6). Additive and reversible: two new tables, no data step. Numbered 0011 because T1c owns 0009/0010.

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teachers', '0010_specialties_optional'),
    ]

    operations = [
        migrations.CreateModel(
            name='TeacherDateOverride',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date', models.DateField(help_text="Date in the teacher's local timezone")),
                ('kind', models.CharField(choices=[('open', 'Extra hours'), ('closed', 'Hours removed')], max_length=10)),
                ('start_time', models.TimeField(blank=True, null=True)),
                ('end_time', models.TimeField(blank=True, null=True)),
                ('reason', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='date_overrides', to='teachers.teacherprofile')),
            ],
            options={
                'ordering': ['date', 'start_time'],
                'indexes': [models.Index(fields=['teacher', 'date'], name='teacher_dateoverride_t_d_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(('kind__in', ['open', 'closed'])), name='teacherdateoverride_kind_valid'), models.CheckConstraint(condition=models.Q(models.Q(('end_time__isnull', True), ('start_time__isnull', True)), models.Q(('end_time__isnull', False), ('start_time__isnull', False), ('start_time__lt', models.F('end_time'))), _connector='OR'), name='teacherdateoverride_hours_pair_ordered'), models.CheckConstraint(condition=models.Q(('kind', 'closed'), ('start_time__isnull', False), _connector='OR'), name='teacherdateoverride_open_needs_hours')],
            },
        ),
        migrations.CreateModel(
            name='TeacherTimeOff',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('start_utc', models.DateTimeField()),
                ('end_utc', models.DateTimeField()),
                ('reason', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='time_off', to='teachers.teacherprofile')),
            ],
            options={
                'ordering': ['start_utc'],
                'indexes': [models.Index(fields=['teacher', 'end_utc'], name='teacher_timeoff_t_end_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(('end_utc__gt', models.F('start_utc'))), name='teachertimeoff_end_after_start')],
            },
        ),
    ]
