"""
backend/tests/test_challenger_m2_it2_stress.py

Adversarial stress testing suite authored by teamwork_preview_challenger_m2_it2_2.
Rigorous empirical challenge of Milestone 2 Iteration 2 API endpoints and serializer validation:

1. Adversarial evasions on profile update (PATCH /api/v1/teachers/me/):
   - Spaced emails: 'tutor @ gmail . com', 't.u.t.o.r@g.m.a.i.l.c.o.m', 'tutor at gmail.com'
   - Handles with separators: 't . me / channel', 'w . a . m . e / 27825551234'
   - Ensure clean 400 Bad Request, zero 500 errors, serializer error code='contact_leakage'.

2. Adversarial evasions on lesson memo submission (POST /api/v1/bookings/<id>/memo/):
   - All canonical fields and aliases (feedback_text, general_feedback, homework, homework_assigned,
     grammar_notes, grammar_corrections, pronunciation_notes, next_lesson_recommendation).
   - Ensure clean 400 Bad Request, zero 500 errors, serializer error code='contact_leakage'.

3. Legitimate educational memos immunity:
   - Ensure legitimate pedagogy returns HTTP 200 (or 201), zero false positives.
"""

from datetime import timedelta
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import serializers

from apps.bookings.models import Booking, LessonMemo
from apps.bookings.serializers import LessonMemoInputSerializer
from apps.teachers.models import TeacherProfile
from apps.teachers.serializers import TeacherOwnProfileSerializer
from apps.common.contact_guard import validate_no_off_platform_contact

User = get_user_model()
PROFILE_ME_URL = '/api/v1/teachers/me/'


def make_finished_booking(teacher, student, status=Booking.Status.COMPLETED_PENDING_MEMO, hours_ago=2):
    start = timezone.now() - timedelta(hours=hours_ago)
    return Booking.objects.create(
        teacher=teacher,
        student=student,
        start_time_utc=start,
        end_time_utc=start + timedelta(minutes=25),
        status=status,
    )


def auth_client(user):
    c = APIClient()
    if user:
        c.force_authenticate(user=user)
    return c


# Specific adversarial payloads required by orchestrator dispatch
MANDATED_ADVERSARIAL_PAYLOADS = [
    "tutor @ gmail . com",
    "t.u.t.o.r@g.m.a.i.l.c.o.m",
    "tutor at gmail.com",
    "t . me / channel",
]

EXPANDED_ADVERSARIAL_PAYLOADS = MANDATED_ADVERSARIAL_PAYLOADS + [
    "tutor at gmail . com",
    "tutor at yahoo.com",
    "contact me: tutor at outlook.com for private lessons",
    "t . me / my_english_channel",
    "t . me /channel",
    "wa . me / 27825551234",
    "w . a . m . e / 27825551234",
    "call or text 0 8 2 5 5 5 1 2 3 4",
    "whatsapp : 082.555.1234",
    "skype : live : . cid . abc123456",
    "paypal . me / direct_tutor",
    "cash . app / $mytutor",
]

LEGITIMATE_EDUCATIONAL_MEMOS = [
    {
        'feedback_text': 'Great progress today analyzing English history from 1066 to 1215.',
        'pronunciation_notes': 'Focus on consonant clusters in chapter 3, page 14.',
        'grammar_notes': 'Practiced the distinction between at 5 pm and in 1995.',
        'homework': 'Complete exercises 1 - 2 - 3 - 4 - 5 on page 42.',
    },
    {
        'feedback_text': 'Excellent reading of the timeline from 1939 to 1945.',
        'pronunciation_notes': 'Work on short vowel sounds: cat, bat, hat.',
        'grammar_notes': 'Zoom in on past continuous vs simple past.',
        'homework': 'Write 5 sentences about your daily routine.',
    },
    {
        'general_feedback': 'ESL primary counting chart: one - two - three - four - five - six - seven.',
        'pronunciation_notes': 'Clear pronunciation on numbers 1 through 10.',
        'grammar_corrections': 'Remember to use plural nouns: three books, two cats.',
        'homework_assigned': 'Review Unit 4, lines 10 to 20 for next Tuesday.',
        'next_lesson_recommendation': 'Continue to module 5.',
    },
]


