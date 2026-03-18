from __future__ import annotations

import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .audit import log_audit_event
from .config import BACKUPS_DIR, DATA_DIR, DB_PATH, IMAGE_ORIGINALS_DIR, IMAGE_THUMBNAILS_DIR
from .models import AuditEvent, Patient, RetinalImage, StudySession


@dataclass
class BackupResult:
    archive_path: str
    created_at: str
    patients: int
    sessions: int
    images: int
    audit_events: int
    original_files: int
    thumbnail_files: int
    size_bytes: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def iter_relative_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file())


def create_backup_archive(db: Session, *, actor_name: str | None = None) -> BackupResult:
    created_at = datetime.now(timezone.utc)
    archive_name = f"retina-backup-{created_at:%Y%m%d-%H%M%S-%f}.zip"
    archive_path = BACKUPS_DIR / archive_name

    originals = iter_relative_files(IMAGE_ORIGINALS_DIR)
    thumbnails = iter_relative_files(IMAGE_THUMBNAILS_DIR)

    manifest = {
        "created_at": created_at.isoformat(),
        "database": "app.db",
        "patients": db.scalar(select(func.count()).select_from(Patient)) or 0,
        "sessions": db.scalar(select(func.count()).select_from(StudySession)) or 0,
        "images": db.scalar(select(func.count()).select_from(RetinalImage)) or 0,
        "audit_events": db.scalar(select(func.count()).select_from(AuditEvent)) or 0,
        "original_files": len(originals),
        "thumbnail_files": len(thumbnails),
    }

    with tempfile.TemporaryDirectory(prefix="retina-backup-") as temp_dir:
        temp_root = Path(temp_dir)
        snapshot_db_path = temp_root / "app.db"
        manifest_path = temp_root / "manifest.json"

        with closing(sqlite3.connect(DB_PATH)) as source_connection:
            with closing(sqlite3.connect(snapshot_db_path)) as snapshot_connection:
                source_connection.backup(snapshot_connection)

        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot_db_path, "app.db")
            archive.write(manifest_path, "manifest.json")
            for path in originals + thumbnails:
                archive.write(path, path.relative_to(DATA_DIR))

    size_bytes = archive_path.stat().st_size
    result = BackupResult(
        archive_path=str(archive_path),
        created_at=created_at.isoformat(),
        patients=manifest["patients"],
        sessions=manifest["sessions"],
        images=manifest["images"],
        audit_events=manifest["audit_events"],
        original_files=manifest["original_files"],
        thumbnail_files=manifest["thumbnail_files"],
        size_bytes=size_bytes,
    )

    log_audit_event(
        db,
        action="backup_created",
        entity_type="backup",
        entity_id=archive_name,
        source="backup",
        actor_name=actor_name,
        summary=f"Created backup archive {archive_name}",
        payload=result.to_dict(),
    )
    db.commit()

    return result
