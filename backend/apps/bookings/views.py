from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from .models import Booking, LessonMemo
from apps.teachers.models import TeacherProfile
from .serializers import (
    BookingDetailSerializer,
    BookingCreateSerializer,
    ReserveSlotRequestSerializer,
    LessonMemoSerializer,
    ReviewSubmitSerializer
)
from .services.slot_generator import generate_teacher_slots
from .services.lock_service import acquire_slot_lock, release_slot_lock
from .services.reservation import ReservationError, reservation_payload, reserve_slot
from apps.materials.models import Material

class TeacherSlotsView(APIView):
    """
    Returns concrete 25-minute slots for a given teacher projected into the requested timezone.
    """
    permission_classes = (permissions.AllowAny,)

    def get(self, request, teacher_id):
        teacher = get_object_or_404(TeacherProfile, id=teacher_id, is_active=True)
        days_ahead = int(request.query_params.get('days', 7))
        viewer_tz = request.query_params.get('tz', 'UTC')

        slots = generate_teacher_slots(
            teacher=teacher,
            days_ahead=min(days_ahead, 14),
            viewer_tz_name=viewer_tz
        )
        return Response({
            "teacher_id": str(teacher.id),
            "teacher_name": teacher.user.get_full_name() or teacher.user.username,
            "viewer_timezone": viewer_tz,
            "slot_count": len(slots),
            "slots": slots
        })

