"""
backend/tests/test_challenger_empirical_m2_it2.py

Empirical Challenger verification test harness for Milestone 2 Iteration 2.
Author: teamwork_preview_challenger_m2_it2_1

Stress tests:
1. Novel homoglyphs (mixed Greek, Cyrillic, Latin across words and within words).
2. Multi-layer separator tricks (dots, dashes, tildes, stars, spaces, slashes).
3. Complex historical date paragraphs (pre-1800 years: 1066, 1215, 1337, 1492, 1517, 1648, 1776).
4. Syllabus and curriculum sequences vs pseudo-syllabus phone evasion attacks.
5. Email evasions (spaced, bare-at, dotted, bracketed).
6. Spelled and mixed digit/word phone evasion.
7. Legitimate educational prose (idiomatic verbs, dates, time ranges, currency, page numbers).
"""

import pytest
from apps.common.contact_guard import (
    detect_off_platform_contact,
    validate_no_off_platform_contact,
)
from rest_framework.exceptions import ValidationError


class TestNovelMixedHomoglyphs:
    """Stress tests homoglyphs combining Cyrillic, Greek, and Latin inside identical tokens."""

    @pytest.mark.parametrize("payload,expected_detection", [
        # Mixed Cyrillic + Greek + Latin in "whatsapp"
        ("wh\u0430\u03c4s\u03b1\u0440\u0440", "whatsapp"),  # w + Cyrillic а + Greek τ + s + Greek α + Cyrillic р + Cyrillic р
        ("w\u041d\u03b1\u0442s\u0430\u0440\u0440", "whatsapp"),  # Cyrillic capital Н, Greek α, Cyrillic т, Cyrillic а, Cyrillic р, Cyrillic р
        # Mixed Cyrillic + Greek + Latin in "telegram"
        ("\u03c4\u0435l\u0435gr\u03b1\u041c", "telegram"),  # Greek τ, Cyrillic е, Latin l, Cyrillic е, Latin gr, Greek α, Cyrillic М
        # Mixed Cyrillic + Greek + Latin in "skype"
        ("\u0455\u043a\u0443\u0440\u03b5", "skype"),  # Cyrillic ѕ, Cyrillic к, Cyrillic у, Cyrillic р, Greek ε
        ("\u0405\u041a\u0423\u0420\u0395", "skype"),  # Cyrillic Ѕ, Cyrillic К, Cyrillic У, Cyrillic Р, Greek Ε
        # Mixed Cyrillic + Greek + Latin in "paypal"
        ("\u0440\u03b1\u0443\u03c1\u03b1l", "paypal"),  # Cyrillic р, Greek α, Cyrillic у, Greek ρ, Greek α, Latin l
        ("\u0420\u0391\u0423\u03a1\u0391L", "paypal"),  # Cyrillic Р, Greek Α, Cyrillic У, Greek Ρ, Greek Α, Latin L
        # Mixed Cyrillic + Greek + Latin in "venmo"
        # Greek omega \u03c9 visual lookalike for Latin 'w'
        ("\u03c9hatsapp", "whatsapp"),
        ("\u03c9echat", "wechat"),
        # Mixed Cyrillic + Greek + Latin in "cashapp"
        ("\u0441\u03b1\u0455h\u03b1\u0440\u0440", "cashapp"),  # Cyrillic с, Greek α, Cyrillic ѕ, Latin h, Greek α, Cyrillic р, Cyrillic р
        # Mathematical Bold/Italic/Sans/Script alphanumeric
        ("𝒘𝒉𝒂𝒕𝒔𝒂𝒑𝒑", "whatsapp"),
        ("𝕥𝕖𝕝𝕖𝕘𝕣𝕒𝕞", "telegram"),
        ("𝓈𝓀𝓎𝓅𝑒", "skype"),
        ("𝕡𝕒𝕪𝕡𝕒𝕝", "paypal"),
        ("𝓿𝓮𝓷𝓶𝓸", "venmo"),
        ("𝓬𝓪𝓼𝓱𝓪𝓹𝓹", "cashapp"),
    ])
    def test_novel_mixed_homoglyphs(self, payload, expected_detection):
        findings = detect_off_platform_contact(payload)
        assert expected_detection in findings, (
            f"Adversarial mixed homoglyph payload '{payload}' bypassed detection! Findings: {findings}"
        )


