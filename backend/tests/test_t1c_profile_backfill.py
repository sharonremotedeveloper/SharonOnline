"""
T1c: teachers 0009 backfills a tutor profile (`applied`, baseline audit row, actor `system:migration_0009`) for every
`role=teacher` user without one; the reverse removes only the profiles it created that nobody has touched since.
Round trip on SQLite and (CI, `-m postgres`) on Postgres (plan §5: every data migration has a Postgres-marked test).
"""
from datetime import time

import pytest
from django.db import connection

from migration_helpers import _migrate, apps_at, latest_targets

BEFORE, AFTER = ('teachers', '0008_generated_flags'), ('teachers', '0009_backfill_teacher_profiles')
ACTOR = 'system:migration_0009'


def _targets(teachers):
    return [t for t in latest_targets() if t[0] != 'teachers'] + [teachers]


def _build(old_apps):
    User = old_apps.get_model('users', 'User')
    Profile = old_apps.get_model('teachers', 'TeacherProfile')
    for name, role in [('bare_tutor', 'teacher'), ('touched_tutor', 'teacher'), ('busy_tutor', 'teacher'),
                       ('noted_tutor', 'teacher'), ('student', 'student'), ('staff', 'admin')]:
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
        backfilled = ['bare_tutor', 'busy_tutor', 'noted_tutor', 'touched_tutor']
        created = Profile.objects.filter(user__username__in=backfilled)
        assert sorted(p.status for p in created) == ['applied'] * 4
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
        _migrate(before)
        old = apps_at(before).get_model('teachers', 'TeacherProfile')
        kept = ['busy_tutor', 'has_profile', 'noted_tutor', 'old_applicant', 'touched_tutor']
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


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_backfill_round_trip_on_postgres():
    if connection.vendor != 'postgresql':
        pytest.skip('PostgreSQL migration round trip')
    _round_trip()
