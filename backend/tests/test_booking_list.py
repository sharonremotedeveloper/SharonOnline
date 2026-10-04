"""Task 9.5: GET /bookings/ - scoped to the caller, filterable by status / when / date range, validated, ordered, paginated."""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.teachers.models import TeacherProfile

S = Booking.Status
User = get_user_model()
URL = '/api/v1/bookings/'
MIN = timedelta(minutes=1)


def make(teacher, student, status=S.CONFIRMED, *, start=None, hours=0):
    start = start or (timezone.now() + timedelta(hours=hours))
    return Booking.objects.create(teacher=teacher, student=student, start_time_utc=start,
                                  end_time_utc=start + 25 * MIN, status=status)


def get(user, query=''):
    c = APIClient()
    if user:
        c.force_authenticate(user=user)
    return c.get(URL + query)


def ids(res):
    assert res.status_code == 200, res.content
    return [r['id'] for r in res.json()['results']]


@pytest.fixture
def other_student(db):
    return User.objects.create_user(username='stu2', email='stu2@x.com', password='x-pass-12345', role='student')


@pytest.fixture
def other_tutor(db):
    u = User.objects.create_user(username='t2', email='t2@x.com', password='x-pass-12345', role='teacher')
    return TeacherProfile.objects.create(user=u, headline='x', price_per_25min_usd=9, status='approved')


# ------------------------------------------------------------------ who sees what
@pytest.mark.django_db
class TestScoping:
    def test_anonymous_is_rejected(self):
        assert get(None).status_code == 401

    def test_a_student_sees_only_their_own_lessons(self, teacher_user, student_user, other_student):
        mine = make(teacher_user, student_user, hours=5)
        make(teacher_user, other_student, hours=7)
        assert ids(get(student_user)) == [str(mine.id)]

    def test_a_tutor_sees_only_their_own_roster(self, teacher_user, other_tutor, student_user):
        mine = make(teacher_user, student_user, hours=5)
        make(other_tutor, student_user, hours=7)
        assert ids(get(teacher_user.user)) == [str(mine.id)]

    def test_filters_never_widen_the_scope(self, teacher_user, student_user, other_student):
        make(teacher_user, other_student, hours=5)
        for q in ('?when=upcoming', '?status=confirmed', '?from=2000-01-01&to=2999-01-01', '?student=' + str(other_student.id)):
            assert ids(get(student_user, q)) == [], q

    def test_a_teacher_account_without_a_profile_sees_nothing_not_someone_elses(self, teacher_user, student_user):
        make(teacher_user, student_user, hours=5)
        ghost = User.objects.create_user(username='ghost', email='g@x.com', password='x-pass-12345', role='teacher')
        make(teacher_user, ghost, hours=6)          # even a lesson they once booked as a student is not their tutor roster
        assert ids(get(ghost)) == []


# ------------------------------------------------------------------ status
@pytest.mark.django_db
class TestStatusFilter:
    def test_single_and_comma_separated_statuses(self, teacher_user, student_user):
        a = make(teacher_user, student_user, S.CONFIRMED, hours=1)
        b = make(teacher_user, student_user, S.COMPLETED, hours=-30)
        c = make(teacher_user, student_user, S.CANCELLED, hours=-60)
        assert set(ids(get(student_user, '?status=confirmed'))) == {str(a.id)}
        assert set(ids(get(student_user, '?status=completed,cancelled'))) == {str(b.id), str(c.id)}
        assert set(ids(get(student_user, '?status=completed, cancelled&status=confirmed'))) == {str(a.id), str(b.id), str(c.id)}

    @pytest.mark.parametrize('bad', ['nonsense', 'confirmed,nonsense', 'CONFIRMED;drop', "confirmed' or 1=1"])
    def test_unknown_status_is_a_400_naming_the_field(self, teacher_user, student_user, bad):
        res = get(student_user, f'?status={bad}')
        assert res.status_code == 400 and 'status' in res.json()

    def test_empty_status_means_no_filter(self, teacher_user, student_user):
        make(teacher_user, student_user, hours=1)
        assert len(ids(get(student_user, '?status='))) == 1


# ------------------------------------------------------------------ upcoming / past
@pytest.mark.django_db
class TestWhen:
    def test_upcoming_is_lessons_still_to_happen_or_under_way(self, teacher_user, student_user):
        future = make(teacher_user, student_user, S.CONFIRMED, hours=3)
        under_way = make(teacher_user, student_user, S.IN_PROGRESS, start=timezone.now() - 10 * MIN)
        make(teacher_user, student_user, S.COMPLETED, hours=-4)
        make(teacher_user, student_user, S.CANCELLED, hours=6)                  # cancelled is never "upcoming"
        make(teacher_user, student_user, S.CONFIRMED, hours=-3)                 # ended and nobody settled it yet: past
        assert set(ids(get(student_user, '?when=upcoming'))) == {str(future.id), str(under_way.id)}

    def test_upcoming_includes_an_unpaid_hold_only_while_it_is_live(self, teacher_user, student_user):
        live = make(teacher_user, student_user, S.PENDING_PAYMENT, hours=4)
        stale = make(teacher_user, student_user, S.PENDING_PAYMENT, hours=5)
        Booking.objects.filter(pk=stale.pk).update(created_at=timezone.now() - 40 * MIN)
        assert ids(get(student_user, '?when=upcoming')) == [str(live.id)]

    def test_past_is_everything_that_has_ended(self, teacher_user, student_user):
        done = make(teacher_user, student_user, S.COMPLETED, hours=-4)
        gone = make(teacher_user, student_user, S.CANCELLED, hours=-8)
        make(teacher_user, student_user, S.CONFIRMED, hours=3)
        assert set(ids(get(student_user, '?when=past'))) == {str(done.id), str(gone.id)}

    def test_when_combines_with_status(self, teacher_user, student_user):
        done = make(teacher_user, student_user, S.COMPLETED, hours=-4)
        make(teacher_user, student_user, S.CANCELLED, hours=-8)
        assert ids(get(student_user, '?when=past&status=completed')) == [str(done.id)]

    @pytest.mark.parametrize('bad', ['soon', 'UPCOMING', 'past,upcoming', '1'])
    def test_bad_when_is_a_400(self, student_user, bad):
        res = get(student_user, f'?when={bad}')
        assert res.status_code == 400 and 'when' in res.json()


