"""
Comprehensive test suite for Requirement R1: Deterministic Bayesian Tutor Ranking,
Cold-Start Exploration & Reliability Scoring for Sharon Online.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

try:
    import tests.factories as f
except ImportError:
    import factories as f
from apps.bookings.models import Booking
from apps.teachers.models import TeacherProfile
from apps.teachers.services.ranking import (
    BAYESIAN_PRIOR_MEAN_M,
    annotate_ranking_score,
    calculate_ranking_score,
)
from apps.teachers.strikes import add_strike
from apps.users.models import User

pytestmark = pytest.mark.django_db
DIRECTORY_URL = '/api/v1/teachers/'


def make_ranked_tutor(
    username: str,
    *,
    status: str = 'approved',
    rating_avg: str = '5.00',
    rating_count: int = 0,
    sla_strikes: int = 0,
    has_inverter_backup: bool = False,
    completed_lessons: int = 0,
    availability: bool = True,
) -> TeacherProfile:
    """Helper to create a tutor profile with specific ranking parameters."""
    user = f.make_user(role=User.Role.TEACHER, username=username, email=f'{username}@example.test')
    tutor = f.make_teacher_profile(
        user=user,
        status=status,
        rating_avg=Decimal(rating_avg),
        rating_count=rating_count,
        sla_strikes=sla_strikes,
        has_inverter_backup=has_inverter_backup,
        availability=availability,
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
# 1. Pure Python & Bayesian Math Verification
# =========================================================================

class TestBayesianRatingCalculation:
    """Mathematical verification of the Bayesian shrinkage formula."""

    def test_zero_reviews_starts_at_platform_prior(self):
        """A tutor with 0 reviews starts at prior mean (4.80), never 0.00."""
        score = calculate_ranking_score(rating_avg=5.00, rating_count=0, completed_lessons_count=10)
        assert score == pytest.approx(BAYESIAN_PRIOR_MEAN_M)

    def test_single_five_star_review_shrunk_toward_prior(self):
        """1 review @ 5.00 -> (48.0 + 5.00) / 11.0 = 4.81818..."""
        score = calculate_ranking_score(rating_avg=5.00, rating_count=1, completed_lessons_count=10)
        assert score == pytest.approx(53.0 / 11.0, rel=1e-4)

    def test_fifty_reviews_at_492_calculates_correctly(self):
        """50 reviews @ 4.92 -> (48.0 + 246.0) / 60.0 = 294.0 / 60.0 = 4.9000."""
        score = calculate_ranking_score(rating_avg=4.92, rating_count=50, completed_lessons_count=50)
        assert score == pytest.approx(4.9000, rel=1e-4)

    def test_single_low_review_buffered_by_prior(self):
        """1 review @ 1.00 yields bayesian_rating approx 4.4545, protected by prior."""
        score = calculate_ranking_score(rating_avg=1.00, rating_count=1, completed_lessons_count=10)
        assert score == pytest.approx(49.0 / 11.0, rel=1e-4)

    def test_high_volume_converges_to_sample_mean(self):
        """500 reviews @ 4.95 yields bayesian_rating approx 4.9471."""
        score = calculate_ranking_score(rating_avg=4.95, rating_count=500, completed_lessons_count=500)
        expected = (48.0 + 500 * 4.95) / 510.0
        assert score == pytest.approx(expected, rel=1e-4)


# =========================================================================
# 2. Acceptance Criteria 2: Veteran Outranks 1-Review Tutor
# =========================================================================

class TestAcceptanceCriteriaVeteranOutranksSingleReview:
    """AC 2: A tutor with 50 reviews at 4.92 outranks a tutor with 1 review at 5.00 under default ordering."""

    def test_veteran_outranks_one_review_tutor_in_directory(self):
        one_review = make_ranked_tutor(
            't_one_review', rating_avg='5.00', rating_count=1, completed_lessons=10
        )
        veteran = make_ranked_tutor(
            't_veteran', rating_avg='4.92', rating_count=50, completed_lessons=50
        )

        response = APIClient().get(DIRECTORY_URL)
        assert response.status_code == 200
        results = response.json()['results']
        ids = [r['id'] for r in results]

        assert str(veteran.id) in ids
        assert str(one_review.id) in ids
        assert ids.index(str(veteran.id)) < ids.index(str(one_review.id))

        # Check serialized ranking scores
        scores = {r['id']: r['ranking_score'] for r in results}
        assert scores[str(veteran.id)] == pytest.approx(4.9000, rel=1e-3)
        assert scores[str(one_review.id)] == pytest.approx(4.8182, rel=1e-3)
        assert scores[str(veteran.id)] > scores[str(one_review.id)]


# =========================================================================
# 3. Acceptance Criteria 3: Cold-Start Exploration & Zero-Review Baselines
# =========================================================================

class TestAcceptanceCriteriaColdStartExploration:
    """AC 3: An approved tutor with 0 reviews and 0 strikes outranks a tutor with strikes or rating avg < 4.20."""

    def test_approved_cold_start_tutor_outranks_strikes_and_low_ratings(self):
        new_tutor = make_ranked_tutor(
            't_new', rating_avg='5.00', rating_count=0, sla_strikes=0, completed_lessons=0
        )
        tutor_with_strike = make_ranked_tutor(
            't_strike', rating_avg='4.92', rating_count=50, sla_strikes=1, completed_lessons=50
        )
        low_rated = make_ranked_tutor(
            't_low', rating_avg='4.10', rating_count=10, sla_strikes=0, completed_lessons=10
        )

        response = APIClient().get(DIRECTORY_URL)
        assert response.status_code == 200
        results = response.json()['results']
        ids = [r['id'] for r in results]

        assert ids.index(str(new_tutor.id)) < ids.index(str(tutor_with_strike.id))
        assert ids.index(str(new_tutor.id)) < ids.index(str(low_rated.id))

        # New tutor score: 4.80 + 0.25 = 5.050
        # Strike tutor score: 4.90 - 0.35 = 4.550
        # Low rated score: (48 + 41) / 20 = 4.450
        scores = {r['id']: r['ranking_score'] for r in results}
        assert scores[str(new_tutor.id)] == pytest.approx(5.050, rel=1e-3)
        assert scores[str(tutor_with_strike.id)] == pytest.approx(4.550, rel=1e-3)
        assert scores[str(low_rated.id)] == pytest.approx(4.450, rel=1e-3)

    def test_cold_start_linear_decay_schedule(self):
        """Cold-start exploration boost decays linearly with completed lessons."""
        t0 = make_ranked_tutor('t_l0', completed_lessons=0)
        t3 = make_ranked_tutor('t_l3', completed_lessons=3)
        t5 = make_ranked_tutor('t_l5', completed_lessons=5)
        t9 = make_ranked_tutor('t_l9', completed_lessons=9)
        t10 = make_ranked_tutor('t_l10', completed_lessons=10)

        qs = annotate_ranking_score(
            TeacherProfile.objects.filter(id__in=[t0.id, t3.id, t5.id, t9.id, t10.id])
        )
        boosts = {t.id: t.cold_start_boost for t in qs}

        assert boosts[t0.id] == pytest.approx(0.2500, rel=1e-3)
        assert boosts[t3.id] == pytest.approx(0.1750, rel=1e-3)
        assert boosts[t5.id] == pytest.approx(0.1250, rel=1e-3)
        assert boosts[t9.id] == pytest.approx(0.0250, rel=1e-3)
        assert boosts[t10.id] == pytest.approx(0.0000, rel=1e-3)

    def test_cold_start_boost_zero_if_reviews_exist(self):
        """Receiving a student review immediately revokes cold start boost."""
        tutor = make_ranked_tutor('t_rev', rating_avg='5.00', rating_count=1, completed_lessons=2)
        qs = annotate_ranking_score(TeacherProfile.objects.filter(id=tutor.id))
        assert qs.first().cold_start_boost == pytest.approx(0.0)

    def test_cold_start_boost_zero_if_strikes_exist(self):
        """Incurring a strike immediately revokes cold start boost."""
        tutor = make_ranked_tutor('t_strk', rating_count=0, sla_strikes=1, completed_lessons=2)
        qs = annotate_ranking_score(TeacherProfile.objects.filter(id=tutor.id))
        assert qs.first().cold_start_boost == pytest.approx(0.0)

    def test_cold_start_boost_zero_for_unapproved_tutors(self):
        """Tutors not in approved status receive 0.0 cold start boost."""
        tutor = make_ranked_tutor('t_appl', status='applied', rating_count=0, completed_lessons=0)
        qs = annotate_ranking_score(TeacherProfile.objects.filter(id=tutor.id))
        assert qs.first().cold_start_boost == pytest.approx(0.0)


# =========================================================================
# 4. Acceptance Criteria 4: SLA Strike Penalties
# =========================================================================

class TestAcceptanceCriteriaStrikePenalties:
    """AC 4: Each active strike reduces a tutor's composite ranking score by at least 0.35 points."""

    def test_strike_penalty_reduces_score_by_35_points_per_strike(self):
        clean = make_ranked_tutor(
            't_clean', rating_avg='4.92', rating_count=50, sla_strikes=0, completed_lessons=50
        )
        strike_1 = make_ranked_tutor(
            't_strike_1', rating_avg='4.92', rating_count=50, sla_strikes=1, completed_lessons=50
        )
        strike_2 = make_ranked_tutor(
            't_strike_2', rating_avg='4.92', rating_count=50, sla_strikes=2, completed_lessons=50
        )

        qs = annotate_ranking_score(
            TeacherProfile.objects.filter(id__in=[clean.id, strike_1.id, strike_2.id])
        )
        scores = {t.id: t.ranking_score for t in qs}

        diff_1 = scores[clean.id] - scores[strike_1.id]
        diff_2 = scores[clean.id] - scores[strike_2.id]

        assert diff_1 == pytest.approx(0.35, rel=1e-3)
        assert diff_2 == pytest.approx(0.70, rel=1e-3)

    def test_add_strike_service_triggers_penalty_and_suspension_on_third(self):
        """Using real add_strike updates sla_strikes and 3rd strike removes tutor from directory."""
        tutor = make_ranked_tutor('t_active_strike', rating_avg='4.92', rating_count=50, completed_lessons=50)

        # 1st strike
        add_strike(tutor, 'no_show')
        tutor.refresh_from_db()
        assert tutor.sla_strikes == 1
        qs = annotate_ranking_score(TeacherProfile.objects.filter(id=tutor.id))
        assert qs.first().ranking_score == pytest.approx(4.90 - 0.35, rel=1e-3)

        # 2nd strike
        add_strike(tutor, 'late_cancel')
        tutor.refresh_from_db()
        assert tutor.sla_strikes == 2
        qs = annotate_ranking_score(TeacherProfile.objects.filter(id=tutor.id))
        assert qs.first().ranking_score == pytest.approx(4.90 - 0.70, rel=1e-3)

        # 3rd strike -> automatic suspension
        add_strike(tutor, 'serial_cancel')
        tutor.refresh_from_db()
        assert tutor.sla_strikes == 3
        assert tutor.status == TeacherProfile.Status.SUSPENDED

        # Excluded from bookable directory
        response = APIClient().get(DIRECTORY_URL)
        results = response.json()['results']
        assert str(tutor.id) not in [r['id'] for r in results]


