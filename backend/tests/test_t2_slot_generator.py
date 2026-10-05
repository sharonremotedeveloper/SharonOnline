"""
Slice T2 (PRP 11.6): the slot generator on zoneinfo.

DST fixtures (documented in docs/slices/T2.md): the expected UTC lists below were derived by hand from the IANA rules and
cross-checked with a throwaway zoneinfo script. The rule (plan 3.5): build each slot from NAIVE local wall-clock time, skip
a local time that does not exist (spring forward), take the first fold of an ambiguous one (fall back), and give every slot
a real 25-minute length in UTC. A tutor whose stored timezone is not an IANA zone gets NO slots and an error log with ids;
there is no Johannesburg fallback.
"""
import logging
from datetime import date, datetime, time, timedelta, timezone as dt_tz

import pytest

import factories as f
from apps.bookings.services.slot_generator import generate_teacher_slots
from apps.teachers.models import TeacherAvailability, TeacherDateOverride, TeacherTimeOff
from apps.users.models import User

pytestmark = pytest.mark.django_db

UTC = dt_tz.utc


def utc(*parts):
    return datetime(*parts, tzinfo=UTC)


def tutor_in(tz, windows):
    """An approved tutor whose clock is `tz`; windows = [(day_of_week, time, time)]."""
    profile = f.make_teacher_profile(f.make_user('teacher', timezone=tz), availability=False)
    for dow, start, end in windows:
        TeacherAvailability.objects.create(teacher=profile, day_of_week=dow, start_time=start, end_time=end, is_active=True)
    return profile


def starts(profile, day, days=1, **kwargs):
    return [s['start_time_utc'] for s in generate_teacher_slots(teacher=profile, start_date=day, days_ahead=days, **kwargs)]


def iso(*stamps):
    return [utc(*s).isoformat() for s in stamps]


@pytest.fixture(autouse=True)
def long_before(frozen_clock):
    frozen_clock.set(utc(2026, 1, 1, 0, 0))
    return frozen_clock


