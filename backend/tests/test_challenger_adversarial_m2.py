"""
backend/tests/test_challenger_adversarial_m2.py

Empirical adversarial stress test suite authored by teamwork_preview_challenger_m2_1.
Tests the robustness, edge cases, and failure modes of backend/apps/common/contact_guard.py.

Evaluates 5 critical vectors:
1. Exotic homoglyphs (Cyrillic, Greek, mathematical symbols).
2. Multi-layer zero-width and steganography (Unicode variation selectors, format characters).
3. Deeply nested separator tricks (multi-character separators, spaced emails, wide phone spacing).
4. Mixed spelled numbers with separators.
5. Extreme educational texts (dates and year ranges 1000-2050, counting exercises, curriculum citations).
"""

import pytest
from apps.common.contact_guard import (
    detect_off_platform_contact,
)


class TestAdversarialExoticHomoglyphs:
    """Evaluates evasion using Cyrillic and Greek homoglyphs."""

    @pytest.mark.parametrize("payload,expected_platform", [
        # Greek alphabet lookalikes
        ("wh\u03B1ts\u03B1pp", "whatsapp"),                 # Greek alpha \u03B1
        ("\u03C4\u03B5l\u03B5gr\u03B1m", "telegram"),        # Greek tau \u03C4, epsilon \u03B5, alpha \u03B1
        ("skyp\u03B5", "skype"),                             # Greek epsilon \u03B5
        ("\u03C1\u03B1yp\u03B1l", "paypal"),                 # Greek rho \u03C1, alpha \u03B1
        ("\u03BD\u03B5nm\u03BF", "venmo"),                   # Greek nu \u03BD, epsilon \u03B5, omicron \u03BF
        ("c\u03B1sh\u03B1pp", "cashapp"),                   # Greek alpha \u03B1
        ("z\u03BF\u03BFm meeting", "zoom"),                  # Greek omicron \u03BF
        # Cyrillic lookalikes missing from CYRILLIC_LOOKALIKES
        ("wha\u0422sapp", "whatsapp"),                       # Cyrillic capital Te \u0422
        ("telegra\u041C", "telegram"),                       # Cyrillic capital Em \u041C
        ("s\u041Aype", "skype"),                             # Cyrillic capital Ka \u041A
        ("s\u043Aype", "skype"),                             # Cyrillic small Ka \u043A
        ("w\u041Datsapp", "whatsapp"),                       # Cyrillic capital En \u041D
    ])
    def test_exotic_homoglyphs_evasion(self, payload, expected_platform):
        """These homoglyphs are visually identical to Latin characters but evade current normalization."""
        findings = detect_off_platform_contact(payload)
        assert expected_platform in findings, (
            f"VULNERABILITY CONFIRMED: Homoglyph payload '{payload}' evaded detection. "
            f"Got: {findings}"
        )


class TestAdversarialZeroWidthSteganography:
    """Evaluates evasion using invisible Unicode characters outside the current regex."""

    @pytest.mark.parametrize("payload,expected_detection", [
        # Unicode Variation Selectors (U+FE00 through U+FE0F)
        ("w\uFE00h\uFE00a\uFE00t\uFE00s\uFE00a\uFE00p\uFE00p", "whatsapp"),
        ("0\uFE008\uFE002\uFE005\uFE005\uFE005\uFE001\uFE002\uFE003\uFE004", "phone"),
    ])
    def test_variation_selector_steganography(self, payload, expected_detection):
        """Variation selectors (U+FE00-U+FE0F) are invisible formatting characters that defeat regex matching."""
        findings = detect_off_platform_contact(payload)
        assert expected_detection in findings, (
            f"VULNERABILITY CONFIRMED: Invisible variation selector payload evaded detection. "
            f"Got: {findings}"
        )