class TestMultiLayerSeparatorTricks:
    """Stress tests multi-layer and compound separator tricks."""

    @pytest.mark.parametrize("payload,expected_detection", [
        # Repeated dots, dashes, tildes, stars
        ("0 8 2 . . . 5 5 5 - - - 1 2 3 4", "phone"),
        ("082 . . . 555 . . . 1234", "phone"),
        ("082 - - - 555 - - - 1234", "phone"),
        ("082 * * * 555 * * * 1234", "phone"),
        ("082 ~ ~ ~ 555 ~ ~ ~ 1234", "phone"),
        ("0 8 2     5 5 5     1 2 3 4", "phone"),
        ("0 8 2 . . 5 5 5 - - 1 2 3 4", "phone"),
        ("+27 (0) 82   555   1234", "phone"),
        ("+27 . 82 . 555 . 1234", "phone"),
        ("+27-82-555-1234", "phone"),
        ("w...h...a...t...s...a...p...p", "whatsapp"),
        ("w---h---a---t---s---a---p---p", "whatsapp"),
        ("w~~~h~~~a~~~t~~~s~~~a~~~p~~~p", "whatsapp"),
        ("w***h***a***t***s***a***p***p", "whatsapp"),
        ("w . . . h . . . a . . . t . . . s . . . a . . . p . . . p", "whatsapp"),
        ("t . . . e . . . l . . . e . . . g . . . r . . . a . . . m", "telegram"),
        ("s . . . k . . . y . . . p . . . e", "skype"),
        ("p . . . a . . . y . . . p . . . a . . . l", "paypal"),
    ])
    def test_multi_layer_separators(self, payload, expected_detection):
        findings = detect_off_platform_contact(payload)
        assert expected_detection in findings, (
            f"Multi-layer separator payload '{payload}' bypassed detection! Findings: {findings}"
        )


class TestEmailEvasionTricks:
    """Stress tests email evasions with spaces, brackets, bare-at, dotted-at."""

    @pytest.mark.parametrize("payload", [
        "tutor @ gmail.com",
        "tutor@ gmail.com",
        "tutor @gmail.com",
        "tutor @ gmail . com",
        "tutor at gmail.com",
        "tutor AT gmail.com",
        "tutor at gmail dot com",
        "tutor [at] gmail [dot] com",
        "tutor (at) gmail (dot) com",
        "tutor {at} gmail {dot} com",
        "tutor [@] gmail [.] com",
        "t.u.t.o.r @ g.m.a.i.l . c.o.m",
        "t u t o r @ g m a i l . c o m",
        "t...u...t...o...r @ g...m...a...i...l . c...o...m",
        "teacher at sharononline.co.za",
        "contact at yahoo.com",
        "teacher at outlook.com",
    ])
    def test_email_evasions(self, payload):
        findings = detect_off_platform_contact(payload)
        assert "email" in findings, (
            f"Email evasion payload '{payload}' bypassed detection! Findings: {findings}"
        )


class TestSpelledAndMixedNumbers:
    """Stress tests phone numbers concealed via spelled out words and mixed separators."""

    @pytest.mark.parametrize("payload", [
        "zero eight two five five five one two three four",
        "zero-eight-two-five-five-five-one-two-three-four",
        "zero . eight . two . five . five . five . one . two . three . four",
        "zero...eight...two...five...five...five...one...two...three...four",
        "zero eight two double five five one two three four",
        "zero eight two triple five one two three four",
        "0 eight 2 5 five 5 1 2 3 four",
        "0-eight-2-5-five-5-1-2-3-four",
        "o...n...e e...i...g...h...t t...w...o f...i...v...e f...i...v...e f...i...v...e o...n...e t...w...o t...h...r...e...e f...o...u...r",
    ])
    def test_spelled_numbers_phone_evasion(self, payload):
        findings = detect_off_platform_contact(payload)
        assert "phone" in findings, (
            f"Spelled number phone payload '{payload}' bypassed detection! Findings: {findings}"
        )


