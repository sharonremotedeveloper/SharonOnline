"""
backend/tests/test_challenger_empirical_m2_it3.py

Milestone 2 Iteration 3 Empirical Adversarial Verification Suite.
Author: teamwork_preview_challenger_m2_it3_1

Empirically tests detect_off_platform_contact and validate_no_off_platform_contact:
1. Spaced punctuation phone variations (e.g., 0 8 2 . . . 5 5 5 - - - 1 2 3 4, +27 (0) 82 . . . 555 - - - 1234)
2. Spaced punctuation platform handles (e.g., w . . . h . . . a . . . t . . . s . . . a . . . p . . . p)
3. Greek omega homoglyph variations (\u03c9hatsapp, \u03c9echat, \u03a9hatsapp, \u03a9echat)
4. Educational historical dates & syllabus counting charts (Confirm ZERO false positives)
5. Adversarial pseudo-educational evasion attacks (Confirm ZERO false negatives)
6. ReDoS / catastrophic backtracking resilience under pathological input
7. Django REST Framework ValidationError contract enforcement
"""

import time
import pytest
from rest_framework.exceptions import ValidationError

from apps.common.contact_guard import (
    detect_off_platform_contact,
    validate_no_off_platform_contact,
)


class TestSpacedPunctuationPhoneVariations:
    """Stress tests spaced punctuation phone number variations."""

    @pytest.mark.parametrize("payload,description", [
        ("0 8 2 . . . 5 5 5 - - - 1 2 3 4", "Multi-dot and multi-dash spaced digits"),
        ("+27 (0) 82 . . . 555 - - - 1234", "E.164 with parentheses and multi-separator runs"),
        ("+27 (0) 82 - - - 555 . . . 1234", "E.164 with inverted dash-dot runs"),
        ("+27 (0) 82 * * * 555 ~ ~ ~ 1234", "E.164 with stars and tildes"),
        ("0 8 2 . . . 5 5 5 . . . 1 2 3 4", "All-dot multi-spaced digits"),
        ("082 . . . 555 - - - 1234", "Grouped digits with spaced dots and dashes"),
        ("082 - - - 555 - - - 1234", "Grouped digits with spaced dashes"),
        ("082 * * * 555 * * * 1234", "Grouped digits with spaced asterisks"),
        ("082 ~ ~ ~ 555 ~ ~ ~ 1234", "Grouped digits with spaced tildes"),
        ("0 8 2 . . 5 5 5 - - 1 2 3 4", "Double dots and double dashes"),
        ("+27 . . . 82 . . . 555 . . . 1234", "Country code with spaced dots"),
        ("+27 - - - 82 - - - 555 - - - 1234", "Country code with spaced dashes"),
        ("+27 * * * 82 * * * 555 * * * 1234", "Country code with spaced asterisks"),
        ("+27 ~ ~ ~ 82 ~ ~ ~ 555 ~ ~ ~ 1234", "Country code with spaced tildes"),
        ("( 0 8 2 ) . . . 5 5 5 . . . 1 2 3 4", "Parenthesized area code with spaced dots"),
        ("( 0 8 2 ) - - - 5 5 5 - - - 1 2 3 4", "Parenthesized area code with spaced dashes"),
        ("+ 2 7 ( 0 ) 8 2 . . . 5 5 5 - - - 1 2 3 4", "Fully spaced E.164 prefix with spaced punctuation"),
        ("0 8 2 / 5 5 5 / 1 2 3 4", "Slash separators between groups"),
        ("Call or text me on 0 8 2 . . . 5 5 5 - - - 1 2 3 4 after class", "In-sentence spaced punctuation phone"),
        ("Reach me at +27 (0) 82 . . . 555 - - - 1234 for details", "In-sentence E.164 spaced punctuation phone"),
    ])
    def test_spaced_punctuation_phones_detected(self, payload, description):
        findings = detect_off_platform_contact(payload)
        assert "phone" in findings, (
            f"Adversarial spaced phone evasion '{payload}' ({description}) bypassed detection! Findings: {findings}"
        )