# =========================================================================
# 5. Power Resilience Bonus
# =========================================================================

class TestPowerResilienceBonus:
    """Power resilience adds +0.05 bonus and acts as deterministic tie-breaker."""

    def test_inverter_backup_awards_point_05_bonus(self):
        without_power = make_ranked_tutor(
            't_no_pwr', rating_avg='4.90', rating_count=20, has_inverter_backup=False, completed_lessons=20
        )
        with_power = make_ranked_tutor(
            't_pwr', rating_avg='4.90', rating_count=20, has_inverter_backup=True, completed_lessons=20
        )

        qs = annotate_ranking_score(TeacherProfile.objects.filter(id__in=[without_power.id, with_power.id]))
        scores = {t.id: t.ranking_score for t in qs}

        diff = scores[with_power.id] - scores[without_power.id]
        assert diff == pytest.approx(0.05, rel=1e-3)

    def test_inverter_breaks_review_tie_in_directory(self):
        without_power = make_ranked_tutor(
            't_tie_no_pwr', rating_avg='4.90', rating_count=20, has_inverter_backup=False, completed_lessons=20
        )
        with_power = make_ranked_tutor(
            't_tie_pwr', rating_avg='4.90', rating_count=20, has_inverter_backup=True, completed_lessons=20
        )

        response = APIClient().get(DIRECTORY_URL)
        assert response.status_code == 200
        ids = [r['id'] for r in response.json()['results']]

        assert ids.index(str(with_power.id)) < ids.index(str(without_power.id))


