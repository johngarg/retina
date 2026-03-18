from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import DATA_DIR
from .constants import IMAGE_ORIGINAL_ROOT, IMAGE_THUMBNAIL_ROOT
from .models import RetinalImage


def normalize_relpath(value: str | Path) -> str:
    return Path(value).as_posix()


@dataclass
class IntegrityIssue:
    issue_type: str
    image_id: str | None
    path: str
    detail: str


@dataclass
class IntegrityScanResult:
    total_images: int
    missing_originals: list[IntegrityIssue]
    missing_thumbnails: list[IntegrityIssue]
    orphaned_originals: list[IntegrityIssue]
    orphaned_thumbnails: list[IntegrityIssue]

    @property
    def ok(self) -> bool:
        return not (
            self.missing_originals
            or self.missing_thumbnails
            or self.orphaned_originals
            or self.orphaned_thumbnails
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "total_images": self.total_images,
            "ok": self.ok,
            "missing_originals": [asdict(issue) for issue in self.missing_originals],
            "missing_thumbnails": [asdict(issue) for issue in self.missing_thumbnails],
            "orphaned_originals": [asdict(issue) for issue in self.orphaned_originals],
            "orphaned_thumbnails": [asdict(issue) for issue in self.orphaned_thumbnails],
        }


def relative_files(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {
        normalize_relpath(path.relative_to(DATA_DIR))
        for path in root.rglob("*")
        if path.is_file()
    }


def scan_storage_integrity(db: Session) -> IntegrityScanResult:
    images = list(db.scalars(select(RetinalImage)))
    expected_originals = {normalize_relpath(image.storage_relpath) for image in images}
    expected_thumbnails = {
        normalize_relpath(image.thumbnail_relpath) for image in images if image.thumbnail_relpath
    }

    existing_originals = relative_files(DATA_DIR / IMAGE_ORIGINAL_ROOT)
    existing_thumbnails = relative_files(DATA_DIR / IMAGE_THUMBNAIL_ROOT)

    missing_originals = [
        IntegrityIssue(
            issue_type="missing_original",
            image_id=image.id,
            path=image.storage_relpath,
            detail="Database row references an original image file that does not exist on disk.",
        )
        for image in images
        if image.storage_relpath not in existing_originals
    ]
    missing_thumbnails = [
        IntegrityIssue(
            issue_type="missing_thumbnail",
            image_id=image.id,
            path=image.thumbnail_relpath or "",
            detail="Database row references a thumbnail file that does not exist on disk.",
        )
        for image in images
        if not image.thumbnail_relpath or image.thumbnail_relpath not in existing_thumbnails
    ]
    orphaned_originals = [
        IntegrityIssue(
            issue_type="orphaned_original",
            image_id=None,
            path=path,
            detail="Original image file exists on disk but is not referenced by the database.",
        )
        for path in sorted(existing_originals - expected_originals)
    ]
    orphaned_thumbnails = [
        IntegrityIssue(
            issue_type="orphaned_thumbnail",
            image_id=None,
            path=path,
            detail="Thumbnail file exists on disk but is not referenced by the database.",
        )
        for path in sorted(existing_thumbnails - expected_thumbnails)
    ]

    return IntegrityScanResult(
        total_images=len(images),
        missing_originals=missing_originals,
        missing_thumbnails=missing_thumbnails,
        orphaned_originals=orphaned_originals,
        orphaned_thumbnails=orphaned_thumbnails,
    )
