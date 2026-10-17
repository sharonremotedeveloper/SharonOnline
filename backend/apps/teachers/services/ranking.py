"""
Deterministic Bayesian tutor ranking, cold-start exploration, and reliability scoring service.

Implements Requirement R1 for Sharon Online ESL platform.
Compatible with PostgreSQL and SQLite.
"""

from decimal import Decimal
from typing import Optional

from django.db.models import (
    Case,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Cast, Coalesce

from apps.bookings.models import Booking
from apps.teachers.models import TeacherProfile

# --- Core Algorithmic Constants ---
BAYESIAN_PRIOR_WEIGHT_C: float = 10.0
BAYESIAN_PRIOR_MEAN_M: float = 4.80
BAYESIAN_PRIOR_PRODUCT: float = BAYESIAN_PRIOR_WEIGHT_C * BAYESIAN_PRIOR_MEAN_M  # 48.0

COLD_START_LESSON_THRESHOLD: int = 10
COLD_START_MAX_BOOST: float = 0.25

STRIKE_PENALTY_WEIGHT: float = 0.35
POWER_BACKUP_BONUS: float = 0.05

COMPLETED_LESSON_STATUSES = (
    Booking.Status.COMPLETED,
    Booking.Status.COMPLETED_PENDING_MEMO,
    Booking.Status.COMPLETED_MEMO_FORFEITED,
)

DEFAULT_DIRECTORY_ORDERING = (
    '-ranking_score',
    '-completed_lessons_count',
    '-rating_count',
    'pk',
)

ORDERING_MAP = {
    'ranking': ('-ranking_score', '-completed_lessons_count', '-rating_count', 'pk'),
    '-ranking': ('-ranking_score', '-completed_lessons_count', '-rating_count', 'pk'),
    'ranking_score': ('-ranking_score', '-completed_lessons_count', '-rating_count', 'pk'),
    '-ranking_score': ('-ranking_score', '-completed_lessons_count', '-rating_count', 'pk'),
    'rating': ('-rating_avg', '-rating_count', 'pk'),
    '-rating': ('-rating_avg', '-rating_count', 'pk'),
    'rating_avg': ('-rating_avg', '-rating_count', 'pk'),
    '-rating_avg': ('-rating_avg', '-rating_count', 'pk'),
    'lessons_completed': ('-completed_lessons_count', '-ranking_score', 'pk'),
    '-lessons_completed': ('-completed_lessons_count', '-ranking_score', 'pk'),
    'completed_lessons': ('-completed_lessons_count', '-ranking_score', 'pk'),
    '-completed_lessons': ('-completed_lessons_count', '-ranking_score', 'pk'),
}


def get_completed_lessons_subquery() -> Subquery:
    """
    Correlated subquery counting completed bookings for a tutor.
    Explicit .order_by() strips model Meta ordering to avoid GROUP BY pollution.
    """
    subquery = (
        Booking.objects.filter(
            teacher_id=OuterRef('pk'),
            status__in=COMPLETED_LESSON_STATUSES,
        )
        .order_by()
        .values('teacher_id')
        .annotate(cnt=Count('id'))
        .values('cnt')
    )
    return Subquery(subquery[:1], output_field=IntegerField())


def get_ranking_expressions():
    """
    Builds the constituent Django ORM expressions for the ranking engine.
    Uses FloatField and Cast to guarantee cross-database float division.
    """
    # 1. Completed lessons count (coalesced to 0)
    completed_lessons_expr = Coalesce(
        get_completed_lessons_subquery(),
        Value(0),
        output_field=IntegerField(),
    )

    # 2. Bayesian shrinkage rating:
    # S_Bayes = (C * m + n * r) / (C + n), with C = 10.0, m = 4.80.
    # When n == 0 or null, evaluates immediately to prior mean 4.80.
    bayesian_rating_expr = Case(
        When(Q(rating_count=0) | Q(rating_count__isnull=True), then=Value(BAYESIAN_PRIOR_MEAN_M)),
        default=ExpressionWrapper(
            (
                Value(BAYESIAN_PRIOR_PRODUCT)
                + (Cast(F('rating_count'), FloatField()) * Cast(F('rating_avg'), FloatField()))
            )
            / (Value(BAYESIAN_PRIOR_WEIGHT_C) + Cast(F('rating_count'), FloatField())),
            output_field=FloatField(),
        ),
        output_field=FloatField(),
    )

    # 3. Cold-start exploration boost:
    # B_cold = 0.25 * (10 - L) / 10.0 for approved tutors with L < 10, strikes == 0, and reviews == 0.
    cold_start_boost_expr = Case(
        When(
            Q(status=TeacherProfile.Status.APPROVED)
            & Q(completed_lessons_count__lt=COLD_START_LESSON_THRESHOLD)
            & (Q(sla_strikes=0) | Q(sla_strikes__isnull=True))
            & (Q(rating_count=0) | Q(rating_count__isnull=True)),
            then=ExpressionWrapper(
                Value(COLD_START_MAX_BOOST)
                * (Value(float(COLD_START_LESSON_THRESHOLD)) - Cast(F('completed_lessons_count'), FloatField()))
                / Value(float(COLD_START_LESSON_THRESHOLD)),
                output_field=FloatField(),
            ),
        ),
        default=Value(0.0),
        output_field=FloatField(),
    )

    # 4. Reliability / SLA strike penalty: -0.35 * sla_strikes
    strike_penalty_expr = ExpressionWrapper(
        Coalesce(Cast(F('sla_strikes'), FloatField()), Value(0.0)) * Value(STRIKE_PENALTY_WEIGHT),
        output_field=FloatField(),
    )

    # 5. Power resilience backup bonus: +0.05 when has_inverter_backup is True
    power_bonus_expr = Case(
        When(has_inverter_backup=True, then=Value(POWER_BACKUP_BONUS)),
        default=Value(0.0),
        output_field=FloatField(),
    )

    # 6. Composite ranking score
    ranking_score_expr = ExpressionWrapper(
        F('bayesian_rating') + F('cold_start_boost') - F('strike_penalty') + F('power_bonus'),
        output_field=FloatField(),
    )

    return (
        completed_lessons_expr,
        bayesian_rating_expr,
        cold_start_boost_expr,
        strike_penalty_expr,
        power_bonus_expr,
        ranking_score_expr,
    )


def apply_directory_ordering(
    queryset: QuerySet[TeacherProfile],
    ordering: Optional[str] = None,
) -> QuerySet[TeacherProfile]:
    """
    Applies directory ordering based on the ?ordering= query parameter.
    Supported parameters: 'ranking', 'rating', 'lessons_completed'.
    Defaults to ('-ranking_score', '-completed_lessons_count', '-rating_count', 'pk').
    """
    clean_ordering = (ordering or '').strip().lower()
    selected_ordering = ORDERING_MAP.get(clean_ordering, DEFAULT_DIRECTORY_ORDERING)
    return queryset.order_by(*selected_ordering)


def annotate_ranking_score(
    queryset: QuerySet[TeacherProfile],
    ordering: Optional[str] = None,
) -> QuerySet[TeacherProfile]:
    """
    Annotates queryset with completed_lessons_count, bayesian_rating, cold_start_boost,
    strike_penalty, power_bonus, and composite ranking_score.
    Applies directory ordering (defaults to '-ranking_score', '-completed_lessons_count', '-rating_count', 'pk').
    """
    (
        completed_lessons_expr,
        bayesian_rating_expr,
        cold_start_boost_expr,
        strike_penalty_expr,
        power_bonus_expr,
        ranking_score_expr,
    ) = get_ranking_expressions()

    annotated_qs = (
        queryset
        .annotate(completed_lessons_count=completed_lessons_expr)
        .annotate(
            bayesian_rating=bayesian_rating_expr,
            cold_start_boost=cold_start_boost_expr,
            strike_penalty=strike_penalty_expr,
            power_bonus=power_bonus_expr,
        )
        .annotate(ranking_score=ranking_score_expr)
    )

    return apply_directory_ordering(annotated_qs, ordering)


def calculate_ranking_score(
    rating_avg: float | Decimal = 4.80,
    rating_count: int = 0,
    completed_lessons_count: int = 0,
    sla_strikes: int = 0,
    has_inverter_backup: bool = False,
    is_approved: bool = True,
) -> float:
    """
    Pure Python reference evaluator of the composite ranking score.
    Useful for offline evaluation, debugging, and fast unit verification.
    """
    avg = float(rating_avg)
    n = int(rating_count)
    lessons = int(completed_lessons_count)
    strikes = int(sla_strikes)

    # Bayesian shrinkage
    if n == 0:
        bayesian_rating = BAYESIAN_PRIOR_MEAN_M
    else:
        bayesian_rating = (BAYESIAN_PRIOR_PRODUCT + (n * avg)) / (BAYESIAN_PRIOR_WEIGHT_C + n)

    # Cold start exploration boost
    if is_approved and lessons < COLD_START_LESSON_THRESHOLD and strikes == 0 and n == 0:
        cold_start_boost = (
            COLD_START_MAX_BOOST
            * (float(COLD_START_LESSON_THRESHOLD) - float(lessons))
            / float(COLD_START_LESSON_THRESHOLD)
        )
    else:
        cold_start_boost = 0.0

    # Reliability penalty
    strike_penalty = float(strikes) * STRIKE_PENALTY_WEIGHT

    # Power bonus
    power_bonus = POWER_BACKUP_BONUS if has_inverter_backup else 0.0

    return bayesian_rating + cold_start_boost - strike_penalty + power_bonus
