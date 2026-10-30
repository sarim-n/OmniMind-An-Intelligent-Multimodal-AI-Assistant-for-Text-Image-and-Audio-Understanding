"""Unit tests for the integrated image understanding pipeline."""

from __future__ import annotations

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from app.models.attachment import Attachment
from app.models.image_analysis import ImageAnalysis
from app.models.user import User
from app.services.image_pipeline import run_image_pipeline
from app.services.storage_service import get_storage_root


@pytest.mark.asyncio
async def test_image_pipeline_end_to_end(db: Session, test_user: User) -> None:
    # 1. Create a dummy image file in storage
    storage_root = get_storage_root()
    user_upload_dir = storage_root / "uploads" / "images" / test_user.id
    user_upload_dir.mkdir(parents=True, exist_ok=True)
    img_file = user_upload_dir / "pipeline_test.jpg"

    pil_img = Image.new("RGB", (300, 200), (45, 120, 210))
    pil_img.save(str(img_file), format="JPEG")

    # 2. Create Attachment record in DB
    att = Attachment(
        user_id=test_user.id,
        type="image",
        path=f"uploads/images/{test_user.id}/pipeline_test.jpg",
        mime="image/jpeg",
        size=img_file.stat().st_size,
    )
    db.add(att)
    db.commit()
    db.refresh(att)

    # 3. Run image understanding pipeline
    analysis = await run_image_pipeline(
        attachment_id=att.id,
        file_path=img_file,
        user_id=test_user.id,
        enhance=True,
    )

    # 4. Assertions on returned structured object
    assert analysis.attachment_id == att.id
    assert analysis.caption is not None and len(analysis.caption) > 0
    assert isinstance(analysis.objects, list)
    assert len(analysis.objects) >= 2
    assert "person" in analysis.counts
    assert analysis.ocr_text is not None
    assert "blur_score" in analysis.quality
    assert len(analysis.dominant_colors) > 0
    assert analysis.annotated_path is not None

    # 5. Verify annotated file was generated on disk
    annotated_disk_file = storage_root / analysis.annotated_path
    assert annotated_disk_file.is_file()
    assert annotated_disk_file.stat().st_size > 0

    # 6. Verify record persisted in database
    db_record = db.query(ImageAnalysis).filter(ImageAnalysis.attachment_id == att.id).first()
    assert db_record is not None
    assert db_record.caption == analysis.caption
    assert db_record.ocr_text == analysis.ocr_text
    assert db_record.metadata_ is not None
    assert "counts" in db_record.metadata_

    # Clean up test file
    if img_file.exists():
        img_file.unlink()
    if annotated_disk_file.exists():
        annotated_disk_file.unlink()
