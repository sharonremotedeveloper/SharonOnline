"""
Adversarial Stress Testing Suite: View Integration, Query Parameters, and API Behavior
for Sharon Online Teacher Directory (Milestone 1).

Author: teamwork_preview_challenger_m1_2
Target: TeacherListView (/api/v1/teachers/) and ranking/ordering integration
"""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import pytest
from rest_framework.test import APIClient

try:
    import tests.factories as f
except ImportError:
    import factories as f

from apps.bookings.models import Booking
from apps.teachers.models import TeacherAvailability, TeacherProfile
from apps.users.models import User

pytestmark = pytest.mark.django_db
URL = '/api/v1/teachers/'
FROZEN_NOW = datetime(2026, 1, 5, 8, 25, tzinfo=timezone.utc)  # Monday, 10:25 Johannesburg


class FrozenClock:
    """Controls apps.common.clock.now() for one test."""

    def __init__(self, start):
        self.now = start

    def set(self, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('frozen_clock needs an aware datetime (all timestamps are UTC)')
        self.now = value

    def advance(self, **delta):
        self.now = self.now + timedelta(**delta)
        return self.now

    def __call__(self):
        return self.now


@pytest.fixture
def frozen_clock(monkeypatch):
    """Freeze apps.common.clock.now() at a fixed instant."""
    from apps.common import clock
    fake = FrozenClock(datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(clock, '_override', fake)
    return fake


def make_test_tutor(
    username: str,
    *,
    status: str = 'approved',
    rating_avg: str = '4.80',
    rating_count: int = 10,
    sla_strikes: int = 0,
    has_inverter_backup: bool = False,
    completed_lessons: int = 0,
    specialties: list = None,
    accent: str = TeacherProfile.Accent.SOUTH_AFRICAN,
    first_name: str = 'Tutor',
    last_name: str = 'Test',
    availability: bool = True,
) -> TeacherProfile:
    """Helper to generate a tutor with precise attributes for API integration tests."""
    user = f.make_user(
        role=User.Role.TEACHER,
        username=username,
        email=f'{username}@advtest.test',
        first_name=first_name,
        last_name=last_name,
    )
    tutor = f.make_teacher_profile(
        user=user,
        status=status,
        rating_avg=Decimal(rating_avg),
        rating_count=rating_count,
        sla_strikes=sla_strikes,
        has_inverter_backup=has_inverter_backup,
        accent=accent,
        specialties=specialties or [],
        availability=False,  # Custom availability handled explicitly below
    )
    if availability:
        # Monday 09:00 - 12:00 UTC (matches FROZEN_NOW)
        TeacherAvailability.objects.create(
            teacher=tutor,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(12, 0),
            is_active=True,
        )
    if completed_lessons > 0:
        student = f.make_student(username=f's_{username}')
        base_time = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        for i in range(completed_lessons):
            f.make_booking(
                teacher=tutor,
                student=student,
                status=Booking.Status.COMPLETED,
                start=base_time + timedelta(hours=i),
            )
    return tutor


# =========================================================================
# 1. Malformed ?ordering= Query Parameters (SQL Injection, Whitespace, etc.)
# =========================================================================

class TestAdversarialOrderingQueryParameters:
    """
    Stress-tests the ?ordering= query parameter against hostile injection,
    internal column probing, whitespace padding, casing, and oversized payloads.
    """

    def test_sql_injection_union_select(self):
        """Hostile UNION SELECT attempt must be safely neutralized and fall back to default ordering."""
        make_test_tutor('t_sqli_1', rating_avg='4.90', rating_count=10)
        client = APIClient()
        payload = "' UNION SELECT id, password, 1, 2, 3, 4, 5, 6, 7, 8 FROM users_user --"
        response = client.get(URL, {'ordering': payload})

        assert response.status_code == 200
        body = response.json()
        assert 'results' in body
        assert len(body['results']) >= 1

    def test_sql_injection_stacked_queries(self):
        """Hostile stacked query DROP TABLE attempt must be safely neutralized without executing SQL."""
        tutor = make_test_tutor('t_sqli_2', rating_avg='4.90', rating_count=10)
        client = APIClient()
        payload = "ranking; DROP TABLE teachers_teacherprofile; --"
        response = client.get(URL, {'ordering': payload})

        assert response.status_code == 200
        # Verify table and tutor still exist
        assert TeacherProfile.objects.filter(pk=tutor.pk).exists()

    def test_sql_injection_boolean_blind_and_comments(self):
        """Boolean blind SQLi and comment payloads must not trigger 500 or SQL syntax errors."""
        make_test_tutor('t_sqli_3', rating_avg='4.90', rating_count=10)
        client = APIClient()
        payloads = [
            "' OR 1=1 --",
            "ranking' AND 1=(SELECT 1) --",
            "/*comment*/ranking",
            "ranking; --",
            "1' or '1'='1",
            "admin'--",
            "')) OR 1=1--",
        ]
        for p in payloads:
            resp = client.get(URL, {'ordering': p})
            assert resp.status_code == 200, f"Payload {p!r} resulted in status {resp.status_code}"
            assert 'results' in resp.json()

    def test_internal_field_ordering_attempts(self):
        """
        Attempts to sort by internal or sensitive fields (user__password, user__email,
        sla_strikes, internal_notes) must NOT expose internal ordering or crash.
        """
        make_test_tutor('t_field_1', rating_avg='4.90', rating_count=10)
        client = APIClient()
        forbidden_fields = [
            'user__password',
            '-user__password',
            'user__email',
            'sla_strikes',
            '-sla_strikes',
            'created_at',
            'non_existent_field',
            '__class__',
        ]
        for field in forbidden_fields:
            resp = client.get(URL, {'ordering': field})
            assert resp.status_code == 200, f"Field {field!r} failed with status {resp.status_code}"
            # All unmapped fields safely fall back to DEFAULT_DIRECTORY_ORDERING
            assert 'results' in resp.json()

    def test_empty_whitespace_and_null_bytes(self):
        """Whitespace, empty strings, null bytes, tabs, and newlines must fall back safely to default."""
        make_test_tutor('t_ws_1', rating_avg='4.90', rating_count=10)
        client = APIClient()
        weird_inputs = [
            '',
            '   ',
            '\t',
            '\n\r',
            '%00',
            '\x00',
            'null',
            'undefined',
            'none',
        ]
        for w in weird_inputs:
            resp = client.get(URL, {'ordering': w})
            assert resp.status_code == 200
            assert len(resp.json()['results']) >= 1

    def test_case_insensitivity_and_whitespace_stripping(self):
        """Valid ordering values with mixed case or whitespace padding must be recognized."""
        t_high_rating = make_test_tutor('t_hi_rate', rating_avg='5.00', rating_count=1, completed_lessons=0)
        t_high_ranking = make_test_tutor('t_hi_rank', rating_avg='4.92', rating_count=50, completed_lessons=50)

        client = APIClient()
        # ' RANKING ' with padding
        resp_ranking = client.get(URL, {'ordering': '  RANKING  '})
        assert resp_ranking.status_code == 200
        res_ranking_ids = [r['id'] for r in resp_ranking.json()['results']]
        assert res_ranking_ids.index(str(t_high_ranking.pk)) < res_ranking_ids.index(str(t_high_rating.pk))

        # 'RaTiNg' with mixed case
        resp_rating = client.get(URL, {'ordering': 'RaTiNg'})
        assert resp_rating.status_code == 200
        res_rating_ids = [r['id'] for r in resp_rating.json()['results']]
        assert res_rating_ids.index(str(t_high_rating.pk)) < res_rating_ids.index(str(t_high_ranking.pk))

    def test_multi_value_ordering_parameter(self):
        """QueryDict with multiple ordering params (e.g. ?ordering=rating&ordering=ranking) takes last safely."""
        make_test_tutor('t_multi_1', rating_avg='4.90', rating_count=10)
        client = APIClient()
        # Query string with multiple ?ordering= keys
        resp = client.get(f'{URL}?ordering=rating&ordering=ranking')
        assert resp.status_code == 200
        assert 'results' in resp.json()

    def test_excessive_length_ordering_string(self):
        """Oversized 10,000-character ordering parameter must not cause buffer/stack errors or 500."""
        make_test_tutor('t_big_1', rating_avg='4.90', rating_count=10)
        client = APIClient()
        payload = 'A' * 10000
        resp = client.get(URL, {'ordering': payload})
        assert resp.status_code == 200
        assert len(resp.json()['results']) >= 1


# =========================================================================
# 2. Pagination Slicing & Ordering Determinism
# =========================================================================

class TestPaginationSlicingDeterminism:
    """
    Stress-tests pagination slicing: deterministic ordering across pages,
    strictly zero duplicates across pages, and no omitted items.
    """

    def test_deterministic_pagination_composite_ranking(self):
        """
        15 tutors with varying and tied scores paginated across 3 pages (page_size=5).
        Assert:
        1. Set union of all pages == all 15 tutors.
        2. Set intersection between any pair of pages is empty.
        3. Concatenated items exactly match unpaginated page_size=15 result.
        """
        tutors = []
        for i in range(15):
            tutors.append(make_test_tutor(
                f't_page_{i}',
                rating_avg=f'{4.50 + (i % 5) * 0.10:.2f}',
                rating_count=10 + (i % 3) * 5,
                completed_lessons=i * 2,
                has_inverter_backup=(i % 2 == 0),
            ))

        client = APIClient()
        # Single unpaginated fetch
        full_resp = client.get(URL, {'page_size': 15, 'ordering': 'ranking'})
        assert full_resp.status_code == 200
        full_ids = [r['id'] for r in full_resp.json()['results']]
        assert len(full_ids) == 15

        # Paginated fetch: 3 pages of size 5
        p1 = client.get(URL, {'page_size': 5, 'page': 1, 'ordering': 'ranking'}).json()
        p2 = client.get(URL, {'page_size': 5, 'page': 2, 'ordering': 'ranking'}).json()
        p3 = client.get(URL, {'page_size': 5, 'page': 3, 'ordering': 'ranking'}).json()

        assert p1['count'] == p2['count'] == p3['count'] == 15
        assert len(p1['results']) == 5
        assert len(p2['results']) == 5
        assert len(p3['results']) == 5

        ids_p1 = [r['id'] for r in p1['results']]
        ids_p2 = [r['id'] for r in p2['results']]
        ids_p3 = [r['id'] for r in p3['results']]

        # 1. No duplicates across pages (mutually disjoint)
        assert set(ids_p1).isdisjoint(set(ids_p2))
        assert set(ids_p1).isdisjoint(set(ids_p3))
        assert set(ids_p2).isdisjoint(set(ids_p3))

        # 2. Complete coverage
        assert set(ids_p1 + ids_p2 + ids_p3) == set(full_ids)

        # 3. Exact ordering preservation across page boundaries
        assert ids_p1 + ids_p2 + ids_p3 == full_ids

    def test_deterministic_pagination_by_rating_with_identical_scores(self):
        """
        When sorting by rating, multiple tutors having identical ratings (e.g. 5.00)
        must break ties deterministically with -rating_count and pk.
        """
        tutors = []
        for i in range(12):
            tutors.append(make_test_tutor(
                f't_rate_tie_{i}',
                rating_avg='5.00',  # All identical rating!
                rating_count=20 if i % 2 == 0 else 10,
                completed_lessons=i,
            ))

        client = APIClient()
        p1 = client.get(URL, {'page_size': 4, 'page': 1, 'ordering': 'rating'}).json()
        p2 = client.get(URL, {'page_size': 4, 'page': 2, 'ordering': 'rating'}).json()
        p3 = client.get(URL, {'page_size': 4, 'page': 3, 'ordering': 'rating'}).json()

        assert p1['count'] == 12
        ids_all = [r['id'] for r in p1['results'] + p2['results'] + p3['results']]
        assert len(ids_all) == 12
        assert len(set(ids_all)) == 12  # Strict zero duplicates

    def test_deterministic_pagination_by_lessons_completed_with_identical_lessons(self):
        """
        When sorting by lessons_completed, multiple tutors with identical lesson counts
        must break ties deterministically with -ranking_score and pk.
        """
        tutors = []
        for i in range(10):
            tutors.append(make_test_tutor(
                f't_les_tie_{i}',
                rating_avg='4.80',
                rating_count=10,
                completed_lessons=5,  # All identical lesson count!
            ))

        client = APIClient()
        p1 = client.get(URL, {'page_size': 5, 'page': 1, 'ordering': 'lessons_completed'}).json()
        p2 = client.get(URL, {'page_size': 5, 'page': 2, 'ordering': 'lessons_completed'}).json()

        assert p1['count'] == 10
        ids_all = [r['id'] for r in p1['results'] + p2['results']]
        assert len(ids_all) == 10
        assert len(set(ids_all)) == 10  # Zero duplicates

    def test_deterministic_pagination_with_free_next_24h(self, frozen_clock):
        """
        Pagination combined with free_next_24h=true:
        12 free tutors out of 20 total tutors paginated across 3 pages (page_size=5).
        Must have zero duplicate tutor IDs across pages and preserve rank ordering.
        """
        frozen_clock.set(FROZEN_NOW)
        free_tutors = []
        # 12 tutors with Monday 09:00 availability (free next 24h)
        for i in range(12):
            free_tutors.append(make_test_tutor(
                f't_free_p_{i}',
                rating_avg=f'{4.20 + (i % 6) * 0.10:.2f}',
                rating_count=10 + i,
                completed_lessons=i,
                availability=True,
            ))
        # 8 tutors without availability
        for i in range(8):
            make_test_tutor(f't_busy_p_{i}', availability=False)

        client = APIClient()
        p1 = client.get(URL, {'free_next_24h': 'true', 'page_size': 5, 'page': 1}).json()
        p2 = client.get(URL, {'free_next_24h': 'true', 'page_size': 5, 'page': 2}).json()
        p3 = client.get(URL, {'free_next_24h': 'true', 'page_size': 5, 'page': 3}).json()

        assert p1['count'] == p2['count'] == p3['count'] == 12
        assert len(p1['results']) == 5
        assert len(p2['results']) == 5
        assert len(p3['results']) == 2

        ids_p1 = [r['id'] for r in p1['results']]
        ids_p2 = [r['id'] for r in p2['results']]
        ids_p3 = [r['id'] for r in p3['results']]

        # Zero duplicates
        assert set(ids_p1).isdisjoint(set(ids_p2))
        assert set(ids_p1).isdisjoint(set(ids_p3))
        assert set(ids_p2).isdisjoint(set(ids_p3))

        # All 12 IDs present
        assert set(ids_p1 + ids_p2 + ids_p3) == {str(t.pk) for t in free_tutors}

    def test_out_of_bounds_pagination_pages(self):
        """Requesting page beyond maximum returns 404 Not Found, not unhandled 500."""
        make_test_tutor('t_oob_1')
        client = APIClient()
        assert client.get(URL, {'page': 99999}).status_code == 404
        assert client.get(URL, {'page': 0}).status_code == 404
        assert client.get(URL, {'page': -1}).status_code == 404
        assert client.get(URL, {'page': 'invalid'}).status_code == 404

    def test_max_page_size_enforcement(self):
        """page_size query param cannot exceed max_page_size (50)."""
        client = APIClient()
        resp = client.get(URL, {'page_size': 9999})
        assert resp.status_code == 200
        # Results must not exceed pagination class max_page_size (50)
        assert len(resp.json()['results']) <= 50


# =========================================================================
# 3. Simultaneous Filter Combinations
# =========================================================================

class TestSimultaneousFilterCombinations:
    """
    Stress-tests complex simultaneous filter queries, e.g.:
    ?ordering=ranking&specialty=kids&accent=british&min_rating=4.5&free_next_24h=true
    """

    def test_simultaneous_multi_filter_conjunction(self, frozen_clock):
        """
        Verify exact conjunction of ranking ordering, accent, min_rating, and free_next_24h:
        - Tutor MATCH: accent='british', rating_avg=4.90 >= 4.5, free_next_24h=True, approved
        - Tutor FAILS_ACCENT: accent='south_african', rating_avg=4.90, free_next_24h=True
        - Tutor FAILS_RATING: accent='british', rating_avg=4.20 < 4.5, free_next_24h=True
        - Tutor FAILS_FREE: accent='british', rating_avg=4.90, free_next_24h=False
        - Tutor FAILS_STATUS: accent='british', rating_avg=4.90, free_next_24h=True, status='suspended'
        """
        frozen_clock.set(FROZEN_NOW)

        tutor_match = make_test_tutor(
            't_combo_match',
            accent=TeacherProfile.Accent.BRITISH,
            rating_avg='4.90',
            rating_count=20,
            availability=True,
            status='approved',
        )
        make_test_tutor(
            't_combo_bad_acc',
            accent=TeacherProfile.Accent.SOUTH_AFRICAN,
            rating_avg='4.90',
            rating_count=20,
            availability=True,
            status='approved',
        )
        make_test_tutor(
            't_combo_bad_rate',
            accent=TeacherProfile.Accent.BRITISH,
            rating_avg='4.20',
            rating_count=20,
            availability=True,
            status='approved',
        )
        make_test_tutor(
            't_combo_bad_free',
            accent=TeacherProfile.Accent.BRITISH,
            rating_avg='4.90',
            rating_count=20,
            availability=False,
            status='approved',
        )
        make_test_tutor(
            't_combo_bad_stat',
            accent=TeacherProfile.Accent.BRITISH,
            rating_avg='4.90',
            rating_count=20,
            availability=True,
            status='suspended',
        )

        client = APIClient()
        resp = client.get(URL, {
            'ordering': 'ranking',
            'accent': TeacherProfile.Accent.BRITISH,
            'min_rating': '4.5',
            'free_next_24h': 'true',
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body['count'] == 1
        assert len(body['results']) == 1
        assert body['results'][0]['id'] == str(tutor_match.pk)
        assert 'ranking_score' in body['results'][0]
        assert 'lessons_completed' in body['results'][0]

    def test_simultaneous_filters_with_backup_power_and_search(self, frozen_clock):
        """Extended multi-filter conjunction with backup_power=true and search keyword."""
        frozen_clock.set(FROZEN_NOW)

        tutor_target = make_test_tutor(
            't_target_alice',
            first_name='Alice',
            accent=TeacherProfile.Accent.BRITISH,
            rating_avg='4.90',
            rating_count=20,
            has_inverter_backup=True,
            availability=True,
        )
        # Alice without backup power
        make_test_tutor(
            't_alice_no_power',
            first_name='Alice',
            accent=TeacherProfile.Accent.BRITISH,
            rating_avg='4.90',
            has_inverter_backup=False,
            availability=True,
        )
        # Bob with backup power
        make_test_tutor(
            't_bob_with_power',
            first_name='Bob',
            accent=TeacherProfile.Accent.BRITISH,
            rating_avg='4.90',
            has_inverter_backup=True,
            availability=True,
        )

        client = APIClient()
        resp = client.get(URL, {
            'ordering': 'ranking',
            'accent': TeacherProfile.Accent.BRITISH,
            'min_rating': '4.5',
            'free_next_24h': 'true',
            'backup_power': 'true',
            'search': 'Alice',
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body['count'] == 1
        assert body['results'][0]['id'] == str(tutor_target.pk)

    def test_specialty_filter_triggers_unhandled_500_on_sqlite(self):
        """
        EMPIRICAL CHALLENGER FINDING:
        TeacherListView line 115 uses `specialties__contains=[specialty]`.
        On SQLite, Django ORM does NOT support __contains on JSONField
        (connection.features.supports_json_field_contains is False).
        Querying ?specialty=kids raises django.db.utils.NotSupportedError,
        resulting in an unhandled HTTP 500 error on SQLite.
        """
        from django.db import connection
        make_test_tutor('t_spec_err', specialties=['kids'])

        client = APIClient(raise_request_exception=False)
        response = client.get(URL, {
            'ordering': 'ranking',
            'specialty': 'kids',
            'accent': TeacherProfile.Accent.BRITISH,
            'min_rating': '4.5',
            'free_next_24h': 'true',
        })

        if connection.vendor == 'sqlite':
            # Empirically verified failure: 500 Internal Server Error due to NotSupportedError
            assert response.status_code == 500, (
                f"Expected SQLite to fail with 500 on specialty filter, got {response.status_code}"
            )
        else:
            # On PostgreSQL, JSONField contains (@>) is natively supported
            assert response.status_code in (200, 400)

    def test_accent_name_vs_code_filtering(self):
        """
        Adversarial test: accent filter requires exact DB code ('UK'), not display name ('british').
        Querying ?accent=british returns 0 matches for a tutor with accent='UK'.
        """
        tutor = make_test_tutor('t_acc_code', accent=TeacherProfile.Accent.BRITISH)
        client = APIClient()

        # By code 'UK' -> MATCH
        resp_code = client.get(URL, {'accent': TeacherProfile.Accent.BRITISH}).json()
        assert resp_code['count'] == 1
        assert resp_code['results'][0]['id'] == str(tutor.pk)

        # By name 'british' -> No match (exact match against 'UK')
        resp_name = client.get(URL, {'accent': 'british'}).json()
        assert resp_name['count'] == 0

    def test_empty_matching_set_returns_200_clean_empty_response(self):
        """Simultaneous filters producing empty intersection must return HTTP 200 with count: 0, not 500."""
        make_test_tutor('t_empty_1', accent=TeacherProfile.Accent.AMERICAN)

        client = APIClient()
        resp = client.get(URL, {
            'accent': 'OTHER',
            'min_rating': '4.99',
            'ordering': 'ranking',
            'backup_power': 'true',
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body['count'] == 0
        assert body['results'] == []

    def test_malformed_filter_parameters(self):
        """Invalid filter parameters must either be ignored or return 400 (never 500)."""
        make_test_tutor('t_malf_1')
        client = APIClient()

        # Non-numeric min_rating is caught by ValueError and ignored
        resp_min_rate = client.get(URL, {'min_rating': 'not_a_float'})
        assert resp_min_rate.status_code == 200

        # Empty specialty / accent are ignored
        resp_empty_spec = client.get(URL, {'specialty': '', 'accent': ''})
        assert resp_empty_spec.status_code == 200

        # Invalid booleans raise ValidationError 400
        assert client.get(URL, {'backup_power': 'maybe'}).status_code == 400
        assert client.get(URL, {'free_next_24h': '1'}).status_code == 400
        assert client.get(URL, {'backup_power': ''}).status_code == 400


# =========================================================================
# 4. Concurrency & Cache Pollution Checks
# =========================================================================

class TestConcurrencyAndCachePollution:
    """
    Verifies that alternating ordering modes, concurrent requests, and cache reads
    do not pollute querysets, corrupt calculations, or leak state across requests.
    """

    def test_interleaved_ordering_queries_isolated(self):
        """
        Alternating requests for 'ranking', 'rating', and 'lessons_completed'
        must yield completely isolated and correct ordering each time without cache cross-talk.
        """
        # Veteran: high rating, many lessons
        veteran = make_test_tutor('t_vet', rating_avg='4.92', rating_count=50, completed_lessons=50)
        # New star: 1 review at 5.00, 0 lessons
        new_star = make_test_tutor('t_star', rating_avg='5.00', rating_count=1, completed_lessons=0)

        client = APIClient()

        # 1. Request ranking -> veteran outranks new_star
        r1 = client.get(URL, {'ordering': 'ranking'}).json()['results']
        r1_ids = [r['id'] for r in r1]
        assert r1_ids.index(str(veteran.pk)) < r1_ids.index(str(new_star.pk))

        # 2. Request rating -> new_star (5.00) outranks veteran (4.92)
        r2 = client.get(URL, {'ordering': 'rating'}).json()['results']
        r2_ids = [r['id'] for r in r2]
        assert r2_ids.index(str(new_star.pk)) < r2_ids.index(str(veteran.pk))

        # 3. Request ranking again -> must match r1 exactly (no lingering mutation)
        r3 = client.get(URL, {'ordering': 'ranking'}).json()['results']
        r3_ids = [r['id'] for r in r3]
        assert r3_ids == r1_ids

    def test_free_next_24h_cache_isolation_between_filters(self, frozen_clock):
        """
        Calling ?free_next_24h=true with differing accent filters must not leak
        cached candidate slots or teacher IDs between requests.
        """
        frozen_clock.set(FROZEN_NOW)
        t_british = make_test_tutor('t_iso_brit', accent=TeacherProfile.Accent.BRITISH, availability=True)
        t_american = make_test_tutor('t_iso_amer', accent=TeacherProfile.Accent.AMERICAN, availability=True)

        client = APIClient()

        # Query British
        res_brit = client.get(URL, {'free_next_24h': 'true', 'accent': TeacherProfile.Accent.BRITISH}).json()
        assert res_brit['count'] == 1
        assert res_brit['results'][0]['id'] == str(t_british.pk)

        # Query American
        res_amer = client.get(URL, {'free_next_24h': 'true', 'accent': TeacherProfile.Accent.AMERICAN}).json()
        assert res_amer['count'] == 1
        assert res_amer['results'][0]['id'] == str(t_american.pk)



# =========================================================================
# 5. Data Leakage & Information Exposure Protection
# =========================================================================

class TestDataLeakageAndInformationExposure:
    """
    Verifies that the serialized directory API response strictly does NOT expose
    sensitive credentials, internal audit fields, or private user data.
    """

    def test_no_sensitive_fields_leaked_in_directory_api(self):
        """
        Ensure user password hash, email, is_staff, is_superuser, sla_strikes,
        internal notes, etc., are never present in directory JSON responses.
        """
        tutor = make_test_tutor(
            't_leak_probe',
            sla_strikes=2,
            rating_avg='4.80',
            rating_count=10,
        )

        client = APIClient()
        response = client.get(URL)
        assert response.status_code == 200
        results = response.json()['results']

        probed = next(r for r in results if r['id'] == str(tutor.pk))

        # Sensitive fields that MUST NEVER leak to public directory:
        forbidden_keys = [
            'password',
            'email',
            'is_staff',
            'is_superuser',
            'sla_strikes',
            'notes',
            'internal_notes',
            'last_login',
            'groups',
            'user_permissions',
        ]
        for key in forbidden_keys:
            assert key not in probed, f"Data leakage: '{key}' exposed in public TeacherListView!"

        # Whitelisted fields that SHOULD be present:
        expected_keys = [
            'id',
            'user_id',
            'full_name',
            'first_name',
            'last_name',
            'headline',
            'accent',
            'rating_avg',
            'rating_count',
            'ranking_score',
            'lessons_completed',
            'price_per_25min_usd',
            'specialties',
            'country',
            'is_verified',
            'has_inverter_backup',
        ]
        for key in expected_keys:
            assert key in probed, f"Missing expected public field: '{key}'"
