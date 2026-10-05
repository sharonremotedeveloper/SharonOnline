"""
Slice T2: database-level behaviour of the availability tables (CHECK constraints, migration 0011 round trip) and the
Postgres-only locking of the atomic weekly replace. The lock tests are skipped on SQLite (CI runs them with `-m postgres`).
"""
import threading
from datetime import date, datetime, time, timezone as dt_tz

import pytest
from django.db import IntegrityError, connection, transaction

import factories as f
from apps.teachers.models import TeacherAvailability, TeacherDateOverride, TeacherTimeOff
from migration_helpers import _migrate, apps_at, latest_targets

BEFORE = ('teachers', '0010_specialties_optional')      # the leaf before T2 (T1c)
AFTER = ('teachers', '0011_availability_timeoff_overrides')


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


# ------------------------------------------------------------------ CHECK constraints (every backend)
@pytest.mark.django_db
class TestConstraints:
    def test_time_off_must_end_after_it_starts(self):
        tutor = f.make_teacher_profile()
        now = datetime.now(dt_tz.utc)
        with pytest.raises(IntegrityError), transaction.atomic():
            TeacherTimeOff.objects.create(teacher=tutor, start_utc=now, end_utc=now)

    def test_an_open_override_needs_hours(self):
        tutor = f.make_teacher_profile()
        with pytest.raises(IntegrityError), transaction.atomic():
            TeacherDateOverride.objects.create(teacher=tutor, date=date(2027, 1, 4), kind='open')

    def test_override_hours_come_as_a_pair_and_in_order(self):
        tutor = f.make_teacher_profile()
        for kwargs in ({'start_time': time(9, 0)}, {'end_time': time(9, 0)}, {'start_time': time(10, 0), 'end_time': time(9, 0)}):
            with pytest.raises(IntegrityError), transaction.atomic():
                TeacherDateOverride.objects.create(teacher=tutor, date=date(2027, 1, 4), kind='closed', **kwargs)

    def test_override_kind_is_restricted(self):
        tutor = f.make_teacher_profile()
        with pytest.raises(IntegrityError), transaction.atomic():
            TeacherDateOverride.objects.create(teacher=tutor, date=date(2027, 1, 4), kind='maybe')

    def test_valid_rows_are_accepted(self):
        tutor = f.make_teacher_profile()
        TeacherDateOverride.objects.create(teacher=tutor, date=date(2027, 1, 4), kind='closed')
        TeacherDateOverride.objects.create(teacher=tutor, date=date(2027, 1, 4), kind='open', start_time=time(9, 0), end_time=time(10, 0))


# ------------------------------------------------------------------ migration 0011
def _round_trip():
    before, after = [t for t in latest_targets() if t[0] != 'teachers'] + [BEFORE], [t for t in latest_targets() if t[0] != 'teachers'] + [AFTER]
    try:
        _migrate(before)
        old = apps_at(before)
        User, Profile, Avail = (old.get_model('users', 'User'), old.get_model('teachers', 'TeacherProfile'),
                                old.get_model('teachers', 'TeacherAvailability'))
        user = User.objects.create(username='mig_t2', email='mig_t2@example.test', password='!', role='teacher')
        profile = Profile.objects.create(user=user, status='approved')
        Avail.objects.create(teacher=profile, day_of_week=0, start_time=time(9, 0), end_time=time(12, 0))
        _migrate(after)
        new = apps_at(after)
        assert new.get_model('teachers', 'TeacherAvailability').objects.count() == 1          # data untouched
        new.get_model('teachers', 'TeacherTimeOff').objects.create(
            teacher_id=profile.pk, start_utc=datetime(2027, 1, 1, tzinfo=dt_tz.utc), end_utc=datetime(2027, 1, 2, tzinfo=dt_tz.utc))
        new.get_model('teachers', 'TeacherDateOverride').objects.create(teacher_id=profile.pk, date=date(2027, 1, 4), kind='closed')
        _migrate(before)                                                                      # reversible
        assert apps_at(before).get_model('teachers', 'TeacherAvailability').objects.count() == 1
        with pytest.raises(LookupError):
            apps_at(before).get_model('teachers', 'TeacherTimeOff')
    finally:
        _migrate(latest_targets())


@pytest.mark.django_db(transaction=True)
def test_migration_0011_round_trip():
    _round_trip()


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_migration_0011_round_trip_on_postgres():
    _pg_only()
    _round_trip()


# ------------------------------------------------------------------ the atomic replace under concurrency (Postgres)
@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_replaces_leave_exactly_one_whole_matrix():
    _pg_only()
    from apps.teachers.models import TeacherProfile
    from apps.teachers.services.availability import replace_weekly_matrix
    tutor = f.make_teacher_profile(availability=False)
    matrices = [[{'day_of_week': d, 'start_time': time(8 + n, 0), 'end_time': time(9 + n, 0)} for d in range(3)] for n in range(4)]
    barrier = threading.Barrier(4)

    def replace(rows):
        barrier.wait()
        return replace_weekly_matrix(TeacherProfile.objects.get(pk=tutor.pk), rows, acknowledged=True)
    runs = [_in_thread(replace, m) for m in matrices]
    for thread, _ in runs:
        thread.join(60)
    assert all('error' not in o for _, o in runs), [o for _, o in runs]
    final = sorted(TeacherAvailability.objects.filter(teacher=tutor).values_list('day_of_week', 'start_time', 'end_time'))
    assert final in [sorted((r['day_of_week'], r['start_time'], r['end_time']) for r in m) for m in matrices]    # never a mix, never doubled


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_replace_locks_the_tutor_row_and_never_a_booking():
    """Lock order is booking -> tutor everywhere else; the replace reads bookings without locking them."""
    _pg_only()
    from django.test.utils import CaptureQueriesContext
    from apps.bookings.models import Booking
    from apps.teachers.services.availability import replace_weekly_matrix
    tutor = f.make_teacher_profile()
    f.make_booking(teacher=tutor, status=Booking.Status.CONFIRMED, offset_hours=48)
    with CaptureQueriesContext(connection) as ctx:
        replace_weekly_matrix(tutor, [], acknowledged=True)
    sql = [q['sql'] for q in ctx.captured_queries]
    assert any('teachers_teacherprofile' in s and 'FOR UPDATE' in s for s in sql)
    assert not any('bookings_booking' in s and 'FOR UPDATE' in s for s in sql)


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_a_replace_does_not_wait_for_a_held_booking_lock():
    _pg_only()
    from apps.bookings.models import Booking
    from apps.teachers.services.availability import replace_weekly_matrix
    tutor = f.make_teacher_profile()
    booking = f.make_booking(teacher=tutor, status=Booking.Status.CONFIRMED, offset_hours=48)
    locked, release = threading.Event(), threading.Event()

    def hold_booking():
        with transaction.atomic():
            Booking.objects.select_for_update().get(pk=booking.pk)
            locked.set()
            release.wait(30)
    thread, outcome = _in_thread(hold_booking)
    assert locked.wait(30)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '5s'")
            replace_weekly_matrix(tutor, [], acknowledged=True)
    finally:
        release.set()
        thread.join(30)
    assert 'error' not in outcome, outcome