class TestAdversarialDeeplyNestedSeparators:
    """Evaluates evasion using multi-character separators, spaced emails, and wide phone gaps."""

    @pytest.mark.parametrize("payload,expected_platform", [
        # Multi-dot separators
        ("w...h...a...t...s...a...p...p", "whatsapp"),
        ("w..h..a..t..s..a..p..p", "whatsapp"),
        ("t...e...l...e...g...r...a...m", "telegram"),
        ("s...k...y...p...e", "skype"),
        ("p...a...y...p...a...l", "paypal"),
        # Multi-space separators
        ("w   h   a   t   s   a   p   p", "whatsapp"),
        ("w  h  a  t  s  a  p  p", "whatsapp"),
        # Mixed space-dot separators
        ("w . h . a . t . s . a . p . p", "whatsapp"),
    ])
    def test_multi_character_separator_platform_evasion(self, payload, expected_platform):
        """SINGLE_LETTER_SEPARATOR_RE only matches single separator chars, failing on multi-char gaps."""
        findings = detect_off_platform_contact(payload)
        assert expected_platform in findings, (
            f"VULNERABILITY CONFIRMED: Multi-separator payload '{payload}' evaded detection. "
            f"Got: {findings}"
        )

    @pytest.mark.parametrize("payload", [
        "user @ domain.com",
        "user @ domain . com",
        "user@ domain.com",
        "user @domain.com",
    ])
    def test_spaced_literal_email_evasion(self, payload):
        """EMAIL_RE requires no spaces around '@' or '.', evading detection when space is inserted."""
        findings = detect_off_platform_contact(payload)
        assert "email" in findings, (
            f"VULNERABILITY CONFIRMED: Spaced email '{payload}' evaded detection. Got: {findings}"
        )

    @pytest.mark.parametrize("payload", [
        "082    555    1234",      # 4 spaces
        "082....555....1234",      # 4 dots
        "082----555----1234",      # 4 dashes
    ])
    def test_wide_separator_phone_evasion(self, payload):
        """PHONE_RE restricts separators to {0,3}, so 4+ spaces/dots bypass detection."""
        findings = detect_off_platform_contact(payload)
        assert "phone" in findings, (
            f"VULNERABILITY CONFIRMED: Phone with wide separators '{payload}' evaded detection. Got: {findings}"
        )


class TestAdversarialMixedSpelledNumbers:
    """Evaluates spelled numbers with nested separators."""

    def test_dotted_spelled_numbers_phone_evasion(self):
        payload = "o...n...e e...i...g...h...t t...w...o f...i...v...e f...i...v...e f...i...v...e o...n...e t...w...o t...h...r...e...e f...o...u...r"
        findings = detect_off_platform_contact(payload)
        assert "phone" in findings, (
            f"VULNERABILITY CONFIRMED: Dotted spelled numbers evaded phone detection. Got: {findings}"
        )


class TestAdversarialEducationalFalsePositives:
    """Evaluates legitimate educational prose that is incorrectly blocked (false positives)."""

    @pytest.mark.parametrize("text,description", [
        # Historical dates & date ranges before 1800 (prompt explicitly notes 1000 to 2050)
        ("The medieval era (1066-1215) saw dramatic changes.", "Medieval English date range"),
        ("The Hundred Years War (1337-1453) was prolonged.", "14th-15th century date range"),
        ("The Protestant Reformation (1517-1648) transformed Europe.", "16th-17th century date range"),
        ("Timeline: 1066 - 1215 - 1492 - 1588.", "Historical timeline list of 4-digit years"),
        ("Eras studied: 1066/1215/1492.", "Slashed historical years"),
        # Educational citations with colons or counting lists
        ("Chapters: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8", "Curriculum chapters listing with colon"),
        ("Scores: 1 / 2 / 3 / 4 / 5 / 6 / 7 / 8", "Pronunciation scores listing"),
        ("Grade 1 counting chart: one - two - three - four - five - six - seven - eight - nine", "ESL primary counting chart"),
    ])
    def test_educational_prose_incorrectly_blocked(self, text, description):
        r"""EDUCATIONAL_MASKS hardcodes (?:18|19|20)\d{2}, incorrectly blocking historical texts before 1800."""
        findings = detect_off_platform_contact(text)
        assert findings == [], (
            f"FALSE POSITIVE CONFIRMED: Educational text '{text}' ({description}) was rejected with {findings}"
        )
