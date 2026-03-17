from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import DATA_DIR
from .models import RetinalImage
from .storage import StorageValidationError, create_thumbnail_from_original, remove_storage_artifacts


def backfill_missing_thumbnails(db: Session) -> int:
    repaired = 0
    images = list(db.scalars(select(RetinalImage)))

    for image in images:
        thumbnail_missing = (
            not image.thumbnail_relpath
            or not (DATA_DIR / Path(image.thumbnail_relpath)).exists()
        )
        if not thumbnail_missing:
            continue

        if image.thumbnail_relpath:
            remove_storage_artifacts(image.thumbnail_relpath)

        try:
            thumbnail = create_thumbnail_from_original(image.id, image.storage_relpath)
        except StorageValidationError:
            continue

        image.thumbnail_relpath = thumbnail.thumbnail_relpath
        image.thumbnail_width_px = thumbnail.thumbnail_width_px
        image.thumbnail_height_px = thumbnail.thumbnail_height_px
        repaired += 1

    if repaired:
        db.commit()

    return repaired
