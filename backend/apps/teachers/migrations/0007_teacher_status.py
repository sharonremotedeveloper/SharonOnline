"""
T1a step 1 of 2: add `TeacherProfile.status` + `training_completed_at` and the TeacherStatusChange audit table, then map the
two old booleans onto a status (plan §3.1, docs/TUTOR_STATUS_MACHINE.md §6). Historical models only.

    (is_verified, is_active)  ->  status        reverse: status -> (is_verified, is_active)
    (True,  True)             ->  approved      approved                                   -> (True,  True)
    (False, False)            ->  rejected      rejected                                   -> (False, False)
    (False, True)             ->  applied       suspended                                  -> (True,  False)
    (True,  False)            ->  suspended     applied|submitted|in_review|changes_requested -> (False, True)

Approved and suspended tutors (both were vetted and live) are grandfathered (`training_completed_at` = migration time) so
the T6 training gate never blocks a live or reinstated tutor. Note: any (is_verified True, is_active False) row maps to
`suspended`, whatever produced it (a strike deactivation, a Django-admin edit, or a reject recorded that way by hand);
the old booleans cannot tell these apart, so staff must review suspended tutors after the deploy. Every profile gets one baseline audit row ('' -> status, actor 'system:migration_0007').
"""
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone

ACTOR = 'system:migration_0007'
FORWARD = {(True, True): 'approved', (False, False): 'rejected', (False, True): 'applied', (True, False): 'suspended'}
BACKWARD = {'approved': (True, True), 'suspended': (True, False), 'rejected': (False, False)}   # others -> (False, True)
# Vetted, once-live tutors count as trained: approved, and suspended (they were approved before the strike/admin action).
GRANDFATHERED = ('approved', 'suspended')
STATUS_CHOICES = [
    ('applied', 'Applied'), ('submitted', 'Submitted for review'), ('in_review', 'In review'), ('approved', 'Approved'),
    ('changes_requested', 'Changes requested'), ('rejected', 'Rejected'), ('suspended', 'Suspended'),
]


def booleans_to_status(apps, schema_editor):
    Profile = apps.get_model('teachers', 'TeacherProfile')
    Change = apps.get_model('teachers', 'TeacherStatusChange')
    now = timezone.now()
    for (verified, active), status in FORWARD.items():
        extra = {'training_completed_at': now} if status in GRANDFATHERED else {}
        Profile.objects.filter(is_verified=verified, is_active=active).update(status=status, **extra)
    rows = [Change(teacher_id=pk, from_status='', to_status=status, actor=ACTOR, reason='baseline', reviewed_assets={})
            for pk, status in Profile.objects.values_list('pk', 'status').iterator()]
    Change.objects.bulk_create(rows, batch_size=500)


def status_to_booleans(apps, schema_editor):
    Profile = apps.get_model('teachers', 'TeacherProfile')
    Profile.objects.exclude(status__in=list(BACKWARD)).update(is_verified=False, is_active=True)
    for status, (verified, active) in BACKWARD.items():
        Profile.objects.filter(status=status).update(is_verified=verified, is_active=active)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('teachers', '0006_teacherstrike'),
    ]

    operations = [
        migrations.AddField(
            model_name='teacherprofile',
            name='status',
            field=models.CharField(choices=STATUS_CHOICES, db_index=True, default='applied', max_length=20),
        ),
        migrations.AddField(
            model_name='teacherprofile',
            name='training_completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='TeacherStatusChange',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('from_status', models.CharField(blank=True, max_length=20)),
                ('to_status', models.CharField(max_length=20)),
                ('actor', models.CharField(help_text="'user:<username>' or a system source such as 'system:strikes'.", max_length=80)),
                ('reason', models.CharField(blank=True, max_length=500)),
                ('rubric', models.JSONField(blank=True, null=True)),
                ('reviewed_assets', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('actor_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='status_changes', to='teachers.teacherprofile')),
            ],
            options={
                'ordering': ['created_at'],
                'indexes': [models.Index(fields=['teacher', 'created_at'], name='teacher_statuschange_t_idx')],
            },
        ),
        migrations.RunPython(booleans_to_status, status_to_booleans),
    ]
