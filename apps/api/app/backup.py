from __future__ import annotations

import json
import sqlite3
import tempfile
import shutil
import zipfile
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, close_all_sessions

from .audit import log_audit_event
from .config import BACKUPS_DIR, DATA_DIR, DB_PATH, IMAGE_ORIGINALS_DIR, IMAGE_THUMBNAILS_DIR, ensure_app_dirs
from .database import SessionLocal, engine
from .maintenance import backfill_missing_thumbnails
from .migrations import run_migrations
from .models import AuditEvent, Patient, RetinalImage, StudySession


class BackupValidationError(ValueError):
    pass


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


@dataclass
class RestoreResult:
    restored_at: str
    source_archive_name: str
    safety_backup_path: str
    patients: int
    sessions: int
    images: int
    audit_events: int
    original_files: int
    thumbnail_files: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def iter_relative_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file())


def _normalize_archive_member(name: str) -> Path:
    member_path = Path(name)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise BackupValidationError(f"Backup archive contains an unsafe path: {name}")
    return member_path


def _extract_backup_archive(archive_path: Path, destination_root: Path) -> dict[str, object]:
    with zipfile.ZipFile(archive_path) as archive:
        member_names = set(archive.namelist())
        if "app.db" not in member_names:
            raise BackupValidationError("Backup archive is missing app.db")
        if "manifest.json" not in member_names:
            raise BackupValidationError("Backup archive is missing manifest.json")

        for member in archive.infolist():
            member_path = _normalize_archive_member(member.filename)
            destination = destination_root / member_path
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)

    manifest_path = destination_root / "manifest.json"
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BackupValidationError("Backup archive manifest.json is invalid") from exc


def _snapshot_current_data(snapshot_root: Path) -> None:
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, snapshot_root / "app.db")
    if IMAGE_ORIGINALS_DIR.exists():
        shutil.copytree(IMAGE_ORIGINALS_DIR, snapshot_root / "images" / "original", dirs_exist_ok=True)
    if IMAGE_THUMBNAILS_DIR.exists():
        shutil.copytree(IMAGE_THUMBNAILS_DIR, snapshot_root / "images" / "thumbnail", dirs_exist_ok=True)


def _replace_directory(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    if source.exists():
        shutil.copytree(source, destination)
    else:
        destination.mkdir(parents=True, exist_ok=True)


def _restore_extracted_data(extracted_root: Path) -> None:
    ensure_app_dirs()

    restored_db_path = extracted_root / "app.db"
    restored_originals = extracted_root / "images" / "original"
    restored_thumbnails = extracted_root / "images" / "thumbnail"

    if not restored_db_path.exists():
        raise BackupValidationError("Extracted backup is missing app.db")

    if DB_PATH.exists():
        DB_PATH.unlink()
    shutil.copy2(restored_db_path, DB_PATH)
    _replace_directory(restored_originals, IMAGE_ORIGINALS_DIR)
    _replace_directory(restored_thumbnails, IMAGE_THUMBNAILS_DIR)


def _restore_snapshot(snapshot_root: Path) -> None:
    ensure_app_dirs()

    snapshot_db_path = snapshot_root / "app.db"
    snapshot_originals = snapshot_root / "images" / "original"
    snapshot_thumbnails = snapshot_root / "images" / "thumbnail"

    if snapshot_db_path.exists():
        if DB_PATH.exists():
            DB_PATH.unlink()
        shutil.copy2(snapshot_db_path, DB_PATH)
    _replace_directory(snapshot_originals, IMAGE_ORIGINALS_DIR)
    _replace_directory(snapshot_thumbnails, IMAGE_THUMBNAILS_DIR)


def _collect_restore_counts() -> RestoreResult:
    with SessionLocal() as session:
        backfill_missing_thumbnails(session)
        return RestoreResult(
            restored_at=datetime.now(timezone.utc).isoformat(),
            source_archive_name="",
            safety_backup_path="",
            patients=session.scalar(select(func.count()).select_from(Patient)) or 0,
            sessions=session.scalar(select(func.count()).select_from(StudySession)) or 0,
            images=session.scalar(select(func.count()).select_from(RetinalImage)) or 0,
            audit_events=session.scalar(select(func.count()).select_from(AuditEvent)) or 0,
            original_files=len(iter_relative_files(IMAGE_ORIGINALS_DIR)),
            thumbnail_files=len(iter_relative_files(IMAGE_THUMBNAILS_DIR)),
        )


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


def restore_backup_archive(
    archive_path: Path,
    *,
    actor_name: str | None = None,
    source_archive_name: str | None = None,
) -> RestoreResult:
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup archive not found: {archive_path}")

    with SessionLocal() as session:
        safety_backup = create_backup_archive(session, actor_name=actor_name)

    with tempfile.TemporaryDirectory(prefix="retina-restore-") as temp_dir:
        temp_root = Path(temp_dir)
        extracted_root = temp_root / "extracted"
        snapshot_root = temp_root / "snapshot"
        extracted_root.mkdir(parents=True, exist_ok=True)
        snapshot_root.mkdir(parents=True, exist_ok=True)

        _extract_backup_archive(archive_path, extracted_root)
        _snapshot_current_data(snapshot_root)

        close_all_sessions()
        engine.dispose()

        try:
            _restore_extracted_data(extracted_root)
            run_migrations()
        except Exception:
            close_all_sessions()
            engine.dispose()
            _restore_snapshot(snapshot_root)
            run_migrations()
            raise

    close_all_sessions()
    engine.dispose()

    restored = _collect_restore_counts()
    restored.source_archive_name = source_archive_name or archive_path.name
    restored.safety_backup_path = safety_backup.archive_path
    return restored