class ReserveSlotView(APIView):
    """
    Validates a slot, takes the 10-minute Redis hold and creates the PENDING_PAYMENT booking in one step.
    The returned `booking_id` is what checkout pays for. Retrying the same request returns the existing live hold.
    """
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'reserve'

    def post(self, request):
        serializer = ReserveSlotRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            booking, created = reserve_slot(
                student=request.user,
                teacher_id=serializer.validated_data['teacher_id'],
                start_time_utc=serializer.validated_data['start_time_utc'],
            )
        except ReservationError as exc:
            return Response({"error": exc.message}, status=exc.status_code)
        return Response(reservation_payload(booking),
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class BookingListCreateView(generics.ListCreateAPIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return BookingCreateSerializer
        return BookingDetailSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == 'teacher' and hasattr(user, 'teacher_profile'):
            return Booking.objects.filter(teacher=user.teacher_profile).select_related('teacher__user', 'student', 'material')
        return Booking.objects.filter(student=user).select_related('teacher__user', 'student', 'material')

    def create(self, request, *args, **kwargs):
        """Same validated, locked path as /reserve/ - there is no way to create a booking that skips the hold."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        material = None
        if data.get('material_id'):
            material = Material.objects.filter(id=data['material_id']).first()
            if material is None:
                return Response({"material_id": ["Unknown material."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            booking, created = reserve_slot(
                student=request.user, teacher_id=data['teacher_id'],
                start_time_utc=data['start_time_utc'], material=material)
        except ReservationError as exc:
            return Response({"error": exc.message}, status=exc.status_code)
        return Response(reservation_payload(booking),
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

class BookingDetailView(generics.RetrieveAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = BookingDetailSerializer
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        if user.role == 'teacher' and hasattr(user, 'teacher_profile'):
            return Booking.objects.filter(teacher=user.teacher_profile)
        return Booking.objects.filter(student=user)

class SubmitMemoView(APIView):
    """
    Allows a teacher to submit the post-lesson feedback memo.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, booking_id):
        booking = get_object_or_404(Booking, id=booking_id)
        if booking.teacher.user != request.user and not request.user.is_staff:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        memo_allowed = {
            Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED,
            Booking.Status.COMPLETED_PENDING_MEMO, Booking.Status.COMPLETED_MEMO_FORFEITED,
        }
        if booking.status not in memo_allowed:
            return Response({"error": f"A memo cannot be submitted for a booking in status '{booking.status}'."},
                            status=status.HTTP_409_CONFLICT)

        feedback_text = request.data.get('feedback_text', '')
        vocabulary_words = request.data.get('vocabulary_words', [])
        pronunciation_notes = request.data.get('pronunciation_notes', '')
        homework = request.data.get('homework', '')

        memo, _ = LessonMemo.objects.update_or_create(
            booking=booking,
            defaults={
                'teacher': booking.teacher,
                'student': booking.student,
                'feedback_text': feedback_text,
                'vocabulary_words': vocabulary_words,
                'pronunciation_notes': pronunciation_notes,
                'homework': homework
            }
        )

        booking.status = Booking.Status.COMPLETED
        booking.save()

        # Automatically populate / update student's spaced repetition flashcard deck
        try:
            from apps.srs.models import StudentFlashcard
            lesson_source = f"{booking.material.title if booking.material else 'Conversation'} ({booking.teacher.user.get_full_name() or booking.teacher.user.username})"
            for vocab in vocabulary_words:
                if isinstance(vocab, dict):
                    word = vocab.get('word', '').strip()
                    definition = vocab.get('definition', '').strip()
                    phonetic = vocab.get('phonetic', '').strip()
                    part_of_speech = vocab.get('part_of_speech', '').strip()
                else:
                    word = str(vocab).strip()
                    definition = "Practiced during lesson"
                    phonetic = ""
                    part_of_speech = ""

                if word:
                    StudentFlashcard.objects.update_or_create(
                        student=booking.student,
                        word=word,
                        defaults={
                            'definition': definition or "Practiced during lesson",
                            'phonetic': phonetic,
                            'part_of_speech': part_of_speech,
                            'lesson_source': lesson_source,
                            'mastery': StudentFlashcard.Mastery.NEW,
                            'next_review_due': timezone.now().date()
                        }
                    )
        except Exception:
            pass

        return Response(LessonMemoSerializer(memo).data, status=status.HTTP_200_OK)

class SubmitReviewView(APIView):
    """
    Allows a student to submit a 1-5 star rating and optional written review.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, booking_id):
        booking = get_object_or_404(Booking, id=booking_id, student=request.user)
        serializer = ReviewSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        rating = serializer.validated_data['rating']
        review = serializer.validated_data.get('review', '')

        booking.student_rating = rating
        booking.student_review = review
        booking.save()

        # Update teacher aggregate stats
        teacher = booking.teacher
        total_ratings = Booking.objects.filter(teacher=teacher, student_rating__isnull=False)
        count = total_ratings.count()
        avg = sum(b.student_rating for b in total_ratings) / count if count > 0 else 5.0
        teacher.rating_count = count
        teacher.rating_avg = round(avg, 2)
        teacher.save()

        return Response({"status": "review_recorded", "rating_avg": teacher.rating_avg}, status=status.HTTP_200_OK)

class ReportOutageView(APIView):
    """
    Handles Eskom load shedding / grid power interruption during or before a lesson:
    1. Marks booking as INTERRUPTED_POWER.
    2. Refunds 1 lesson credit to student's wallet (or increments active CreditBundle).
    3. Waives any cancellation penalty for the teacher.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, booking_id):
        booking = get_object_or_404(Booking, id=booking_id)
        is_student = (booking.student == request.user)
        is_teacher = (booking.teacher.user == request.user)
        if not (is_student or is_teacher or request.user.is_staff):
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        reason = request.data.get("reason", "Eskom Load Shedding / Power Interruption")
        with transaction.atomic():
            # Row lock + status guard make the refund idempotent: one outage report per live booking.
            booking = Booking.objects.select_for_update().get(pk=booking.pk)
            if booking.status not in (Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS):
                return Response({"error": f"Outage cannot be reported for a booking in status '{booking.status}'."},
                                status=status.HTTP_409_CONFLICT)
            booking.status = Booking.Status.INTERRUPTED_POWER
            booking.save()

            # Refund 1 credit to student
            from apps.payments.models import CreditBundle
            bundle = CreditBundle.objects.filter(user=booking.student).order_by('-created_at').first()
            if bundle:
                bundle.remaining_credits += 1
                bundle.save()
            else:
                CreditBundle.objects.create(
                    user=booking.student,
                    pack_name="Eskom Outage Refund Credit",
                    total_credits=1,
                    remaining_credits=1,
                    amount_paid=0.00,
                    currency="USD"
                )

            # Record double-entry ledger journal entry
            from apps.payments.services.ledger_service import record_outage_refund_entry
            record_outage_refund_entry(booking=booking, user=booking.student)

        return Response({
            "status": "interrupted_power",
            "message": "Eskom power interruption recorded. 1 lesson credit has been automatically refunded to the student's wallet.",
            "reason": reason,
            "refunded": True
        }, status=status.HTTP_200_OK)
