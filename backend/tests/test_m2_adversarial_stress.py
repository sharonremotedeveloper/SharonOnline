"""
backend/tests/test_m2_adversarial_stress.py

Adversarial stress testing suite for Milestone 2 API endpoints and serializer validation.
Verifies:
1. Malicious evasion payloads across tutor profile and lesson memo endpoints.
2. Hostile JSON inputs (null, array/dict for string, >100KB strings, unicode BOM, root non-objects).
3. Mixed alias testing (general_feedback alongside feedback_text, homework_assigned, grammar_corrections).
4. Clean HTTP 400 Bad Request responses with field error keys and ZERO HTTP 500 errors.
5. Educational false-positive exemptions under live API endpoints.
"""

from datetime import timedelta
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bookings.models import Booking, LessonMemo
from apps.teachers.models import TeacherProfile

User = get_user_model()
PROFILE_ME_URL = '/api/v1/teachers/me/'


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
# 1. TUTOR PROFILE (PATCH /api/v1/teachers/me/) ADVERSARIAL EVASION
# =====================================================================
@pytest.mark.django_db
class TestTutorProfileAdversarialEvasion:
    """Stress tests PATCH /api/v1/teachers/me/ with malicious obfuscated contact evasion payloads."""

    EVASION_PAYLOADS = [
        # Spaced & dotted phone numbers
        "Call me directly at 0 8 2 5 5 5 1 2 3 4 anytime",
        "Phone: 082.555.1234 or 082-555-1234",
        "Reach me: +27 82 555 1234",
        # Spelled-out number words
        "Dial zero eight two five five five one two three four",
        "My number is 0 eight 2 double five five 1 2 3 4",
        # Emails with homoglyphs and separators
        "Email me at tutor [at] gmail (dot) com",
        "Reach me: tutor [@] domain [.] com",
        "tutor @ gmail . com",
        "t.u.t.o.r@g.m.a.i.l.c.o.m",
        "t u t o r @ g m a i l . c o m",
        "tutor\u200B@\u200Dgmail.com",
        "ｔｕｔｏｒ@ｇｍａｉｌ.ｃｏｍ",
        # Off-platform messaging handles & links
        "Chat on wa.me/27825551234 for private rates",
        "Find me on w.h.a.t.s.a.p.p",
        "My w h a t s a p p is available",
        "Message me on wh\u0430ts\u0430\u0440\u0440",  # Cyrillic visual homoglyphs
        "t.me/tutor_direct_lessons",
        "Add my telegram: @tutor_john",
        "Find me on t.e.l.e.g.r.a.m",
        "WeChat: my_wechat_id_123",
        "Add me on wxid_9988776655",
        "line id: sharon_english_tutor",
        "Add me on line app: sharon123",
        "open.kakao.com/o/s123456",
        "skype: live:.cid.1234567890abcdef",
        "join.skype.com/invite/abcdef123",
        # Off-platform payment handles
        "paypal.me/tutorjohn",
        "pay me via venmo: @tutorjohn",
        "Send funds to $tutorcashtag",
        "cash.app/$tutorcashtag",
        # External meeting rooms
        "zoom.us/j/9876543210",
        "meet.google.com/abc-defg-hij",
    ]

    @pytest.mark.parametrize('payload', EVASION_PAYLOADS)
    def test_headline_rejects_evasion_payloads(self, teacher_user, payload):
        client = auth_client(teacher_user.user)
        res = client.patch(PROFILE_ME_URL, {'headline': payload}, format='json')
        assert res.status_code == 400, f"Expected 400 for headline evasion: {payload}, got {res.status_code}"
        assert 'headline' in res.json()
        assert res.status_code != 500
        # Verify DB integrity: headline not updated to malicious payload
        profile = TeacherProfile.objects.get(user=teacher_user.user)
        assert profile.headline != payload

    @pytest.mark.parametrize('payload', EVASION_PAYLOADS)
    def test_bio_rejects_evasion_payloads(self, teacher_user, payload):
        client = auth_client(teacher_user.user)
        res = client.patch(PROFILE_ME_URL, {'bio': payload}, format='json')
        assert res.status_code == 400, f"Expected 400 for bio evasion: {payload}, got {res.status_code}"
        assert 'bio' in res.json()
        assert res.status_code != 500
        # Verify DB integrity: bio not updated to malicious payload
        profile = TeacherProfile.objects.get(user=teacher_user.user)
        assert profile.bio != payload


