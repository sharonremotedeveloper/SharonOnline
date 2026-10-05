from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError as DRFValidationError
from apps.users.serializers import validate_iana_timezone
from apps.common.schema import (CancelPreviewSerializer, CancelRequestSerializer, CancelResultSerializer, ErrorCodeSerializer,
                                RescheduleRequestSerializer, ReserveRequestSerializer, ReservationSerializer, ReviewResultSerializer)
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import AttendanceAudit, Booking, LessonMemo
from apps.srs.models import StudentFlashcard
from apps.teachers.models import TeacherProfile
from .serializers import (
    BookingDetailSerializer,
    BookingCreateSerializer,
    ReserveSlotRequestSerializer,
    LessonMemoInputSerializer,
    LessonMemoSerializer,
    ReviewInputSerializer
)
from .services.slot_generator import generate_teacher_slots
from .services.lock_service import acquire_slot_lock, release_slot_lock
from .services.reservation import ReservationError, reservation_payload, reserve_slot
from .services import cancellation, rescheduling
from .services.listing import BookingListQuerySerializer, BookingPagination, filter_bookings, scoped_bookings
from .services.reviews import ReviewError, submit_review
from .services.state_machine import InvalidTransition, transition_booking
from apps.users.permissions import IsStudent
from apps.payments.services.credits import grant_credit
from apps.payments.services.credits import CreditRedemptionError, redeem_booking_credit
from apps.payments.services.settlement import successful_transaction
from apps.payments.services.funding import funding_for_settlement
from apps.payments.models import CreditWalletEntry
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
        teacher = get_object_or_404(TeacherProfile.objects.bookable(), id=teacher_id)

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


@extend_schema_view(get=extend_schema(
    summary='My lessons (students: lessons I booked; tutors: my roster)',
    parameters=[
        OpenApiParameter('status', str, description='One or more booking statuses, comma-separated or repeated.'),
        OpenApiParameter('when', str, enum=['upcoming', 'past'], description='upcoming = not yet ended, excluding cancelled and lapsed unpaid holds; past = already ended.'),
        OpenApiParameter('from', str, description='Lessons starting on/after this UTC date (YYYY-MM-DD) or ISO date-time.'),
        OpenApiParameter('to', str, description='Lessons starting on/before this UTC date (whole day) or ISO date-time.'),
        OpenApiParameter('ordering', str, enum=['start_time_utc', '-start_time_utc'], description='Default: soonest first for when=upcoming, newest first otherwise.'),
        OpenApiParameter('page_size', int, description='1-100 (default 20).'),
    ]))
