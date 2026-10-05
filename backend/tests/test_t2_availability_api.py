"""
Slice T2 (PRP 11.6): availability CRUD, the atomic weekly replace, time off, date overrides and the conflict contract.

Contract (docs/UI_VERTICAL_SLICE_MIGRATION_PLAN.md, Slice 7): every change that can strand a confirmed lesson answers 409
{code: 'availability_conflicts', conflicts: [...]} and changes nothing until the tutor resends it with
`acknowledge_conflicts: true`; an acknowledged change is applied, the lessons stay CONFIRMED (editing availability never
cancels a booking) and the same list comes back so the tutor can cancel through the penalty path.
"""
from datetime import datetime, time, timedelta, timezone as dt_tz
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

import factories as f
from apps.bookings.models import Booking
from apps.teachers.models import TeacherAvailability, TeacherDateOverride, TeacherTimeOff
from t2_helpers import BASE, SAST, client, lesson, monday_row, next_weekday_utc, row

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def tutor(teacher_user):
    """teacher_user already has Monday 09:00-12:00 SAST."""
    return teacher_user


@pytest.fixture
def me(tutor):
    return client(tutor.user)


# ------------------------------------------------------------------ list / create
class TestListAndCreate:
    def test_the_list_is_paginated_and_owner_only(self, me, tutor):
        other = f.make_teacher_profile()
        TeacherAvailability.objects.create(teacher=other, day_of_week=3, start_time=time(8, 0), end_time=time(9, 0))
        body = me.get(f'{BASE}/manage/').json()
        assert body['count'] == 1 and [r['day_of_week'] for r in body['results']] == [0]
        assert set(body['results'][0]) == {'id', 'day_of_week', 'start_time', 'end_time', 'is_active'}

    def test_create_a_row(self, me, tutor):
        res = me.post(f'{BASE}/manage/', row(day=2, start='13:00', end='15:00'), format='json')
        assert res.status_code == 201 and res.json()['day_of_week'] == 2
        assert TeacherAvailability.objects.filter(teacher=tutor, day_of_week=2).count() == 1

    @pytest.mark.parametrize('payload,field', [
        (row(start='12:00', end='09:00'), 'end_time'),
        (row(start='09:00', end='09:00'), 'end_time'),
        (row(start='09:00', end='09:20'), 'end_time'),             # shorter than one 25-minute lesson
        (row(day=7), 'day_of_week'),
        (row(day=-1), 'day_of_week'),
        (row(start='09:00:30', end='12:00'), 'start_time'),       # whole minutes only
    ])
    def test_invalid_rows_are_rejected(self, me, tutor, payload, field):
        res = me.post(f'{BASE}/manage/', payload, format='json')
        assert res.status_code == 400 and field in res.json()

    def test_an_overlap_with_an_active_row_of_the_same_day_is_rejected(self, me, tutor):
        res = me.post(f'{BASE}/manage/', row(start='11:00', end='13:00'), format='json')
        assert res.status_code == 400 and 'overlap' in str(res.json()).lower()

    def test_touching_rows_and_other_days_are_fine(self, me, tutor):
        assert me.post(f'{BASE}/manage/', row(start='12:00', end='13:00'), format='json').status_code == 201
        assert me.post(f'{BASE}/manage/', row(day=1, start='09:00', end='12:00'), format='json').status_code == 201

    def test_an_inactive_row_may_overlap(self, me, tutor):
        assert me.post(f'{BASE}/manage/', row(start='10:00', end='11:00', is_active=False), format='json').status_code == 201

    def test_a_tutor_cannot_hold_more_than_the_row_limit(self, me, tutor, monkeypatch):
        import apps.teachers.services.availability as svc
        monkeypatch.setattr(svc, 'MAX_AVAILABILITY_ROWS', 2)
        assert me.post(f'{BASE}/manage/', row(day=1), format='json').status_code == 201
        res = me.post(f'{BASE}/manage/', row(day=2), format='json')
        assert res.status_code == 400 and 'at most' in str(res.json()).lower()

    def test_a_student_and_anonymous_callers_are_refused(self, student_user):
        assert client(student_user).get(f'{BASE}/manage/').status_code == 403
        assert APIClient().get(f'{BASE}/manage/').status_code == 401


