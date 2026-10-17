"""
backend/apps/common/tests/test_contact_guard.py

Comprehensive test suite for Anti-Disintermediation & Contact-Leakage Sanitization Pipeline.
Organized into 8 suites covering 47 test specifications across normalization, pattern detection,
educational exemptions, validator contracts, DRF serializer integrations, and adversarial evasion combos.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.bookings.serializers import LessonMemoInputSerializer
from apps.common.contact_guard import (
    convert_number_words,
    detect_off_platform_contact,
    normalize_text,
    validate_no_off_platform_contact,
)
from apps.teachers.models import TeacherProfile
from apps.teachers.serializers import ApplicationDraftSerializer, TeacherOwnProfileSerializer

User = get_user_model()


# =====================================================================
# Suite 1: TestTextNormalization
# =====================================================================
class TestTextNormalization:
    def test_nfkc_normalizes_fullwidth_latin_alphabet(self):
        assert normalize_text("ｗｈａｔｓａｐｐ") == "whatsapp"
        assert normalize_text("ｔｅｌｅｇｒａｍ") == "telegram"
        assert normalize_text("ｐａｙｐａｌ") == "paypal"

    def test_nfkc_normalizes_fullwidth_digits(self):
        assert normalize_text("０８２５５５１２３４") == "0825551234"

    def test_strips_zero_width_spaces_and_joiners(self):
        assert normalize_text("w\u200Bhats\u200Dapp") == "whatsapp"
        assert normalize_text("082\uFEFF555\u00AD1234") == "0825551234"
        assert normalize_text("name\u200C@\u2060domain.com") == "name@domain.com"

    def test_collapses_dotted_single_characters(self):
        assert normalize_text("w.h.a.t.s.a.p.p") == "whatsapp"
        assert normalize_text("t.e.l.e.g.r.a.m") == "telegram"
        assert normalize_text("p.a.y.p.a.l") == "paypal"

    def test_collapses_spaced_single_characters(self):
        assert normalize_text("w h a t s a p p") == "whatsapp"
        assert normalize_text("s k y p e") == "skype"

    def test_collapses_punctuation_separated_characters(self):
        assert normalize_text("w-h-a-t-s-a-p-p") == "whatsapp"
        assert normalize_text("w_h_a_t_s_a_p_p") == "whatsapp"
        assert normalize_text("w/h/a/t/s/a/p/p") == "whatsapp"
        assert normalize_text("w*h*a*t*s*a*p*p") == "whatsapp"

    def test_normalizes_cyrillic_visual_homoglyphs(self):
        assert normalize_text("wh\u0430ts\u0430\u0440\u0440") == "whatsapp"

    def test_converts_whole_word_numbers_to_digits(self):
        assert convert_number_words("zero eight two five five five one two three four") == "0 8 2 5 5 5 1 2 3 4"

    def test_word_number_conversion_respects_word_boundaries(self):
        sample = "bone weight often tonight shine"
        assert convert_number_words(sample) == sample


# =====================================================================
# Suite 2: TestPhoneNumberDetection
# =====================================================================
class TestPhoneNumberDetection:
    def test_detects_10_digit_contiguous_phone_number(self):
        assert "phone" in detect_off_platform_contact("Call me at 0825551234 anytime.")

    def test_detects_e164_international_phone_number(self):
        for phone in ["+27 82 555 1234", "+1 (555) 234-5678", "+44 7911 123456"]:
            assert "phone" in detect_off_platform_contact(phone)

    def test_detects_spaced_digit_phone_number(self):
        assert "phone" in detect_off_platform_contact("0 8 2  5 5 5  1 2 3 4")

    def test_detects_dotted_and_dashed_phone_number(self):
        assert "phone" in detect_off_platform_contact("082.555.1234")
        assert "phone" in detect_off_platform_contact("082-555-1234")

    def test_detects_spelled_out_word_numbers_phone(self):
        assert "phone" in detect_off_platform_contact("zero eight two five five five one two three four")

    def test_detects_mixed_digit_and_word_phone(self):
        assert "phone" in detect_off_platform_contact("0 eight 2 double five five 1 2 3 4")

    def test_allows_short_number_sequences(self):
        for item in ["Lesson 4", "Page 12", "Room 101", "$25.00"]:
            assert detect_off_platform_contact(item) == []


# =====================================================================
# Suite 3: TestEmailDetection
# =====================================================================
class TestEmailDetection:
    def test_detects_standard_email_addresses(self):
        for email in ["john.doe@gmail.com", "tutor@esl-academy.org", "sarah@domain.co.za"]:
            assert "email" in detect_off_platform_contact(email)

    def test_detects_bracketed_homoglyph_emails(self):
        for text in ["name [at] domain (dot) com", "name(at)domain(dot)com", "name<at>domain<dot>com"]:
            assert "email" in detect_off_platform_contact(text)

    def test_detects_spaced_word_homoglyph_emails(self):
        for text in ["teacher at gmail dot com", "sarah AT yahoo DOT com"]:
            assert "email" in detect_off_platform_contact(text)

    def test_detects_zero_width_injected_emails(self):
        for text in ["user\u200B@\u200Bdomain.com", "user@\uFEFFdomain.com"]:
            assert "email" in detect_off_platform_contact(text)


# =====================================================================
# Suite 4: TestOffPlatformMessagingAndPayments
# =====================================================================
class TestOffPlatformMessagingAndPayments:
    def test_detects_whatsapp_mentions_and_links(self):
        for text in ["Add me on WhatsApp", "wa.me/27825551234", "api.whatsapp.com/send?phone=27825551234"]:
            assert "whatsapp" in detect_off_platform_contact(text)

    def test_detects_telegram_mentions_and_handles(self):
        for text in ["Message me on Telegram", "t.me/tutor_sarah", "telegram: @tutor_sarah"]:
            assert "telegram" in detect_off_platform_contact(text)

    def test_detects_wechat_mentions_and_ids(self):
        for text in ["My WeChat ID is esl_pro", "WeChat: esl_pro", "weixin"]:
            assert "wechat" in detect_off_platform_contact(text)

    def test_detects_line_handles(self):
        for text in ["LINE ID: esl_teacher", "add me on line: esl_teacher", "line.me/ti/p/12345"]:
            assert "line" in detect_off_platform_contact(text)

    def test_detects_kakaotalk_mentions(self):
        for text in ["KakaoTalk: teacher123", "kakao ID: teacher123", "open.kakao.com/o/12345"]:
            assert "kakaotalk" in detect_off_platform_contact(text)

    def test_detects_skype_mentions(self):
        for text in ["Skype: live:.cid.12345678", "Skype ID: john_esl", "live:john_doe"]:
            assert "skype" in detect_off_platform_contact(text)

    def test_detects_paypal_payment_links(self):
        for text in ["paypal.me/englishtutor", "Pay via PayPal: user@domain.com"]:
            assert "paypal" in detect_off_platform_contact(text)

    def test_detects_venmo_handles(self):
        for text in ["Venmo: @englishtutor", "My Venmo is @englishtutor", "venmo.com"]:
            assert "venmo" in detect_off_platform_contact(text)

    def test_detects_cashapp_handles_and_cashtags(self):
        for text in ["cash.app/$EnglishTutor", "CashApp: $EnglishTutor", "$EnglishTutor"]:
            assert "cashapp" in detect_off_platform_contact(text)

    def test_detects_zoom_and_google_meet_links(self):
        assert "zoom" in detect_off_platform_contact("zoom.us/j/9876543210")
        assert "google_meet" in detect_off_platform_contact("meet.google.com/xyz-uvwx-rst")


# =====================================================================
# Suite 5: TestEducationalFalsePositiveExemptions
# =====================================================================
class TestEducationalFalsePositiveExemptions:
    def test_allows_historical_dates_and_four_digit_years(self):
        for text in [
            "In 1995 I was born, and in 2017 I graduated from university.",
            "World War II took place between 1939 and 1945.",
            "The platform was founded in 2024.",
        ]:
            assert detect_off_platform_contact(text) == []

    def test_allows_historical_date_ranges_with_conjunctions(self):
        for text in [
            "The economy boomed between 1980 and 1990.",
            "I taught in Japan from 1999 to 2005.",
        ]:
            assert detect_off_platform_contact(text) == []

    def test_allows_grammar_pedagogy_preposition_at(self):
        for text in [
            "Use 'at' for specific times (e.g. at 5 PM, at noon, at midnight).",
            "She is exceptionally good at conversational English.",
            "We arrived at the airport early in the morning.",
        ]:
            assert detect_off_platform_contact(text) == []

    def test_allows_punctuation_pedagogy_dot(self):
        for text in [
            "Remember to put a dot (full stop) at the end of every complete sentence.",
            "Connect the dots from 1 to 10 to draw the outline.",
            "Dot your i's and cross your t's carefully.",
        ]:
            assert detect_off_platform_contact(text) == []

    def test_allows_curriculum_and_page_citations(self):
        for text in [
            "Please open your book to Lesson 4, Page 12, Exercise 3.",
            "Review units 5, 6, and 7 before our next lesson.",
            "Complete chapter 3, section 2, questions 1 through 5.",
        ]:
            assert detect_off_platform_contact(text) == []

    def test_allows_conversational_verbs_matching_app_names(self):
        for text in [
            "Please read the second line on page 15 aloud.",
            "Can you zoom in on the diagram on the screen?",
            "It was wonderful to meet you today in class.",
            "Many tourists still pay in cash when traveling abroad.",
            "You must pay attention to syllable stress in multisyllabic words.",
        ]:
            assert detect_off_platform_contact(text) == []

    def test_allows_number_words_in_normal_english_sentences(self):
        for text in [
            "I have lived in five different countries over eight years.",
            "There are three brothers and two sisters in my family.",
            "We will have two lessons a week for four weeks.",
        ]:
            assert detect_off_platform_contact(text) == []

    def test_allows_empty_and_whitespace_inputs(self):
        assert detect_off_platform_contact("") == []
        assert detect_off_platform_contact("   ") == []
        assert detect_off_platform_contact(None) == []
        assert validate_no_off_platform_contact("") == ""
        assert validate_no_off_platform_contact(None) is None


# =====================================================================
# Suite 6: TestValidatorContract
# =====================================================================
class TestValidatorContract:
    def test_validate_no_off_platform_contact_passes_clean_prose(self):
        clean_bio = "Passionate ESL tutor with 10 years of experience teaching conversational English and IELTS preparation."
        assert validate_no_off_platform_contact(clean_bio) == clean_bio

    def test_validate_no_off_platform_contact_raises_validation_error_on_violation(self):
        with pytest.raises(serializers.ValidationError) as exc_info:
            validate_no_off_platform_contact("Contact me on w.h.a.t.s.a.p.p")
        assert "whatsapp" in str(exc_info.value).lower()


# =====================================================================
# Suite 7: TestSerializerIntegration
# =====================================================================
@pytest.mark.django_db
class TestSerializerIntegration:
    @pytest.fixture
    def teacher_profile(self):
        user = User.objects.create_user(
            username="guard_tutor", email="guard_tutor@example.com", password="password123", role="teacher"
        )
        return TeacherProfile.objects.create(user=user, headline="Certified ESL Instructor", bio="Hello students.")

    def test_teacher_own_profile_serializer_bio_rejects_leakage(self, teacher_profile):
        serializer = TeacherOwnProfileSerializer(
            instance=teacher_profile, data={"bio": "Call 0825551234 for direct lessons."}, partial=True
        )
        assert serializer.is_valid() is False
        assert "bio" in serializer.errors

    def test_teacher_own_profile_serializer_headline_rejects_leakage(self, teacher_profile):
        serializer = TeacherOwnProfileSerializer(
            instance=teacher_profile, data={"headline": "Tutor | paypal.me/tutor"}, partial=True
        )
        assert serializer.is_valid() is False
        assert "headline" in serializer.errors

    def test_teacher_own_profile_serializer_allows_educational_bio(self, teacher_profile):
        serializer = TeacherOwnProfileSerializer(
            instance=teacher_profile,
            data={"bio": "Taught since 1995. Good at grammar and pronunciation."},
            partial=True,
        )
        assert serializer.is_valid() is True, serializer.errors

    def test_application_draft_serializer_rejects_leakage(self):
        serializer = ApplicationDraftSerializer(data={"bio": "telegram: @tutor_sarah"})
        assert serializer.is_valid() is False
        assert "bio" in serializer.errors

    def test_lesson_memo_input_serializer_all_fields_guarded(self):
        guarded_fields = [
            ("feedback_text", "Call 0825551234"),
            ("general_feedback", "Email me at teacher@gmail.com"),
            ("pronunciation_notes", "WhatsApp me at +27825551234"),
            ("grammar_notes", "Pay via paypal.me/tutor"),
            ("grammar_corrections", "t.me/tutor_sarah"),
            ("homework", "Add me on WeChat: esl_pro"),
            ("homework_assigned", "LINE ID: esl_teacher"),
            ("next_lesson_recommendation", "join zoom.us/j/1234567890"),
        ]
        for field_name, leakage_val in guarded_fields:
            payload = {
                "feedback_text": "Good work today.",
                field_name: leakage_val,
            }
            serializer = LessonMemoInputSerializer(data=payload)
            assert serializer.is_valid() is False, f"Expected {field_name} with '{leakage_val}' to be rejected"
            assert field_name in serializer.errors, f"Expected error keyed on {field_name}, got {serializer.errors}"

    def test_lesson_memo_input_serializer_allows_legitimate_lesson_feedback(self):
        valid_memo = {
            "feedback_text": "Great progress on past tense rules today. Reviewed historical dates from 1980 to 1990.",
            "vocabulary_words": [{"word": "metaphor", "definition": "figurative comparison"}],
            "pronunciation_notes": "Watch syllable stress on multisyllabic words.",
            "grammar_notes": "Remember: use 'at' for specific times such as at 5 PM.",
            "homework": "Complete exercises 1, 2, 3 on page 42.",
        }
        serializer = LessonMemoInputSerializer(data=valid_memo)
        assert serializer.is_valid() is True, serializer.errors


# =====================================================================
# Suite 8: TestAdversarialEvasionCombos
# =====================================================================
class TestAdversarialEvasionCombos:
    def test_multi_layer_obfuscation_combo_defeated(self):
        combo = "ｃａｌｌ　ｍｅ\u200B: zero eight two\u200D5 5 5-1 2 3 4 or email name [at] domain (dot) com"
        violations = detect_off_platform_contact(combo)
        assert "phone" in violations
        assert "email" in violations
        with pytest.raises(serializers.ValidationError):
            validate_no_off_platform_contact(combo)