# =====================================================================
# 2. TUTOR PROFILE HOSTILE JSON INPUTS
# =====================================================================
@pytest.mark.django_db
class TestTutorProfileHostileJSON:
    """Stress tests PATCH /api/v1/teachers/me/ with malformed, null, oversized, and non-dict JSON."""

    @pytest.mark.parametrize('field', ['headline', 'bio', 'specialties'])
    def test_null_value_rejected_with_clean_400(self, teacher_user, field):
        client = auth_client(teacher_user.user)
        res = client.patch(PROFILE_ME_URL, {field: None}, format='json')
        assert res.status_code == 400
        assert field in res.json()
        assert res.status_code != 500

    @pytest.mark.parametrize('field,bad_val', [
        ('headline', ['array', 'of', 'words']),
        ('headline', {'nested': 'object'}),
        ('headline', True),
        ('bio', ['array', 'of', 'sentences']),
        ('bio', {'nested': 'dict'}),
        ('bio', False),
        ('specialties', 'not-a-list'),
        ('specialties', {'key': 'val'}),
    ])
    def test_wrong_datatype_rejected_with_clean_400(self, teacher_user, field, bad_val):
        client = auth_client(teacher_user.user)
        res = client.patch(PROFILE_ME_URL, {field: bad_val}, format='json')
        assert res.status_code == 400
        assert field in res.json()
        assert res.status_code != 500

    def test_oversized_headline_rejected_with_clean_400(self, teacher_user):
        client = auth_client(teacher_user.user)
        # 256 chars (max is 255)
        res = client.patch(PROFILE_ME_URL, {'headline': 'A' * 256}, format='json')
        assert res.status_code == 400
        assert 'headline' in res.json()

        # 64KB giant string (resource exhaustion test)
        res_giant = client.patch(PROFILE_ME_URL, {'headline': 'A' * 65536}, format='json')
        assert res_giant.status_code == 400
        assert 'headline' in res_giant.json()
        assert res_giant.status_code != 500

    def test_oversized_bio_rejected_with_clean_400(self, teacher_user):
        client = auth_client(teacher_user.user)
        # 5001 chars (max is 5000)
        res = client.patch(PROFILE_ME_URL, {'bio': 'A' * 5001}, format='json')
        assert res.status_code == 400
        assert 'bio' in res.json()

        # 128KB giant string (resource exhaustion test)
        res_giant = client.patch(PROFILE_ME_URL, {'bio': 'A' * 131072}, format='json')
        assert res_giant.status_code == 400
        assert 'bio' in res_giant.json()
        assert res_giant.status_code != 500

    @pytest.mark.parametrize('root_payload', [
        ['root', 'is', 'a', 'list'],
        'just_a_string',
        123456,
    ])
    def test_non_dictionary_root_json_rejected_with_clean_400(self, teacher_user, root_payload):
        client = auth_client(teacher_user.user)
        res = client.patch(PROFILE_ME_URL, root_payload, format='json')
        assert res.status_code == 400
        assert res.status_code != 500

    def test_unicode_bom_raw_bytes_handling(self, teacher_user):
        client = auth_client(teacher_user.user)
        raw_body_clean = b'\xef\xbb\xbf{"headline": "Clean Valid Headline"}'
        res = client.generic('PATCH', PROFILE_ME_URL, data=raw_body_clean, content_type='application/json')
        # DRF either decodes or returns a clean 400 ParseError, NEVER a 500 server error
        assert res.status_code in (200, 400)
        assert res.status_code != 500

    def test_unicode_bom_in_string_normalizes_or_detects_evasion(self, teacher_user):
        client = auth_client(teacher_user.user)
        # Clean headline with BOM character inside string
        res_clean = client.patch(PROFILE_ME_URL, {'headline': '\ufeffClean Native Headline'}, format='json')
        assert res_clean.status_code == 200
        profile = TeacherProfile.objects.get(user=teacher_user.user)
        assert 'Clean Native Headline' in profile.headline

        # Evasion concealed with BOM character
        res_evasion = client.patch(PROFILE_ME_URL, {'headline': '\ufeffwa.me/27825551234'}, format='json')
        assert res_evasion.status_code == 400
        assert 'headline' in res_evasion.json()


