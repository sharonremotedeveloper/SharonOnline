"""
T1a: teachers 0007 (status + audit table + data mapping) and 0008 (GeneratedField flags + CHECK constraint), round trip on
a populated database; plus the Postgres-only lock behaviour of the service (plan §5: every new select_for_update and data
migration has a Postgres-marked test; CI runs them in the `postgres-ledger` job with `-m postgres`).
"""
import threading

import pytest
from django.db import connection, transaction

from migration_helpers import _migrate, apps_at, latest_targets

TEACHERS_BEFORE, TEACHERS_AFTER = ('teachers', '0006_teacherstrike'), ('teachers', '0008_generated_flags')


def _targets(teachers):
    """Every other app stays on its latest migration (so the historical User matches the real users table)."""
    return [t for t in latest_targets() if t[0] != 'teachers'] + [teachers]
# (is_verified, is_active) on the old schema -> status after 0007 (plan §3.1 migration mapping).
FORWARD = {(True, True): 'approved', (False, False): 'rejected', (False, True): 'applied', (True, False): 'suspended'}
# status -> (is_verified, is_active) after migrating back to 0006.
BACKWARD = {'approved': (True, True), 'suspended': (True, False), 'rejected': (False, False), 'applied': (False, True),
            'in_review': (False, True)}


def _build(old_apps):
    User = old_apps.get_model('users', 'User')
    Profile = old_apps.get_model('teachers', 'TeacherProfile')
    for n, (verified, active) in enumerate(FORWARD):
        user = User.objects.create(username=f'mig_{n}', email=f'mig_{n}@example.test', password='!', role='teacher')
        Profile.objects.create(user=user, headline=f'{verified}-{active}', is_verified=verified, is_active=active)


def _round_trip():
    before, after = _targets(TEACHERS_BEFORE), _targets(TEACHERS_AFTER)
    try:
        _migrate(before)
        _build(apps_at(before))
        _migrate(after)
        new = apps_at(after)
        Profile = new.get_model('teachers', 'TeacherProfile')
        Change = new.get_model('teachers', 'TeacherStatusChange')
        for (verified, active), status in FORWARD.items():
            p = Profile.objects.get(headline=f'{verified}-{active}')
            assert (p.status, p.is_verified, p.is_active) == (status, verified, active)
            # vetted tutors (approved, and suspended ones that were live) are grandfathered as trained
            assert (p.training_completed_at is not None) == (status in ('approved', 'suspended'))
            change = Change.objects.get(teacher=p)
            assert (change.from_status, change.to_status, change.actor) == ('', status, 'system:migration_0007')
        Profile.objects.filter(headline='False-True').update(status='in_review')
        expected = {'True-True': BACKWARD['approved'], 'False-False': BACKWARD['rejected'],
                    'True-False': BACKWARD['suspended'], 'False-True': BACKWARD['in_review']}
        middle = _targets(('teachers', '0007_teacher_status'))     # 0008 reversed alone must already restore the booleans
        _migrate(middle)
        at_0007 = apps_at(middle).get_model('teachers', 'TeacherProfile')
        assert {p.headline: (p.is_verified, p.is_active) for p in at_0007.objects.all()} == expected
        _migrate(before)
        old = apps_at(before).get_model('teachers', 'TeacherProfile')
        assert {p.headline: (p.is_verified, p.is_active) for p in old.objects.all()} == expected
        assert 'status' not in {f.name for f in old._meta.get_fields()}
    finally:
        _migrate(latest_targets())


@pytest.mark.django_db(transaction=True)
def test_migration_round_trip():
    _round_trip()


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_migration_round_trip_on_postgres():
    if connection.vendor != 'postgresql':
        pytest.skip('PostgreSQL migration round trip')
    _round_trip()


# ------------------------------------------------------------------ Postgres lock behaviour
def _pg_only():
    if connection.vendor != 'postgresql':
        pytest.skip('PostgreSQL row-lock test')


def _in_thread(fn, *args):
    from django.db import connections
    outcome = {}

    def run():
        try:
            outcome['value'] = fn(*args)
        except BaseException as exc:          # surfaced by the asserting caller
            outcome['error'] = exc
        finally:
            connections.close_all()
    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_suspensions_write_one_audit_row():
    _pg_only()
    import factories as f
    from apps.teachers.models import TeacherProfile, TeacherStatusChange
    from apps.teachers.vetting import transition_teacher
    tutor = f.make_teacher_profile(status='approved')
    barrier = threading.Barrier(4)

    def suspend():
        barrier.wait()
        return transition_teacher(TeacherProfile.objects.get(pk=tutor.pk), 'suspended', actor='system:test').changed
    runs = [_in_thread(suspend) for _ in range(4)]
    for thread, _ in runs:
        thread.join(30)
    outcomes = [outcome for _, outcome in runs]
    assert all('error' not in o for o in outcomes), outcomes
    assert sorted(o['value'] for o in outcomes) == [False, False, False, True]
    assert TeacherStatusChange.objects.filter(teacher=tutor).count() == 1


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_the_service_locks_the_tutor_row_and_never_a_booking():
    _pg_only()
    from django.test.utils import CaptureQueriesContext
    import factories as f
    from apps.bookings.models import Booking
    from apps.teachers.vetting import transition_teacher
    tutor = f.make_teacher_profile(status='approved')
    f.make_booking(teacher=tutor, status=Booking.Status.CONFIRMED, offset_hours=48)
    with CaptureQueriesContext(connection) as ctx:
        transition_teacher(tutor, 'suspended', actor='system:test')
    sql = [q['sql'] for q in ctx.captured_queries]
    assert any('teachers_teacherprofile' in s and 'FOR UPDATE' in s for s in sql)
    assert not any('bookings_booking' in s and 'FOR UPDATE' in s for s in sql)


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_a_suspension_does_not_wait_for_a_held_booking_lock():
    """Lock order is booking -> tutor (cancel / memo / no-show paths). The service must never take them the other way round."""
    _pg_only()
    import factories as f
    from apps.bookings.models import Booking
    from apps.teachers.models import TeacherStrike
    from apps.teachers.strikes import add_strike
    from apps.teachers.vetting import transition_teacher
    tutor = f.make_teacher_profile(status='approved')
    booking = f.make_booking(teacher=tutor, status=Booking.Status.CONFIRMED, offset_hours=48)
    locked, release = threading.Event(), threading.Event()

    def hold_booking_then_strike():
        with transaction.atomic():
            row = Booking.objects.select_for_update().get(pk=booking.pk)
            locked.set()
            release.wait(30)
            return add_strike(row.teacher, TeacherStrike.Kind.NO_SHOW, booking=row)
    thread, outcome = _in_thread(hold_booking_then_strike)
    assert locked.wait(30)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '5s'")
            assert transition_teacher(tutor, 'suspended', actor='system:test').changed
    finally:
        release.set()
        thread.join(30)
    assert 'error' not in outcome, outcome
    tutor.refresh_from_db()
    assert tutor.status == 'suspended' and tutor.sla_strikes == 1
