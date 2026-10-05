"""
T1c: teachers 0009 backfills a tutor profile (`applied`, baseline audit row, actor `system:migration_0009`) for every
`role=teacher` user without one; the reverse removes only the profiles it created that nobody has touched since.
Round trip on SQLite and (CI, `-m postgres`) on Postgres (plan §5: every data migration has a Postgres-marked test).
"""
import importlib
from datetime import time

import pytest
from django.db import connection

from migration_helpers import _migrate, apps_at, latest_targets

BEFORE, AFTER = ('teachers', '0008_generated_flags'), ('teachers', '0009_backfill_teacher_profiles')
ACTOR = 'system:migration_0009'
# Backfilled tutors that later got data of their own WITHOUT any audit row, availability or booking (QA M1): a tutor edit
# through /teachers/me/, a power-backup declaration, a staff-set Eskom area, an uploaded photo, a strike row.
EDITED = {
    'edited_tutor': {'bio': 'I teach business English.'},
    'power_tutor': {'has_inverter_backup': True},
    'area_tutor': {'eskom_area_id': 'eskde-10-fourways'},
    'photo_tutor': {'avatar_url': 'https://assets.example.test/a.jpg'},
    'tagged_tutor': {'specialties': ['TOEIC']},
}
RELATED = 'struck_tutor'       # a related row of another kind (TeacherStrike), no field edits


def _migration_module():
    return importlib.import_module('apps.teachers.migrations.0009_backfill_teacher_profiles')


def _targets(teachers):
    return [t for t in latest_targets() if t[0] != 'teachers'] + [teachers]


def _build(old_apps):
    User = old_apps.get_model('users', 'User')
    Profile = old_apps.get_model('teachers', 'TeacherProfile')
    for name, role in [('bare_tutor', 'teacher'), ('touched_tutor', 'teacher'), ('busy_tutor', 'teacher'),
                       ('noted_tutor', 'teacher'), ('student', 'student'), ('staff', 'admin')] + [
                           (name, 'teacher') for name in [*EDITED, RELATED]]:
        User.objects.create(username=name, email=f'{name}@example.test', password='!', role=role)
    has = User.objects.create(username='has_profile', email='has@example.test', password='!', role='teacher')
    Profile.objects.create(user=has, headline='existing', status='approved')
    # An older applicant (still `applied`, no 0009 audit row): the reverse must never treat it as its own.
    old = User.objects.create(username='old_applicant', email='old@example.test', password='!', role='teacher')
    Profile.objects.create(user=old, headline='older', status='applied')


def _round_trip():
    before, after = _targets(BEFORE), _targets(AFTER)
    try:
        _migrate(before)
        _build(apps_at(before))
        _migrate(after)
        new = apps_at(after)
        Profile = new.get_model('teachers', 'TeacherProfile')
        Change = new.get_model('teachers', 'TeacherStatusChange')
        backfilled = ['bare_tutor', 'busy_tutor', 'noted_tutor', 'touched_tutor', *EDITED, RELATED]
        created = Profile.objects.filter(user__username__in=backfilled)
        assert sorted(p.status for p in created) == ['applied'] * len(backfilled)
        assert not Profile.objects.filter(user__username__in=['student', 'staff']).exists()
        assert Profile.objects.get(user__username='has_profile').headline == 'existing'
        for p in created:
            change = Change.objects.get(teacher=p)
            assert (change.from_status, change.to_status, change.actor) == ('', 'applied', ACTOR)
        assert not Change.objects.filter(teacher__user__username='has_profile', actor=ACTOR).exists()
        # Someone moved one of the backfilled tutors on: the reverse must not delete that history.
        touched = Profile.objects.get(user__username='touched_tutor')
        Profile.objects.filter(pk=touched.pk).update(status='submitted')
        Change.objects.create(teacher=touched, from_status='applied', to_status='submitted', actor='user:touched_tutor',
                              reviewed_assets={})
        # Still `applied` but with history of its own (another audit row), or with availability: kept as well.
        noted = Profile.objects.get(user__username='noted_tutor')
        Change.objects.create(teacher=noted, from_status='applied', to_status='applied', actor='user:admin', reviewed_assets={})
        busy = Profile.objects.get(user__username='busy_tutor')
        new.get_model('teachers', 'TeacherAvailability').objects.create(
            teacher=busy, day_of_week=0, start_time=time(9, 0), end_time=time(10, 0), is_active=True)
        # Data entered later without any audit trace (QA M1): kept.
        for name, fields in EDITED.items():
            Profile.objects.filter(user__username=name).update(**fields)
        assert Profile.objects.get(user__username='bare_tutor').bio == ''      # the one that really is untouched
        new.get_model('teachers', 'TeacherStrike').objects.create(
            teacher=Profile.objects.get(user__username=RELATED), kind='no_show')
        _migrate(before)
        old = apps_at(before).get_model('teachers', 'TeacherProfile')
        kept = sorted(['busy_tutor', 'has_profile', 'noted_tutor', 'old_applicant', 'touched_tutor', *EDITED, RELATED])
        assert sorted(old.objects.values_list('user__username', flat=True)) == kept
        # Forward again is idempotent: only the missing one comes back, nobody gets a second profile.
        _migrate(after)
        again = apps_at(after).get_model('teachers', 'TeacherProfile')
        assert sorted(again.objects.values_list('user__username', flat=True)) == sorted(['bare_tutor', *kept])
    finally:
        _migrate(latest_targets())


@pytest.mark.django_db(transaction=True)
def test_backfill_round_trip():
    _round_trip()


@pytest.mark.django_db
def test_backfill_defaults_cover_every_data_field_of_the_profile_at_0009():
    """The reverse compares every tutor-editable / staff-set / derived column with the value the backfill wrote; the list
    lives next to the backfill (BACKFILL_DEFAULTS) and must name every concrete column but the identity / lifecycle ones."""
    module = _migration_module()
    Profile = apps_at(_targets(AFTER)).get_model('teachers', 'TeacherProfile')
    data_fields = {f.name for f in Profile._meta.concrete_fields if not f.generated} - set(module.IDENTITY_FIELDS)
    assert set(module.BACKFILL_DEFAULTS) == data_fields
    assert set(module.IDENTITY_FIELDS) == {'id', 'user', 'status', 'created_at', 'updated_at'}


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_backfill_round_trip_on_postgres():
    if connection.vendor != 'postgresql':
        pytest.skip('PostgreSQL migration round trip')
    _round_trip()