# =====================================================================
# 3. LESSON MEMO (POST /api/v1/bookings/<id>/memo/) ADVERSARIAL EVASION
# =====================================================================
@pytest.mark.django_db
class TestLessonMemoAdversarialEvasion:
    """Stress tests POST /api/v1/bookings/<id>/memo/ across all fields with contact evasion payloads."""

    EVASIONS = [
        "Call me at 0 8 2 5 5 5 1 2 3 4",
        "My WhatsApp is 082.555.1234",
        "Reach out on wa.me/27825551234",
        "Find me on w.h.a.t.s.a.p.p",
        "wh\u0430ts\u0430\u0440\u0440 me anytime",
        "t.me/tutor_channel",
        "telegram: @tutor_john",
        "skype: tutor.john",
        "paypal.me/tutorpay",
        "venmo: @tutorvenmo",
        "$cashtag123",
        "zoom.us/j/123456789",
        "meet.google.com/abc-defg-hij",
        "email me at student [at] gmail (dot) com",
        "tutor @ gmail . com",
        "t.u.t.o.r@g.m.a.i.l.c.o.m",
        "zero eight two five five five one two three four",
    ]

    BASE_VALID = {
        'feedback_text': 'Great lesson today on English grammar.',
        'pronunciation_notes': 'Focus on short vowels.',
        'grammar_notes': 'Practiced the past perfect tense.',
        'homework': 'Read chapter 4 and write a summary.',
        'vocabulary_words': [{'word': 'meticulous', 'definition': 'very careful'}],
    }

    @pytest.mark.parametrize('payload', EVASIONS)
    def test_feedback_text_rejects_evasion(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_VALID, 'feedback_text': payload}
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert 'feedback_text' in res.json()
        assert res.status_code != 500
        assert not LessonMemo.objects.filter(booking=booking).exists()
        assert Booking.objects.get(pk=booking.pk).status == Booking.Status.COMPLETED_PENDING_MEMO

    @pytest.mark.parametrize('payload', EVASIONS)
    def test_general_feedback_alias_rejects_evasion(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_VALID, 'general_feedback': payload}
        body.pop('feedback_text')
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert 'general_feedback' in res.json()
        assert res.status_code != 500
        assert not LessonMemo.objects.filter(booking=booking).exists()

    @pytest.mark.parametrize('payload', EVASIONS)
    def test_pronunciation_notes_rejects_evasion(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_VALID, 'pronunciation_notes': payload}
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert 'pronunciation_notes' in res.json()
        assert res.status_code != 500
        assert not LessonMemo.objects.filter(booking=booking).exists()

    @pytest.mark.parametrize('payload', EVASIONS)
    def test_grammar_notes_rejects_evasion(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_VALID, 'grammar_notes': payload}
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert 'grammar_notes' in res.json()
        assert res.status_code != 500
        assert not LessonMemo.objects.filter(booking=booking).exists()

    @pytest.mark.parametrize('payload', EVASIONS)
    def test_grammar_corrections_alias_rejects_evasion(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_VALID, 'grammar_corrections': payload}
        body.pop('grammar_notes')
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert 'grammar_corrections' in res.json()
        assert res.status_code != 500
        assert not LessonMemo.objects.filter(booking=booking).exists()

    @pytest.mark.parametrize('payload', EVASIONS)
    def test_homework_rejects_evasion(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_VALID, 'homework': payload}
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert 'homework' in res.json()
        assert res.status_code != 500
        assert not LessonMemo.objects.filter(booking=booking).exists()

    @pytest.mark.parametrize('payload', EVASIONS)
    def test_homework_assigned_alias_rejects_evasion(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_VALID, 'homework_assigned': payload}
        body.pop('homework')
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert 'homework_assigned' in res.json()
        assert res.status_code != 500
        assert not LessonMemo.objects.filter(booking=booking).exists()

    @pytest.mark.parametrize('payload', EVASIONS)
    def test_next_lesson_recommendation_alias_rejects_evasion(self, teacher_user, student_user, payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_VALID, 'next_lesson_recommendation': payload}
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert 'next_lesson_recommendation' in res.json()
        assert res.status_code != 500
        assert not LessonMemo.objects.filter(booking=booking).exists()


