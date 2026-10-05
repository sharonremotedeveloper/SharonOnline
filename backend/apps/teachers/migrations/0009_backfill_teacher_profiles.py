"""
T1c (data only): every `role=teacher` user without a tutor profile gets one in `applied`, with its baseline audit row
('' -> applied, actor 'system:migration_0009'). From now on registration creates the profile (users/serializers.py), so
this only catches accounts made before T1c. Historical models only; each row is written exactly once (`bulk_create` of the
profiles, then of the audit rows) and the step ends with `SET CONSTRAINTS ALL IMMEDIATE` on PostgreSQL so the deferred
foreign-key checks never meet later DDL (ERR-192).

Reverse (QA M1): deleting a profile cascades strikes, dossiers, disputes and memos and orphans stored files, so the reverse
removes a backfilled profile ONLY when nothing has happened to it since:
  * status is still `applied` and its only audit row is the 0009 baseline row;
  * every column in BACKFILL_DEFAULTS (every tutor-editable, staff-set or derived column) still holds the value the backfill
    wrote (a test fails when a column is added to the model without being listed here or in IDENTITY_FIELDS);
  * no row in ANY reverse relation points at it (checked generically through `_meta.related_objects`, so a model added later
    is covered), apart from that one baseline audit row.
Anything else is kept. The reverse is deliberately not a full inverse; it never destroys tutor data or history.
"""
import uuid
from decimal import Decimal

from django.db import migrations

ACTOR = 'system:migration_0009'

# Columns that identify or drive the lifecycle of the row (not tutor data): id, owner, status (checked separately), stamps.
IDENTITY_FIELDS = ('id', 'user', 'status', 'created_at', 'updated_at')
# Every other column and the value the backfill leaves in it (the model defaults). Keep in step with TeacherProfile.
BACKFILL_DEFAULTS = {
    'bio': '', 'headline': '', 'accent': 'ZA', 'intro_video_url': '', 'intro_video_thumbnail': '', 'avatar_image': '',
    'avatar_url': '', 'intro_audio_file': '', 'intro_audio_url': '', 'tefl_certificate_file': '', 'tefl_certificate_url': '',
    'rating_avg': Decimal('5.00'), 'rating_count': 0, 'price_per_25min_usd': Decimal('9.00'), 'specialties': [],
    'training_completed_at': None, 'sla_strikes': 0, 'eskom_area_id': '', 'has_inverter_backup': False,
    'has_lte_failover': False,
}


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


def _blank(value):
    return value in (None, '') or (hasattr(value, 'name') and not value.name)


def _at_defaults(profile) -> bool:
    for name, default in BACKFILL_DEFAULTS.items():
        value = getattr(profile, name)
        if _blank(default):
            if not _blank(value):
                return False
        elif value != default:
            return False
    return True


def _has_other_rows(profile, Change) -> bool:
    """Any row in any reverse relation, except the single 0009 baseline audit row."""
    for rel in profile._meta.related_objects:
        rows = rel.related_model._default_manager.filter(**{rel.field.name: profile})
        if rel.related_model is Change:
            rows = rows.exclude(actor=ACTOR, from_status='')
        if rows.exists():
            return True
    return False


def remove_untouched_backfill(apps, schema_editor):
    Profile = apps.get_model('teachers', 'TeacherProfile')
    Change = apps.get_model('teachers', 'TeacherStatusChange')
    ours = Change.objects.filter(actor=ACTOR, from_status='').values_list('teacher_id', flat=True)
    removable = [p.pk for p in Profile.objects.filter(pk__in=ours, status='applied').iterator()
                 if _at_defaults(p) and not _has_other_rows(p, Change)]
    Profile.objects.filter(pk__in=removable).delete()
    _check_constraints_now(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_grace_failure_runbook'),
        ('teachers', '0008_generated_flags'),
    ]

    operations = [
        migrations.RunPython(backfill, remove_untouched_backfill),
    ]