# ------------------------------------------------------------------ PATCH / DELETE one row
class TestPatchAndDelete:
    def test_patch_a_row(self, me, tutor):
        r = monday_row(tutor)
        res = me.patch(f'{BASE}/manage/{r.id}/', {'end_time': '13:00'}, format='json')
        assert res.status_code == 200 and res.json()['availability']['end_time'].startswith('13:00') and res.json()['conflicts'] == []
        r.refresh_from_db()
        assert r.end_time == time(13, 0)

    def test_the_overlap_check_excludes_the_row_being_edited(self, me, tutor):
        """Legacy data can hold an overlapping pair; either row can be fixed without first deleting it."""
        a = monday_row(tutor)
        b = TeacherAvailability.objects.create(teacher=tutor, day_of_week=0, start_time=time(11, 0), end_time=time(13, 0))
        assert me.patch(f'{BASE}/manage/{a.id}/', {'end_time': '11:00'}, format='json').status_code == 200   # now touching
        assert me.patch(f'{BASE}/manage/{b.id}/', {'end_time': '14:00'}, format='json').status_code == 200   # own old extent ignored
        res = me.patch(f'{BASE}/manage/{a.id}/', {'end_time': '11:30'}, format='json')
        assert res.status_code == 400 and 'overlap' in str(res.json()).lower()

    def test_deactivating_an_overlapping_legacy_row_is_allowed(self, me, tutor):
        a = monday_row(tutor)
        TeacherAvailability.objects.create(teacher=tutor, day_of_week=0, start_time=time(11, 0), end_time=time(13, 0))
        assert me.patch(f'{BASE}/manage/{a.id}/', {'is_active': False}, format='json').status_code == 200

    def test_another_tutors_row_is_a_404(self, me, tutor):
        other = f.make_teacher_profile(availability=False)
        r = TeacherAvailability.objects.create(teacher=other, day_of_week=1, start_time=time(9, 0), end_time=time(10, 0))
        assert me.patch(f'{BASE}/manage/{r.id}/', {'end_time': '11:00'}, format='json').status_code == 404
        assert me.delete(f'{BASE}/manage/{r.id}/').status_code == 404
        assert TeacherAvailability.objects.filter(pk=r.pk).exists()

    def test_delete_a_row(self, me, tutor):
        r = monday_row(tutor)
        res = me.delete(f'{BASE}/manage/{r.id}/')
        assert res.status_code == 200 and res.json() == {'deleted': True, 'conflicts': []}
        assert not TeacherAvailability.objects.filter(pk=r.pk).exists()

    def test_shrinking_a_row_over_a_confirmed_lesson_needs_acknowledgement(self, me, tutor, student_user):
        booking = lesson(tutor, student_user, next_weekday_utc(0, 11))            # Monday 11:00 SAST
        r = monday_row(tutor)
        res = me.patch(f'{BASE}/manage/{r.id}/', {'end_time': '10:00'}, format='json')
        assert res.status_code == 409
        body = res.json()
        assert body['code'] == 'availability_conflicts'
        assert [c['booking_id'] for c in body['conflicts']] == [str(booking.id)]
        assert set(body['conflicts'][0]) == {'booking_id', 'start_time_utc', 'end_time_utc'}
        r.refresh_from_db()
        assert r.end_time == time(12, 0)                                           # nothing was applied

        ok = me.patch(f'{BASE}/manage/{r.id}/', {'end_time': '10:00', 'acknowledge_conflicts': True}, format='json')
        assert ok.status_code == 200 and [c['booking_id'] for c in ok.json()['conflicts']] == [str(booking.id)]
        r.refresh_from_db()
        booking.refresh_from_db()
        assert r.end_time == time(10, 0) and booking.status == Booking.Status.CONFIRMED

    def test_deleting_a_row_under_a_lesson_follows_the_same_contract(self, me, tutor, student_user):
        booking = lesson(tutor, student_user, next_weekday_utc(0, 10))
        r = monday_row(tutor)
        assert me.delete(f'{BASE}/manage/{r.id}/').status_code == 409
        assert TeacherAvailability.objects.filter(pk=r.pk).exists()
        ok = me.delete(f'{BASE}/manage/{r.id}/?acknowledge_conflicts=true')
        assert ok.status_code == 200 and ok.json()['conflicts'][0]['booking_id'] == str(booking.id)
        booking.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED

    def test_a_lesson_still_inside_the_new_hours_is_not_a_conflict(self, me, tutor, student_user):
        lesson(tutor, student_user, next_weekday_utc(0, 9, 30))
        r = monday_row(tutor)
        assert me.patch(f'{BASE}/manage/{r.id}/', {'end_time': '10:00'}, format='json').status_code == 200

    @pytest.mark.parametrize('status', [Booking.Status.CANCELLED, Booking.Status.COMPLETED, Booking.Status.PENDING_PAYMENT])
    def test_only_confirmed_future_lessons_count(self, me, tutor, student_user, status):
        lesson(tutor, student_user, next_weekday_utc(0, 11), status=status)
        r = monday_row(tutor)
        assert me.patch(f'{BASE}/manage/{r.id}/', {'end_time': '10:00'}, format='json').status_code == 200

    def test_a_past_lesson_is_not_a_conflict(self, me, tutor, student_user):
        lesson(tutor, student_user, datetime.now(dt_tz.utc) - timedelta(days=2))
        r = monday_row(tutor)
        assert me.delete(f'{BASE}/manage/{r.id}/').status_code == 200


