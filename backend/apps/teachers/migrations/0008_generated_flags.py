"""
T1a step 2 of 2: `is_verified` / `is_active` become STORED GeneratedFields of `status` (plan §3.1 truth table) and the
database refuses an unknown status. AlterField to a GeneratedField is not supported, hence RemoveField + AddField.

Reverse: the generated columns are dropped, plain boolean columns come back with their old defaults, and the first
operation (a no-op forwards) recomputes them from `status` so no tutor's state is lost before 0007's own reverse runs.
"""
from django.db import migrations, models
from django.db.models import Case, Q, Value, When

STATUS_VALUES = ('applied', 'submitted', 'in_review', 'approved', 'changes_requested', 'rejected', 'suspended')
VERIFIED_STATUSES = ('approved', 'suspended')
ACTIVE_STATUSES = ('applied', 'submitted', 'in_review', 'changes_requested', 'approved')


def restore_booleans(apps, schema_editor):
    """One UPDATE per row: on PostgreSQL a second update of a row already changed in this transaction queues deferred
    foreign-key checks, and the index on the restored column (created at the end of this migration) then fails with
    "pending trigger events" (ERR-192, found by the CI Postgres job)."""
    Profile = apps.get_model('teachers', 'TeacherProfile')
    Profile.objects.update(
        is_verified=Case(When(status__in=VERIFIED_STATUSES, then=Value(True)), default=Value(False)),
        is_active=Case(When(status__in=ACTIVE_STATUSES, then=Value(True)), default=Value(False)),
    )
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('SET CONSTRAINTS ALL IMMEDIATE')    # nothing may stay pending before the deferred DDL


class Migration(migrations.Migration):

    dependencies = [
        ('teachers', '0007_teacher_status'),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, restore_booleans),
        migrations.RemoveField(model_name='teacherprofile', name='is_verified'),
        migrations.RemoveField(model_name='teacherprofile', name='is_active'),
        migrations.AddField(
            model_name='teacherprofile',
            name='is_verified',
            field=models.GeneratedField(
                db_index=True, db_persist=True,
                expression=Case(When(status__in=VERIFIED_STATUSES, then=Value(True)), default=Value(False)),
                output_field=models.BooleanField()),
        ),
        migrations.AddField(
            model_name='teacherprofile',
            name='is_active',
            field=models.GeneratedField(
                db_index=True, db_persist=True,
                expression=Case(When(status__in=ACTIVE_STATUSES, then=Value(True)), default=Value(False)),
                output_field=models.BooleanField()),
        ),
        migrations.AddConstraint(
            model_name='teacherprofile',
            constraint=models.CheckConstraint(condition=Q(status__in=STATUS_VALUES), name='teacherprofile_status_valid'),
        ),
    ]
