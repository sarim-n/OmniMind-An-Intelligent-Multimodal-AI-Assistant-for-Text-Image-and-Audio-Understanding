"""Multimodal image understanding pipeline.

Orchestrates: safe preprocessing -> parallel/sequential object detection & VLM captioning ->
OpenCV visual annotation -> untrusted OCR text capture -> database persistence.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from PIL import Image

from app.core.config import settings
from app.core.logging import get_logger
from app.models.image_analysis import ImageAnalysis
from app.schemas.vision import ImageAnalysisRead
from app.services.detector_service import get_detector_service
from app.services.image_preprocess import preprocess_image
from app.services.metrics_service import track
from app.services.storage_service import get_storage_root
from app.services.vision_service import get_vision_service

logger = get_logger(__name__)


async def run_image_pipeline(
    attachment_id: str,
    file_path: Path | str,
    user_id: str,
    enhance: bool = False,
) -> ImageAnalysisRead:
    """Execute full computer vision understanding pipeline and persist results to database."""
    detector_service = get_detector_service()
    vision_service = get_vision_service()

    start_time = time.perf_counter()
    with track("vision", "pipeline") as tracker:
        # 1. Preprocessing & Quality Verification
        logger.info(
            "Preprocessing image for analysis", attachment_id=attachment_id, user_id=user_id
        )
        preprocessed = await asyncio.to_thread(
            preprocess_image,
            source=file_path,
            enhance=enhance,
            max_side=settings.VLM_MAX_IMAGE_SIDE,
        )

        pil_img: Image.Image = preprocessed.image

        # 2. Object Detection & VLM Captioning (Sequential on CPU / Parallel on GPU)
        is_cpu_profile = settings.PROFILE == "cpu"

        if is_cpu_profile:
            logger.info("Executing vision tasks sequentially (CPU profile)")
            det_result, _ = await asyncio.to_thread(detector_service.detect, pil_img)
            caption_text, _ = await asyncio.to_thread(vision_service.describe, pil_img, "detailed")
            ocr_text, _ = await asyncio.to_thread(vision_service.extract_text, pil_img)
        else:
            logger.info("Executing vision tasks concurrently (GPU profile)")
            det_task = asyncio.to_thread(detector_service.detect, pil_img)
            caption_task = asyncio.to_thread(vision_service.describe, pil_img, "detailed")
            ocr_task = asyncio.to_thread(vision_service.extract_text, pil_img)

            det_tuple, caption_tuple, ocr_tuple = await asyncio.gather(
                det_task, caption_task, ocr_task
            )
            det_result = det_tuple[0]
            caption_text = caption_tuple[0]
            ocr_text = ocr_tuple[0]

        # 3. Generate and Save Annotated Image with OpenCV
        storage_root = get_storage_root()
        derived_rel_path = f"uploads/derived/{user_id}/{attachment_id}_annotated.jpg"
        annotated_abs_path = storage_root / derived_rel_path

        await asyncio.to_thread(
            detector_service.draw_annotations,
            image=pil_img,
            objects=det_result.objects,
            output_path=annotated_abs_path,
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        tracker.extra["object_count"] = len(det_result.objects)
        tracker.extra["image_size"] = (
            f"{preprocessed.processed_size[0]}x{preprocessed.processed_size[1]}"
        )

        # 4. CRITICAL SECURITY: Treat OCR text as UNTRUSTED passive data
        sanitized_ocr = ocr_text.strip() if ocr_text else ""

        # 5. Persist ImageAnalysis to Database
        import app.db.session

        analysis_id = ""
        analysis_metadata: dict[str, Any] = {
            "counts": det_result.counts,
            "quality": preprocessed.quality,
            "dominant_colors": preprocessed.dominant_colors,
            "warnings": preprocessed.warnings,
            "annotated_path": derived_rel_path,
            "timing_ms": round(latency_ms, 2),
        }

        with app.db.session.SessionLocal() as session:
            existing = (
                session.query(ImageAnalysis)
                .filter(ImageAnalysis.attachment_id == attachment_id)
                .first()
            )
            if existing:
                existing.caption = caption_text
                existing.objects = [obj.model_dump() for obj in det_result.objects]
                existing.ocr_text = sanitized_ocr
                existing.metadata_ = analysis_metadata
                session.commit()
                analysis_id = existing.id
            else:
                record = ImageAnalysis(
                    attachment_id=attachment_id,
                    caption=caption_text,
                    objects=[obj.model_dump() for obj in det_result.objects],
                    ocr_text=sanitized_ocr,
                    metadata_=analysis_metadata,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
                analysis_id = record.id

        logger.info(
            "Completed image understanding pipeline",
            attachment_id=attachment_id,
            analysis_id=analysis_id,
            latency_ms=round(latency_ms, 2),
        )

        return ImageAnalysisRead(
            id=analysis_id,
            attachment_id=attachment_id,
            caption=caption_text,
            objects=det_result.objects,
            counts=det_result.counts,
            ocr_text=sanitized_ocr,
            quality=preprocessed.quality,
            dominant_colors=[
                {"hex": c["hex"], "name": c["name"]} for c in preprocessed.dominant_colors  # type: ignore[misc]
            ],
            warnings=preprocessed.warnings,
            annotated_path=derived_rel_path,
            timing_ms=round(latency_ms, 2),
        )