class BookingListCreateView(generics.ListCreateAPIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return BookingCreateSerializer
        return BookingDetailSerializer

    pagination_class = BookingPagination

    def get_queryset(self):
        qs = scoped_bookings(self.request.user)
        if self.request.method != 'GET':
            return qs
        query = BookingListQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        return filter_bookings(qs, query.validated_data)[0]

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
            return Booking.objects.select_related('student__student_profile', 'teacher__user', 'material').filter(teacher=user.teacher_profile)
        return Booking.objects.select_related('student__student_profile', 'teacher__user', 'material').filter(student=user)


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
class RedeemCreditView(APIView):
    permission_classes = (IsStudent,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'checkout'

    def post(self, request, booking_id):
        booking = get_object_or_404(Booking, pk=booking_id, student=request.user)
        try:
            booking, changed = redeem_booking_credit(booking=booking, student=request.user)
        except CreditRedemptionError as exc:
            return Response({'error': exc.message}, status=exc.status_code)
        return Response({
            'success': True,
            'booking_id': str(booking.id),
            'status': booking.status,
            'redeemed': changed,
            'message': '1 lesson credit redeemed successfully.' if changed else 'Credit was already redeemed.',
        })

# A memo is only for lessons that have actually ended. CONFIRMED / IN_PROGRESS lessons are settled by the attendance job
# first (which decides completed-pending-memo vs disputed), so a tutor cannot skip that check by posting a memo early.
MEMO_ALLOWED_STATUSES = (
    Booking.Status.COMPLETED_PENDING_MEMO, Booking.Status.COMPLETED, Booking.Status.COMPLETED_MEMO_FORFEITED,
)


def _sync_flashcards(booking, words):
    """One card per distinct word. Existing cards are left alone so correcting a memo never resets a student's progress."""
    lesson_source = (f"{booking.material.title if booking.material else 'Conversation'} "
                     f"({booking.teacher.user.get_full_name() or booking.teacher.user.username})")[:255]
    today = timezone.now().date()
    for entry in words:
        StudentFlashcard.objects.get_or_create(
            student=booking.student, word=entry['word'],
            defaults={
                'definition': entry['definition'] or "Practiced during lesson",
                'phonetic': entry['phonetic'],
                'part_of_speech': entry['part_of_speech'],
                'lesson_source': lesson_source,
                'mastery': StudentFlashcard.Mastery.NEW,
                'next_review_due': today,
            })


@extend_schema(request=LessonMemoInputSerializer, responses=LessonMemoSerializer)
class SubmitMemoView(APIView):
    """
    The lesson's own tutor submits (or later corrects) the post-lesson memo. Everything below succeeds or fails together:
    the validated memo, the booking's move to COMPLETED, and the student's flashcards.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, booking_id):
        booking = get_object_or_404(Booking.objects.select_related('teacher__user', 'student', 'material'), id=booking_id)
        if booking.teacher.user_id != request.user.id:
            return Response({"error": "Only this lesson's tutor can submit its memo."}, status=status.HTTP_403_FORBIDDEN)
        if booking.status not in MEMO_ALLOWED_STATUSES:
            return Response({"error": f"A memo cannot be submitted for a booking in status '{booking.status}'."},
                            status=status.HTTP_409_CONFLICT)

        serializer = LessonMemoInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            with transaction.atomic():
                transition_booking(booking, Booking.Status.COMPLETED, actor=request.user, reason='memo submitted')
                memo, _ = LessonMemo.objects.update_or_create(
                    booking=booking,
                    defaults={
                        'teacher': booking.teacher,
                        'student': booking.student,
                        'feedback_text': data['feedback_text'],
                        'vocabulary_words': data['vocabulary_words'],
                        'pronunciation_notes': data['pronunciation_notes'],
                        'grammar_notes': data['grammar_notes'],
                        'homework': data['homework'],
                    }
                )
                _sync_flashcards(booking, data['vocabulary_words'])
        except InvalidTransition:
            return Response({"error": "The booking's status changed; refresh and try again."}, status=status.HTTP_409_CONFLICT)

        return Response(LessonMemoSerializer(memo).data, status=status.HTTP_200_OK)


@extend_schema(request=ReviewInputSerializer, responses={200: ReviewResultSerializer})
class SubmitReviewView(APIView):
    """
    A student rates a lesson that took place: 1-5 stars, optional rubric tags and private notes. One review per lesson;
    the written text is private to staff. Canonical URL: POST /student/bookings/<id>/review/.
    """
    permission_classes = (IsStudent,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'review'

    def post(self, request, booking_id=None, pk=None):
        serializer = ReviewInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            submit_review(booking_id=booking_id or pk, student=request.user, rating=data['rating'],
                          tags=data['tags'], notes=data['notes'])
        except ReviewError as exc:
            return Response({"error": exc.message}, status=exc.status_code)
        return Response({"success": True, "status": "review_recorded",
                         "message": "Thank you! Your confidential review has been recorded."})


@extend_schema(deprecated=True, request=ReviewInputSerializer, responses={200: ReviewResultSerializer})
class LegacySubmitReviewView(SubmitReviewView):
    """Old URL (POST /bookings/<id>/review/), kept for existing clients; identical behaviour."""


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)  # TODO(8.8+): replace with typed serializers
class ReportOutageView(APIView):
    """
    An Eskom load-shedding / grid outage around the lesson (D-6):
    1. The lesson's tutor or staff can report it; a student only when the provider confirms an active outage in the tutor's area
       (a student's own power or internet problem is a dispute, since it would refund them while the tutor goes unpaid).
    2. The booking becomes INTERRUPTED_POWER and a full gateway refund is queued (the student may convert it to wallet credit).
       The tutor is not paid and gets no strike.
    3. A lesson the tutor already taught for the minimum lesson time is a delivered lesson, not an outage.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, booking_id):
        booking = get_object_or_404(Booking, id=booking_id)
        is_student = (booking.student_id == request.user.id)
        is_teacher = (booking.teacher.user_id == request.user.id)
        if not (is_student or is_teacher or request.user.is_staff):
            return Response({"error": "Only the student or the tutor of this lesson can report a power outage.",
                             "code": "not_a_party"}, status=status.HTTP_403_FORBIDDEN)

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

            # A student's report is accepted only when the provider independently confirms an outage in the tutor's area right now;
            # the lesson's tutor and staff do not need that corroboration.
            if is_student and not (is_teacher or request.user.is_staff):
                from apps.integrations.models import EskomAreaStatus
                area = EskomAreaStatus.objects.filter(
                    area_id=booking.teacher.eskom_area_id,
                    provider_status=EskomAreaStatus.ProviderStatus.OK,
                    fresh_until__gte=now,
                ).first()
                corroborated = False
                for outage in (area.outages if area and isinstance(area.outages, list) else []):
                    start = parse_datetime(str(outage.get('start') or '')) if isinstance(outage, dict) else None
                    end = parse_datetime(str(outage.get('end') or '')) if isinstance(outage, dict) else None
                    if start and end and start <= now <= end:
                        corroborated = True
                        break
                if not corroborated:
                    return Response({
                        'code': 'outage_unconfirmed',
                        'error': 'A student outage report requires an active provider outage in the tutor\'s area, '
                                 'or confirmation from the tutor or staff.',
                    }, status=status.HTTP_409_CONFLICT)

            # A lesson the tutor already taught for the minimum lesson time is a delivered lesson, not an outage.
            from apps.integrations.services.attendance import credited_attendance_minutes, TEACHER
            taught = credited_attendance_minutes(booking, TEACHER)
            if taught >= settings.LESSON_DELIVERED_MIN_TEACHER_MINUTES:
                return Response({"error": f"The tutor already taught {taught} minutes, so this lesson counts as delivered.",
                                 "code": "lesson_delivered"}, status=status.HTTP_409_CONFLICT)

            funding = funding_for_settlement(booking, context='power_outage_refund')
            if funding is None:
                return Response({'error': 'This booking has no verified funding record; support review is required.'},
                                status=status.HTTP_409_CONFLICT)
            result = transition_booking(booking, Booking.Status.INTERRUPTED_POWER, actor=request.user, reason=reason)
            if result.changed:
                # The lesson did not run: the whole capture goes back to the student (through the gateway, or as a restored
                # credit for a credit-funded lesson) and the booking's escrow drains by exactly what was captured.
                from apps.payments.models import LedgerEntry, RefundRequest
                from apps.payments.services.refunds import request_refund
                request_refund(booking, RefundRequest.Reason.OUTAGE, event_type=LedgerEntry.EventType.OUTAGE_REFUND,
                               description='Power outage interrupted the lesson')

        return Response({
            "status": "interrupted_power",
            "message": "Power interruption recorded. The student will be refunded to their original payment method.",
            "reason": reason,
            "refunded": True
        }, status=status.HTTP_200_OK)


def _booking_of_party(request, booking_id):
    """The booking, if the caller is its student or tutor. Strangers get a 404 (it does not exist for them); staff a 403."""
    booking = get_object_or_404(Booking.objects.select_related('teacher__user', 'student'), id=booking_id)
    if cancellation.party_of(booking, request.user) is None:
        if request.user.is_staff or getattr(request.user, 'role', '') == 'admin':
            raise PermissionDenied('Staff resolve lessons through disputes, not by cancelling them.')
        raise NotFound()
    return booking


@extend_schema(responses=CancelPreviewSerializer)
class CancelPreviewView(APIView):
    """What would happen if I cancelled now? Read-only: shown before the student/tutor confirms."""
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request, booking_id):
        booking = _booking_of_party(request, booking_id)
        return Response(cancellation.preview(booking, request.user))


@extend_schema(request=CancelRequestSerializer, responses={200: CancelResultSerializer, 400: ErrorCodeSerializer, 409: ErrorCodeSerializer})
class CancelBookingView(APIView):
    """
    The student or the tutor cancels a lesson. Refunds, bonus credit and strikes follow the D-6 policy (see
    docs/CANCELLATION_AND_REFUNDS.md). A student cancelling inside the free window must send acknowledge_forfeit=true.
    """
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'cancel'

    def post(self, request, booking_id):
        booking = _booking_of_party(request, booking_id)
        body = CancelRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            result = cancellation.cancel_booking(booking.id, request.user, reason=body.validated_data['reason'],
                                                 acknowledge_forfeit=body.validated_data['acknowledge_forfeit'])
        except cancellation.CancelError as exc:
            return Response({"error": exc.message, "code": exc.code}, status=exc.status_code)
        return Response(result)


@extend_schema(request=RescheduleRequestSerializer, responses={200: BookingDetailSerializer, 400: ErrorCodeSerializer, 409: ErrorCodeSerializer})
class RescheduleBookingView(APIView):
    """
    The student moves a paid, still-future lesson to another open slot of the same tutor (once, more than 2 hours before it
    starts). The booking keeps its id, payment and escrow. Tutors who cannot teach a lesson cancel it instead.
    """
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = 'cancel'

    def post(self, request, booking_id):
        booking = _booking_of_party(request, booking_id)
        if booking.student_id != request.user.id:
            raise PermissionDenied('Only the student can reschedule a lesson. Tutors cancel instead.')
        body = RescheduleRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            moved = rescheduling.reschedule_booking(booking.id, request.user, body.validated_data['start_time_utc'])
        except rescheduling.RescheduleError as exc:
            return Response({"error": exc.message, "code": exc.code}, status=exc.status_code)
        return Response(BookingDetailSerializer(moved, context={'request': request}).data)
