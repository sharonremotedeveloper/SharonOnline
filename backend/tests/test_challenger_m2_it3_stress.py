"""
backend/tests/test_challenger_m2_it3_stress.py

Adversarial Stress & Endpoint Verification Test Suite for Milestone 2 Iteration 3.
Author: teamwork_preview_challenger_m2_it3_2

Verifies:
1. Serializer validation raises serializers.ValidationError with code='contact_leakage'.
2. PATCH /api/v1/teachers/me/ returns clean HTTP 400 Bad Request with code='contact_leakage'
   and ZERO 500 errors across all newly resolved iteration 3 evasion payloads.
3. POST /api/v1/bookings/<id>/memo/ returns clean HTTP 400 Bad Request with code='contact_leakage'
   and ZERO 500 errors across canonical fields and descriptive aliases.
4. Legitimate educational memos with historical dates (1066), curriculum sequences, page numbers,
   and time intervals pass cleanly with HTTP 200/201 (zero false positives).
5. Computational complexity / ReDoS immunity on repetitive spaced delimiter strings.
"""

from datetime import timedelta
import time
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APIClient

from apps.bookings.models import Booking, LessonMemo
from apps.bookings.serializers import LessonMemoInputSerializer
from apps.common.contact_guard import (
    detect_off_platform_contact,
    validate_no_off_platform_contact,
)
from apps.teachers.models import TeacherProfile
from apps.teachers.serializers import ApplicationDraftSerializer, TeacherOwnProfileSerializer

User = get_user_model()
PROFILE_ME_URL = '/api/v1/teachers/me/'

# Newly tested evasion payloads mandated for Milestone 2 Iteration 3
MANDATED_NEW_EVASIONS = [
    "w . . . h . . . a . . . t . . . s . . . a . . . p . . . p",
    "0 8 2 . . . 5 5 5 - - - 1 2 3 4",
    "\u03c9hatsapp",
]

# Comprehensive set of all Iteration 3 resolved evasion vectors
ALL_IT3_RESOLVED_EVASIONS = [
    # Greek omega lookalikes
    "\u03c9hatsapp",
    "\u03c9echat",
    # Spaced and interleaved phone delimiters
    "0 8 2 . . . 5 5 5 - - - 1 2 3 4",
    "082 . . . 555 . . . 1234",
    "082 - - - 555 - - - 1234",
    "082 * * * 555 * * * 1234",
    "082 ~ ~ ~ 555 ~ ~ ~ 1234",
    "0 8 2 . . 5 5 5 - - 1 2 3 4",
    # Spaced platform single-letter collapsing
    "w . . . h . . . a . . . t . . . s . . . a . . . p . . . p",
    "t . . . e . . . l . . . e . . . g . . . r . . . a . . . m",
    "s . . . k . . . y . . . p . . . e",
    "p . . . a . . . y . . . p . . . a . . . l",
]

LEGITIMATE_EDUCATIONAL_MEMOS = [
    {
        'feedback_text': 'Great lesson today on English history! In 1066 the Battle of Hastings changed language development. Read pages 12-34 for next time.',
        'pronunciation_notes': 'Practiced the vowel sounds in "history" and "battle".',
        'grammar_notes': 'Past perfect tense: had conquered vs had ruled.',
        'homework': 'Write 3 sentences comparing 1066 with 1215 Magna Carta.',
        'vocabulary_words': [{'word': 'conquest', 'definition': 'taking control of a territory'}],
    },
    {
        'general_feedback': 'Student demonstrated excellent progress during our 14:00 session. Covered unit 4, exercise 1-5.',
        'pronunciation_notes': 'Focus on consonant clusters: str-, spl-, scr-.',
        'grammar_corrections': 'I went to school yesterday instead of I have went.',
        'homework_assigned': 'Complete review exercises on page 45-50.',
        'vocabulary_words': [{'word': 'cluster', 'definition': 'a group of similar things'}],
    },
    {
        'feedback_text': 'Focused on conversation practice about economics. Discussed exchange rates: $10 USD = R180 ZAR.',
        'pronunciation_notes': 'Clear diction throughout.',
        'grammar_notes': 'Conditionals: If inflation rises, interest rates will increase.',
        'homework': 'Read chapter 3 section 2. Meet next Tuesday at 15:30.',
        'vocabulary_words': [{'word': 'inflation', 'definition': 'a general increase in prices'}],
    },
    {
        'feedback_text': 'Studied the year *1945* post-war rebuilding era. Counting exercises 1 through 10 completed.',
        'pronunciation_notes': 'Work on "th" in thirteenth and thirty.',
        'grammar_notes': 'Ordinal vs cardinal numbers.',
        'homework': 'Memorize vocabulary list 7.',
        'vocabulary_words': [{'word': 'reconstruction', 'definition': 'the process of building again'}],
    },
]


