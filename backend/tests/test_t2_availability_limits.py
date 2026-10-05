"""Slice T2: boundaries, limits, lock calls and throttling of the availability endpoints (split from test_t2_availability_api.py)."""
from datetime import datetime, timedelta, timezone as dt_tz

import pytest

from t2_helpers import BASE, SAST, client, lesson, monday_row, next_weekday_utc, row

pytestmark = pytest.mark.django_db


@pytest.fixture
def tutor(teacher_user):
    return teacher_user


@pytest.fixture
def me(tutor):
    return client(tutor.user)


class TestBoundaries:
    def test_a_window_of_exactly_one_lesson_is_accepted(self, me, tutor):
        assert me.post(f'{BASE}/manage/', row(day=2, start='09:00', end='09:25'), format='json').status_code == 201

    def test_the_matrix_may_hold_exactly_the_row_limit(self, me, tutor, monkeypatch):
        import apps.teachers.services.availability as svc
        monkeypatch.setattr(svc, 'MAX_AVAILABILITY_ROWS', 2)
        assert me.put(f'{BASE}/replace/', {'rows': [row(day=1), row(day=2)]}, format='json').status_code == 200

    def test_touching_matrix_rows_and_inactive_overlaps_are_fine(self, me, tutor):
        rows = [row(day=1, start='09:00', end='12:00'), row(day=1, start='12:00', end='13:00'),
                row(day=1, start='11:00', end='12:30', is_active=False)]
        assert me.put(f'{BASE}/replace/', {'rows': rows}, format='json').status_code == 200

    def test_an_override_for_today_and_for_the_last_allowed_day_is_accepted(self, me, tutor):
        today = datetime.now(SAST).date()
        for day in (today, today + timedelta(days=366)):
            res = me.post(f'{BASE}/overrides/', {'date': day.isoformat(), 'kind': 'closed'}, format='json')
            assert res.status_code == 201, res.json()

    def test_time_off_of_zero_length_is_rejected(self, me, tutor):
        moment = (datetime.now(dt_tz.utc) + timedelta(days=2)).isoformat()
        res = me.post(f'{BASE}/time-off/', {'start_utc': moment, 'end_utc': moment}, format='json')
        assert res.status_code == 400

    def test_deactivating_a_row_under_a_lesson_is_a_conflict(self, me, tutor, student_user):
        lesson(tutor, student_user, next_weekday_utc(0, 10))
        res = me.patch(f'{BASE}/manage/{monday_row(tutor).id}/', {'is_active': False}, format='json')
        assert res.status_code == 409 and res.json()['code'] == 'availability_conflicts'

    def test_a_lesson_spanning_two_touching_rows_is_covered(self, me, tutor, student_user):
        lesson(tutor, student_user, next_weekday_utc(0, 11, 45))                      # 11:45-12:10
        res = me.put(f'{BASE}/replace/', {'rows': [row(start='09:00', end='12:00'), row(start='12:00', end='13:00')]}, format='json')
        assert res.status_code == 200 and res.json()['conflicts'] == []

    def test_lessons_flush_with_the_window_edges_are_covered(self, me, tutor, student_user):
        lesson(tutor, student_user, next_weekday_utc(0, 9, 0))                         # starts exactly when the window opens
        lesson(tutor, student_user, next_weekday_utc(0, 11, 35))                       # ends exactly when it closes
        res = me.put(f'{BASE}/replace/', {'rows': [row(start='09:00', end='12:00')]}, format='json')
        assert res.status_code == 200 and res.json()['conflicts'] == []

    def test_the_time_off_and_override_limits_apply(self, me, tutor, monkeypatch):
        import apps.teachers.services.availability as svc
        monkeypatch.setattr(svc, 'MAX_TIME_OFF_ROWS', 1)
        monkeypatch.setattr(svc, 'MAX_OVERRIDE_ROWS', 1)
        start = datetime.now(dt_tz.utc) + timedelta(days=5)
        body = {'start_utc': start.isoformat(), 'end_utc': (start + timedelta(days=1)).isoformat()}
        assert me.post(f'{BASE}/time-off/', body, format='json').status_code == 201
        assert me.post(f'{BASE}/time-off/', body, format='json').status_code == 400
        day = (datetime.now(SAST) + timedelta(days=5)).date().isoformat()
        assert me.post(f'{BASE}/overrides/', {'date': day, 'kind': 'closed'}, format='json').status_code == 201
        assert me.post(f'{BASE}/overrides/', {'date': day, 'kind': 'closed'}, format='json').status_code == 400


class TestTutorRowIsLocked:
    """SQLite ignores FOR UPDATE, so assert the call; tests/test_t2_postgres.py checks the SQL and the behaviour on Postgres."""

    def _spy(self, monkeypatch):
        from django.db.models import QuerySet
        calls = []
        original = QuerySet.select_for_update

        def spy(self, *args, **kwargs):
            calls.append((self.model.__name__, kwargs))
            return original(self, *args, **kwargs)
        monkeypatch.setattr(QuerySet, 'select_for_update', spy)
        return calls

    def test_every_write_locks_the_tutor_row_only(self, me, tutor, monkeypatch):
        calls = self._spy(monkeypatch)
        r = monday_row(tutor)
        start = datetime.now(dt_tz.utc) + timedelta(days=4)
        day = (datetime.now(SAST) + timedelta(days=4)).date().isoformat()
        responses = [
            me.post(f'{BASE}/manage/', row(day=3), format='json'),
            me.patch(f'{BASE}/manage/{r.id}/', {'end_time': '11:00'}, format='json'),
            me.put(f'{BASE}/replace/', {'rows': [row(day=2)]}, format='json'),
            me.post(f'{BASE}/time-off/', {'start_utc': start.isoformat(), 'end_utc': (start + timedelta(days=1)).isoformat()}, format='json'),
            me.post(f'{BASE}/overrides/', {'date': day, 'kind': 'closed'}, format='json'),
        ]
        assert [x.status_code for x in responses] == [201, 200, 200, 201, 201]
        assert len(calls) == 5 and all(model == 'TeacherProfile' and kw == {'of': ('self',)} for model, kw in calls), calls


def test_every_new_endpoint_is_throttled(settings):
    from django.urls import resolve
    assert 'availability' in settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
    for path in (f'{BASE}/manage/', f'{BASE}/replace/', f'{BASE}/time-off/', f'{BASE}/overrides/'):
        view = resolve(path).func.cls
        assert view.throttle_scope == 'availability' and view.throttle_classes, path