# =====================================================================
# 4. LESSON MEMO HOSTILE JSON INPUTS
# =====================================================================
@pytest.mark.django_db
class TestLessonMemoHostileJSON:
    """Stress tests POST /api/v1/bookings/<id>/memo/ with nulls, wrong datatypes, and oversized payloads."""

    BASE_VALID = {
        'feedback_text': 'Great lesson today on English grammar.',
        'pronunciation_notes': 'Focus on short vowels.',
        'grammar_notes': 'Practiced the past perfect tense.',
        'homework': 'Read chapter 4.',
        'vocabulary_words': [{'word': 'meticulous', 'definition': 'very careful'}],
    }

    @pytest.mark.parametrize('field', [
        'feedback_text', 'general_feedback', 'pronunciation_notes',
        'grammar_notes', 'grammar_corrections', 'homework', 'homework_assigned',
        'vocabulary_words',
    ])
    def test_null_field_rejected_with_clean_400(self, teacher_user, student_user, field):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_VALID, field: None}
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert field in res.json()
        assert res.status_code != 500

    @pytest.mark.parametrize('field,bad_val', [
        ('feedback_text', ['array', 'instead', 'of', 'str']),
        ('feedback_text', {'nested': 'dict'}),
        ('feedback_text', True),
        ('homework', ['task1', 'task2']),
        ('homework', {'task': 'read'}),
        ('grammar_notes', False),
        ('pronunciation_notes', ['note']),
        ('vocabulary_words', 'not-a-list'),
        ('vocabulary_words', {'word': 'single'}),
    ])
    def test_wrong_datatype_rejected_with_clean_400(self, teacher_user, student_user, field, bad_val):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {**self.BASE_VALID, field: bad_val}
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert field in res.json()
        assert res.status_code != 500

    @pytest.mark.parametrize('field', ['feedback_text', 'general_feedback', 'homework', 'grammar_notes', 'pronunciation_notes'])
    def test_oversized_string_rejected_with_clean_400(self, teacher_user, student_user, field):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        # 5001 chars (limit is 5000)
        body_5001 = {**self.BASE_VALID, field: 'X' * 5001}
        if field == 'general_feedback':
            body_5001.pop('feedback_text', None)
        res_5001 = client.post(f'/api/v1/bookings/{booking.id}/memo/', body_5001, format='json')
        assert res_5001.status_code == 400
        assert field in res_5001.json()

        # 100KB giant string (resource exhaustion test)
        body_giant = {**self.BASE_VALID, field: 'X' * 102400}
        if field == 'general_feedback':
            body_giant.pop('feedback_text', None)
        res_giant = client.post(f'/api/v1/bookings/{booking.id}/memo/', body_giant, format='json')
        assert res_giant.status_code == 400
        assert field in res_giant.json()
        assert res_giant.status_code != 500

    @pytest.mark.parametrize('root_payload', [
        ['array', 'root', 'not', 'dict'],
        'plain_string',
        999999,
    ])
    def test_non_dictionary_root_json_rejected_with_clean_400(self, teacher_user, student_user, root_payload):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', root_payload, format='json')
        assert res.status_code == 400
        assert res.status_code != 500

    def test_unicode_bom_raw_bytes_handling(self, teacher_user, student_user):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        raw_body = b'\xef\xbb\xbf{"feedback_text": "Clean valid feedback notes."}'
        res = client.generic('POST', f'/api/v1/bookings/{booking.id}/memo/', data=raw_body, content_type='application/json')
        # DRF returns 200 or clean 400 ParseError, NEVER 500
        assert res.status_code in (200, 400)
        assert res.status_code != 500