def make_finished_booking(teacher, student, status=Booking.Status.COMPLETED_PENDING_MEMO, hours_ago=2):
    start = timezone.now() - timedelta(hours=hours_ago)
    return Booking.objects.create(
        teacher=teacher,
        student=student,
        start_time_utc=start,
        end_time_utc=start + timedelta(minutes=25),
        status=status
    )


def auth_client(user):
    c = APIClient()
    if user:
        c.force_authenticate(user=user)
    return c


# =====================================================================
# 1. SERIALIZER VALIDATION & CODE='contact_leakage' EMPIRICAL VERIFICATION
# =====================================================================
@pytest.mark.django_db
class TestSerializerContactLeakageCodesM2It3:
    """Empirically tests that DRF serializers raise ValidationError with code='contact_leakage'."""

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_contact_guard_direct_code(self, payload):
        with pytest.raises(serializers.ValidationError) as exc_info:
            validate_no_off_platform_contact(payload)
        detail = exc_info.value.detail
        assert isinstance(detail, list)
        assert detail[0].code == 'contact_leakage'

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_teacher_serializer_headline_code(self, teacher_user, payload):
        profile = TeacherProfile.objects.get(user=teacher_user.user)
        serializer = TeacherOwnProfileSerializer(instance=profile, data={'headline': payload}, partial=True)
        assert not serializer.is_valid()
        assert 'headline' in serializer.errors
        errors = serializer.errors['headline']
        codes = [err.code for err in errors]
        assert 'contact_leakage' in codes, f"Expected code 'contact_leakage' in {codes}"

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_teacher_serializer_bio_code(self, teacher_user, payload):
        profile = TeacherProfile.objects.get(user=teacher_user.user)
        serializer = TeacherOwnProfileSerializer(instance=profile, data={'bio': payload}, partial=True)
        assert not serializer.is_valid()
        assert 'bio' in serializer.errors
        errors = serializer.errors['bio']
        codes = [err.code for err in errors]
        assert 'contact_leakage' in codes, f"Expected code 'contact_leakage' in {codes}"

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_application_draft_serializer_code(self, teacher_user, payload):
        profile = TeacherProfile.objects.get(user=teacher_user.user)
        serializer = ApplicationDraftSerializer(instance=profile, data={'headline': payload}, partial=True)
        assert not serializer.is_valid()
        assert 'headline' in serializer.errors
        codes = [err.code for err in serializer.errors['headline']]
        assert 'contact_leakage' in codes

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_lesson_memo_serializer_feedback_text_code(self, payload):
        serializer = LessonMemoInputSerializer(data={'feedback_text': payload})
        assert not serializer.is_valid()
        assert 'feedback_text' in serializer.errors
        codes = [err.code for err in serializer.errors['feedback_text']]
        assert 'contact_leakage' in codes

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_lesson_memo_serializer_general_feedback_code(self, payload):
        serializer = LessonMemoInputSerializer(data={'general_feedback': payload})
        assert not serializer.is_valid()
        assert 'general_feedback' in serializer.errors
        codes = [err.code for err in serializer.errors['general_feedback']]
        assert 'contact_leakage' in codes

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_lesson_memo_serializer_grammar_notes_code(self, payload):
        serializer = LessonMemoInputSerializer(data={'grammar_notes': payload})
        assert not serializer.is_valid()
        assert 'grammar_notes' in serializer.errors
        codes = [err.code for err in serializer.errors['grammar_notes']]
        assert 'contact_leakage' in codes

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_lesson_memo_serializer_grammar_corrections_code(self, payload):
        serializer = LessonMemoInputSerializer(data={'grammar_corrections': payload})
        assert not serializer.is_valid()
        assert 'grammar_corrections' in serializer.errors
        codes = [err.code for err in serializer.errors['grammar_corrections']]
        assert 'contact_leakage' in codes

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_lesson_memo_serializer_homework_code(self, payload):
        serializer = LessonMemoInputSerializer(data={'homework': payload})
        assert not serializer.is_valid()
        assert 'homework' in serializer.errors
        codes = [err.code for err in serializer.errors['homework']]
        assert 'contact_leakage' in codes

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_lesson_memo_serializer_homework_assigned_code(self, payload):
        serializer = LessonMemoInputSerializer(data={'homework_assigned': payload})
        assert not serializer.is_valid()
        assert 'homework_assigned' in serializer.errors
        codes = [err.code for err in serializer.errors['homework_assigned']]
        assert 'contact_leakage' in codes


