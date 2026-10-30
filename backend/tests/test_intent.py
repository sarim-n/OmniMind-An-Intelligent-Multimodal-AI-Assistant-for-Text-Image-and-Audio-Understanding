"""Unit tests for multimodal intent classification."""

from app.services.intent import classify_intent


def test_classify_generate_report() -> None:
    """Verify report generation intent detection."""
    assert classify_intent("Please generate a report about Q3 findings") == "generate_report"
    assert classify_intent("Export report to PDF") == "generate_report"
    assert classify_intent("Create a report on the meeting") == "generate_report"


def test_classify_search() -> None:
    """Verify search intent detection."""
    assert classify_intent("Search for invoices in documents") == "search"
    assert classify_intent("Find relevant documents regarding tax") == "search"
    assert classify_intent("Look up in files") == "search"


def test_classify_compare_image_and_audio() -> None:
    """Verify cross-modal comparison intent."""
    assert (
        classify_intent(
            "Does what the speaker says match the chart?",
            has_image=True,
            has_audio=True,
        )
        == "compare_image_and_audio"
    )
    assert (
        classify_intent(
            "Compare the audio with the diagram",
            has_image=True,
            has_audio=True,
        )
        == "compare_image_and_audio"
    )
    # Empty query with both image and audio attached
    assert (
        classify_intent(
            "",
            has_image=True,
            has_audio=True,
        )
        == "compare_image_and_audio"
    )


def test_classify_qa_about_image() -> None:
    """Verify visual QA intent."""
    assert classify_intent("What colour is the second car?", has_image=True) == "qa_about_image"
    assert classify_intent("How many people are in this image?", has_image=True) == "qa_about_image"
    # Image follow-up turn without re-uploading
    assert (
        classify_intent("What colour was the second car?", has_prior_image=True) == "qa_about_image"
    )


def test_classify_summarise_audio() -> None:
    """Verify audio summary intent."""
    assert classify_intent("Please summarize the meeting", has_audio=True) == "summarise_audio"
    assert (
        classify_intent("What did they say about the budget?", has_audio=True) == "summarise_audio"
    )
    # Audio follow-up turn without re-uploading
    assert (
        classify_intent("What did he say about the budget?", has_prior_audio=True)
        == "summarise_audio"
    )


def test_classify_general_chat() -> None:
    """Verify general conversation fallback."""
    assert classify_intent("Hello, how are you today?") == "general_chat"
    assert classify_intent("Tell me a funny joke about programming") == "general_chat"