class TestSpacedPunctuationPlatformHandles:
    """Stress tests spaced punctuation platform handles."""

    @pytest.mark.parametrize("payload,expected_platform,description", [
        ("w . . . h . . . a . . . t . . . s . . . a . . . p . . . p", "whatsapp", "Dots with interleaved spaces"),
        ("w - - - h - - - a - - - t - - - s - - - a - - - p - - - p", "whatsapp", "Dashes with interleaved spaces"),
        ("w * * * h * * * a * * * t * * * s * * * a * * * p * * * p", "whatsapp", "Asterisks with interleaved spaces"),
        ("w ~ ~ ~ h ~ ~ ~ a ~ ~ ~ t ~ ~ ~ s ~ ~ ~ a ~ ~ ~ p ~ ~ ~ p", "whatsapp", "Tildes with interleaved spaces"),
        ("w / / / h / / / a / / / t / / / s / / / a / / / p / / / p", "whatsapp", "Slashes with interleaved spaces"),
        ("w . - . h . - . a . - . t . - . s . - . a . - . p . - . p", "whatsapp", "Mixed punctuation with spaces"),
        ("w   .   .   h   .   .   a   .   .   t   .   .   s   .   .   a   .   .   p   .   .   p", "whatsapp", "Wide spaces and dots"),
        ("t . . . e . . . l . . . e . . . g . . . r . . . a . . . m", "telegram", "Telegram spaced dots"),
        ("s . . . k . . . y . . . p . . . e", "skype", "Skype spaced dots"),
        ("p . . . a . . . y . . . p . . . a . . . l", "paypal", "Paypal spaced dots"),
        ("v . . . e . . . n . . . m . . . o", "venmo", "Venmo spaced dots"),
        ("w . . . e . . . c . . . h . . . a . . . t", "wechat", "Wechat spaced dots"),
        ("c . . . a . . . s . . . h . . . a . . . p . . . p", "cashapp", "Cashapp spaced dots"),
        ("Message me on w . . . h . . . a . . . t . . . s . . . a . . . p . . . p for assignment solutions", "whatsapp", "In-sentence handle"),
    ])
    def test_spaced_punctuation_platforms_detected(self, payload, expected_platform, description):
        findings = detect_off_platform_contact(payload)
        assert expected_platform in findings, (
            f"Adversarial spaced platform evasion '{payload}' ({description}) bypassed detection! Findings: {findings}"
        )


class TestGreekOmegaVariations:
    """Stress tests lowercase and uppercase Greek omega lookalikes for Latin 'w'."""

    @pytest.mark.parametrize("payload,expected_detection,description", [
        ("\u03c9hatsapp", "whatsapp", "Lowercase Greek omega (\\u03c9) in whatsapp"),
        ("\u03c9echat", "wechat", "Lowercase Greek omega (\\u03c9) in wechat"),
        ("\u03a9hatsapp", "whatsapp", "Uppercase Greek Omega (\\u03a9) in whatsapp"),
        ("\u03a9echat", "wechat", "Uppercase Greek Omega (\\u03a9) in wechat"),
        ("\u03a9HATSAPP", "whatsapp", "Uppercase Greek Omega in all-caps whatsapp"),
        ("\u03c9h\u03b1ts\u03b1pp", "whatsapp", "Lowercase Greek omega + Greek alphas"),
        ("\u03a9H\u0391TS\u0391PP", "whatsapp", "Uppercase Greek Omega + Greek Alphas"),
        ("\u03c9 . . . h . . . a . . . t . . . s . . . a . . . p . . . p", "whatsapp", "Lowercase omega with spaced dots"),
        ("\u03a9 . . . h . . . a . . . t . . . s . . . a . . . p . . . p", "whatsapp", "Uppercase Omega with spaced dots"),
        ("\u03c9 . . . e . . . c . . . h . . . a . . . t", "wechat", "Lowercase omega with spaced dots"),
        ("\u03a9 . . . e . . . c . . . h . . . a . . . t", "wechat", "Uppercase Omega with spaced dots"),
        ("\u03c9a.me/27825551234", "phone", "Lowercase omega in wa.me link"),
        ("\u03a9A.ME/27825551234", "phone", "Uppercase Omega in WA.ME link"),
        ("Add me on \u03c9hatsapp for homework files", "whatsapp", "In-sentence lowercase omega"),
        ("Message \u03a9echat: teacher123", "wechat", "In-sentence uppercase Omega"),
    ])
    def test_greek_omega_variations_detected(self, payload, expected_detection, description):
        findings = detect_off_platform_contact(payload)
        assert expected_detection in findings, (
            f"Adversarial Greek omega evasion '{payload}' ({description}) bypassed detection! Findings: {findings}"
        )


class TestEducationalHistoricalDatesAndCountingChartsZeroFalsePositives:
    """Stress tests educational historical dates and counting charts to confirm ZERO false positives."""

    @pytest.mark.parametrize("payload,description", [
        ("1066-1215", "Hyphenated Norman and Magna Carta era dates"),
        ("1337-1453", "Hyphenated Hundred Years War era dates"),
        ("1517-1648", "Hyphenated Reformation and Thirty Years War dates"),
        ("1776-1789", "Hyphenated American and French revolution dates"),
        ("1066 - 1215", "Spaced hyphen historical dates"),
        ("1337 - 1453", "Spaced hyphen historical dates"),
        ("Chapters: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8", "Chapter listing with dash separators"),
        ("Chapters: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8 - 9 - 10", "Chapter listing 1 to 10"),
        ("Grade 1 counting chart: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8 - 9 - 10", "Grade 1 counting chart 1 to 10"),
        ("Grade 1 counting chart: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8", "Grade 1 counting chart 1 to 8"),
        ("Grade 1 counting chart: 1 - 2...", "Grade 1 counting chart with trailing ellipsis"),
        ("Grade 2 counting chart: 10 - 9 - 8 - 7 - 6 - 5 - 4 - 3 - 2 - 1", "Grade 2 descending counting chart"),
        ("Counting chart: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10", "Comma-separated counting chart"),
        ("Counting chart: 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0", "Comma-separated descending counting chart"),
        ("The Hundred Years' War (1337-1453) reshaped French and English feudalism.", "Historical era in parentheses"),
        ("Between 1066-1215 the legal system changed substantially.", "Historical era narrative"),
        ("History readings: 1066-1215 (Norman period) and 1337-1453 (Valois period).", "Compound historical periods"),
        ("Primary math chart: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8 - 9 - 10.", "Primary math chart"),
        ("Grade 1 math syllabus chapters 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8.", "Grade 1 math syllabus chapters"),
    ])
    def test_educational_historical_dates_and_charts_pass(self, payload, description):
        findings = detect_off_platform_contact(payload)
        assert findings == [], (
            f"FALSE POSITIVE: Educational input '{payload}' ({description}) blocked with findings: {findings}"
        )