# ------------------------------------------------------------------ PUT replace
class TestReplace:
    def test_replace_swaps_the_whole_matrix(self, me, tutor):
        res = me.put(f'{BASE}/replace/', {'rows': [row(day=1, start='08:00', end='10:00'), row(day=1, start='13:00', end='17:00'),
                                                    row(day=4, start='08:00', end='12:00')]}, format='json')
        assert res.status_code == 200 and res.json()['conflicts'] == []
        assert [(r['day_of_week'], r['start_time'][:5]) for r in res.json()['rows']] == [(1, '08:00'), (1, '13:00'), (4, '08:00')]
        assert sorted(TeacherAvailability.objects.filter(teacher=tutor).values_list('day_of_week', flat=True)) == [1, 1, 4]

    def test_replace_is_all_or_nothing(self, me, tutor):
        res = me.put(f'{BASE}/replace/', {'rows': [row(day=1), row(day=2, start='12:00', end='09:00')]}, format='json')
        assert res.status_code == 400
        assert list(TeacherAvailability.objects.filter(teacher=tutor).values_list('day_of_week', flat=True)) == [0]

    def test_rows_that_overlap_each_other_are_rejected(self, me, tutor):
        res = me.put(f'{BASE}/replace/', {'rows': [row(day=1, start='09:00', end='11:00'), row(day=1, start='10:00', end='12:00')]}, format='json')
        assert res.status_code == 400 and 'overlap' in str(res.json()).lower()

    def test_an_empty_matrix_clears_availability(self, me, tutor):
        res = me.put(f'{BASE}/replace/', {'rows': []}, format='json')
        assert res.status_code == 200 and res.json()['rows'] == [] and not TeacherAvailability.objects.filter(teacher=tutor).exists()

    def test_the_row_limit_applies(self, me, tutor, monkeypatch):
        import apps.teachers.services.availability as svc
        monkeypatch.setattr(svc, 'MAX_AVAILABILITY_ROWS', 2)
        res = me.put(f'{BASE}/replace/', {'rows': [row(day=d) for d in range(3)]}, format='json')
        assert res.status_code == 400 and 'at most' in str(res.json()).lower()

    def test_it_never_touches_another_tutors_rows(self, me, tutor):
        other = f.make_teacher_profile()
        assert me.put(f'{BASE}/replace/', {'rows': []}, format='json').status_code == 200
        assert TeacherAvailability.objects.filter(teacher=other).count() == 1

    def test_conflicting_lessons_are_listed_and_nothing_changes_until_acknowledged(self, me, tutor, student_user):
        inside, outside = lesson(tutor, student_user, next_weekday_utc(1, 10)), lesson(tutor, student_user, next_weekday_utc(0, 10))
        payload = {'rows': [row(day=1, start='09:00', end='12:00')]}          # Monday is gone, Tuesday arrives
        res = me.put(f'{BASE}/replace/', payload, format='json')
        assert res.status_code == 409 and res.json()['code'] == 'availability_conflicts'
        assert [c['booking_id'] for c in res.json()['conflicts']] == [str(outside.id)]
        assert list(TeacherAvailability.objects.filter(teacher=tutor).values_list('day_of_week', flat=True)) == [0]

        ok = me.put(f'{BASE}/replace/', {**payload, 'acknowledge_conflicts': True}, format='json')
        assert ok.status_code == 200 and [c['booking_id'] for c in ok.json()['conflicts']] == [str(outside.id)]
        assert list(TeacherAvailability.objects.filter(teacher=tutor).values_list('day_of_week', flat=True)) == [1]
        for b in (inside, outside):
            b.refresh_from_db()
            assert b.status == Booking.Status.CONFIRMED                       # editing availability never cancels

    def test_non_tutors_and_tutors_without_a_profile_are_refused(self, student_user):
        assert client(student_user).put(f'{BASE}/replace/', {'rows': []}, format='json').status_code == 403
        assert APIClient().put(f'{BASE}/replace/', {'rows': []}, format='json').status_code == 401
        bare = User.objects.create_user(username='bare', email='bare@x.com', password='x-pass-12345', role='teacher')
        assert client(bare).put(f'{BASE}/replace/', {'rows': []}, format='json').status_code == 403

    def test_replace_works_on_a_zone_with_dst_and_judges_conflicts_in_local_time(self, student_user):
        """A lesson at 09:30 Berlin-local on a CEST date is covered by a 09:00-10:00 row (not shifted by the UTC offset)."""
        berlin = ZoneInfo('Europe/Berlin')
        tutor = f.make_teacher_profile(f.make_user('teacher', timezone='Europe/Berlin'), availability=False)
        day = (datetime.now(berlin) + timedelta(days=200)).date()
        start = datetime.combine(day, time(9, 30), berlin).astimezone(dt_tz.utc)
        lesson(tutor, student_user, start)
        res = client(tutor.user).put(f'{BASE}/replace/', {'rows': [row(day=day.weekday(), start='09:00', end='10:00')]}, format='json')
        assert res.status_code == 200 and res.json()['conflicts'] == []