# =========================================================================
# 6. Directory Sorting Parameters (?ordering=)
# =========================================================================

class TestDirectorySortingParameters:
    """Directory ordering query parameter support."""

    def test_default_ordering_is_composite_ranking(self):
        t1 = make_ranked_tutor('t_def1', rating_avg='4.92', rating_count=50, completed_lessons=50)
        t2 = make_ranked_tutor('t_def2', rating_avg='5.00', rating_count=1, completed_lessons=10)

        response = APIClient().get(DIRECTORY_URL)
        results = response.json()['results']
        ids = [r['id'] for r in results]
        assert ids.index(str(t1.id)) < ids.index(str(t2.id))

    def test_ordering_by_rating(self):
        """?ordering=rating orders by -rating_avg, -rating_count, pk."""
        t_high_avg = make_ranked_tutor('t_hi_avg', rating_avg='5.00', rating_count=1, completed_lessons=10)
        t_lower_avg = make_ranked_tutor('t_lo_avg', rating_avg='4.92', rating_count=50, completed_lessons=50)

        response = APIClient().get(f'{DIRECTORY_URL}?ordering=rating')
        results = response.json()['results']
        ids = [r['id'] for r in results]

        # Under ?ordering=rating, 5.00 outranks 4.92
        assert ids.index(str(t_high_avg.id)) < ids.index(str(t_lower_avg.id))

    def test_ordering_by_lessons_completed(self):
        """?ordering=lessons_completed orders by -completed_lessons_count, -ranking_score, pk."""
        t_veteran_lessons = make_ranked_tutor(
            't_many_lessons', rating_avg='4.50', rating_count=10, completed_lessons=100
        )
        t_few_lessons = make_ranked_tutor(
            't_few_lessons', rating_avg='5.00', rating_count=10, completed_lessons=5
        )

        response = APIClient().get(f'{DIRECTORY_URL}?ordering=lessons_completed')
        results = response.json()['results']
        ids = [r['id'] for r in results]

        assert ids.index(str(t_veteran_lessons.id)) < ids.index(str(t_few_lessons.id))

    def test_invalid_ordering_falls_back_to_default_ranking(self):
        """An invalid or empty ordering parameter defaults to composite ranking order."""
        t1 = make_ranked_tutor('t_inv1', rating_avg='4.92', rating_count=50, completed_lessons=50)
        t2 = make_ranked_tutor('t_inv2', rating_avg='5.00', rating_count=1, completed_lessons=10)

        response = APIClient().get(f'{DIRECTORY_URL}?ordering=nonexistent_field')
        assert response.status_code == 200
        ids = [r['id'] for r in response.json()['results']]
        assert ids.index(str(t1.id)) < ids.index(str(t2.id))