# ------------------------------------------------------------------ DST (the confirmed pytz bug)
class TestDaylightSaving:
    def test_spring_forward_berlin_skips_nonexistent_local_times_and_stays_inside_the_window(self):
        """Window 00:00-02:30 on 2026-03-29 (02:00 -> 03:00). pytz resolved the 02:30 end as CET and offered a slot at
        03:00 CEST, outside what the tutor declared."""
        tutor = tutor_in('Europe/Berlin', [(6, time(0, 0), time(2, 30))])
        assert starts(tutor, date(2026, 3, 29)) == iso((2026, 3, 28, 23, 0), (2026, 3, 28, 23, 30), (2026, 3, 29, 0, 0),
                                                       (2026, 3, 29, 0, 30))

    def test_fall_back_berlin_uses_the_first_fold_and_never_lists_a_wall_clock_time_twice(self):
        """2026-10-25 (03:00 -> 02:00): 02:00 and 02:30 happen twice; each is listed once, in its first (CEST) occurrence."""
        tutor = tutor_in('Europe/Berlin', [(6, time(0, 0), time(4, 0))])
        assert starts(tutor, date(2026, 10, 25)) == iso(
            (2026, 10, 24, 22, 0), (2026, 10, 24, 22, 30), (2026, 10, 24, 23, 0), (2026, 10, 24, 23, 30),
            (2026, 10, 25, 0, 0), (2026, 10, 25, 0, 30), (2026, 10, 25, 2, 0), (2026, 10, 25, 2, 30))

    def test_lord_howe_half_hour_fall_back(self):
        """Lord Howe moves by 30 minutes: 01:30-02:00 is ambiguous on 2026-04-05 (offset +11 -> +10:30)."""
        tutor = tutor_in('Australia/Lord_Howe', [(6, time(0, 30), time(3, 0))])
        assert starts(tutor, date(2026, 4, 5)) == iso((2026, 4, 4, 13, 30), (2026, 4, 4, 14, 0), (2026, 4, 4, 14, 30),
                                                      (2026, 4, 4, 15, 30), (2026, 4, 4, 16, 0))

    def test_lord_howe_half_hour_spring_forward(self):
        tutor = tutor_in('Australia/Lord_Howe', [(6, time(1, 0), time(3, 30))])
        assert starts(tutor, date(2026, 10, 4)) == iso((2026, 10, 3, 14, 30), (2026, 10, 3, 15, 0), (2026, 10, 3, 15, 30),
                                                       (2026, 10, 3, 16, 0))

    def test_new_york_spring_forward(self):
        tutor = tutor_in('America/New_York', [(6, time(1, 0), time(4, 0))])
        assert starts(tutor, date(2026, 3, 8)) == iso((2026, 3, 8, 6, 0), (2026, 3, 8, 6, 30), (2026, 3, 8, 7, 0),
                                                      (2026, 3, 8, 7, 30))

    def test_non_whole_hour_zone_without_dst(self):
        tutor = tutor_in('Asia/Kolkata', [(0, time(9, 0), time(10, 0))])
        assert starts(tutor, date(2026, 1, 5)) == iso((2026, 1, 5, 3, 30), (2026, 1, 5, 4, 0))

    def test_every_slot_is_twenty_five_real_minutes_long(self):
        tutor = tutor_in('Europe/Berlin', [(6, time(0, 0), time(4, 0))])
        for slot in generate_teacher_slots(teacher=tutor, start_date=date(2026, 10, 25), days_ahead=1):
            length = datetime.fromisoformat(slot['end_time_utc']) - datetime.fromisoformat(slot['start_time_utc'])
            assert length == timedelta(minutes=25)

    def test_johannesburg_is_unchanged(self):
        tutor = tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(10, 0))])
        assert starts(tutor, date(2026, 1, 5)) == iso((2026, 1, 5, 7, 0), (2026, 1, 5, 7, 30))

    def test_viewer_timezone_is_applied_with_zoneinfo(self):
        tutor = tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(9, 30))])
        slot = generate_teacher_slots(teacher=tutor, start_date=date(2026, 1, 5), days_ahead=1, viewer_tz_name='Asia/Kolkata')[0]
        assert (slot['local_date'], slot['local_start_time'], slot['viewer_timezone']) == ('2026-01-05', '12:30', 'Asia/Kolkata')

    def test_the_default_start_date_is_the_tutors_local_today(self, long_before):
        """23:00 UTC on Monday is already Tuesday 01:00 in Johannesburg, so a Tuesday-only tutor has slots 'today'."""
        long_before.set(utc(2026, 1, 5, 23, 0))
        tutor = tutor_in('Africa/Johannesburg', [(1, time(9, 0), time(10, 0))])
        assert [s['start_time_utc'] for s in generate_teacher_slots(teacher=tutor, days_ahead=1)] == iso(
            (2026, 1, 6, 7, 0), (2026, 1, 6, 7, 30))