# ------------------------------------------------------------------ time off
class TestTimeOff:
    def _body(self, start, end, **extra):
        return {'start_utc': start.isoformat(), 'end_utc': end.isoformat(), 'reason': 'holiday', **extra}

    def test_create_list_and_delete(self, me, tutor):
        start = datetime.now(dt_tz.utc) + timedelta(days=10)
        res = me.post(f'{BASE}/time-off/', self._body(start, start + timedelta(days=2)), format='json')
        assert res.status_code == 201 and res.json()['conflicts'] == []
        created = res.json()['time_off']
        assert TeacherTimeOff.objects.filter(teacher=tutor).count() == 1
        assert me.get(f'{BASE}/time-off/').json()['count'] == 1
        gone = me.delete(f"{BASE}/time-off/{created['id']}/")
        assert gone.status_code == 200 and gone.json() == {'deleted': True, 'conflicts': []}
        assert not TeacherTimeOff.objects.exists()

    def test_validation(self, me, tutor):
        now = datetime.now(dt_tz.utc)
        assert me.post(f'{BASE}/time-off/', self._body(now + timedelta(days=2), now + timedelta(days=1)), format='json').status_code == 400
        assert me.post(f'{BASE}/time-off/', self._body(now - timedelta(days=3), now - timedelta(days=2)), format='json').status_code == 400
        assert me.post(f'{BASE}/time-off/', self._body(now + timedelta(days=1), now + timedelta(days=500)), format='json').status_code == 400

    def test_it_is_owner_only(self, me, tutor):
        other = f.make_teacher_profile()
        row_ = TeacherTimeOff.objects.create(teacher=other, start_utc=datetime.now(dt_tz.utc) + timedelta(days=5),
                                             end_utc=datetime.now(dt_tz.utc) + timedelta(days=6))
        assert me.delete(f'{BASE}/time-off/{row_.id}/').status_code == 404
        assert me.get(f'{BASE}/time-off/').json()['count'] == 0

    def test_time_off_over_a_confirmed_lesson_needs_acknowledgement(self, me, tutor, student_user):
        start = next_weekday_utc(0, 10)
        booking = lesson(tutor, student_user, start)
        body = self._body(start - timedelta(hours=1), start + timedelta(hours=1))
        res = me.post(f'{BASE}/time-off/', body, format='json')
        assert res.status_code == 409 and [c['booking_id'] for c in res.json()['conflicts']] == [str(booking.id)]
        assert not TeacherTimeOff.objects.exists()
        ok = me.post(f'{BASE}/time-off/', {**body, 'acknowledge_conflicts': True}, format='json')
        assert ok.status_code == 201 and ok.json()['conflicts'][0]['booking_id'] == str(booking.id)
        booking.refresh_from_db()
        assert TeacherTimeOff.objects.count() == 1 and booking.status == Booking.Status.CONFIRMED

    def test_time_off_that_misses_every_lesson_has_no_conflict(self, me, tutor, student_user):
        start = next_weekday_utc(0, 10)
        lesson(tutor, student_user, start)
        assert me.post(f'{BASE}/time-off/', self._body(start + timedelta(hours=1), start + timedelta(hours=3)), format='json').status_code == 201

    def test_a_lesson_inside_the_new_matrix_is_still_a_conflict_when_time_off_covers_it(self, me, tutor, student_user):
        """Conflicts are judged against the whole schedule, not just the weekly rows."""
        start = next_weekday_utc(0, 9, 30)
        lesson(tutor, student_user, start)
        res = me.post(f'{BASE}/time-off/', self._body(start - timedelta(minutes=5), start + timedelta(minutes=30)), format='json')
        assert res.status_code == 409