# =====================================================================
# 5. MIXED ALIAS TESTING
# =====================================================================
@pytest.mark.django_db
class TestLessonMemoMixedAliases:
    """Tests simultaneous submission of canonical fields alongside descriptive aliases."""

    def test_both_feedback_text_and_general_feedback_valid(self, teacher_user, student_user):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {
            'feedback_text': 'Canonical feedback prose.',
            'general_feedback': 'Alias feedback prose.',
            'homework': 'Page 10',
        }
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 200
        data = res.json()
        assert 'feedback_text' in data
        assert 'general_feedback' in data
        memo = LessonMemo.objects.get(booking=booking)
        assert memo.feedback_text == 'Canonical feedback prose.'

    def test_mixed_feedback_evasion_on_alias_triggers_400_with_alias_key(self, teacher_user, student_user):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {
            'feedback_text': 'Clean canonical feedback text.',
            'general_feedback': 'Call me at 0 8 2 5 5 5 1 2 3 4',
        }
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert 'general_feedback' in res.json()
        assert not LessonMemo.objects.filter(booking=booking).exists()

    def test_mixed_feedback_evasion_on_canonical_triggers_400_with_canonical_key(self, teacher_user, student_user):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {
            'feedback_text': 'wa.me/27825551234',
            'general_feedback': 'Clean alias feedback prose.',
        }
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert 'feedback_text' in res.json()
        assert not LessonMemo.objects.filter(booking=booking).exists()

    def test_mixed_homework_evasion_on_alias_triggers_400(self, teacher_user, student_user):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {
            'feedback_text': 'Clean feedback.',
            'homework': 'Read chapter 3',
            'homework_assigned': 'Contact my telegram @tutor_john for assignment',
        }
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert 'homework_assigned' in res.json()
        assert not LessonMemo.objects.filter(booking=booking).exists()

    def test_mixed_grammar_evasion_on_alias_triggers_400(self, teacher_user, student_user):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {
            'feedback_text': 'Clean feedback.',
            'grammar_notes': 'Clean grammar note',
            'grammar_corrections': 'Pay on paypal.me/tutorjohn to get corrections',
        }
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 400
        assert 'grammar_corrections' in res.json()
        assert not LessonMemo.objects.filter(booking=booking).exists()

    def test_neither_feedback_text_nor_general_feedback_supplied_triggers_clean_400(self, teacher_user, student_user):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        # Empty payload
        res_empty = client.post(f'/api/v1/bookings/{booking.id}/memo/', {}, format='json')
        assert res_empty.status_code == 400
        assert 'feedback_text' in res_empty.json()

        # Only auxiliary fields provided
        res_aux = client.post(f'/api/v1/bookings/{booking.id}/memo/', {'homework': 'Only homework'}, format='json')
        assert res_aux.status_code == 400
        assert 'feedback_text' in res_aux.json()

        # Both blank/whitespace
        res_blank = client.post(f'/api/v1/bookings/{booking.id}/memo/', {
            'feedback_text': '   ',
            'general_feedback': '   ',
        }, format='json')
        assert res_blank.status_code == 400
        assert 'feedback_text' in res_blank.json()


# =====================================================================
# 6. EDUCATIONAL EXEMPTION LIVE IMMUNITY
# =====================================================================
@pytest.mark.django_db
class TestEducationalExemptionLiveImmunity:
    """Verifies that legitimate pedagogical content is NEVER blocked with false positives."""

    LEGITIMATE_EDUCATIONAL_CASES = [
        "In 1995, South Africa won the Rugby World Cup.",
        "The period 1939 to 1945 was World War II.",
        "From 1990–2000, the internet expanded globally.",
        "Our next lesson is scheduled from 10:30 to 11:45 am.",
        "Please read page 12, line 4 of your textbook.",
        "Complete chapter 3, exercises 1, 2, and 3 for homework.",
        "Refer to unit 5, questions 10 to 15.",
        "Let's zoom in on this paragraph to analyze the verb tense.",
        "It was nice to meet you today in class.",
        "You can pay in cash or card at the store in this story.",
        "Please read line 4 out loud.",
        "There are 10,000,000 speakers of this dialect and a $25.00 dictionary.",
        "I have three siblings and five years of English teaching experience.",
    ]

    @pytest.mark.parametrize('text', LEGITIMATE_EDUCATIONAL_CASES)
    def test_tutor_bio_allows_educational_prose(self, teacher_user, text):
        client = auth_client(teacher_user.user)
        res = client.patch(PROFILE_ME_URL, {'bio': text}, format='json')
        assert res.status_code == 200, f"False positive rejection on bio: {text}. Error: {res.json()}"
        profile = TeacherProfile.objects.get(user=teacher_user.user)
        assert profile.bio == text

    @pytest.mark.parametrize('text', LEGITIMATE_EDUCATIONAL_CASES)
    def test_lesson_memo_allows_educational_prose(self, teacher_user, student_user, text):
        booking = make_finished_booking(teacher_user, student_user)
        client = auth_client(teacher_user.user)
        body = {
            'feedback_text': text,
            'homework': text,
            'grammar_notes': text,
            'pronunciation_notes': 'Good job',
        }
        res = client.post(f'/api/v1/bookings/{booking.id}/memo/', body, format='json')
        assert res.status_code == 200, f"False positive rejection on memo: {text}. Error: {res.json()}"
        memo = LessonMemo.objects.get(booking=booking)
        assert memo.feedback_text == text