# ------------------------------------------------------------------ date range
@pytest.mark.django_db
class TestDateRange:
    def base(self, teacher_user, student_user):
        d = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=20)
        return [make(teacher_user, student_user, start=d + timedelta(days=i)) for i in range(4)], d

    def test_from_and_to_as_dates_cover_whole_utc_days_inclusive(self, teacher_user, student_user):
        bs, d = self.base(teacher_user, student_user)
        q = f'?from={(d + timedelta(days=1)).date()}&to={(d + timedelta(days=2)).date()}'
        assert set(ids(get(student_user, q))) == {str(bs[1].id), str(bs[2].id)}

    def test_from_and_to_as_datetimes(self, teacher_user, student_user):
        bs, d = self.base(teacher_user, student_user)
        res = APIClient()
        res.force_authenticate(user=student_user)
        r = res.get(URL, {'from': (d + timedelta(days=1)).isoformat(), 'to': (d + timedelta(days=1, hours=1)).isoformat()})
        assert [x['id'] for x in r.json()['results']] == [str(bs[1].id)]

    def test_only_from_or_only_to(self, teacher_user, student_user):
        bs, d = self.base(teacher_user, student_user)
        assert len(ids(get(student_user, f'?from={(d + timedelta(days=2)).date()}'))) == 2
        assert len(ids(get(student_user, f'?to={d.date()}'))) == 1

    @pytest.mark.parametrize('q', ['?from=yesterday', '?to=2025-13-45', '?from=2025-01-01T99:00', '?from=' + 'x' * 100,
                                   '?from=2025-05-02&to=2025-05-01'])
    def test_bad_dates_or_reversed_range_are_a_400(self, student_user, q):
        res = get(student_user, q)
        assert res.status_code == 400 and ({'from', 'to'} & set(res.json())), res.json()

    def test_naive_datetimes_are_read_as_utc(self, teacher_user, student_user):
        bs, d = self.base(teacher_user, student_user)
        naive = (d + timedelta(days=1)).replace(tzinfo=None).isoformat()
        assert ids(get(student_user, f'?from={naive}&to={naive}')) == [str(bs[1].id)]


# ------------------------------------------------------------------ ordering + paging
@pytest.mark.django_db
class TestOrderingAndPaging:
    def test_default_is_newest_first_but_upcoming_is_soonest_first(self, teacher_user, student_user):
        late = make(teacher_user, student_user, hours=9)
        soon = make(teacher_user, student_user, hours=2)
        assert ids(get(student_user)) == [str(late.id), str(soon.id)]
        assert ids(get(student_user, '?when=upcoming')) == [str(soon.id), str(late.id)]

    def test_explicit_ordering_wins(self, teacher_user, student_user):
        late = make(teacher_user, student_user, hours=9)
        soon = make(teacher_user, student_user, hours=2)
        assert ids(get(student_user, '?ordering=start_time_utc')) == [str(soon.id), str(late.id)]
        assert ids(get(student_user, '?when=upcoming&ordering=-start_time_utc')) == [str(late.id), str(soon.id)]

    @pytest.mark.parametrize('bad', ['price', 'student__password', '-created_at', 'start_time_utc,id'])
    def test_ordering_is_limited_to_start_time(self, student_user, bad):
        res = get(student_user, f'?ordering={bad}')
        assert res.status_code == 400 and 'ordering' in res.json()

    def test_page_size_is_honoured_and_capped(self, teacher_user, student_user):
        for i in range(5):
            make(teacher_user, student_user, hours=i + 1)
        body = get(student_user, '?page_size=2').json()
        assert (body['count'], len(body['results']), bool(body['next'])) == (5, 2, True)
        assert len(get(student_user, '?page_size=100000').json()['results']) == 5          # capped, not an error
        assert len(get(student_user, '?page_size=0').json()['results']) == 5               # falls back to the default

    def test_filters_survive_into_the_next_page_link(self, teacher_user, student_user):
        for i in range(3):
            make(teacher_user, student_user, hours=i + 1)
        nxt = get(student_user, '?when=upcoming&page_size=2').json()['next']
        assert 'when=upcoming' in nxt and 'page_size=2' in nxt

    def test_a_single_query_count_does_not_grow_with_the_number_of_lessons(self, teacher_user, student_user, django_assert_max_num_queries):
        for i in range(12):
            make(teacher_user, student_user, hours=i + 1)
        c = APIClient(); c.force_authenticate(user=student_user)
        with django_assert_max_num_queries(30):
            assert c.get(URL + '?when=upcoming').status_code == 200
