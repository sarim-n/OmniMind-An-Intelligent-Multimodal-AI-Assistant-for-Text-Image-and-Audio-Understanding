"""Comprehensive tests for structured report generation, PDF export, multilingual rendering,
error resilience, API endpoints, user isolation, and orchestrator integration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pypdf
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.image_analysis import ImageAnalysis
from app.models.message import Message
from app.models.report import Report
from app.models.transcript import Transcript
from app.models.user import User
from app.schemas.report import ReportOptions, ReportSchema, ReportSection
from app.services.pdf_service import get_pdf_service
from app.services.report_service import get_report_service


@pytest.fixture
def auth_headers(db: Session) -> dict[str, str]:
    """Create test user A and return authorization headers."""
    user = User(email="analyst_alice@omnimind.com", hashed_password="hashed_pwd_alice")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_user_b(db: Session) -> dict[str, str]:
    """Create test user B and return authorization headers."""
    user = User(email="intruder_bob@omnimind.com", hashed_password="hashed_pwd_bob")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def multimodal_conversation(db: Session, auth_headers: dict[str, str]) -> tuple[Conversation, User]:
    """Populate a complete multimodal conversation with audio, image, and messages."""
    user = db.query(User).filter(User.email == "analyst_alice@omnimind.com").first()
    assert user is not None

    conv = Conversation(
        user_id=user.id,
        title="Quarterly Operations & Facility Security Review",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)

    msg = Message(
        conversation_id=conv.id,
        role="user",
        content="Review facility surveillance capture and team meeting audio.",
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Audio Attachment & Transcript
    audio_att = Attachment(
        user_id=user.id,
        message_id=msg.id,
        type="audio",
        path="audio/quarterly_sync.wav",
        mime="audio/wav",
        size=8192,
        duration_sec=140.0,
        metadata_={"original_filename": "quarterly_sync.wav"},
    )
    db.add(audio_att)
    db.commit()
    db.refresh(audio_att)

    transcript = Transcript(
        attachment_id=audio_att.id,
        language="en",
        text="Director: We agreed to implement enhanced badge verification by October 15th.",
        insights={
            "executive_summary": "Quarterly operational sync focused on facility security and budget.",
            "inferred_agenda": ["Facility access security", "Budget ratification"],
            "decisions": ["Approved badge verification upgrades"],
            "action_items": [
                {
                    "owner": "Security Lead",
                    "task": "Deploy upgraded badge scanners",
                    "deadline": "Oct 15",
                    "source_timestamp": "01:15",
                }
            ],
            "per_topic_timeline": [
                {
                    "topic": "Security Standards",
                    "start": 0.0,
                    "end": 70.0,
                    "summary": "Review of access protocols.",
                },
                {
                    "topic": "Action Planning",
                    "start": 70.0,
                    "end": 140.0,
                    "summary": "Vendor delivery deadlines.",
                },
            ],
        },
    )
    db.add(transcript)

    # Image Attachment & Image Analysis
    img_att = Attachment(
        user_id=user.id,
        message_id=msg.id,
        type="image",
        path="images/entrance_gate.jpg",
        mime="image/jpeg",
        size=16384,
        metadata_={"original_filename": "entrance_gate.jpg"},
    )
    db.add(img_att)
    db.commit()
    db.refresh(img_att)

    analysis = ImageAnalysis(
        attachment_id=img_att.id,
        caption="Security entrance gate with RFID readers and biometric scanners.",
        ocr_text="GATE 4 - RESTRICTED ENTRY ONLY",
        objects=[
            {"label": "turnstile", "confidence": 0.94, "box_2d": [100, 150, 400, 300]},
            {"label": "security camera", "confidence": 0.88, "box_2d": [50, 400, 120, 480]},
        ],
        metadata_={"warnings": ["Slight lens glare near top border"]},
    )
    db.add(analysis)
    db.commit()

    return conv, user


def test_report_generation_from_multimodal_conversation_and_fact_tables(
    db: Session, multimodal_conversation: tuple[Conversation, User]
) -> None:
    """Verify that a multimodal conversation produces a valid ReportSchema and fact tables match DB rows."""
    conv, user = multimodal_conversation
    report_svc = get_report_service()

    report = report_svc.generate(
        conversation_id=conv.id,
        user_id=user.id,
        options=ReportOptions(length="standard", include_images=True, include_metrics=True),
        db=db,
    )

    assert isinstance(report, Report)
    assert report.id is not None
    assert report.conversation_id == conv.id

    # 1. Validate Pydantic Schema
    schema = ReportSchema(**report.content)
    assert schema.title.startswith("OmniMind Intelligence Report:")
    assert len(schema.executive_summary) > 0
    assert len(schema.sections) >= 2
    assert len(schema.conclusions) > 0
    assert len(schema.recommendations) > 0

    # 2. Assert factual tables match database rows exactly (no hallucination)
    assert len(schema.audio_findings) == 1
    audio = schema.audio_findings[0]
    assert audio.file == "quarterly_sync.wav"
    assert audio.duration == 140.0
    assert len(audio.action_items) == 1
    assert audio.action_items[0]["owner"] == "Security Lead"
    assert audio.action_items[0]["task"] == "Deploy upgraded badge scanners"
    assert audio.decisions == ["Approved badge verification upgrades"]
    assert len(audio.timeline) == 2

    assert len(schema.image_findings) == 1
    img = schema.image_findings[0]
    assert img.file == "entrance_gate.jpg"
    assert "RFID readers" in img.caption
    assert img.extracted_text == "GATE 4 - RESTRICTED ENTRY ONLY"
    assert len(img.objects) == 2
    assert img.objects[0]["label"] == "turnstile"
    assert img.quality_warnings == ["Slight lens glare near top border"]

    # 3. Assert appendix models and metrics match active configurations
    assert schema.appendix.models_used == settings.active_models
    assert schema.appendix.processing_metrics["total_audio_assets"] == 1
    assert schema.appendix.processing_metrics["total_image_assets"] == 1


def test_pdf_export_multipage_pypdf_validation(
    db: Session, multimodal_conversation: tuple[Conversation, User]
) -> None:
    """Verify that the generated PDF opens with pypdf, contains multiple pages, and renders expected text."""
    conv, user = multimodal_conversation
    report_svc = get_report_service()

    report = report_svc.generate(
        conversation_id=conv.id,
        user_id=user.id,
        options=ReportOptions(length="standard"),
        db=db,
    )

    assert report.pdf_path is not None
    pdf_path = Path(report.pdf_path)
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 1000

    # Inspect PDF with pypdf
    reader = pypdf.PdfReader(str(pdf_path))
    num_pages = len(reader.pages)
    assert num_pages > 1, f"Expected multi-page PDF, but got {num_pages} page(s)"

    # Validate Cover Page and Interior Pages
    page_0_text = reader.pages[0].extract_text()
    assert "OMNIMIND MULTIMODAL ASSISTANT" in page_0_text
    assert conv.title in page_0_text or "Quarterly Operations" in page_0_text

    page_1_text = reader.pages[1].extract_text()
    assert "Table of Contents" in page_1_text or "Executive Summary" in page_1_text


def test_multilingual_pdf_build_hindi_and_tamil(tmp_path: Path) -> None:
    """Verify that Hindi (Devanagari) and Tamil reports compile into valid multi-page PDFs without errors."""
    pdf_svc = get_pdf_service()

    # Hindi Report
    hindi_schema = ReportSchema(
        title="सुरक्षा और परिचालन समीक्षा रिपोर्ट",
        language="hi",
        executive_summary="यह एक व्यापक बहुविध विश्लेषण रिपोर्ट है। इसमें ऑडियो और दृश्य साक्ष्य शामिल हैं।",
        sections=[
            ReportSection(
                heading="परिचालन विश्लेषण",
                body="सभी सुरक्षा प्रोटोकॉल की सावधानीपूर्वक समीक्षा की गई।",
                bullet_points=["प्रवेश द्वार सत्यापन पूर्ण", "निगरानी कैमरे सक्रिय"],
            )
        ],
        conclusions=["योजना का क्रियान्वयन समय पर पूरा होगा।"],
        recommendations=["नियमित सुरक्षा ऑडिट जारी रखें।"],
    )
    hindi_pdf = tmp_path / "hindi_report.pdf"
    pdf_svc.build_pdf(hindi_schema, hindi_pdf)
    assert hindi_pdf.exists()

    reader_hi = pypdf.PdfReader(str(hindi_pdf))
    assert len(reader_hi.pages) >= 2

    # Tamil Report
    tamil_schema = ReportSchema(
        title="செயல்முறை மற்றும் பாதுகாப்பு அறிக்கை",
        language="ta",
        executive_summary="இது ஒரு முழுமையான பல பயன்முறை பகுப்பாய்வு அறிக்கை ஆகும்.",
        sections=[
            ReportSection(
                heading="பாதுகாப்பு பகுப்பாய்வு",
                body="அனைத்து பாதுகாப்பு நெறிமுறைகளும் மதிப்பாய்வு செய்யப்பட்டன.",
                bullet_points=["அங்கீகார அமைப்புகள் சரிபார்க்கப்பட்டன"],
            )
        ],
        conclusions=["செயல்பாடுகள் திட்டமிட்டபடி தொடரும்."],
        recommendations=["தொடர்ச்சியான கண்காணிப்பை உறுதி செய்யவும்."],
    )
    tamil_pdf = tmp_path / "tamil_report.pdf"
    pdf_svc.build_pdf(tamil_schema, tamil_pdf)
    assert tamil_pdf.exists()

    reader_ta = pypdf.PdfReader(str(tamil_pdf))
    assert len(reader_ta.pages) >= 2


def test_partial_llm_failure_still_returns_report_with_errors(
    db: Session, multimodal_conversation: tuple[Conversation, User]
) -> None:
    """Verify that if LLM narrative synthesis fails, a valid report is returned with errors noted."""
    conv, user = multimodal_conversation
    report_svc = get_report_service()

    # Force LLM generation failure while MOCK_MODELS=False
    mock_llm = MagicMock()
    mock_llm.generate_json.side_effect = RuntimeError("Inference cluster timeout")

    with (
        patch("app.core.config.settings.MOCK_MODELS", False),
        patch("app.services.report_service.get_llm_service", return_value=mock_llm),
    ):
        report = report_svc.generate(
            conversation_id=conv.id,
            user_id=user.id,
            options=ReportOptions(length="standard"),
            db=db,
        )

    assert isinstance(report, Report)
    schema = ReportSchema(**report.content)
    assert len(schema.errors) > 0
    assert any("Inference cluster timeout" in err for err in schema.errors)
    # Factual tables must still be preserved
    assert len(schema.audio_findings) == 1
    assert len(schema.image_findings) == 1


def test_length_options_change_output_size(
    db: Session, multimodal_conversation: tuple[Conversation, User]
) -> None:
    """Verify that brief and detailed options vary the output narrative length."""
    conv, user = multimodal_conversation
    report_svc = get_report_service()

    brief_rep = report_svc.generate(
        conversation_id=conv.id,
        user_id=user.id,
        options=ReportOptions(length="brief"),
        db=db,
    )
    detailed_rep = report_svc.generate(
        conversation_id=conv.id,
        user_id=user.id,
        options=ReportOptions(length="detailed"),
        db=db,
    )

    brief_schema = ReportSchema(**brief_rep.content)
    detailed_schema = ReportSchema(**detailed_rep.content)

    assert len(detailed_schema.sections) > len(brief_schema.sections)
    assert len(detailed_schema.conclusions) >= len(brief_schema.conclusions)
    assert len(detailed_schema.executive_summary) > len(brief_schema.executive_summary)


def test_malformed_markup_escaping_in_pdf(tmp_path: Path) -> None:
    """Verify that malformed XML/HTML tags and special characters do not break PDF compilation."""
    pdf_svc = get_pdf_service()

    toxic_schema = ReportSchema(
        title="Security Test: <script>alert('xss')</script> & <b>unclosed",
        executive_summary="Testing entities: <<<UNTRUSTED>>> & <tag> &amp; <invalid>",
        sections=[
            ReportSection(
                heading="Malformed Heading <div id='test'> & more",
                body='Arbitrary brackets < > << >> & "quotes" and tags.',
                bullet_points=["Item with <i>tag</i> & <broken"],
            )
        ],
        conclusions=["Special char & and <conclusion>"],
        recommendations=["Recommending <safe> & <escaped> output."],
    )
    out_pdf = tmp_path / "escaped_test.pdf"
    # Must not raise reportlab.platypus.flowables.FlowableError or xml.parsers.expat.ExpatError
    pdf_svc.build_pdf(toxic_schema, out_pdf)
    assert out_pdf.exists()

    reader = pypdf.PdfReader(str(out_pdf))
    assert len(reader.pages) >= 2


@pytest.mark.asyncio
async def test_reports_api_endpoints_and_download_headers(
    client: AsyncClient,
    auth_headers: dict[str, str],
    multimodal_conversation: tuple[Conversation, User],
) -> None:
    """Verify POST, GET, GET/pdf, and download headers."""
    conv, _ = multimodal_conversation

    # 1. POST /api/v1/reports -> Enqueue job
    post_res = await client.post(
        "/api/v1/reports",
        json={"conversation_id": conv.id, "options": {"length": "standard"}},
        headers=auth_headers,
    )
    assert post_res.status_code == 202
    job_data = post_res.json()
    assert "job_id" in job_data
    assert job_data["status"] == "pending"

    # Wait for synchronous execution in test environment or trigger report directly
    report_svc = get_report_service()
    report = report_svc.generate(conversation_id=conv.id, user_id=conv.user_id)

    # 2. GET /api/v1/reports -> List user reports
    list_res = await client.get("/api/v1/reports", headers=auth_headers)
    assert list_res.status_code == 200
    reports_list = list_res.json()
    assert len(reports_list) >= 1
    assert any(r["id"] == report.id for r in reports_list)

    # 3. GET /api/v1/reports/{id} -> Detailed JSON
    get_res = await client.get(f"/api/v1/reports/{report.id}", headers=auth_headers)
    assert get_res.status_code == 200
    rep_data = get_res.json()
    assert rep_data["id"] == report.id
    assert "executive_summary" in rep_data["content"]
    assert len(rep_data["content"]["audio_findings"]) == 1

    # 4. GET /api/v1/reports/{id}/pdf -> Download with proper headers
    pdf_res = await client.get(f"/api/v1/reports/{report.id}/pdf", headers=auth_headers)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in pdf_res.headers.get("content-disposition", "")
    assert len(pdf_res.content) > 1000


@pytest.mark.asyncio
async def test_cross_user_isolation_and_deletion(
    client: AsyncClient,
    auth_headers: dict[str, str],
    auth_headers_user_b: dict[str, str],
    multimodal_conversation: tuple[Conversation, User],
    db: Session,
) -> None:
    """Verify that User B cannot access User A's report or PDF, and deletion removes the file."""
    conv, user_a = multimodal_conversation
    report_svc = get_report_service()
    report = report_svc.generate(conversation_id=conv.id, user_id=user_a.id, db=db)

    # 1. User B cannot access User A's report details (404)
    b_get = await client.get(f"/api/v1/reports/{report.id}", headers=auth_headers_user_b)
    assert b_get.status_code == 404

    # 2. User B cannot download User A's PDF (404)
    b_pdf = await client.get(f"/api/v1/reports/{report.id}/pdf", headers=auth_headers_user_b)
    assert b_pdf.status_code == 404

    # 3. User B cannot delete User A's report (404)
    b_del = await client.delete(f"/api/v1/reports/{report.id}", headers=auth_headers_user_b)
    assert b_del.status_code == 404

    # 4. User A deletes report -> file on disk is removed
    pdf_file = Path(report.pdf_path) if report.pdf_path else None
    assert pdf_file is not None and pdf_file.exists()

    a_del = await client.delete(f"/api/v1/reports/{report.id}", headers=auth_headers)
    assert a_del.status_code == 200
    assert not pdf_file.exists()

    # Subsequent GET returns 404
    a_get = await client.get(f"/api/v1/reports/{report.id}", headers=auth_headers)
    assert a_get.status_code == 404


@pytest.mark.asyncio
async def test_chat_intent_generate_report_returns_report_event(
    client: AsyncClient,
    auth_headers: dict[str, str],
    multimodal_conversation: tuple[Conversation, User],
) -> None:
    """Verify that submitting a message with report generation intent returns the report event."""
    conv, _ = multimodal_conversation

    events: list[dict[str, Any]] = []
    async with client.stream(
        "POST",
        f"/api/v1/conversations/{conv.id}/messages",
        data={"content": "Please generate a full executive report summarizing our discussion."},
        headers=auth_headers,
    ) as response:
        assert response.status_code == 200
        current_event = "message"
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                current_event = line.replace("event: ", "").strip()
            elif line.startswith("data: "):
                import json

                data_str = line.replace("data: ", "").strip()
                try:
                    payload = json.loads(data_str)
                    events.append({"event": current_event, "data": payload})
                except Exception:
                    pass

    event_names = [e["event"] for e in events]
    assert "report" in event_names
    report_event = next(e for e in events if e["event"] == "report")
    assert "report_id" in report_event["data"]
    assert "pdf_url" in report_event["data"]
    assert report_event["data"]["pdf_url"].startswith("/api/v1/reports/")