class TestHistoricalDateProseNoFalsePositives:
    """Stress tests complex historical paragraphs with pre-1800 years in varied structures."""

    @pytest.mark.parametrize("text,description", [
        (
            "In 1066 the Normans invaded England. By 1215 the barons forced King John to grant Magna Carta. "
            "Later in 1492 Columbus arrived in the Americas, and in 1776 the American colonies declared independence.",
            "Multi-sentence historical narrative with 1066, 1215, 1492, 1776"
        ),
        (
            "Major milestones: 1066, 1215, 1492, 1776, and 1865.",
            "Comma-separated list of milestone years"
        ),
        (
            "We study four eras: 1066-1215, 1337-1453, 1517-1648, and 1776-1789.",
            "Multiple hyphenated date ranges in one sentence"
        ),
        (
            "Between 1066 and 1215, feudal England transformed. From 1492 through 1776, transatlantic trade expanded.",
            "Historical ranges with 'Between X and Y' and 'From X through Y'"
        ),
        (
            "Key battle dates: 1066-10-14 at Hastings, 1215-06-15 at Runnymede, and 1776-07-04 in Philadelphia.",
            "ISO historical dates"
        ),
        (
            "Historical timeline: 1066 / 1215 / 1492 / 1776 / 1914 / 1945.",
            "Slash-separated chronological timeline"
        ),
        (
            "The period spanning 1066 to 1215 was critical, as was 1492 to 1776.",
            "Ranges using 'to'"
        ),
        (
            "In the year 1066 William the Conqueror won. In 1215 the charter was signed. In 1492 a new era began.",
            "Separate sentences each starting with year"
        ),
    ])
    def test_historical_date_paragraphs_pass(self, text, description):
        findings = detect_off_platform_contact(text)
        assert findings == [], (
            f"FALSE POSITIVE: Historical narrative '{text}' ({description}) blocked with findings: {findings}"
        )


class TestSyllabusListsAndCounterAttacks:
    """Stress tests legitimate syllabus listings and ensures pseudo-syllabus phone attacks ARE blocked."""

    @pytest.mark.parametrize("legitimate_text,description", [
        ("Chapters: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8", "Chapter listing with dash separators"),
        ("Units: 1, 2, 3, 4, 5, 6, 7, 8, 9", "Units listing with commas"),
        ("Lessons 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8 - 9 - 10", "Lesson range ascending 1 to 10"),
        ("Exercises: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8", "Exercises list"),
        ("Questions: 1, 2, 3, 4, 5, 6, 7, 8", "Questions list"),
        ("Sections: 1 - 2 - 3 - 4 - 5 - 6", "Sections list"),
        ("Grades: 1, 2, 3, 4, 5, 6, 7, 8, 9", "Grades list"),
        ("Counting chart: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8 - 9 - 10", "Counting chart ascending"),
        ("Counting chart: 10 - 9 - 8 - 7 - 6 - 5 - 4 - 3 - 2 - 1 - 0", "Counting chart descending"),
        ("Scores: 1 / 2 / 3 / 4 / 5 / 6 / 7 / 8", "Scores listing with slashes"),
        ("Parts: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8", "Parts listing"),
        ("Modules: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8", "Modules listing"),
        ("Tracks: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8", "Tracks listing"),
        ("Tasks: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8", "Tasks listing"),
        ("Items: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8", "Items listing"),
    ])
    def test_legitimate_syllabus_allowed(self, legitimate_text, description):
        findings = detect_off_platform_contact(legitimate_text)
        assert findings == [], (
            f"FALSE POSITIVE: Legitimate syllabus '{legitimate_text}' ({description}) blocked with findings: {findings}"
        )

    @pytest.mark.parametrize("attack_payload,attack_desc", [
        # Disguising a phone number behind a syllabus keyword
        ("Chapters: 082-555-1234", "Phone disguised as chapters with dashes"),
        ("Chapters: 082 555 1234", "Phone disguised as chapters with spaces"),
        ("Units: 082.555.1234", "Phone disguised as units with dots"),
        ("Lessons: +27 82 555 1234", "E164 phone disguised as lessons"),
        ("Exercises: 0 8 2 5 5 5 1 2 3 4", "Non-monotonic single digits disguised as exercises"),
        ("Questions: 0825551234", "Contiguous phone disguised as questions"),
        ("Modules: 083-491-9922", "Phone disguised as modules"),
        ("Chapters: 9 - 3 - 8 - 1 - 5 - 2 - 4 - 7", "Non-monotonic random sequence disguised as chapters"),
    ])
    def test_pseudo_syllabus_phone_attacks_blocked(self, attack_payload, attack_desc):
        """Attacker attempts to evade phone detection by prefixing 'Chapters:' or 'Units:'."""
        findings = detect_off_platform_contact(attack_payload)
        assert "phone" in findings, (
            f"FALSE NEGATIVE: Attacker payload '{attack_payload}' ({attack_desc}) bypassed detection! Got: {findings}"
        )


