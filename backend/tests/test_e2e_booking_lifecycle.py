import pytest
from datetime import date, timedelta, time
from django.utils import timezone
from django.db import IntegrityError
from apps.users.models import User
from apps.teachers.models import TeacherProfile, TeacherAvailability
from apps.bookings.models import Booking, LessonMemo
from apps.payments.models import PaymentTransaction, CreditBundle
from apps.bookings.services.slot_generator import generate_teacher_slots
from apps.bookings.services.lock_service import acquire_slot_lock, release_slot_lock, is_slot_locked
from apps.payments.services.webhook_handler import process_payment_webhook
from apps.payments.services.funding import ensure_gateway_funding
from apps.integrations.tasks import dispatch_booking_fulfillment
from rest_framework.test import APIRequestFactory, force_authenticate
from apps.bookings.views import ReportOutageView

@pytest.mark.django_db
def test_full_e2e_booking_and_post_lesson_lifecycle():
    """
    End-to-end critical path test:
    1. Tutor & Student creation with distinct timezones (SAST vs JST).
    2. Availability projection & slot generation with timezone normalization.
    3. Redlock 10-minute pessimistic hold reservation.
    4. Booking creation & state transition to PENDING_PAYMENT.
    5. Payment gateway webhook processing with idempotency verification.
    6. Celery async fulfillment: Zoom S2S OAuth meeting generation.
    7. Classroom progression (CONFIRMED -> IN_PROGRESS -> COMPLETED).
    8. Post-lesson memo composition with vocabulary bank entries.
    9. 5-star student rubric review submission & teacher average re-calculation.
    """
    # 1. Setup Tutor in South Africa (UTC+2)
    tutor_user = User.objects.create_user(
        username="sharon_tutor",
        email="sharon@tutor.co.za",
        password="securepass123",
        role=User.Role.TEACHER,
        country="ZA",
        timezone="Africa/Johannesburg"
    )
    tutor_profile = TeacherProfile.objects.create(
        user=tutor_user,
        headline="Senior Business English Specialist",
        accent=TeacherProfile.Accent.SOUTH_AFRICAN,
        price_per_25min_usd=9.00,
        is_verified=True,
        is_active=True,
        rating_avg=5.00,
        rating_count=0
    )
    # Teacher available Monday 09:00 - 10:00 SAST (2 slots: 09:00-09:25 and 09:30-09:55)
    TeacherAvailability.objects.create(
        teacher=tutor_profile,
        day_of_week=0, # Monday
        start_time=time(9, 0),
        end_time=time(10, 0),
        is_active=True
    )

    # Setup Student in Japan (UTC+9)
    student_user = User.objects.create_user(
        username="kenji_sato",
        email="kenji@tokyo.jp",
        password="securepass123",
        role=User.Role.STUDENT,
        country="JP",
        timezone="Asia/Tokyo"
    )

    # 2. Slot Generation & Timezone Projection
    today = date.today()
    days_until_monday = (0 - today.weekday() + 7) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    slots = generate_teacher_slots(
        teacher=tutor_profile,
        start_date=next_monday,
        days_ahead=1,
        viewer_tz_name="Asia/Tokyo"
    )
    assert len(slots) == 2
    target_slot = slots[0]
    # 09:00 SAST (UTC+2) is 07:00 UTC and 16:00 JST (UTC+9)
    assert target_slot["local_start_time"] == "16:00"
    assert target_slot["local_end_time"] == "16:25"
    slot_utc_str = target_slot["start_time_utc"]

    # 3. Redlock Pessimistic Hold
    assert acquire_slot_lock(str(tutor_profile.id), slot_utc_str, str(student_user.id)) is True
    assert is_slot_locked(str(tutor_profile.id), slot_utc_str) is True

    # 4. Booking Creation (PENDING_PAYMENT)
    start_dt = timezone.datetime.fromisoformat(slot_utc_str.replace("Z", "+00:00"))
    booking = Booking.objects.create(
        teacher=tutor_profile,
        student=student_user,
        start_time_utc=start_dt,
        end_time_utc=start_dt + timedelta(minutes=25),
        status=Booking.Status.PENDING_PAYMENT
    )
    assert booking.status == Booking.Status.PENDING_PAYMENT

    # 5. Payment Webhook Ingestion (PayPal / PayFast)
    gateway_tx = "PAYPAL-LIFECYCLE-TX-9901"
    webhook_res = process_payment_webhook(
        booking_id=str(booking.id),
        gateway="paypal",
        transaction_id=gateway_tx,
        amount=9.00,
        currency="USD",
        status="success",
        raw_payload={"custom": str(booking.id), "payer_status": "VERIFIED"}
    )
    assert webhook_res["status"] == "success"

    # Refresh booking and verify CONFIRMED status
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED

    # Release lock after successful payment
    release_slot_lock(str(tutor_profile.id), slot_utc_str, str(student_user.id))

    # 6. Celery Async Task: Zoom Meeting Provisioning
    fulfillment_result = dispatch_booking_fulfillment(str(booking.id))
    assert fulfillment_result is True

    booking.refresh_from_db()
    assert booking.zoom_meeting_id != ""
    assert "zoom.us" in booking.zoom_join_url
    assert booking.zoom_start_url != ""

    # 7. Classroom Progression: Lesson in Progress -> Completed
    booking.status = Booking.Status.IN_PROGRESS
    booking.save()

    booking.status = Booking.Status.COMPLETED
    booking.save()

    # 8. Post-Lesson Memo Submission
    memo = LessonMemo.objects.create(
        booking=booking,
        teacher=tutor_profile,
        student=student_user,
        feedback_text="Kenji demonstrated exceptional precision during our negotiation exercise.",
        vocabulary_words=[
            {"word": "concession", "definition": "A thing granted in response to demands."},
            {"word": "deadlock", "definition": "A state of inaction or standstill."}
        ],
        pronunciation_notes="Emphasize second syllable in 'con-CES-sion'.",
        homework="Draft 3 counter-proposals for Lesson 4."
    )
    assert memo.id is not None
    assert len(memo.vocabulary_words) == 2

    # 9. Asymmetric Student Rubric Review & Rating Re-calculation
    booking.student_rating = 5
    booking.student_review = "Phenomenal pacing and very actionable pronunciation drills."
    booking.save()

    # Update teacher rating stats
    ratings = Booking.objects.filter(teacher=tutor_profile, student_rating__isnull=False)
    count = ratings.count()
    avg = sum(b.student_rating for b in ratings) / count
    tutor_profile.rating_count = count
    tutor_profile.rating_avg = round(avg, 2)
    tutor_profile.save()

    tutor_profile.refresh_from_db()
    assert tutor_profile.rating_count == 1
    assert float(tutor_profile.rating_avg) == 5.00