# =====================================================================
# 2. PROFILE UPDATE (PATCH /api/v1/teachers/me/) EMPIRICAL STRESS
# =====================================================================
@pytest.mark.django_db
class TestProfileUpdateAdversarialStressM2It3:
    """Stress tests PATCH /api/v1/teachers/me/ with newly tested evasion payloads."""

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_patch_headline_rejects_with_400_and_contact_leakage(self, teacher_user, payload):
        client = auth_client(teacher_user.user)
        initial_headline = TeacherProfile.objects.get(user=teacher_user.user).headline

        res = client.patch(PROFILE_ME_URL, {'headline': payload}, format='json')
        assert res.status_code == 400, f"Expected 400 for headline '{payload}', got {res.status_code}: {res.content}"
        assert res.status_code != 500

        # Verify error structure and code='contact_leakage'
        assert 'headline' in res.data
        codes = [err.code for err in res.data['headline']]
        assert 'contact_leakage' in codes, f"Expected code='contact_leakage' in {codes}"

        # Verify DB integrity: headline was not mutated to malicious payload
        profile = TeacherProfile.objects.get(user=teacher_user.user)
        assert profile.headline == initial_headline
        assert profile.headline != payload

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_patch_bio_rejects_with_400_and_contact_leakage(self, teacher_user, payload):
        client = auth_client(teacher_user.user)
        initial_bio = TeacherProfile.objects.get(user=teacher_user.user).bio

        res = client.patch(PROFILE_ME_URL, {'bio': payload}, format='json')
        assert res.status_code == 400, f"Expected 400 for bio '{payload}', got {res.status_code}: {res.content}"
        assert res.status_code != 500

        # Verify error structure and code='contact_leakage'
        assert 'bio' in res.data
        codes = [err.code for err in res.data['bio']]
        assert 'contact_leakage' in codes, f"Expected code='contact_leakage' in {codes}"

        # Verify DB integrity: bio was not mutated to malicious payload
        profile = TeacherProfile.objects.get(user=teacher_user.user)
        assert profile.bio == initial_bio
        assert profile.bio != payload