class TestLegitimateEducationalProseNoFalsePositives:
    """Stress tests conversational expressions, math, currency, time ranges, and pedagogy."""

    @pytest.mark.parametrize("text,description", [
        ("The class starts at 09:00 and finishes at 10:30 am.", "Class time specification"),
        ("Please meet me at the library at 3 pm.", "Preposition 'at' in normal sentence"),
        ("Make sure to put a dot at the end of each sentence.", "Word 'dot' in English writing lesson"),
        ("We will zoom in on the irregular verbs during today's reading.", "Conversational verb 'zoom in'"),
        ("Line up your arguments before writing the essay.", "Conversational phrase 'line up'"),
        ("Pay attention and do not slack off.", "Conversational verb 'pay'"),
        ("The course fee is $1,500 or R25,000 for the full semester.", "Currency format"),
        ("Over 10,000,000 students have taken this exam worldwide.", "Large formatted number"),
        ("Please refer to pages 120-135 in the Oxford English Grammar.", "Page range"),
        ("Review questions 1 through 5 on page 42.", "Question range with 'through'"),
        ("The Roman Empire reached its peak around 117 AD.", "Historical year"),
        ("From 1939 to 1945 the world experienced major conflict.", "20th century date range"),
    ])
    def test_educational_expressions_allowed(self, text, description):
        findings = detect_off_platform_contact(text)
        assert findings == [], (
            f"FALSE POSITIVE: Educational prose '{text}' ({description}) blocked with findings: {findings}"
        )


class TestValidatorContractIntegration:
    """Stress tests validate_no_off_platform_contact directly."""

    def test_validator_raises_validation_error_with_clean_detail(self):
        with pytest.raises(ValidationError) as exc:
            validate_no_off_platform_contact("Reach me on w...h...a...t...s...a...p...p at 082-555-1234")
        msg = str(exc.value)
        assert "Off-platform contact or payment details are not permitted" in msg
        assert "phone" in msg
        assert "whatsapp" in msg

    def test_validator_returns_original_string_on_clean_prose(self):
        clean = "The Norman Conquest of 1066 transformed the English language forever. Chapters: 1 - 2 - 3 - 4."
        result = validate_no_off_platform_contact(clean)
        assert result == clean

    def test_validator_handles_empty_and_non_string_safely(self):
        assert validate_no_off_platform_contact("") == ""
        assert validate_no_off_platform_contact(None) is None
