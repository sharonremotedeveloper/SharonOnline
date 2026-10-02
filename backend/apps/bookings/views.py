from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from apps.users.serializers import validate_iana_timezone
from apps.common.schema import ReserveRequestSerializer, ReservationSerializer
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import timedelta
from django.conf import settings
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
from .services.state_machine import InvalidTransition, transition_booking
from apps.payments.services.credits import grant_credit
from apps.payments.services.settlement import successful_transaction
from apps.materials.models import Material

MAX_SLOT_DAYS = 14


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class TeacherSlotsView(APIView):
    """
    Returns concrete 25-minute slots for a given teacher projected into the requested timezone.
    """
    permission_classes = (permissions.AllowAny,)

    def get(self, request, teacher_id):
        # Same visibility rule as reserve: a tutor you cannot book has no public slots.
        teacher = get_object_or_404(TeacherProfile, id=teacher_id, is_active=True, is_verified=True)

        raw_days = request.query_params.get('days', '7')
        if not (raw_days.isascii() and raw_days.isdigit() and int(raw_days) >= 1):
            return Response({"days": "Must be a whole number of days, 1 to 14."}, status=status.HTTP_400_BAD_REQUEST)
        days_ahead = min(int(raw_days), MAX_SLOT_DAYS)

        viewer_tz = request.query_params.get('tz', 'UTC')
        try:
            validate_iana_timezone(viewer_tz)
        except DRFValidationError:
            return Response({"tz": 'Enter a valid IANA timezone, e.g. "Asia/Tokyo".'}, status=status.HTTP_400_BAD_REQUEST)

        slots = generate_teacher_slots(
            teacher=teacher,
            days_ahead=days_ahead,
            viewer_tz_name=viewer_tz
        )
        return Response({
            "teacher_id": str(teacher.id),
            "teacher_name": teacher.user.get_full_name() or teacher.user.username,
            "viewer_timezone": viewer_tz,
            "days": days_ahead,
            "slot_count": len(slots),
            "slots": slots
        })

@extend_schema(request=ReserveRequestSerializer, responses={201: ReservationSerializer, 200: ReservationSerializer})
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

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class SubmitMemoView(APIView):
    """
    Allows a teacher to submit the post-lesson feedback memo.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, booking_id):
        booking = get_object_or_404(Booking, id=booking_id)
        if booking.teacher.user != request.user and not request.user.is_staff:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        # Only lessons that actually took place can carry a memo (a merely CONFIRMED lesson has not happened yet).
        memo_allowed = {
            Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED,
            Booking.Status.COMPLETED_PENDING_MEMO, Booking.Status.COMPLETED_MEMO_FORFEITED,
        }
        if booking.status not in memo_allowed:
            return Response({"error": f"A memo cannot be submitted for a booking in status '{booking.status}'."},
                            status=status.HTTP_409_CONFLICT)

        feedback_text = request.data.get('feedback_text', '')
        vocabulary_words = request.data.get('vocabulary_words', [])
        pronunciation_notes = request.data.get('pronunciation_notes', '')
        homework = request.data.get('homework', '')

        try:
            with transaction.atomic():
                transition_booking(booking, Booking.Status.COMPLETED, actor=request.user, reason='memo submitted')
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
        except InvalidTransition:
            return Response({"error": "The booking's status changed; refresh and try again."}, status=status.HTTP_409_CONFLICT)

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

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
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

@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
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

        raw_reason = request.data.get("reason") if hasattr(request.data, "get") else None
        reason = (str(raw_reason).strip() if isinstance(raw_reason, str) else "")[:255] or "Eskom Load Shedding / Power Interruption"

        with transaction.atomic():
            # Row lock + the state machine make this idempotent: one outage settlement per booking, ever.
            booking = Booking.objects.select_for_update(of=('self',)).select_related('teacher__user', 'student').get(pk=booking.pk)
            if booking.status not in (Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS):
                return Response({"error": f"Outage cannot be reported for a booking in status '{booking.status}'."},
                                status=status.HTTP_409_CONFLICT)

            # Only around the lesson itself - otherwise "outage" would be a free, instant refund for any future booking.
            now = timezone.now()
            opens = booking.start_time_utc - timedelta(seconds=settings.OUTAGE_REPORT_BEFORE_START_SECONDS)
            closes = booking.end_time_utc + timedelta(seconds=settings.OUTAGE_REPORT_AFTER_END_SECONDS)
            if not (opens <= now <= closes):
                return Response({"error": "A power outage can only be reported from "
                                          f"{settings.OUTAGE_REPORT_BEFORE_START_SECONDS // 60} minutes before the lesson until "
                                          f"{settings.OUTAGE_REPORT_AFTER_END_SECONDS // 60} minutes after it ends."},
                                status=status.HTTP_409_CONFLICT)

            result = transition_booking(booking, Booking.Status.INTERRUPTED_POWER, actor=request.user, reason=reason)
            if result.changed:
                # The lesson did not run: return the student's money as a wallet credit and drain the booking's escrow
                # in the ledger by exactly what was captured (the tutor is not paid for an interrupted lesson).
                grant_credit(booking.student, credits=1, pack_name="Eskom Outage Refund Credit")
                from apps.payments.services.ledger_service import record_outage_refund_entry
                record_outage_refund_entry(booking=booking, user=booking.student,
                                           payment_transaction=successful_transaction(booking))

        return Response({
            "status": "interrupted_power",
            "message": "Eskom power interruption recorded. 1 lesson credit has been automatically refunded to the student's wallet.",
            "reason": reason,
            "refunded": True
        }, status=status.HTTP_200_OK)