# =====================================================================
# 3. LESSON MEMO (POST /api/v1/bookings/<id>/memo/) EMPIRICAL STRESS
# =====================================================================
@pytest.mark.django_db
class TestLessonMemoSubmissionAdversarialStressM2It3:
    """Stress tests POST /api/v1/bookings/<id>/memo/ across all fields with new evasions."""

    BASE_PAYLOAD = {
        'feedback_text': 'Valid lesson feedback on conversational fluency.',
        'pronunciation_notes': 'Good job with past tense endings.',
        'grammar_notes': 'Reviewed irregular verbs.',
        'homework': 'Practice reading aloud.',
        'vocabulary_words': [{'word': 'articulate', 'definition': 'fluent and clear in speech'}],
    }

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_memo_feedback_text_rejects_with_400_and_contact_leakage(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_PAYLOAD, 'feedback_text': payload}

        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400, f"Expected 400 for feedback_text '{payload}', got {res.status_code}: {res.content}"
        assert res.status_code != 500

        # Verify error structure and code='contact_leakage'
        assert 'feedback_text' in res.data
        codes = [err.code for err in res.data['feedback_text']]
        assert 'contact_leakage' in codes, f"Expected code='contact_leakage' in {codes}"

        # DB integrity: memo not created, booking status stays unchanged
        assert not LessonMemo.objects.filter(booking=booking).exists()
        assert Booking.objects.get(id=booking.id).status == Booking.Status.COMPLETED_PENDING_MEMO

    @pytest.mark.parametrize("payload", ALL_IT3_RESOLVED_EVASIONS)
    def test_memo_general_feedback_alias_rejects_with_400_and_contact_leakage(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_PAYLOAD, 'general_feedback': payload}
        body.pop('feedback_text')

        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400, f"Expected 400 for general_feedback '{payload}', got {res.status_code}: {res.content}"
        assert res.status_code != 500

        assert 'general_feedback' in res.data
        codes = [err.code for err in res.data['general_feedback']]
        assert 'contact_leakage' in codes

        assert not LessonMemo.objects.filter(booking=booking).exists()
        assert Booking.objects.get(id=booking.id).status == Booking.Status.COMPLETED_PENDING_MEMO

    @pytest.mark.parametrize("payload", MANDATED_NEW_EVASIONS)
    def test_memo_grammar_corrections_alias_rejects_with_400_and_contact_leakage(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_PAYLOAD, 'grammar_corrections': payload}
        body.pop('grammar_notes')

        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400, f"Expected 400 for grammar_corrections '{payload}', got {res.status_code}: {res.content}"
        assert res.status_code != 500

        assert 'grammar_corrections' in res.data
        codes = [err.code for err in res.data['grammar_corrections']]
        assert 'contact_leakage' in codes

        assert not LessonMemo.objects.filter(booking=booking).exists()

    @pytest.mark.parametrize("payload", MANDATED_NEW_EVASIONS)
    def test_memo_homework_assigned_alias_rejects_with_400_and_contact_leakage(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_PAYLOAD, 'homework_assigned': payload}
        body.pop('homework')

        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400, f"Expected 400 for homework_assigned '{payload}', got {res.status_code}: {res.content}"
        assert res.status_code != 500

        assert 'homework_assigned' in res.data
        codes = [err.code for err in res.data['homework_assigned']]
        assert 'contact_leakage' in codes

        assert not LessonMemo.objects.filter(booking=booking).exists()

    @pytest.mark.parametrize("payload", MANDATED_NEW_EVASIONS)
    def test_memo_pronunciation_notes_rejects_with_400_and_contact_leakage(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_PAYLOAD, 'pronunciation_notes': payload}

        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400, f"Expected 400 for pronunciation_notes '{payload}', got {res.status_code}: {res.content}"
        assert res.status_code != 500

        assert 'pronunciation_notes' in res.data
        codes = [err.code for err in res.data['pronunciation_notes']]
        assert 'contact_leakage' in codes

        assert not LessonMemo.objects.filter(booking=booking).exists()


# =====================================================================
# 4. LEGITIMATE EDUCATIONAL MEMO IMMUNITY (200 OK / 201 CREATED)
# =====================================================================
@pytest.mark.django_db
class TestLegitimateEducationalMemoImmunityM2It3:
    """Confirms legitimate educational memos pass with 200/201 and without false positives."""

    @pytest.mark.parametrize("memo_data", LEGITIMATE_EDUCATIONAL_MEMOS)
    def test_legitimate_educational_memo_submission_passes(self, teacher_user, student_user, memo_data):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)

        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', memo_data, format='json')
        assert res.status_code in (200, 201), (
            f"False positive blocking of educational memo! Status {res.status_code}: {res.content}"
        )
        assert res.status_code != 500
        data = res.json()
        assert 'id' in data

        # Verify DB state: memo created and booking transitioned to COMPLETED
        memo = LessonMemo.objects.get(booking=booking)
        expected_feedback = memo_data.get('feedback_text') or memo_data.get('general_feedback')
        assert memo.feedback_text == expected_feedback
        assert Booking.objects.get(id=booking.id).status == Booking.Status.COMPLETED


# =====================================================================
# 5. COMPUTATIONAL COMPLEXITY & REDOS RESILIENCE
# =====================================================================
class TestRegexPerformanceAndReDoS:
    """Stress tests regex execution latency against repetitive adversarial inputs."""

    ADVERSARIAL_REPETITIVE_INPUTS = [
        "w . . . " * 500,
        "0 8 2 - - - " * 500,
        "082 * * * 555 * * * " * 200 + "1234",
        "a . . . . . . . . . . " * 300,
        "\u03c9 " * 1000,
        "~ * - . _ " * 500,
    ]

    @pytest.mark.parametrize("payload", ADVERSARIAL_REPETITIVE_INPUTS)
    def test_linear_time_execution_no_redos(self, payload):
        t0 = time.perf_counter()
        _ = detect_off_platform_contact(payload)
        elapsed = time.perf_counter() - t0
        # Verification: execution must complete in strictly less than 150ms (0.15s)
        assert elapsed < 0.15, f"ReDoS suspected! Regex took {elapsed:.4f}s on repetitive payload of length {len(payload)}"
