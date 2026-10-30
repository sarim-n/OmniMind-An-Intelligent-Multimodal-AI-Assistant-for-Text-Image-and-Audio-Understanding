"""Unit tests for language detection utility."""

from app.utils.lang import detect_language


def test_detect_language_english() -> None:
    text = "Hello world, how are you doing today?"
    lang = detect_language(text)
    assert lang == "en"


def test_detect_language_short_greetings() -> None:
    assert detect_language("hi") == "en"
    assert detect_language("hello") == "en"
    assert detect_language("namaste") == "hi"
    assert detect_language("vanakkam") == "ta"


def test_detect_language_hindi() -> None:
    # Hindi script text
    text = "नमस्ते, आप कैसे हैं? मुझे मदद चाहिए।"
    lang = detect_language(text)
    assert lang == "hi"


def test_detect_language_tamil() -> None:
    # Tamil script text
    text = "வணக்கம், நீங்கள் எப்படி இருக்கிறீர்கள்?"
    lang = detect_language(text)
    assert lang == "ta"


def test_detect_language_empty_and_symbols() -> None:
    assert detect_language("") == "en"
    assert detect_language(None) == "en"
    assert detect_language("12345 !@#$%") == "en"
    assert detect_language("   ", default="hi") == "hi"
