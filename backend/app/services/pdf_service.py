"""PDF Generation Service utilizing ReportLab Platypus with multilingual font support."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import (
    Image as PlatypusImage,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.report import ReportSchema

logger = get_logger(__name__)

# Registry tracking available TTF font families
_REGISTERED_FONTS: set[str] = set()


def register_fonts(fonts_dir: Path | None = None) -> set[str]:
    """Register Noto Sans multilingual fonts with ReportLab if available on disk."""
    global _REGISTERED_FONTS
    if _REGISTERED_FONTS:
        return _REGISTERED_FONTS

    f_dir = fonts_dir or settings.FONTS_DIR
    font_files = {
        "NotoSans": "NotoSans-Regular.ttf",
        "NotoSans-Bold": "NotoSans-Bold.ttf",
        "NotoSansDevanagari": "NotoSansDevanagari-Regular.ttf",
        "NotoSansDevanagari-Bold": "NotoSansDevanagari-Bold.ttf",
        "NotoSansTamil": "NotoSansTamil-Regular.ttf",
        "NotoSansTamil-Bold": "NotoSansTamil-Bold.ttf",
    }

    registered: set[str] = set()
    for font_name, filename in font_files.items():
        ttf_path = f_dir / filename
        if ttf_path.exists() and ttf_path.stat().st_size > 1000:
            try:
                pdfmetrics.registerFont(TTFont(font_name, str(ttf_path)))
                registered.add(font_name)
            except Exception as e:
                logger.warning("Failed to register font", font=font_name, error=str(e))
        else:
            logger.info("Font file not found on disk; will use standard fallback", font=font_name)

    _REGISTERED_FONTS = registered
    return _REGISTERED_FONTS


def escape_markup(text: Any) -> str:
    """Escape XML/HTML characters to prevent ReportLab Platypus markup parse failures."""
    if text is None:
        return ""
    # Convert to string and escape &, <, >
    s = str(text)
    return html.escape(s, quote=False)


def detect_font_for_text(text: str, is_bold: bool = False) -> str:
    """Select the appropriate registered font based on script detection in the text."""
    register_fonts()

    # Devanagari Unicode Block: U+0900 to U+097F
    if re.search(r"[\u0900-\u097F]", text):
        if is_bold and "NotoSansDevanagari-Bold" in _REGISTERED_FONTS:
            return "NotoSansDevanagari-Bold"
        if "NotoSansDevanagari" in _REGISTERED_FONTS:
            return "NotoSansDevanagari"
        logger.warning(
            "Devanagari script detected but NotoSansDevanagari font is missing; falling back to Helvetica"
        )
        return "Helvetica-Bold" if is_bold else "Helvetica"

    # Tamil Unicode Block: U+0B80 to U+0BFF
    if re.search(r"[\u0B80-\u0BFF]", text):
        if is_bold and "NotoSansTamil-Bold" in _REGISTERED_FONTS:
            return "NotoSansTamil-Bold"
        if "NotoSansTamil" in _REGISTERED_FONTS:
            return "NotoSansTamil"
        logger.warning(
            "Tamil script detected but NotoSansTamil font is missing; falling back to Helvetica"
        )
        return "Helvetica-Bold" if is_bold else "Helvetica"

    # Standard Latin / General
    if is_bold and "NotoSans-Bold" in _REGISTERED_FONTS:
        return "NotoSans-Bold"
    if "NotoSans" in _REGISTERED_FONTS:
        return "NotoSans"

    return "Helvetica-Bold" if is_bold else "Helvetica"


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and render total page count on running headers/footers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int) -> None:
        if self._pageNumber == 1:
            # First page is the formal cover page; omit running header/footer
            return

        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Running Header
        self.drawString(54, 11 * 72 - 36, "OmniMind Multimodal Intelligence Report")
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 11 * 72 - 42, 8.5 * 72 - 54, 11 * 72 - 42)

        # Running Footer
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(8.5 * 72 - 54, 36, page_str)
        self.drawString(54, 36, "CONFIDENTIAL & PROPRIETARY — GENERATED BY OMNIMIND")
        self.line(54, 46, 8.5 * 72 - 54, 46)
        self.restoreState()


class PDFReportGenerator:
    """Engine compiling structured ReportSchema into styled multi-page PDF documents."""

    def __init__(self) -> None:
        register_fonts()
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self) -> None:
        """Initialize custom styled typography for headings, tables, and narrative."""
        self.body_style = ParagraphStyle(
            "ReportBody",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#1F2937"),
            spaceAfter=6,
        )
        self.bullet_style = ParagraphStyle(
            "ReportBullet",
            parent=self.body_style,
            leftIndent=15,
            firstLineIndent=-10,
            spaceAfter=4,
        )
        self.h1_style = ParagraphStyle(
            "ReportH1",
            parent=self.styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True,
        )
        self.h2_style = ParagraphStyle(
            "ReportH2",
            parent=self.styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#0F766E"),
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        )
        self.table_header_style = ParagraphStyle(
            "ReportTableHeader",
            parent=self.body_style,
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#0F172A"),
        )
        self.table_cell_style = ParagraphStyle(
            "ReportTableCell",
            parent=self.body_style,
            fontSize=8.5,
            leading=11,
            spaceAfter=0,
        )

    def _p(
        self,
        text: Any,
        is_bold: bool = False,
        is_bullet: bool = False,
        prefix_bold: str | None = None,
    ) -> Paragraph:
        """Create a paragraph with dynamic font selection and optional bold label prefix."""
        clean_text = escape_markup(text)
        font = detect_font_for_text(clean_text, is_bold=is_bold)
        base = self.bullet_style if is_bullet else self.body_style
        style = ParagraphStyle(
            f"Dyn_{font}_{is_bullet}_{is_bold}",
            parent=base,
            fontName=font,
        )
        bullet_prefix = "&bull; " if is_bullet else ""
        if prefix_bold:
            bold_font = detect_font_for_text(prefix_bold, is_bold=True)
            escaped_prefix = escape_markup(prefix_bold)
            content = f'{bullet_prefix}<font name="{bold_font}"><b>{escaped_prefix}</b></font> {clean_text}'
        else:
            content = f"{bullet_prefix}{clean_text}"
        return Paragraph(content, style)

    def _h1(self, text: Any) -> Paragraph:
        clean_text = escape_markup(text)
        font = detect_font_for_text(clean_text, is_bold=True)
        style = ParagraphStyle(f"DynH1_{font}", parent=self.h1_style, fontName=font)
        return Paragraph(clean_text, style)

    def _h2(self, text: Any) -> Paragraph:
        clean_text = escape_markup(text)
        font = detect_font_for_text(clean_text, is_bold=True)
        style = ParagraphStyle(f"DynH2_{font}", parent=self.h2_style, fontName=font)
        return Paragraph(clean_text, style)

    def _build_cover_page(self, report: ReportSchema, elements: list[Any]) -> None:
        """Construct formal cover page with title, branding, metadata, and visual divider."""
        elements.append(Spacer(1, 40))

        # Brand Tag
        brand_style = ParagraphStyle(
            "BrandBadge",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#0284C7"),
            spaceAfter=15,
        )
        elements.append(Paragraph("OMNIMIND MULTIMODAL ASSISTANT", brand_style))
        elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#0284C7")))
        elements.append(Spacer(1, 20))

        # Main Title
        title_font = detect_font_for_text(report.title, is_bold=True)
        cover_title_style = ParagraphStyle(
            "CoverTitle",
            fontName=title_font,
            fontSize=26,
            leading=32,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=12,
        )
        elements.append(Paragraph(escape_markup(report.title), cover_title_style))

        # Subtitle
        sub_style = ParagraphStyle(
            "CoverSub",
            fontName="Helvetica",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#475569"),
            spaceAfter=30,
        )
        elements.append(
            Paragraph("Structured Multimodal Synthesis & Cross-Asset Analysis", sub_style)
        )

        elements.append(Spacer(1, 50))

        # Metadata Card / Table
        meta_data = [
            [
                Paragraph("<b>Generated Timestamp:</b>", self.table_cell_style),
                Paragraph(escape_markup(report.generated_at), self.table_cell_style),
            ],
            [
                Paragraph("<b>Designated Language:</b>", self.table_cell_style),
                Paragraph(escape_markup(report.language.upper()), self.table_cell_style),
            ],
            [
                Paragraph("<b>Audio Assets Analyzed:</b>", self.table_cell_style),
                Paragraph(str(len(report.audio_findings)), self.table_cell_style),
            ],
            [
                Paragraph("<b>Visual Assets Analyzed:</b>", self.table_cell_style),
                Paragraph(str(len(report.image_findings)), self.table_cell_style),
            ],
            [
                Paragraph("<b>Key Observations:</b>", self.table_cell_style),
                Paragraph(str(len(report.cross_modal_observations)), self.table_cell_style),
            ],
            [
                Paragraph("<b>Classification:</b>", self.table_cell_style),
                Paragraph("CONFIDENTIAL & AUDITABLE", self.table_cell_style),
            ],
        ]
        meta_table = Table(meta_data, colWidths=[160, 320])
        meta_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#EDF2F7")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        elements.append(meta_table)

        elements.append(PageBreak())

    def _build_table_of_contents(self, report: ReportSchema, elements: list[Any]) -> None:
        """Construct a structured Table of Contents."""
        elements.append(self._h1("Table of Contents"))
        elements.append(
            HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceAfter=12)
        )

        toc_items = [
            ("1.0", "Executive Summary"),
            ("2.0", "Thematic Sections"),
            (
                "3.0",
                f"Audio & Acoustic Findings ({len(report.audio_findings)} assets)",
            ),
            (
                "4.0",
                f"Visual & Scene Intelligence ({len(report.image_findings)} assets)",
            ),
            ("5.0", "Cross-Modal Observations"),
            ("6.0", "Conclusions & Strategic Recommendations"),
            ("7.0", "Appendix & System Telemetry"),
        ]

        toc_data = []
        for num, title in toc_items:
            toc_data.append(
                [
                    Paragraph(f"<b>{num}</b>", self.table_cell_style),
                    Paragraph(title, self.table_cell_style),
                ]
            )

        toc_table = Table(toc_data, colWidths=[40, 440])
        toc_table.setStyle(
            TableStyle(
                [
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#F1F5F9")),
                ]
            )
        )
        elements.append(toc_table)
        elements.append(Spacer(1, 16))

    def build_pdf(
        self,
        report: ReportSchema,
        output_path: Path,
        include_images: bool = True,
        include_metrics: bool = True,
    ) -> Path:
        """Generate and write the complete PDF document to the specified destination."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=54,
            bottomMargin=54,
        )

        elements: list[Any] = []

        # 1. Cover Page
        self._build_cover_page(report, elements)

        # 2. Table of Contents
        self._build_table_of_contents(report, elements)

        # 3. Executive Summary
        elements.append(self._h1("1. Executive Summary"))
        exec_summary = report.executive_summary.strip() or "No executive summary provided."
        for line in exec_summary.split("\n"):
            if line.strip():
                elements.append(self._p(line.strip()))
        elements.append(Spacer(1, 10))

        # 4. Thematic Sections
        if report.sections:
            elements.append(self._h1("2. Thematic Sections"))
            for sec in report.sections:
                elements.append(self._h2(sec.heading))
                if sec.body:
                    elements.append(self._p(sec.body))
                for bp in sec.bullet_points:
                    elements.append(self._p(bp, is_bullet=True))
                elements.append(Spacer(1, 6))

        # 5. Audio Findings
        if report.audio_findings:
            elements.append(self._h1("3. Audio & Acoustic Findings"))
            for af in report.audio_findings:
                elements.append(
                    self._h2(f"Recording: {af.file} ({af.duration:.1f}s, lang: {af.language})")
                )
                if af.summary:
                    elements.append(self._p(af.summary, prefix_bold="Summary:"))
                if af.key_points:
                    elements.append(self._p("Key Inferred Agenda Points:", is_bold=True))
                    for kp in af.key_points:
                        elements.append(self._p(kp, is_bullet=True))

                if af.decisions:
                    elements.append(self._p("Ratified Decisions:", is_bold=True))
                    for dec in af.decisions:
                        elements.append(self._p(dec, is_bullet=True))

                # Action Items Table
                if af.action_items:
                    elements.append(Spacer(1, 4))
                    elements.append(self._p("Action Items:", is_bold=True))
                    action_headers = [
                        Paragraph("<b>Owner</b>", self.table_header_style),
                        Paragraph("<b>Task</b>", self.table_header_style),
                        Paragraph("<b>Deadline</b>", self.table_header_style),
                        Paragraph("<b>Timestamp</b>", self.table_header_style),
                    ]
                    action_rows = [action_headers]
                    for item in af.action_items:
                        action_rows.append(
                            [
                                Paragraph(
                                    escape_markup(item.get("owner", "Unassigned")),
                                    self.table_cell_style,
                                ),
                                Paragraph(
                                    escape_markup(item.get("task", "")), self.table_cell_style
                                ),
                                Paragraph(
                                    escape_markup(item.get("deadline", "TBD")),
                                    self.table_cell_style,
                                ),
                                Paragraph(
                                    escape_markup(item.get("source_timestamp", "00:00")),
                                    self.table_cell_style,
                                ),
                            ]
                        )
                    act_table = Table(action_rows, colWidths=[90, 230, 90, 70], repeatRows=1)
                    act_table.setStyle(
                        TableStyle(
                            [
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                                ("TOPPADDING", (0, 0), (-1, -1), 4),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ]
                        )
                    )
                    elements.append(act_table)

                # Timeline Table
                if af.timeline:
                    elements.append(Spacer(1, 4))
                    elements.append(self._p("Topic Progression Timeline:", is_bold=True))
                    time_headers = [
                        Paragraph("<b>Topic</b>", self.table_header_style),
                        Paragraph("<b>Span (s)</b>", self.table_header_style),
                        Paragraph("<b>Segment Summary</b>", self.table_header_style),
                    ]
                    time_rows = [time_headers]
                    for t_item in af.timeline:
                        start_s = t_item.get("start", 0.0)
                        end_s = t_item.get("end", 0.0)
                        time_rows.append(
                            [
                                Paragraph(
                                    escape_markup(t_item.get("topic", "Topic")),
                                    self.table_cell_style,
                                ),
                                Paragraph(f"{start_s:.1f} - {end_s:.1f}", self.table_cell_style),
                                Paragraph(
                                    escape_markup(t_item.get("summary", "")), self.table_cell_style
                                ),
                            ]
                        )
                    timeline_table = Table(time_rows, colWidths=[120, 80, 280], repeatRows=1)
                    timeline_table.setStyle(
                        TableStyle(
                            [
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                                ("TOPPADDING", (0, 0), (-1, -1), 4),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ]
                        )
                    )
                    elements.append(timeline_table)

                elements.append(Spacer(1, 8))

        # 6. Image Findings
        if report.image_findings:
            elements.append(self._h1("4. Visual & Scene Intelligence"))
            for img in report.image_findings:
                elements.append(self._h2(f"Visual Asset: {img.file}"))
                if img.caption:
                    elements.append(self._p(img.caption, prefix_bold="Caption:"))
                if img.extracted_text:
                    elements.append(
                        self._p(img.extracted_text, prefix_bold="Extracted Text (OCR):")
                    )
                if img.quality_warnings:
                    elements.append(
                        self._p(
                            ", ".join(img.quality_warnings),
                            prefix_bold="Image Quality Alerts:",
                        )
                    )

                # Detected Objects Table
                if img.objects:
                    elements.append(Spacer(1, 4))
                    elements.append(self._p("Detected Entities & Objects:", is_bold=True))
                    obj_headers = [
                        Paragraph("<b>Entity Label</b>", self.table_header_style),
                        Paragraph("<b>Confidence</b>", self.table_header_style),
                        Paragraph("<b>Bounding Box [y1, x1, y2, x2]</b>", self.table_header_style),
                    ]
                    obj_rows = [obj_headers]
                    for obj in img.objects:
                        conf = obj.get("confidence", 0.0)
                        box = obj.get("box_2d", [])
                        obj_rows.append(
                            [
                                Paragraph(
                                    escape_markup(obj.get("label", "Unknown")),
                                    self.table_cell_style,
                                ),
                                Paragraph(f"{conf * 100.0:.1f}%", self.table_cell_style),
                                Paragraph(str(box), self.table_cell_style),
                            ]
                        )
                    obj_table = Table(obj_rows, colWidths=[160, 100, 220], repeatRows=1)
                    obj_table.setStyle(
                        TableStyle(
                            [
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                                ("TOPPADDING", (0, 0), (-1, -1), 4),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ]
                        )
                    )
                    elements.append(obj_table)

                # Optional embedded image thumbnail
                if include_images:
                    img_path = Path(img.file)
                    if not img_path.is_absolute():
                        candidates = [
                            settings.STORAGE_DIR / "uploads" / "images" / img.file,
                            settings.STORAGE_DIR / "uploads" / img.file,
                            settings.STORAGE_DIR / img.file,
                        ]
                        for c in candidates:
                            if c.exists():
                                img_path = c
                                break

                    if img_path.exists() and img_path.is_file():
                        try:
                            # Render thumbnail max width 400, max height 220
                            p_img = PlatypusImage(
                                str(img_path), width=360, height=200, kind="proportional"
                            )
                            elements.append(Spacer(1, 6))
                            elements.append(KeepTogether([p_img]))
                        except Exception as e:
                            logger.info(
                                "Could not embed image thumbnail in PDF",
                                file=img.file,
                                error=str(e),
                            )

                elements.append(Spacer(1, 8))

        # 7. Cross-Modal Observations
        if report.cross_modal_observations:
            elements.append(self._h1("5. Cross-Modal Observations"))
            for obs in report.cross_modal_observations:
                elements.append(self._p(obs, is_bullet=True))
            elements.append(Spacer(1, 8))

        # 8. Conclusions & Recommendations
        if report.conclusions or report.recommendations:
            elements.append(self._h1("6. Conclusions & Strategic Recommendations"))
            if report.conclusions:
                elements.append(self._h2("Conclusions"))
                for conc in report.conclusions:
                    elements.append(self._p(conc, is_bullet=True))
            if report.recommendations:
                elements.append(self._h2("Strategic Recommendations"))
                for rec in report.recommendations:
                    elements.append(self._p(rec, is_bullet=True))
            elements.append(Spacer(1, 8))

        # 9. Appendix & Telemetry
        elements.append(self._h1("7. Appendix & System Telemetry"))
        if report.appendix.sources:
            elements.append(self._h2("Source Attachments"))
            for src in report.appendix.sources:
                elements.append(self._p(src, is_bullet=True))

        if report.appendix.models_used:
            elements.append(Spacer(1, 4))
            elements.append(self._h2("Active Model Checkpoints"))
            m_headers = [
                Paragraph("<b>Pipeline Subsystem</b>", self.table_header_style),
                Paragraph("<b>Model Identifier / Checkpoint</b>", self.table_header_style),
            ]
            m_rows = [m_headers]
            for m_key, m_val in report.appendix.models_used.items():
                m_rows.append(
                    [
                        Paragraph(escape_markup(m_key), self.table_cell_style),
                        Paragraph(escape_markup(m_val), self.table_cell_style),
                    ]
                )
            m_table = Table(m_rows, colWidths=[160, 320], repeatRows=1)
            m_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            elements.append(m_table)

        if include_metrics and report.appendix.processing_metrics:
            elements.append(Spacer(1, 4))
            elements.append(self._h2("Execution Telemetry"))
            p_headers = [
                Paragraph("<b>Subsystem Operation</b>", self.table_header_style),
                Paragraph("<b>Recorded Measurement</b>", self.table_header_style),
            ]
            p_rows = [p_headers]
            for p_k, p_v in report.appendix.processing_metrics.items():
                p_rows.append(
                    [
                        Paragraph(escape_markup(p_k), self.table_cell_style),
                        Paragraph(escape_markup(str(p_v)), self.table_cell_style),
                    ]
                )
            p_table = Table(p_rows, colWidths=[200, 280], repeatRows=1)
            p_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            elements.append(p_table)

        if report.errors:
            elements.append(Spacer(1, 6))
            elements.append(self._h2("Processing Anomalies & Warnings"))
            for err in report.errors:
                elements.append(self._p(f"Warning: {err}", is_bullet=True))

        # Build document with NumberedCanvas for multi-page headers and footers
        doc.build(elements, canvasmaker=NumberedCanvas)
        logger.info("Successfully compiled structured PDF report", path=str(output_path))
        return output_path


_pdf_generator: PDFReportGenerator | None = None


def get_pdf_service() -> PDFReportGenerator:
    """Retrieve singleton PDFReportGenerator instance."""
    global _pdf_generator
    if _pdf_generator is None:
        _pdf_generator = PDFReportGenerator()
    return _pdf_generator