# ------------------------------------------------------------------ unknown timezone: no silent Johannesburg
class TestUnknownTimezone:
    @pytest.mark.parametrize('bad', ['Mars/Phobos', '', 'localtime', '../etc/passwd'])
    def test_an_invalid_stored_timezone_yields_no_slots_and_an_error_log_with_ids(self, bad, caplog):
        tutor = tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(10, 0))])
        User.objects.filter(pk=tutor.user_id).update(timezone=bad)      # bypasses every validator: legacy / admin data
        tutor.refresh_from_db()
        with caplog.at_level(logging.ERROR):
            assert generate_teacher_slots(teacher=tutor, start_date=date(2026, 1, 5), days_ahead=1) == []
        text = ' '.join(r.getMessage() for r in caplog.records)
        assert str(tutor.id) in text and str(tutor.user_id) in text
        if bad:
            assert bad not in text              # ids and error types only

    def test_the_teacher_zone_helper_raises_a_typed_error(self):
        from apps.teachers.services.schedule import InvalidTeacherTimezone, teacher_zone
        tutor = tutor_in('Africa/Johannesburg', [])
        User.objects.filter(pk=tutor.user_id).update(timezone='Nope/Nope')
        tutor.refresh_from_db()
        with pytest.raises(InvalidTeacherTimezone):
            teacher_zone(tutor)

    def test_the_tutor_is_not_reservable_while_the_zone_is_invalid(self, student_user):
        from apps.bookings.services.reservation import ReservationError, reserve_slot
        tutor = tutor_in('Africa/Johannesburg', [(d, time(0, 0), time(23, 0)) for d in range(7)])
        slot = next(s for s in generate_teacher_slots(teacher=tutor, days_ahead=3))
        User.objects.filter(pk=tutor.user_id).update(timezone='Nope/Nope')
        with pytest.raises(ReservationError) as err:
            reserve_slot(student=student_user, teacher_id=tutor.id, start_time_utc=datetime.fromisoformat(slot['start_time_utc']))
        assert err.value.status_code == 409


# ------------------------------------------------------------------ minimum notice
class TestMinimumNotice:
    def test_the_default_notice_is_ten_minutes(self, settings, long_before):
        long_before.set(utc(2026, 1, 5, 6, 55))
        tutor = tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(10, 0))])
        assert settings.TUTOR_MIN_NOTICE_MINUTES == 10
        assert starts(tutor, date(2026, 1, 5)) == iso((2026, 1, 5, 7, 30))      # 07:00 is only 5 minutes away

    def test_the_notice_is_a_setting(self, settings, long_before):
        long_before.set(utc(2026, 1, 5, 6, 55))
        tutor = tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(10, 0))])
        settings.TUTOR_MIN_NOTICE_MINUTES = 3
        assert starts(tutor, date(2026, 1, 5)) == iso((2026, 1, 5, 7, 0), (2026, 1, 5, 7, 30))
        settings.TUTOR_MIN_NOTICE_MINUTES = 40
        assert starts(tutor, date(2026, 1, 5)) == []

    def test_a_slot_exactly_at_the_notice_boundary_is_not_offered(self, long_before):
        long_before.set(utc(2026, 1, 5, 6, 50))                                  # 07:00 is exactly 10 minutes away
        tutor = tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(9, 30))])
        assert starts(tutor, date(2026, 1, 5)) == []


# ------------------------------------------------------------------ one horizon setting
class TestBookingHorizon:
    def test_the_three_old_constants_are_gone(self, settings):
        import pathlib
        assert settings.BOOKING_HORIZON_DAYS == 14
        assert not hasattr(settings, 'RESCHEDULE_MAX_DAYS_AHEAD')
        root = pathlib.Path(__file__).resolve().parents[1] / 'apps'
        offenders = [str(p) for p in root.rglob('*.py') if p.name != 'migrations'
                     and any(name in p.read_text(encoding='utf-8') for name in ('MAX_SLOT_DAYS', 'SLOT_HORIZON_DAYS', 'RESCHEDULE_MAX_DAYS_AHEAD'))]
        assert offenders == []

    def test_the_slot_list_is_capped_at_the_horizon(self, settings, student_user):
        from rest_framework.test import APIClient
        tutor = tutor_in('Africa/Johannesburg', [(d, time(9, 0), time(10, 0)) for d in range(7)])
        client = APIClient()
        assert client.get(f'/api/v1/bookings/slots/{tutor.id}/?days=14').json()['days'] == 14
        settings.BOOKING_HORIZON_DAYS = 5
        body = client.get(f'/api/v1/bookings/slots/{tutor.id}/?days=14').json()
        assert body['days'] == 5

    def test_reserving_beyond_the_horizon_is_refused(self, settings, student_user, long_before):
        from apps.bookings.services.reservation import ReservationError, reserve_slot
        tutor = tutor_in('Africa/Johannesburg', [(d, time(9, 0), time(10, 0)) for d in range(7)])
        far = generate_teacher_slots(teacher=tutor, days_ahead=12)[-1]
        when = datetime.fromisoformat(far['start_time_utc'])
        settings.BOOKING_HORIZON_DAYS = 5
        with pytest.raises(ReservationError) as err:
            reserve_slot(student=student_user, teacher_id=tutor.id, start_time_utc=when)
        assert err.value.status_code == 409