# ------------------------------------------------------------------ specific-date overrides (INV TEA-03)
class TestOverrides:
    def _future(self, days=10):
        return (datetime.now(SAST) + timedelta(days=days)).date()

    def test_open_override_needs_hours(self, me, tutor):
        res = me.post(f'{BASE}/overrides/', {'date': self._future().isoformat(), 'kind': 'open'}, format='json')
        assert res.status_code == 400 and 'start_time' in res.json()

    def test_closed_override_without_hours_closes_the_day(self, me, tutor):
        res = me.post(f'{BASE}/overrides/', {'date': self._future().isoformat(), 'kind': 'closed', 'reason': 'exam'}, format='json')
        assert res.status_code == 201 and res.json()['conflicts'] == [] and res.json()['override']['start_time'] is None
        assert TeacherDateOverride.objects.filter(teacher=tutor).count() == 1

    def test_open_override_with_hours(self, me, tutor):
        body = {'date': self._future().isoformat(), 'kind': 'open', 'start_time': '14:00', 'end_time': '16:00'}
        assert me.post(f'{BASE}/overrides/', body, format='json').status_code == 201

    @pytest.mark.parametrize('extra', [
        {'kind': 'open', 'start_time': '16:00', 'end_time': '14:00'},
        {'kind': 'open', 'start_time': '14:00'},
        {'kind': 'bogus'},
    ])
    def test_invalid_overrides(self, me, tutor, extra):
        assert me.post(f'{BASE}/overrides/', {'date': self._future().isoformat(), **extra}, format='json').status_code == 400

    def test_a_date_in_the_past_or_too_far_ahead_is_rejected(self, me, tutor):
        for days in (-3, 800):
            res = me.post(f'{BASE}/overrides/', {'date': self._future(days).isoformat(), 'kind': 'closed'}, format='json')
            assert res.status_code == 400

    def test_closing_a_day_with_a_confirmed_lesson_needs_acknowledgement(self, me, tutor, student_user):
        start = next_weekday_utc(0, 10)
        booking = lesson(tutor, student_user, start)
        day = start.astimezone(SAST).date().isoformat()
        res = me.post(f'{BASE}/overrides/', {'date': day, 'kind': 'closed'}, format='json')
        assert res.status_code == 409 and res.json()['conflicts'][0]['booking_id'] == str(booking.id)
        ok = me.post(f'{BASE}/overrides/', {'date': day, 'kind': 'closed', 'acknowledge_conflicts': True}, format='json')
        assert ok.status_code == 201
        booking.refresh_from_db()
        assert booking.status == Booking.Status.CONFIRMED

    def test_list_delete_and_owner_only(self, me, tutor):
        other = f.make_teacher_profile()
        theirs = TeacherDateOverride.objects.create(teacher=other, date=self._future(), kind='closed')
        mine = me.post(f'{BASE}/overrides/', {'date': self._future(12).isoformat(), 'kind': 'closed'}, format='json').json()['override']
        assert me.get(f'{BASE}/overrides/').json()['count'] == 1
        assert me.delete(f'{BASE}/overrides/{theirs.id}/').status_code == 404
        res = me.delete(f"{BASE}/overrides/{mine['id']}/")
        assert res.status_code == 200 and res.json() == {'deleted': True, 'conflicts': []}

    def test_removing_an_open_override_under_a_lesson_needs_acknowledgement(self, me, tutor, student_user):
        start = next_weekday_utc(2, 15)                                          # Wednesday: no weekly hours, only the override
        day = start.astimezone(SAST).date()
        ov = TeacherDateOverride.objects.create(teacher=tutor, date=day, kind='open', start_time=time(14, 0), end_time=time(17, 0))
        lesson(tutor, student_user, start)
        assert me.delete(f'{BASE}/overrides/{ov.id}/').status_code == 409
        assert me.delete(f'{BASE}/overrides/{ov.id}/?acknowledge_conflicts=true').status_code == 200