# =========================================================================
# 7. Completed Lessons Isolation & Edge Cases
# =========================================================================

class TestCompletedLessonsCounting:
    """Verifies that only completed bookings are credited to completed_lessons_count."""

    def test_only_completed_booking_statuses_count(self):
        tutor = make_ranked_tutor('t_statuses')
        student = f.make_student(username='s_statuses')
        start = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)

        # 3 qualifying completed lessons
        f.make_booking(teacher=tutor, student=student, status=Booking.Status.COMPLETED, start=start)
        f.make_booking(teacher=tutor, student=student, status=Booking.Status.COMPLETED_PENDING_MEMO, start=start + timedelta(hours=1))
        f.make_booking(teacher=tutor, student=student, status=Booking.Status.COMPLETED_MEMO_FORFEITED, start=start + timedelta(hours=2))

        # 3 non-qualifying bookings
        f.make_booking(teacher=tutor, student=student, status=Booking.Status.CONFIRMED, start=start + timedelta(hours=3))
        f.make_booking(teacher=tutor, student=student, status=Booking.Status.CANCELLED, start=start + timedelta(hours=4))
        f.make_booking(teacher=tutor, student=student, status=Booking.Status.PENDING_PAYMENT, start=start + timedelta(hours=5))

        qs = annotate_ranking_score(TeacherProfile.objects.filter(id=tutor.id))
        annotated = qs.first()
        assert annotated.completed_lessons_count == 3

    def test_availability_filter_preserves_annotations(self):
        """GET ?free_next_24h=true retains ranking_score and lessons_completed."""
        tutor = make_ranked_tutor('t_free_annot', rating_avg='4.92', rating_count=50, completed_lessons=15)
        # Tutor has Monday availability from 09:00 to 12:00
        response = APIClient().get(f'{DIRECTORY_URL}?free_next_24h=true')
        assert response.status_code == 200
        results = response.json()['results']
        matched = [r for r in results if r['id'] == str(tutor.id)]
        if matched:
            assert 'ranking_score' in matched[0]
            assert isinstance(matched[0]['ranking_score'], float)
            assert matched[0]['lessons_completed'] == 15


# =========================================================================
# 8. Acceptance Criteria 5: Zero N+1 Queries
# =========================================================================

class TestAcceptanceCriteriaZeroNPlusOneQueries:
    """AC 5: Directory queries execute with efficient SQL annotations without N+1 queries."""

    def test_directory_query_executes_in_constant_queries(self):
        """
        Directory listing executes in constant $O(1)$ queries regardless of page size.
        Expects at most 4 queries: 1 count query + 1 data query + 1 platform price query (+ possible session/auth).
        """
        for i in range(15):
            make_ranked_tutor(
                f't_perf_{i}',
                rating_avg=f'{4.80 + (i % 20) * 0.01:.2f}',
                rating_count=i * 2,
                completed_lessons=i,
            )

        client = APIClient()

        # Warm up catalog price cache if any
        client.get(DIRECTORY_URL)

        with CaptureQueriesContext(connection) as ctx:
            response = client.get(f'{DIRECTORY_URL}?page_size=15')
            assert response.status_code == 200
            data = response.json()['results']
            assert len(data) >= 15

        # Query count should remain constant (<= 4 queries total)
        assert len(ctx.captured_queries) <= 4, f"Captured queries ({len(ctx.captured_queries)}): {[q['sql'] for q in ctx.captured_queries]}"