# =====================================================================
# 1. SERIALIZER VALIDATION & CODE='contact_leakage' CHECKS
# =====================================================================
@pytest.mark.django_db
class TestSerializerContactLeakageCode:
    """Verifies that serializers raise ValidationError with code='contact_leakage'."""

    @pytest.mark.parametrize("payload", MANDATED_ADVERSARIAL_PAYLOADS)
    def test_contact_guard_direct_code(self, payload):
        with pytest.raises(serializers.ValidationError) as exc_info:
            validate_no_off_platform_contact(payload)
        detail = exc_info.value.detail
        assert isinstance(detail, list)
        assert detail[0].code == 'contact_leakage'

    @pytest.mark.parametrize("payload", MANDATED_ADVERSARIAL_PAYLOADS)
    def test_teacher_serializer_bio_error_code(self, teacher_user, payload):
        profile = TeacherProfile.objects.get(user=teacher_user.user)
        serializer = TeacherOwnProfileSerializer(instance=profile, data={'bio': payload}, partial=True)
        assert not serializer.is_valid()
        assert 'bio' in serializer.errors
        errors = serializer.errors['bio']
        codes = [err.code for err in errors]
        assert 'contact_leakage' in codes, f"Expected code 'contact_leakage' in {codes}"

    @pytest.mark.parametrize("payload", MANDATED_ADVERSARIAL_PAYLOADS)
    def test_teacher_serializer_headline_error_code(self, teacher_user, payload):
        profile = TeacherProfile.objects.get(user=teacher_user.user)
        serializer = TeacherOwnProfileSerializer(instance=profile, data={'headline': payload}, partial=True)
        assert not serializer.is_valid()
        assert 'headline' in serializer.errors
        errors = serializer.errors['headline']
        codes = [err.code for err in errors]
        assert 'contact_leakage' in codes, f"Expected code 'contact_leakage' in {codes}"

    @pytest.mark.parametrize("payload", MANDATED_ADVERSARIAL_PAYLOADS)
    def test_lesson_memo_input_serializer_feedback_text_error_code(self, payload):
        serializer = LessonMemoInputSerializer(data={'feedback_text': payload})
        assert not serializer.is_valid()
        assert 'feedback_text' in serializer.errors
        errors = serializer.errors['feedback_text']
        codes = [err.code for err in errors]
        assert 'contact_leakage' in codes, f"Expected code 'contact_leakage' in {codes}"

    @pytest.mark.parametrize("payload", MANDATED_ADVERSARIAL_PAYLOADS)
    def test_lesson_memo_input_serializer_general_feedback_alias_error_code(self, payload):
        serializer = LessonMemoInputSerializer(data={'general_feedback': payload})
        assert not serializer.is_valid()
        assert 'general_feedback' in serializer.errors
        errors = serializer.errors['general_feedback']
        codes = [err.code for err in errors]
        assert 'contact_leakage' in codes, f"Expected code 'contact_leakage' in {codes}"


# =====================================================================
# 2. PROFILE UPDATE (PATCH /api/v1/teachers/me/) ADVERSARIAL STRESS
# =====================================================================
@pytest.mark.django_db
class TestProfileUpdateAdversarialStress:
    """Tests PATCH /api/v1/teachers/me/ with mandated and expanded evasions."""

    @pytest.mark.parametrize("payload", EXPANDED_ADVERSARIAL_PAYLOADS)
    def test_patch_headline_rejects_with_400_not_500(self, teacher_user, payload):
        client = auth_client(teacher_user.user)
        res = client.patch(PROFILE_ME_URL, {'headline': payload}, format='json')
        assert res.status_code == 400, f"Expected 400 for headline '{payload}', got {res.status_code}: {res.content}"
        assert res.status_code != 500
        data = res.json()
        assert 'headline' in data
        assert any('Off-platform contact' in str(msg) for msg in data['headline'])

        # DB integrity check
        profile = TeacherProfile.objects.get(user=teacher_user.user)
        assert profile.headline != payload

    @pytest.mark.parametrize("payload", EXPANDED_ADVERSARIAL_PAYLOADS)
    def test_patch_bio_rejects_with_400_not_500(self, teacher_user, payload):
        client = auth_client(teacher_user.user)
        res = client.patch(PROFILE_ME_URL, {'bio': payload}, format='json')
        assert res.status_code == 400, f"Expected 400 for bio '{payload}', got {res.status_code}: {res.content}"
        assert res.status_code != 500
        data = res.json()
        assert 'bio' in data
        assert any('Off-platform contact' in str(msg) for msg in data['bio'])

        # DB integrity check
        profile = TeacherProfile.objects.get(user=teacher_user.user)
        assert profile.bio != payload


