"""
backend/apps/common/contact_guard.py

Anti-Disintermediation & Contact-Leakage Sanitization Pipeline for Sharon Online.
Prevents platform fee leakage by detecting emails, phone numbers, and external messaging/payment handles,
while preserving legitimate ESL educational language expressions, dates, and curriculum references.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple
from rest_framework import serializers


# =====================================================================
# 1. NORMALIZATION REGEXES & LOOKUPS
# =====================================================================

# Includes zero-width chars, directional markers, soft hyphens, BOM, and Unicode Variation Selectors
INVISIBLE_CHARS_RE = re.compile(
    r'[\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF\u00AD\uFE00-\uFE0F\U000E0100-\U000E01EF]'
)

# Comprehensive homoglyph transliteration table covering Cyrillic and Greek lookalikes
HOMOGLYPH_LOOKALIKES = str.maketrans({
    # Cyrillic lowercase
    '\u0430': 'a', '\u0435': 'e', '\u043e': 'o', '\u0440': 'p', '\u0441': 'c',
    '\u0443': 'y', '\u0445': 'x', '\u0456': 'i', '\u0458': 'j', '\u0455': 's',
    '\u043a': 'k', '\u043c': 'm', '\u043d': 'h', '\u0442': 't', '\u0432': 'b',
    # Cyrillic uppercase
    '\u0410': 'A', '\u0415': 'E', '\u041e': 'O', '\u0420': 'P', '\u0421': 'C',
    '\u0423': 'Y', '\u0425': 'X', '\u0406': 'I', '\u0408': 'J', '\u0405': 'S',
    '\u041a': 'K', '\u041c': 'M', '\u041d': 'H', '\u0422': 'T', '\u0412': 'B',
    # Greek lowercase
    '\u03b1': 'a', '\u03b2': 'b', '\u03b5': 'e', '\u03b7': 'n', '\u03b9': 'i',
    '\u03ba': 'k', '\u03bd': 'v', '\u03bf': 'o', '\u03c1': 'p', '\u03c4': 't',
    '\u03c5': 'u', '\u03c7': 'x', '\u03c9': 'w',
    # Greek uppercase
    '\u0391': 'A', '\u0392': 'B', '\u0395': 'E', '\u0396': 'Z', '\u0397': 'H',
    '\u0399': 'I', '\u039a': 'K', '\u039c': 'M', '\u039d': 'N', '\u039f': 'O',
    '\u03a1': 'P', '\u03a4': 'T', '\u03a5': 'Y', '\u03a7': 'X', '\u03a9': 'W',
})

# Backward compatibility alias
CYRILLIC_LOOKALIKES = HOMOGLYPH_LOOKALIKES

NUMBER_WORDS = {
    'zero': '0', 'oh': '0', 'nil': '0',
    'one': '1', 'two': '2', 'three': '3',
    'four': '4', 'five': '5', 'six': '6',
    'seven': '7', 'eight': '8', 'nine': '9',
}

NUMBER_WORDS_RE = re.compile(
    r'(?<![a-zA-Z])(?:' + '|'.join(NUMBER_WORDS.keys()) + r')(?![a-zA-Z])',
    re.IGNORECASE
)

AT_HOMOGLYPHS_RE = re.compile(
    r'\s*(?:\[at\]|\(at\)|\{at\}|<at>|/at/|\\at\\|\[@\]|\(@\)|\{@\}|\*at\*)\s*',
    re.IGNORECASE
)

DOT_HOMOGLYPHS_RE = re.compile(
    r'\s*(?:\[dot\]|\(dot\)|\{dot\}|<dot>|/dot/|\\dot\\|\[\.\]|\(\.\)|\{\.\}|\*dot\*)\s*',
    re.IGNORECASE
)

SPACED_EMAIL_RE = re.compile(
    r'(\b[A-Za-z0-9._%+-]+)\s+(?:at|AT)\s+([A-Za-z0-9-]+)\s+(?:dot|DOT)\s+([A-Za-z]{2,}\b)',
    re.IGNORECASE
)

# Detects emails with bare 'at' followed by recognized email TLDs (e.g. tutor at gmail.com)
BARE_AT_EMAIL_RE = re.compile(
    r'\b([A-Za-z0-9._%+-]+)\s+(?:at|AT)\s+([A-Za-z0-9-]+)\s*(?:\.|\b(?:dot|DOT)\b)\s*(com|org|net|edu|gov|io|co|me|ai|app|dev|co\.za)\b',
    re.IGNORECASE
)

# Punctuation-delimited single letters (collapses w...h...a...t...s...a...p...p or w . . . h -> whatsapp without merging inter-word spaces)
PUNCT_LETTER_SEP_RE = re.compile(r'\b[a-zA-Z](?:\s*[._\-*/~][\s._\-*/~]*[a-zA-Z]){2,}\b')
# Pure space-delimited single letters (collapses w   h   a   t   s   a   p   p -> whatsapp)
SPACE_LETTER_SEP_RE = re.compile(r'\b[a-zA-Z](?:\s+[a-zA-Z]){2,}\b')
SINGLE_LETTER_SEPARATOR_RE = PUNCT_LETTER_SEP_RE
SINGLE_DIGIT_SEPARATOR_RE = re.compile(r'(?<!\d)\d(?:[\s\-_.]+\d){3,}(?!\d)')


def convert_number_words(text: str) -> str:
    """Converts whole-word English number words and multipliers to digits while respecting boundaries."""
    if not text:
        return ""
    t = NUMBER_WORDS_RE.sub(lambda m: NUMBER_WORDS[m.group(0).lower()], text)
    t = re.sub(r'\bdouble\s+(\d)\b', r'\1 \1', t, flags=re.IGNORECASE)
    t = re.sub(r'\btriple\s+(\d)\b', r'\1 \1 \1', t, flags=re.IGNORECASE)
    return t


def collapse_single_character_separators(text: str) -> str:
    """Collapses spaced or punctuation-delimited single letters and digits."""
    if not text:
        return ""
    t = PUNCT_LETTER_SEP_RE.sub(lambda m: re.sub(r'[\s._\-*/~]+', '', m.group(0)), text)
    t = SPACE_LETTER_SEP_RE.sub(lambda m: re.sub(r'\s+', '', m.group(0)), t)
    t = SINGLE_DIGIT_SEPARATOR_RE.sub(lambda m: re.sub(r'[\s\-_.]+', '', m.group(0)), t)
    return t


def normalize_text(text: str) -> str:
    """Applies canonical multi-stage normalization pipeline to uncover obfuscated contact patterns."""
    if not text or not isinstance(text, str):
        return ''

    # 1. Unicode NFKC normalization (fullwidth latin and digits)
    t = unicodedata.normalize('NFKC', text)

    # 2. Strip zero-width, invisible, variation selectors and directional control characters
    t = INVISIBLE_CHARS_RE.sub('', t)

    # 3. Transliterate Cyrillic and Greek visual lookalikes
    t = t.translate(HOMOGLYPH_LOOKALIKES)

    # 4. Collapse single-character letter separator tricks
    t = PUNCT_LETTER_SEP_RE.sub(lambda m: re.sub(r'[\s._\-*/~]+', '', m.group(0)), t)
    t = SPACE_LETTER_SEP_RE.sub(lambda m: re.sub(r'\s+', '', m.group(0)), t)

    # 5. Normalize homoglyphs for 'at' and 'dot'
    t = AT_HOMOGLYPHS_RE.sub('@', t)
    t = DOT_HOMOGLYPHS_RE.sub('.', t)
    t = SPACED_EMAIL_RE.sub(r'\1@\2.\3', t)
    t = BARE_AT_EMAIL_RE.sub(r'\1@\2.\3', t)

    # 6. Normalize whitespace surrounding literal '@'
    t = re.sub(r'\s*@\s*', '@', t)

    # 7. Normalize spaces surrounding email domain dot (e.g. tutor@gmail . com -> tutor@gmail.com)
    t = re.sub(r'(@[A-Za-z0-9._-]+)\s*\.\s*([A-Za-z]{2,})\b', r'\1.\2', t)

    # 8. Restore domain boundary dot if single-letter collapsing merged domain + TLD (e.g. tutor@gmailcom -> tutor@gmail.com)
    t = re.sub(
        r'(@[a-zA-Z0-9_-]+?)(com|org|net|edu|gov|io|co|me|ai|app|dev)\b',
        r'\1.\2',
        t,
        flags=re.IGNORECASE
    )

    return t


# =====================================================================
# 2. EDUCATIONAL EXCEPTION MASKING
# =====================================================================

YEAR_4D = r'(?:1\d|20)\d{2}'

EDUCATIONAL_MASKS = [
    # 1. ISO and slash/dot formatted dates (1000-2099): 1066-10-14, 1995-12-31, 2024/05/12, 25/12/2024, 12-05-1998, 2024.05.12
    re.compile(rf'\b{YEAR_4D}[-/.]\d{{1,2}}[-/.]\d{{1,2}}\b'),
    re.compile(rf'\b\d{{1,2}}[-/.]\d{{1,2}}[-/.]{YEAR_4D}\b'),

    # 2. Year ranges and chained historical timelines (1000-2099):
    # Matches: 1066-1215, 1337-1453, 1517-1648, 1066/1215/1492, 1066 - 1215 - 1492 - 1588, 1995-2005, 1990 to 2000, 1939 and 1945
    re.compile(
        rf'\b{YEAR_4D}(?:\s*(?:[-–—/,]|to|through|and)\s*{YEAR_4D})+\b',
        re.IGNORECASE
    ),

    # 3. Formatted times and time ranges: 10:30-11:45, 09:00 - 17:00, 10:00 am
    re.compile(r'\b(?:[01]?\d|2[0-3]):[0-5]\d(?:\s*(?:[-–]|to)\s*(?:[01]?\d|2[0-3]):[0-5]\d)?(?:\s*(?:am|pm|AM|PM))?\b'),

    # 4. Large numbers with commas or currency: 10,000,000 or $1,000,000 or R50,000
    re.compile(r'[$€£R]?\s*\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b'),
    re.compile(r'[$€£R]\s*\d+(?:\.\d+)?\b'),

    # 5. Standalone single-digit counting drills & charts (ascending and descending 0..10):
    # Matches: 1 - 2 - 3 - 4 - 5 - 6 - 7 - 8, one - two - three - four - five - six - seven - eight - nine
    re.compile(
        r'\b(?:(?:0\s*[-–—/,]\s*)?1\s*[-–—/,]\s*2\s*[-–—/,]\s*3\s*[-–—/,]\s*4\s*[-–—/,]\s*5\s*[-–—/,]\s*6\s*[-–—/,]\s*7\s*[-–—/,]\s*8(?:\s*[-–—/,]\s*9)?(?:\s*[-–—/,]\s*10)?'
        r'|2\s*[-–—/,]\s*3\s*[-–—/,]\s*4\s*[-–—/,]\s*5\s*[-–—/,]\s*6\s*[-–—/,]\s*7\s*[-–—/,]\s*8\s*[-–—/,]\s*9(?:\s*[-–—/,]\s*10)?'
        r'|(?:10\s*[-–—/,]\s*)?9\s*[-–—/,]\s*8\s*[-–—/,]\s*7\s*[-–—/,]\s*6\s*[-–—/,]\s*5\s*[-–—/,]\s*4\s*[-–—/,]\s*3\s*[-–—/,]\s*2\s*[-–—/,]\s*1(?:\s*[-–—/,]\s*0)?'
        r'|8\s*[-–—/,]\s*7\s*[-–—/,]\s*6\s*[-–—/,]\s*5\s*[-–—/,]\s*4\s*[-–—/,]\s*3\s*[-–—/,]\s*2\s*[-–—/,]\s*1\s*[-–—/,]\s*0)\b'
    ),
]

SYLLABUS_SEQUENCE_RE = re.compile(
    r'\b(?:chapters?|pages?|p\.|pp\.|lines?|units?|lessons?|exercises?|questions?|sections?|'
    r'grades?(?:\s*\d+)?(?:\s+(?:counting\s+)?charts?)?|counting(?:\s+charts?)?|charts?|'
    r'levels?|rules?|steps?|acts?|scenes?|rooms?|scores?|marks?|points?|modules?|tracks?|parts?|'
    r'volumes?|vols?\.?|items?|tasks?|activities?|activity|stages?|series|syllabus(?:es)?|'
    r'curriculum(?:s)?|timelines?|eras?|dates?|years?|topics?|rubrics?|tests?|exams?|quizzes|quiz)\b'
    r'\s*[:#\-]?\s*(?:\d{1,4}|[a-zA-Z]+)(?:\s*(?:[-–—/]|to|,|and)\s*(?:\d{1,4}|[a-zA-Z]+))*\b(?![\s\-_./]{1,4}\d)',
    re.IGNORECASE
)

STANDALONE_YEAR_RE = re.compile(rf'\b{YEAR_4D}\b')


def mask_syllabus_sequences(text: str) -> str:
    """
    Masks curriculum, syllabus, score, and exercise sequences.
    Protects against adversarial phone evasion: if the matched sequence contains 8 or more total digits,
    it verifies that all individual numbers are small (<= 2 digits) and monotonic (strictly non-decreasing
    or non-increasing). Sequences that fail these criteria (e.g. chapters: 082-555-1234) are NOT masked.
    """
    def repl(m: re.Match) -> str:
        matched = m.group(0)
        digits = re.findall(r'\d+', matched)
        total_digits = sum(len(d) for d in digits)
        if total_digits >= 8:
            if any(len(d) > 2 for d in digits):
                return matched
            nums = [int(d) for d in digits]
            is_inc = all(nums[i] <= nums[i+1] for i in range(len(nums)-1))
            is_dec = all(nums[i] >= nums[i+1] for i in range(len(nums)-1))
            if not (is_inc or is_dec):
                return matched
        return ' '
    return SYLLABUS_SEQUENCE_RE.sub(repl, text)


def mask_standalone_years(text: str) -> str:
    """
    Masks standalone 4-digit years from 1000 to 2099 without removing phone number suffixes (e.g. 1234 or 1995).
    Inspects surrounding characters: if preceded or followed by digits across separator characters,
    the number is part of a phone or digit cluster and is left intact.
    """
    def repl(m: re.Match) -> str:
        prefix = text[:m.start()].rstrip(' \t\n\r-_./()~*–—')
        suffix = text[m.end():].lstrip(' \t\n\r-_./()~*–—')
        if (prefix and prefix[-1].isdigit()) or (suffix and suffix[0].isdigit()):
            return m.group(0)
        return ' '
    return STANDALONE_YEAR_RE.sub(repl, text)


def mask_educational_content(text: str) -> str:
    """Replaces valid educational dates, citations, and quantities with whitespace before phone scanning."""
    res = text
    for pat in EDUCATIONAL_MASKS:
        res = pat.sub(' ', res)
    res = mask_syllabus_sequences(res)
    res = mask_standalone_years(res)
    return res


# =====================================================================
# 3. DETECTION PATTERNS
# =====================================================================

EMAIL_RE = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
)

PHONE_RE = re.compile(
    r'(?:(?:\+|00)\d{1,4}[\s\-_./()]{0,3})?'
    r'(?:\(?\d{1,5}\)?[\s\-_./()]{0,3})?'
    r'(?:\d[\s\-_./()]{0,3}){6,13}\d'
)

PLATFORM_PATTERNS = {
    'whatsapp': re.compile(
        r'\bwa\s*\.\s*me/\S+|\bwhats[\s\-_.]*app\b|\bwhatsapp\b|\bapi\.whatsapp\.com/\S+',
        re.IGNORECASE
    ),
    'telegram': re.compile(
        r'\bt\s*\.\s*me\s*/\s*\S+|\btele[\s\-_.]*gram(?:\.me)?\b|\btelegram\b',
        re.IGNORECASE
    ),
    'wechat': re.compile(
        r'\bwe[\s\-_.]*chat\b|\bwechat\b|\bweixin\b|\bwxid_[a-zA-Z0-9_-]+',
        re.IGNORECASE
    ),
    'line': re.compile(
        r'(?:https?://)?(?:www\.)?line\s*\.\s*me/\S+'
        r'|\bline\s*(?:id|app)?\s*[:@=]\s*[a-zA-Z0-9._-]+\b'
        r'|\b(?:add|find|message|contact)\s+me\s+on\s+line\b'
        r'|\bmy\s+line\s+is\b'
        r'|\bline\s+id\b'
        r'|\bline\s+app\b',
        re.IGNORECASE
    ),
    'kakaotalk': re.compile(
        r'\bkakao(?:\s*talk)?\b|(?:open\s*\.\s*)?kakao\s*\.\s*com/\S+',
        re.IGNORECASE
    ),
    'skype': re.compile(
        r'\bskype\b|\bjoin\s*\.\s*skype\s*\.\s*com/\S+|\blive:\.cid\.[a-zA-Z0-9_-]+|\blive:[a-zA-Z0-9_.-]+',
        re.IGNORECASE
    ),
    'paypal': re.compile(
        r'\bpay[\s\-_.]*pal(?:\.me)?\b|\bpaypal\s*\.\s*me/\S+',
        re.IGNORECASE
    ),
    'venmo': re.compile(
        r'\bvenmo(?:\.com)?\b|\bvenmo[:\s]+@?[a-zA-Z0-9_.-]+',
        re.IGNORECASE
    ),
    'cashapp': re.compile(
        r'\bcash\s*\.\s*app/\S*|\bcash[\s\-_.]*app\b|\$[a-zA-Z][a-zA-Z0-9_]{1,19}\b',
        re.IGNORECASE
    ),
    'zoom': re.compile(
        r'\bzoom\s*\.\s*us\b|\b(?:https?://)?(?:[a-zA-Z0-9-]+\.)?zoom\s*\.\s*us/\S+'
        r'|\bzoom\s+(?:meeting|id|link|passcode|code|room)\b'
        r'|\bjoin\s+(?:my\s+)?zoom\b',
        re.IGNORECASE
    ),
    'google_meet': re.compile(
        r'\bmeet\s*\.\s*google\s*\.\s*com\b|\b(?:https?://)?meet\s*\.\s*google\s*\.\s*com/\S+'
        r'|\bgoogle\s+meet\b|\bg-meet\b|\bgmeet\b',
        re.IGNORECASE
    ),
}


# =====================================================================
# 4. PUBLIC API CONTRACT
# =====================================================================

def detect_off_platform_contact(text: str) -> List[str]:
    """
    Scans text for contact leakage or off-platform communication handles.

    Returns:
        List[str]: Detected violation types (e.g. ['email', 'whatsapp', 'phone']),
                   or empty list [] if text is clean.
    """
    if not text or not isinstance(text, str):
        return []

    # 1. Multi-stage canonical normalization
    norm = normalize_text(text)
    findings: List[str] = []

    # 2. Email detection
    if EMAIL_RE.search(norm):
        findings.append('email')

    # 3. Off-platform messaging & payment handles
    for name, pat in PLATFORM_PATTERNS.items():
        if pat.search(norm):
            findings.append(name)

    # 4. Phone number detection (with educational exception masking and number word conversion)
    # Convert number words and multipliers to digits
    phone_scan_text = convert_number_words(norm)
    # Mask educational content (dates, citations, times, large numbers)
    masked_norm = mask_educational_content(phone_scan_text)

    # Collapse repeated whitespace and separator punctuation in candidate phone string
    sanitized_phone_text = re.sub(r'[\s._\-~*]*[._\-~*][\s._\-~*]*', '-', masked_norm)
    sanitized_phone_text = re.sub(r'\s+', ' ', sanitized_phone_text)

    for match in PHONE_RE.finditer(sanitized_phone_text):
        digits = re.sub(r'\D', '', match.group(0))
        # Skip pure arithmetic counting sequences (e.g. 12345678, 123456789)
        if digits in '0123456789012345' or digits in '987654321098765':
            continue
        if 8 <= len(digits) <= 15:
            findings.append('phone')
            break

    return findings


def validate_no_off_platform_contact(value: str) -> str:
    """
    DRF field validator: raises serializers.ValidationError if contact leakage is detected.

    Returns:
        str: Original value if clean.
    """
    if not value or not isinstance(value, str):
        return value
    violations = detect_off_platform_contact(value)
    if violations:
        violation_str = ', '.join(sorted(set(violations)))
        raise serializers.ValidationError(
            f"Off-platform contact or payment details are not permitted ({violation_str} detected).",
            code='contact_leakage'
        )
    return value


# Compatibility Aliases
validate_no_contact_leakage = validate_no_off_platform_contact


def scan_text_for_contact_leakage(text: str) -> Tuple[bool, List[str]]:
    """Compatibility helper returning (has_leakage, violations_list)."""
    violations = detect_off_platform_contact(text)
    return (len(violations) > 0, violations)
