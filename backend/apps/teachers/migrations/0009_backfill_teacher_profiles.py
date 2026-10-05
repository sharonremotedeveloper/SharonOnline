"""
T1c (data only): every `role=teacher` user without a tutor profile gets one in `applied`, with its baseline audit row
('' -> applied, actor 'system:migration_0009'). From now on registration creates the profile (users/serializers.py), so
this only catches accounts made before T1c. Historical models only; each row is written exactly once (`bulk_create` of the
profiles, then of the audit rows) and the step ends with `SET CONSTRAINTS ALL IMMEDIATE` on PostgreSQL so the deferred
foreign-key checks never meet later DDL (ERR-192).

Reverse: deletes only the profiles this migration created (identified by their 'system:migration_0009' baseline row) that
nobody has touched since: still `applied`, no other audit row, no availability and no booking. A backfilled tutor who has
moved on keeps the profile (the reverse is deliberately not a full inverse; it never destroys tutor history).
"""
import uuid

from django.db import migrations

ACTOR = 'system:migration_0009'


def _check_constraints_now(schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('SET CONSTRAINTS ALL IMMEDIATE')


def backfill(apps, schema_editor):
    User = apps.get_model('users', 'User')
    Profile = apps.get_model('teachers', 'TeacherProfile')
    Change = apps.get_model('teachers', 'TeacherStatusChange')
    missing = User.objects.filter(role='teacher', teacher_profile__isnull=True).values_list('pk', flat=True)
    profiles = [Profile(id=uuid.uuid4(), user_id=pk, status='applied') for pk in missing.iterator()]
    Profile.objects.bulk_create(profiles, batch_size=500)
    Change.objects.bulk_create(
        [Change(teacher_id=p.id, from_status='', to_status='applied', actor=ACTOR, reason='baseline', reviewed_assets={})
         for p in profiles], batch_size=500)
    _check_constraints_now(schema_editor)


def remove_untouched_backfill(apps, schema_editor):
    Profile = apps.get_model('teachers', 'TeacherProfile')
    Change = apps.get_model('teachers', 'TeacherStatusChange')
    ours = Change.objects.filter(actor=ACTOR, from_status='').values_list('teacher_id', flat=True)
    touched = Change.objects.exclude(actor=ACTOR).values_list('teacher_id', flat=True)
    Profile.objects.filter(pk__in=ours, status='applied').exclude(pk__in=touched).filter(
        bookings__isnull=True, availabilities__isnull=True).delete()
    _check_constraints_now(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_grace_failure_runbook'),
        ('teachers', '0008_generated_flags'),
    ]

    operations = [
        migrations.RunPython(backfill, remove_untouched_backfill),
    ]
