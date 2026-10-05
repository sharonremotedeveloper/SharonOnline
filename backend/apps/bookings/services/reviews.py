"""
The one place a student's review of a lesson is recorded (Task 9.10).

Rules: the student's own lesson, one that actually took place, reviewed once. The written text and tags are private to
staff (asymmetric-privacy invariant); the tutor's public average is recomputed from the database under a tutor-row lock.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone

from apps.bookings.models import Booking
from apps.teachers.models import TeacherProfile

# Mirrors the rubric in frontend/src/components/student/ReviewRubricModal.tsx (RUBRIC_TAGS).
REVIEW_TAGS = (
    "Patience & Empathy", "Clear Pronunciation", "Great Corrections", "Conversational Flow",
    "Encouraging Atmosphere", "Deep Topic Expertise", "Ideal Pacing", "Helpful Examples",
)

REVIEWABLE_STATUSES = (
    Booking.Status.COMPLETED_PENDING_MEMO, Booking.Status.COMPLETED, Booking.Status.COMPLETED_MEMO_FORFEITED,
)


class ReviewError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code, self.message = status_code, message


def submit_review(*, booking_id, student, rating: int, tags: list, notes: str) -> Booking:
    with transaction.atomic():
        # Lock order booking -> tutor, like cancel / memo / no-show (they strike the tutor while holding the booking row);
        # the old tutor -> booking order could deadlock with them on Postgres (slice T1b). The tutor lock still serialises
        # two students reviewing the same tutor, so neither average is computed from a stale read.
        booking = Booking.objects.select_for_update().filter(pk=booking_id, student=student).first()
        if booking is None:
            raise ReviewError(404, "Lesson not found.")
        teacher_id = booking.teacher_id
        TeacherProfile.objects.select_for_update().only('id').get(pk=teacher_id)

        if booking.status not in REVIEWABLE_STATUSES:
            raise ReviewError(409, "Only a lesson that has taken place can be reviewed.")
        if booking.student_rating is not None:
            raise ReviewError(409, "You have already reviewed this lesson.")

        booking.student_rating = rating
        booking.student_review = notes
        booking.student_review_tags = tags
        booking.reviewed_at = timezone.now()
        booking.save(update_fields=['student_rating', 'student_review', 'student_review_tags', 'reviewed_at', 'updated_at'])

        stats = Booking.objects.filter(teacher_id=teacher_id, student_rating__isnull=False).aggregate(
            avg=Avg('student_rating'), n=Count('id'))
        # Only the two rating columns are written, so a concurrent strike / deactivation is never overwritten.
        TeacherProfile.objects.filter(pk=teacher_id).update(
            rating_avg=Decimal(str(stats['avg'])).quantize(Decimal('0.01'), ROUND_HALF_UP), rating_count=stats['n'])
    return booking