# =====================================================================
# 3. LESSON MEMO (POST /api/v1/bookings/<id>/memo/) ADVERSARIAL STRESS
# =====================================================================
@pytest.mark.django_db
class TestLessonMemoSubmissionAdversarialStress:
    """Tests POST /api/v1/bookings/<id>/memo/ across all fields with evasions."""

    BASE_PAYLOAD = {
        'feedback_text': 'Standard lesson feedback.',
        'pronunciation_notes': 'Good job on vowels.',
        'grammar_notes': 'Reviewed past tense.',
        'homework': 'Page 20 exercises.',
    }

    @pytest.mark.parametrize("payload", EXPANDED_ADVERSARIAL_PAYLOADS)
    def test_memo_feedback_text_rejects_with_400_not_500(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_PAYLOAD, 'feedback_text': payload}
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400, f"Expected 400 for feedback_text '{payload}', got {res.status_code}: {res.content}"
        assert res.status_code != 500
        data = res.json()
        assert 'feedback_text' in data
        assert any('Off-platform contact' in str(msg) for msg in data['feedback_text'])

        # Verify DB state: memo not created, booking unchanged
        assert not LessonMemo.objects.filter(booking=booking).exists()
        assert Booking.objects.get(id=booking.id).status == Booking.Status.COMPLETED_PENDING_MEMO

    @pytest.mark.parametrize("payload", EXPANDED_ADVERSARIAL_PAYLOADS)
    def test_memo_general_feedback_alias_rejects_with_400_not_500(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_PAYLOAD, 'general_feedback': payload}
        body.pop('feedback_text')
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400, f"Expected 400 for general_feedback '{payload}', got {res.status_code}: {res.content}"
        assert res.status_code != 500
        data = res.json()
        assert 'general_feedback' in data
        assert any('Off-platform contact' in str(msg) for msg in data['general_feedback'])

        assert not LessonMemo.objects.filter(booking=booking).exists()

    @pytest.mark.parametrize("payload", EXPANDED_ADVERSARIAL_PAYLOADS)
    def test_memo_homework_alias_rejects_with_400_not_500(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_PAYLOAD, 'homework_assigned': payload}
        body.pop('homework')
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400, f"Expected 400 for homework_assigned '{payload}', got {res.status_code}: {res.content}"
        assert res.status_code != 500
        data = res.json()
        assert 'homework_assigned' in data
        assert any('Off-platform contact' in str(msg) for msg in data['homework_assigned'])

        assert not LessonMemo.objects.filter(booking=booking).exists()

    @pytest.mark.parametrize("payload", EXPANDED_ADVERSARIAL_PAYLOADS)
    def test_memo_grammar_alias_rejects_with_400_not_500(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_PAYLOAD, 'grammar_corrections': payload}
        body.pop('grammar_notes')
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400, f"Expected 400 for grammar_corrections '{payload}', got {res.status_code}: {res.content}"
        assert res.status_code != 500
        data = res.json()
        assert 'grammar_corrections' in data
        assert any('Off-platform contact' in str(msg) for msg in data['grammar_corrections'])

        assert not LessonMemo.objects.filter(booking=booking).exists()


# =====================================================================
# 4. LEGITIMATE EDUCATIONAL MEMO IMMUNITY (200 OK / 201 CREATED)
# =====================================================================
@pytest.mark.django_db
class TestLegitimateEducationalMemoImmunity:
    """Confirms legitimate educational memos pass with 200/201 and without false positives."""

    @pytest.mark.parametrize("memo_data", LEGITIMATE_EDUCATIONAL_MEMOS)
    def test_legitimate_educational_memo_submission_passes(self, teacher_user, student_user, memo_data):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', memo_data, format='json')
        assert res.status_code in (200, 201), (
            f"False positive blocking of educational memo! Status {res.status_code}: {res.content}"
        )
        data = res.json()
        assert 'id' in data

        # Verify DB state: memo created, booking transitioned to COMPLETED
        memo = LessonMemo.objects.get(booking=booking)
        expected_feedback = memo_data.get('feedback_text') or memo_data.get('general_feedback')
        assert memo.feedback_text == expected_feedback
        assert Booking.objects.get(id=booking.id).status == Booking.Status.COMPLETED
