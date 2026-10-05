import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('teachers', '0011_availability_timeoff_overrides')]
    operations = [migrations.CreateModel(
        name='TeacherAsset',
        fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('kind', models.CharField(choices=[('avatar', 'Avatar'), ('accent_audio', 'Accent audio'), ('tefl_certificate', 'TEFL certificate'), ('intro_video', 'Intro video'), ('identity_document', 'Identity document')], max_length=32)),
            ('object_key', models.CharField(max_length=512)), ('quarantine_key', models.CharField(blank=True, max_length=512)),
            ('etag', models.CharField(max_length=128)), ('content_type', models.CharField(max_length=128)),
            ('size_bytes', models.PositiveIntegerField()), ('created_at', models.DateTimeField(auto_now_add=True)),
            ('replaced_at', models.DateTimeField(blank=True, null=True)),
            ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assets', to='teachers.teacherprofile')),
        ],
        options={'indexes': [models.Index(fields=['teacher', 'kind', 'replaced_at'], name='teachers_te_teacher_d9a03c_idx')],
                 'constraints': [models.UniqueConstraint(fields=('teacher', 'kind', 'etag'), name='uniq_teacher_asset_etag')]},
    ), migrations.CreateModel(
        name='PrivateAssetAccessAudit',
        fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)), ('object_key', models.CharField(max_length=512)),
            ('action', models.CharField(default='download', max_length=32)), ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='users.user')),
            ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='private_asset_accesses', to='teachers.teacherprofile')),
        ],
    )]