class TestAdversarialPseudoEducationalAttacksBlockedZeroFalseNegatives:
    """Stress tests adversarial payloads disguised as educational counting charts or dates."""

    @pytest.mark.parametrize("payload,expected_detection,description", [
        ("Grade 1 counting chart: 082-555-1234", "phone", "Standard phone disguised behind counting chart"),
        ("Grade 1 counting chart: 0 8 2 5 5 5 1 2 3 4", "phone", "Spaced phone disguised behind counting chart"),
        ("Grade 1 counting chart: 0 8 2 . . . 5 5 5 - - - 1 2 3 4", "phone", "Spaced punctuation phone disguised behind counting chart"),
        ("Grade 1 counting chart: 9 - 3 - 8 - 1 - 5 - 2 - 4 - 7", "phone", "Non-monotonic random sequence disguised behind counting chart"),
        ("Chapters: +27 (0) 82 . . . 555 - - - 1234", "phone", "E.164 phone disguised behind chapters keyword"),
        ("1066.082.555.1234", "phone", "Historical year prefix attached to phone number"),
        ("1066-1215 contact: \u03a9hatsapp 0825551234", "whatsapp", "Historical date with uppercase Omega whatsapp and phone"),
        ("Chapters: 0825551234", "phone", "Contiguous digits disguised behind chapters"),
        ("Lessons: 082-555-1234", "phone", "Dashed digits disguised behind lessons"),
        ("Units: 0 8 2 . . . 5 5 5 - - - 1 2 3 4", "phone", "Spaced punctuation digits disguised behind units"),
    ])
    def test_pseudo_educational_attacks_blocked(self, payload, expected_detection, description):
        findings = detect_off_platform_contact(payload)
        assert expected_detection in findings, (
            f"FALSE NEGATIVE: Attacker payload '{payload}' ({description}) bypassed detection! Got: {findings}"
        )


class TestReDoSPerformanceStress:
    """Empirically stress-tests performance to rule out catastrophic backtracking (ReDoS)."""

    def test_repetitive_punctuation_linear_time(self):
        # 4000 repetitions of spaced punctuation
        payload = "w " + " . " * 2000 + " h " + " . " * 2000 + " a"
        t0 = time.time()
        _ = detect_off_platform_contact(payload)
        duration = time.time() - t0
        assert duration < 0.2, f"ReDoS suspected: execution took {duration:.4f}s"

    def test_repetitive_multi_separator_phone_linear_time(self):
        # 8000 repetitions of varied phone punctuation delimiters
        payload = "082 " + " . . - - * * ~ ~ " * 1000 + " 555"
        t0 = time.time()
        _ = detect_off_platform_contact(payload)
        duration = time.time() - t0
        assert duration < 0.25, f"ReDoS suspected: execution took {duration:.4f}s"

    def test_long_monotonic_counting_chart_linear_time(self):
        # 50 items monotonic sequence
        payload = "Grade 1 counting chart: " + " - ".join(str(i) for i in range(1, 51))
        t0 = time.time()
        findings = detect_off_platform_contact(payload)
        duration = time.time() - t0
        assert duration < 0.1, f"Execution took {duration:.4f}s"
        assert findings == []


class TestValidatorContractIntegrationM2It3:
    """Empirically tests validate_no_off_platform_contact for DRF serializer compliance."""

    def test_raises_validation_error_on_spaced_phone(self):
        with pytest.raises(ValidationError) as exc:
            validate_no_off_platform_contact("Call me at 0 8 2 . . . 5 5 5 - - - 1 2 3 4")
        assert "phone" in str(exc.value)

    def test_raises_validation_error_on_greek_omega_handle(self):
        with pytest.raises(ValidationError) as exc:
            validate_no_off_platform_contact("Reach me on \u03a9hatsapp")
        assert "whatsapp" in str(exc.value)

    def test_returns_clean_string_on_educational_counting_chart(self):
        clean = "Grade 1 counting chart: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8 - 9 - 10"
        result = validate_no_off_platform_contact(clean)
        assert result == clean

    def test_returns_clean_string_on_historical_date_range(self):
        clean = "In the period 1066-1215 and 1337-1453 English society changed."
        result = validate_no_off_platform_contact(clean)
        assert result == clean
