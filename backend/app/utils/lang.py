"""Language detection utilities with deterministic seeding and safe fallbacks."""

from langdetect import DetectorFactory, detect  # type: ignore[import-untyped]
from langdetect.lang_detect_exception import LangDetectException  # type: ignore[import-untyped]

# Seed langdetect for deterministic evaluation across calls and runs
DetectorFactory.seed = 0

# Mapping of common short tokens to standard ISO 639-1 language codes
SHORT_TOKEN_LANG_MAP: dict[str, str] = {
    "hi": "en",
    "hello": "en",
    "hey": "en",
    "yes": "en",
    "no": "en",
    "ok": "en",
    "okay": "en",
    "thanks": "en",
    "bye": "en",
    "namaste": "hi",
    "shukriya": "hi",
    "vanakkam": "ta",
    "nandri": "ta",
}


def detect_language(text: str | None, default: str = "en") -> str:
    """Detect the language of the provided text safely.

    Handles very short inputs, numbers, and symbols without raising exceptions.
    Returns standard ISO 639-1 code (e.g. 'en', 'hi', 'ta').
    """
    if not text:
        return default

    clean_text = text.strip()
    if not clean_text:
        return default

    # Fast-path for single words or very short expressions
    lowered = clean_text.lower()
    if lowered in SHORT_TOKEN_LANG_MAP:
        return SHORT_TOKEN_LANG_MAP[lowered]

    # If text is purely digits or punctuation, default safely
    if not any(char.isalpha() for char in clean_text):
        return default

    try:
        lang = detect(clean_text)
        return str(lang)
    except (LangDetectException, Exception):
        return default