# ------------------------------------------------------------------ blocked intervals (the G2 / Eskom hook)
class TestBlockedIntervals:
    def test_an_overlapping_blocked_interval_hides_the_slots_it_touches(self):
        tutor = tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(11, 0))])
        blocked = [(utc(2026, 1, 5, 7, 20), utc(2026, 1, 5, 8, 10))]          # touches the 07:00, 07:30 and 08:00 slots
        assert starts(tutor, date(2026, 1, 5), blocked_intervals=blocked) == iso((2026, 1, 5, 8, 30))

    def test_an_interval_that_only_touches_the_edge_blocks_nothing(self):
        tutor = tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(10, 0))])
        blocked = [(utc(2026, 1, 5, 7, 25), utc(2026, 1, 5, 7, 30))]
        assert len(starts(tutor, date(2026, 1, 5), blocked_intervals=blocked)) == 2


# ------------------------------------------------------------------ time off and date overrides (INV TEA-03)
class TestTimeOffAndOverrides:
    def test_time_off_hides_overlapping_slots(self):
        tutor = tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(11, 0))])
        TeacherTimeOff.objects.create(teacher=tutor, start_utc=utc(2026, 1, 5, 7, 0), end_utc=utc(2026, 1, 5, 8, 0), reason='dentist')
        assert starts(tutor, date(2026, 1, 5)) == iso((2026, 1, 5, 8, 0), (2026, 1, 5, 8, 30))

    def test_a_closed_date_removes_the_whole_day(self):
        tutor = tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(10, 0))])
        TeacherDateOverride.objects.create(teacher=tutor, date=date(2026, 1, 5), kind='closed')
        assert starts(tutor, date(2026, 1, 5)) == []

    def test_a_closed_window_removes_only_those_hours(self):
        tutor = tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(11, 0))])
        TeacherDateOverride.objects.create(teacher=tutor, date=date(2026, 1, 5), kind='closed', start_time=time(9, 0), end_time=time(10, 0))
        assert starts(tutor, date(2026, 1, 5)) == iso((2026, 1, 5, 8, 0), (2026, 1, 5, 8, 30))

    def test_an_open_override_adds_hours_on_a_day_without_any(self):
        tutor = tutor_in('Africa/Johannesburg', [])
        TeacherDateOverride.objects.create(teacher=tutor, date=date(2026, 1, 7), kind='open', start_time=time(14, 0), end_time=time(15, 0))
        assert starts(tutor, date(2026, 1, 7)) == iso((2026, 1, 7, 12, 0), (2026, 1, 7, 12, 30))

    def test_an_override_does_not_leak_to_other_dates_or_tutors(self):
        tutor, other = tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(10, 0))]), tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(10, 0))])
        TeacherDateOverride.objects.create(teacher=tutor, date=date(2026, 1, 12), kind='closed')
        assert len(starts(tutor, date(2026, 1, 5))) == 2 and len(starts(other, date(2026, 1, 12))) == 2

    def test_inactive_weekly_rows_do_not_generate_slots(self):
        tutor = tutor_in('Africa/Johannesburg', [(0, time(9, 0), time(10, 0))])
        TeacherAvailability.objects.filter(teacher=tutor).update(is_active=False)
        assert starts(tutor, date(2026, 1, 5)) == []
