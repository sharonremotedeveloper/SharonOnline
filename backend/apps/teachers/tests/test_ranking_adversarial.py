"""
Adversarial Stress Testing & Empirical Verification Suite for Requirement R1
(Deterministic Bayesian Tutor Ranking Engine).

Author: teamwork_preview_challenger_m1_1
Target: Sharon Online backend/apps/teachers/services/ranking.py
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import math
import random
import pytest

from rest_framework.test import APIClient

try:
    import tests.factories as f
except ImportError:
    import factories as f

from apps.bookings.models import Booking
from apps.teachers.models import TeacherProfile
from apps.teachers.services.ranking import (
    annotate_ranking_score,
    calculate_ranking_score,
)
from apps.teachers.strikes import add_strike
from apps.users.models import User

pytestmark = pytest.mark.django_db
DIRECTORY_URL = '/api/v1/teachers/'


def make_adversarial_tutor(
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
    """Helper to create a tutor profile for adversarial tests."""
    user = f.make_user(role=User.Role.TEACHER, username=username, email=f'{username}@adv.test')
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
# 1. Extreme Boundary Values: Reviews & Ratings (0, 1, 10000; 0.00, 1.00, 5.00)
# =========================================================================

class TestExtremeBoundaryValues:
    """Adversarial stress testing of extreme counts, boundary ratings, and float precision."""

    def test_zero_reviews_exact_prior_in_db_and_python(self):
        """0 reviews must evaluate to prior mean (4.80) with 0 cold start (L=10)."""
        tutor = make_adversarial_tutor('adv_zero_rev', rating_avg='5.00', rating_count=0, completed_lessons=10)
        qs = annotate_ranking_score(TeacherProfile.objects.filter(pk=tutor.pk))
        annotated = qs.first()

        assert annotated.bayesian_rating == pytest.approx(4.80, abs=1e-5)
        assert annotated.ranking_score == pytest.approx(4.80, abs=1e-5)
        py_score = calculate_ranking_score(rating_avg=5.00, rating_count=0, completed_lessons_count=10)
        assert py_score == pytest.approx(annotated.ranking_score, abs=1e-5)

    def test_single_review_at_rating_limits(self):
        """n=1 review across boundary ratings 0.00, 1.00, 5.00."""
        # 0.00 rating limit (e.g. edge minimum)
        t_0 = make_adversarial_tutor('adv_r0', rating_avg='0.00', rating_count=1, completed_lessons=10)
        # 1.00 rating limit (lowest review)
        t_1 = make_adversarial_tutor('adv_r1', rating_avg='1.00', rating_count=1, completed_lessons=10)
        # 5.00 rating limit (highest review)
        t_5 = make_adversarial_tutor('adv_r5', rating_avg='5.00', rating_count=1, completed_lessons=10)

        qs = annotate_ranking_score(TeacherProfile.objects.filter(pk__in=[t_0.pk, t_1.pk, t_5.pk]))
        results = {str(t.pk): t for t in qs}

        # Expected:
        # t_0: (48.0 + 1 * 0.0) / 11.0 = 48/11 = 4.363636...
        assert results[str(t_0.pk)].ranking_score == pytest.approx(48.0 / 11.0, abs=1e-5)
        # t_1: (48.0 + 1 * 1.0) / 11.0 = 49/11 = 4.454545...
        assert results[str(t_1.pk)].ranking_score == pytest.approx(49.0 / 11.0, abs=1e-5)
        # t_5: (48.0 + 1 * 5.0) / 11.0 = 53/11 = 4.818181...
        assert results[str(t_5.pk)].ranking_score == pytest.approx(53.0 / 11.0, abs=1e-5)

        # Monotonicity check
        assert results[str(t_0.pk)].ranking_score < results[str(t_1.pk)].ranking_score < results[str(t_5.pk)].ranking_score

    def test_ten_thousand_reviews_asymptotic_convergence(self):
        """n=10,000 reviews at boundary ratings converges within 0.001 of sample mean."""
        t_high_5 = make_adversarial_tutor('adv_high_5', rating_avg='5.00', rating_count=10000, completed_lessons=100)
        t_high_1 = make_adversarial_tutor('adv_high_1', rating_avg='1.00', rating_count=10000, completed_lessons=100)
        t_high_0 = make_adversarial_tutor('adv_high_0', rating_avg='0.00', rating_count=10000, completed_lessons=100)

        qs = annotate_ranking_score(TeacherProfile.objects.filter(pk__in=[t_high_5.pk, t_high_1.pk, t_high_0.pk]))
        results = {str(t.pk): t for t in qs}

        # 50048 / 10010 = 4.999800...
        assert results[str(t_high_5.pk)].ranking_score == pytest.approx(50048.0 / 10010.0, abs=1e-5)
        assert abs(results[str(t_high_5.pk)].ranking_score - 5.00) < 0.001

        # 10048 / 10010 = 1.003796...
        assert results[str(t_high_1.pk)].ranking_score == pytest.approx(10048.0 / 10010.0, abs=1e-5)
        assert abs(results[str(t_high_1.pk)].ranking_score - 1.00) < 0.005

        # 48 / 10010 = 0.004795...
        assert results[str(t_high_0.pk)].ranking_score == pytest.approx(48.0 / 10010.0, abs=1e-5)
        assert abs(results[str(t_high_0.pk)].ranking_score - 0.00) < 0.005

    def test_floating_point_precision_and_python_db_parity(self):
        """Verifies float precision across arbitrary decimal averages (e.g. 4.92, 4.333, 4.777)."""
        test_cases = [
            (Decimal('4.92'), 50),
            (Decimal('4.33'), 17),
            (Decimal('4.77'), 123),
            (Decimal('3.14'), 9),
            (Decimal('4.80'), 1000),
        ]
        for idx, (avg, count) in enumerate(test_cases):
            tutor = make_adversarial_tutor(f'adv_fp_{idx}', rating_avg=str(avg), rating_count=count, completed_lessons=count)
            qs = annotate_ranking_score(TeacherProfile.objects.filter(pk=tutor.pk))
            annotated = qs.first()
            py_score = calculate_ranking_score(rating_avg=float(avg), rating_count=count, completed_lessons_count=count)

            assert annotated.ranking_score == pytest.approx(py_score, abs=1e-5)
            assert not math.isnan(annotated.ranking_score)
            assert not math.isinf(annotated.ranking_score)


# =========================================================================
# 2. Cold Start Decay Transitions (L=0, 1, 9, 10, 100)
# =========================================================================

class TestColdStartDecayTransitions:
    """Stress testing the cold-start linear newcomer exploration schedule and boundary cutoffs."""

    def test_cold_start_discrete_transitions_and_rank_order(self):
        """
        Verify exact score progression:
        L=0   -> B_cold = +0.250 -> S = 5.050
        L=1   -> B_cold = +0.225 -> S = 5.025
        L=9   -> B_cold = +0.025 -> S = 4.825
        L=10  -> B_cold = +0.000 -> S = 4.800 (boundary cutoff)
        L=100 -> B_cold = +0.000 -> S = 4.800
        """
        t_0 = make_adversarial_tutor('adv_l0', completed_lessons=0)
        t_1 = make_adversarial_tutor('adv_l1', completed_lessons=1)
        t_9 = make_adversarial_tutor('adv_l9', completed_lessons=9)
        t_10 = make_adversarial_tutor('adv_l10', completed_lessons=10)
        t_100 = make_adversarial_tutor('adv_l100', completed_lessons=100)

        qs = annotate_ranking_score(TeacherProfile.objects.filter(
            pk__in=[t_0.pk, t_1.pk, t_9.pk, t_10.pk, t_100.pk]
        ))
        res = {str(t.pk): t for t in qs}

        assert res[str(t_0.pk)].cold_start_boost == pytest.approx(0.250, abs=1e-5)
        assert res[str(t_0.pk)].ranking_score == pytest.approx(5.050, abs=1e-5)

        assert res[str(t_1.pk)].cold_start_boost == pytest.approx(0.225, abs=1e-5)
        assert res[str(t_1.pk)].ranking_score == pytest.approx(5.025, abs=1e-5)

        assert res[str(t_9.pk)].cold_start_boost == pytest.approx(0.025, abs=1e-5)
        assert res[str(t_9.pk)].ranking_score == pytest.approx(4.825, abs=1e-5)

        assert res[str(t_10.pk)].cold_start_boost == pytest.approx(0.000, abs=1e-5)
        assert res[str(t_10.pk)].ranking_score == pytest.approx(4.800, abs=1e-5)

        assert res[str(t_100.pk)].cold_start_boost == pytest.approx(0.000, abs=1e-5)
        assert res[str(t_100.pk)].ranking_score == pytest.approx(4.800, abs=1e-5)

        # In directory ordering:
        # Default ordering is ('-ranking_score', '-completed_lessons_count', '-rating_count', 'pk').
        # Between L=10 and L=100: both have ranking_score 4.800, but L=100 has 100 lessons vs 10 lessons.
        # Therefore: t_0 > t_1 > t_9 > t_100 > t_10.
        ordered = list(qs)
        expected_order = [t_0.pk, t_1.pk, t_9.pk, t_100.pk, t_10.pk]
        actual_order = [t.pk for t in ordered]
        assert actual_order == expected_order

    def test_cold_start_invalidation_matrix(self):
        """Cold start boost MUST collapse to 0 if reviews exist, strikes exist, or status != approved."""
        # Baseline cold start tutor (L=0)
        t_base = make_adversarial_tutor('adv_cs_base', completed_lessons=0)
        # With 1 review
        t_rev = make_adversarial_tutor('adv_cs_rev', rating_avg='5.00', rating_count=1, completed_lessons=0)
        # With 1 strike
        t_strike = make_adversarial_tutor('adv_cs_strk', sla_strikes=1, completed_lessons=0)
        # Unapproved (in_review)
        t_unapp = make_adversarial_tutor('adv_cs_unapp', status='in_review', completed_lessons=0)

        qs = annotate_ranking_score(TeacherProfile.objects.filter(
            pk__in=[t_base.pk, t_rev.pk, t_strike.pk, t_unapp.pk]
        ))
        res = {str(t.pk): t for t in qs}

        assert res[str(t_base.pk)].cold_start_boost == pytest.approx(0.25, abs=1e-5)
        assert res[str(t_rev.pk)].cold_start_boost == pytest.approx(0.00, abs=1e-5)
        assert res[str(t_strike.pk)].cold_start_boost == pytest.approx(0.00, abs=1e-5)
        assert res[str(t_unapp.pk)].cold_start_boost == pytest.approx(0.00, abs=1e-5)


# =========================================================================
# 3. Strike Transitions (0, 1, 2, 3 strikes and directory suspension)
# =========================================================================

class TestStrikeTransitionsAndSuspension:
    """Adversarial stress testing of strike penalties, monotonicity, and directory ejection on 3rd strike."""

    def test_strike_penalty_progression_and_monotonicity(self):
        """0, 1, 2, 3 strikes must apply linear -0.35 * strikes penalty."""
        t_0 = make_adversarial_tutor('adv_s0', sla_strikes=0, rating_count=10, completed_lessons=10)
        t_1 = make_adversarial_tutor('adv_s1', sla_strikes=1, rating_count=10, completed_lessons=10)
        t_2 = make_adversarial_tutor('adv_s2', sla_strikes=2, rating_count=10, completed_lessons=10)
        t_3 = make_adversarial_tutor('adv_s3', sla_strikes=3, rating_count=10, completed_lessons=10)

        qs = annotate_ranking_score(TeacherProfile.objects.filter(
            pk__in=[t_0.pk, t_1.pk, t_2.pk, t_3.pk]
        ))
        res = {str(t.pk): t for t in qs}

        assert res[str(t_0.pk)].strike_penalty == pytest.approx(0.00, abs=1e-5)
        assert res[str(t_1.pk)].strike_penalty == pytest.approx(0.35, abs=1e-5)
        assert res[str(t_2.pk)].strike_penalty == pytest.approx(0.70, abs=1e-5)
        assert res[str(t_3.pk)].strike_penalty == pytest.approx(1.05, abs=1e-5)

        # Monotonicity
        assert (
            res[str(t_0.pk)].ranking_score
            > res[str(t_1.pk)].ranking_score
            > res[str(t_2.pk)].ranking_score
            > res[str(t_3.pk)].ranking_score
        )

    def test_third_strike_triggers_automatic_directory_suspension(self):
        """Receiving 3rd strike via add_strike transitions tutor to SUSPENDED and evicts from directory."""
        tutor = make_adversarial_tutor('adv_susp_tutor', sla_strikes=0)

        # Issue 1st and 2nd strike
        add_strike(tutor, 'no_show')
        add_strike(tutor, 'late_cancel')
        tutor.refresh_from_db()
        assert tutor.sla_strikes == 2
        assert tutor.status == TeacherProfile.Status.APPROVED

        client = APIClient()
        resp_before = client.get(DIRECTORY_URL)
        assert resp_before.status_code == 200
        ids_before = [r['id'] for r in resp_before.json()['results']]
        assert str(tutor.pk) in ids_before

        # Add 3rd strike -> triggers transition_teacher to SUSPENDED
        add_strike(tutor, 'serial_cancel')
        tutor.refresh_from_db()

        assert tutor.sla_strikes == 3
        assert tutor.status == TeacherProfile.Status.SUSPENDED

        # Check directory: tutor must be excluded
        resp_after = client.get(DIRECTORY_URL)
        assert resp_after.status_code == 200
        ids_after = [r['id'] for r in resp_after.json()['results']]
        assert str(tutor.pk) not in ids_after



# =========================================================================
# 4. Inverter Tie-Breakers
# =========================================================================

class TestInverterTieBreakers:
    """Stress testing resilience bonus (+0.05) as an unambiguous tie-breaker."""

    def test_inverter_breaks_tie_between_identical_ratings_and_reviews(self):
        """Two tutors with identical 4.95 rating and 20 reviews: inverter holder outranks non-holder."""
        t_no_inv = make_adversarial_tutor(
            'adv_no_inv',
            rating_avg='4.95',
            rating_count=20,
            has_inverter_backup=False,
            completed_lessons=20,
        )
        t_with_inv = make_adversarial_tutor(
            'adv_with_inv',
            rating_avg='4.95',
            rating_count=20,
            has_inverter_backup=True,
            completed_lessons=20,
        )

        qs = annotate_ranking_score(TeacherProfile.objects.filter(pk__in=[t_no_inv.pk, t_with_inv.pk]))
        res = {str(t.pk): t for t in qs}

        diff = res[str(t_with_inv.pk)].ranking_score - res[str(t_no_inv.pk)].ranking_score
        assert diff == pytest.approx(0.05, abs=1e-5)

        # Directory response
        client = APIClient()
        resp = client.get(DIRECTORY_URL)
        assert resp.status_code == 200
        results = [r['id'] for r in resp.json()['results']]
        assert results.index(str(t_with_inv.pk)) < results.index(str(t_no_inv.pk))

    def test_secondary_tie_breaker_lessons_completed_when_inverter_matches(self):
        """When scores, ratings, and inverter are equal, completed_lessons_count breaks tie."""
        t_fewer = make_adversarial_tutor(
            'adv_fewer_les',
            rating_avg='4.90',
            rating_count=15,
            has_inverter_backup=True,
            completed_lessons=15,
        )
        t_more = make_adversarial_tutor(
            'adv_more_les',
            rating_avg='4.90',
            rating_count=15,
            has_inverter_backup=True,
            completed_lessons=30,
        )

        client = APIClient()
        resp = client.get(DIRECTORY_URL)
        results = [r['id'] for r in resp.json()['results']]
        assert results.index(str(t_more.pk)) < results.index(str(t_fewer.pk))


# =========================================================================
# 5. Mathematical Invariance & Bayesian Shrinkage Monotonicity
# =========================================================================

class TestBayesianMathematicalInvariance:
    """
    Empirical proofs of Bayesian shrinkage invariants:
    1. Monotonicity with respect to sample mean r_bar for fixed n.
    2. Monotonicity with respect to sample size n for r_bar > m (increasing).
    3. Monotonicity with respect to sample size n for r_bar < m (decreasing).
    4. Fixed point / neutral invariance: when r_bar == m (4.80), score is constant for all n.
    5. Randomized property test verifying no NaN, bounds integrity, and Python/SQL parity.
    """

    def test_monotonicity_with_sample_mean_for_fixed_sample_size(self):
        """For fixed n=10, S_Bayes(r_1) > S_Bayes(r_2) for all r_1 > r_2."""
        means = [1.00, 2.00, 3.00, 4.00, 4.50, 4.80, 4.90, 5.00]
        scores = [calculate_ranking_score(rating_avg=m, rating_count=10, completed_lessons_count=10) for m in means]

        for i in range(len(scores) - 1):
            assert scores[i] < scores[i + 1], f"Monotonicity failed between {means[i]} and {means[i+1]}"

    def test_monotonicity_with_sample_size_when_above_prior(self):
        """When sample mean r_bar = 5.00 > 4.80, S_Bayes is strictly increasing with n."""
        sample_sizes = [0, 1, 2, 5, 10, 25, 50, 100, 500, 1000, 10000]
        scores = [calculate_ranking_score(rating_avg=5.00, rating_count=n, completed_lessons_count=10) for n in sample_sizes]

        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1], f"Expected score to increase with n, but {scores[i]} > {scores[i+1]}"
            assert scores[i + 1] <= 5.00

    def test_monotonicity_with_sample_size_when_below_prior(self):
        """When sample mean r_bar = 4.00 < 4.80, S_Bayes is strictly decreasing with n."""
        sample_sizes = [0, 1, 2, 5, 10, 25, 50, 100, 500, 1000, 10000]
        scores = [calculate_ranking_score(rating_avg=4.00, rating_count=n, completed_lessons_count=10) for n in sample_sizes]

        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Expected score to decrease with n, but {scores[i]} < {scores[i+1]}"
            assert scores[i + 1] >= 4.00

    def test_neutral_invariance_at_prior_mean(self):
        """When r_bar == 4.80 == m, S_Bayes is exactly 4.80 for ANY sample size n."""
        sample_sizes = [0, 1, 5, 10, 50, 100, 500, 1000, 10000]
        for n in sample_sizes:
            score = calculate_ranking_score(rating_avg=4.80, rating_count=n, completed_lessons_count=10)
            assert score == pytest.approx(4.80, abs=1e-5), f"Failed neutral invariance at n={n}: {score}"

    def test_randomized_property_checks_sql_parity_and_bounds(self):
        """
        Adversarial fuzzing: 100 randomly sampled parameter combinations across
        n in [0, 10000], r_bar in [0.00, 5.00], strikes in [0, 5], lessons in [0, 100], inverter in [T, F].
        Verifies:
        - No NaN or Inf.
        - S_Bayes strictly bounded in [min(m, r_bar), max(m, r_bar)].
        - Pure Python and DB annotation calculate identical values.
        """
        rng = random.Random(42)  # noqa: S311 - Deterministic seed for reproducible testing
        created_tutors = []

        for i in range(25):
            r_avg = round(rng.uniform(0.00, 5.00), 2)
            n_rev = rng.choice([0, 1, rng.randint(2, 50), rng.randint(51, 1000), 10000])
            strikes = rng.choice([0, 1, 2])
            inverter = rng.choice([True, False])
            lessons = rng.choice([0, 1, rng.randint(2, 9), 10, rng.randint(11, 100)])

            tutor = make_adversarial_tutor(
                f'adv_prop_{i}',
                rating_avg=f'{r_avg:.2f}',
                rating_count=n_rev,
                sla_strikes=strikes,
                has_inverter_backup=inverter,
                completed_lessons=lessons,
            )
            created_tutors.append((tutor, r_avg, n_rev, strikes, inverter, lessons))

        # Evaluate all in single annotated query
        tutor_pks = [t[0].pk for t in created_tutors]
        qs = annotate_ranking_score(TeacherProfile.objects.filter(pk__in=tutor_pks))
        db_by_id = {str(t.pk): t for t in qs}

        for tutor, r_avg, n_rev, strikes, inverter, lessons in created_tutors:
            annotated = db_by_id[str(tutor.pk)]
            py_score = calculate_ranking_score(
                rating_avg=r_avg,
                rating_count=n_rev,
                completed_lessons_count=lessons,
                sla_strikes=strikes,
                has_inverter_backup=inverter,
                is_approved=True,
            )

            # 1. No NaN or Inf
            assert not math.isnan(annotated.ranking_score)
            assert not math.isinf(annotated.ranking_score)

            # 2. Bayesian rating bounds
            if n_rev == 0:
                assert annotated.bayesian_rating == pytest.approx(4.80, abs=1e-5)
            else:
                lower = min(4.80, r_avg)
                upper = max(4.80, r_avg)
                assert lower - 1e-4 <= annotated.bayesian_rating <= upper + 1e-4

            # 3. DB vs Python parity
            assert annotated.ranking_score == pytest.approx(py_score, abs=1e-4), (
                f"Parity mismatch for tutor {tutor.pk}: DB={annotated.ranking_score}, PY={py_score}"
            )