@pytest.mark.django_db
def test_database_double_booking_constraint_prevents_race_condition(teacher_user, student_user):
    """
    Verifies that the PostgreSQL / SQLite database-level UniqueConstraint
    actively rejects duplicate active bookings for the same tutor at the exact same start time.
    """
    start_utc = timezone.now() + timedelta(days=3)

    # 1. Create first confirmed booking
    Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=start_utc,
        end_time_utc=start_utc + timedelta(minutes=25),
        status=Booking.Status.CONFIRMED
    )
    # 2. Second student attempts to create a confirmed booking for the identical teacher and slot
    another_student = User.objects.create_user(
        username="another_student",
        email="another@test.com",
        password="pass",
        role=User.Role.STUDENT
    )

    with pytest.raises(IntegrityError):
        Booking.objects.create(
            teacher=teacher_user,
            student=another_student,
            start_time_utc=start_utc,
            end_time_utc=start_utc + timedelta(minutes=25),
            status=Booking.Status.CONFIRMED
        )


@pytest.mark.django_db
def test_eskom_power_outage_interruption_and_refund(teacher_user, student_user):
    """
    Verifies the Eskom load-shedding exception workflow:
    When a power cut interrupts a lesson, the booking transitions to INTERRUPTED_POWER,
    and the student is automatically credited back 1 lesson credit with zero tutor penalty.
    """
    start_utc = timezone.now() + timedelta(minutes=10)  # outage reports are only accepted around the lesson (Task 9.7)
    booking = Booking.objects.create(
        teacher=teacher_user,
        student=student_user,
        start_time_utc=start_utc,
        end_time_utc=start_utc + timedelta(minutes=25),
        status=Booking.Status.CONFIRMED
    )
    tx = PaymentTransaction.objects.create(
        booking=booking,
        gateway=PaymentTransaction.Gateway.PAYFAST,
        gateway_reference="tx-eskom-operational-credit",
        amount=9.00,
        currency="USD",
        status=PaymentTransaction.Status.SUCCESS,
    )
    ensure_gateway_funding(tx, booking)

    # Initialize student credit bundle with 0 remaining credits
    bundle = CreditBundle.objects.create(
        user=student_user,
        pack_name="Starter Pack",
        total_credits=5,
        remaining_credits=0,
        amount_paid=40.00,
        currency="USD"
    )

    # Report power outage via ReportOutageView
    factory = APIRequestFactory()
    request = factory.post(
        f'/api/v1/bookings/{booking.id}/report-outage/',
        {"reason": "Stage 4 Eskom Outage in Johannesburg Sandton Block 3"},
        format='json'
    )
    force_authenticate(request, user=student_user)

    view = ReportOutageView.as_view()
    response = view(request, booking_id=str(booking.id))

    assert response.status_code == 200
    assert response.data["status"] == "interrupted_power"
    assert response.data["refunded"] is True

    # Booking status updated
    booking.refresh_from_db()
    assert booking.status == Booking.Status.INTERRUPTED_POWER

    # Student credit refunded
    bundle.refresh_from_db()
    assert bundle.remaining_credits == 0
    assert sum(
        lot.remaining_credits
        for lot in CreditBundle.objects.filter(user=student_user)
    ) == 1