# ------------------------------------------------------------------ timezone validation at save
class TestTimezoneValidation:
    @pytest.mark.parametrize('bad', ['Mars/Phobos', 'localtime', '', 'africa/johannesburg ', '../../etc/passwd'])
    def test_the_profile_serializer_rejects_unknown_zones(self, student_user, bad):
        res = client(student_user).patch('/api/v1/auth/me/', {'timezone': bad}, format='json')
        assert res.status_code == 400 and 'timezone' in res.json()

    @pytest.mark.parametrize('good', ['Asia/Kolkata', 'Australia/Lord_Howe', 'UTC', 'Europe/Berlin'])
    def test_real_zones_pass(self, student_user, good):
        assert client(student_user).patch('/api/v1/auth/me/', {'timezone': good}, format='json').status_code == 200

    def test_the_model_clean_rejects_an_unknown_zone_for_the_admin_form(self):
        from django.core.exceptions import ValidationError
        user = User(username='z', email='z@x.com', role='teacher', timezone='Mars/Phobos')
        with pytest.raises(ValidationError) as err:
            user.full_clean(exclude=['password'])
        assert 'timezone' in err.value.message_dict

    def test_the_validator_uses_the_tzdata_list(self):
        import zoneinfo
        from apps.common.timezones import is_valid_timezone
        assert is_valid_timezone('Africa/Johannesburg') and not is_valid_timezone('Nope/Nope')
        from apps.common.timezones import _NOT_ZONES            # entries the tz database lists that are not zones (ERR-197)
        zones = sorted(z for z in zoneinfo.available_timezones() if z not in _NOT_ZONES)
        assert all(is_valid_timezone(z) for z in zones[:25] + zones[-25:])


# Boundaries, limits, lock calls and throttling live in tests/test_t2_availability_limits.py.
