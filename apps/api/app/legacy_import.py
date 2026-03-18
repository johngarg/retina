from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import log_audit_event
from .models import Patient, RetinalImage, StudySession, utc_now
from .storage import StorageValidationError, normalize_name, normalize_upper, store_file_path

LEGACY_DATE_RE = re.compile(r"^(?P<day>\d{1,2})/(?P<month>\d{1,2})/(?P<year>\d{4})$")
LEGACY_VISIT_RE = re.compile(
    r"^t:(?P<hour>\d{1,2})\.(?P<minute>\d{1,2})\.(?P<second>\d{1,2})-d:(?P<day>\d{1,2})/(?P<month>\d{1,2})/(?P<year>\d{4})$"
)
LEFT_PATTERNS = ("left", "l eye", "os", "this is the left eye", "left eye")
RIGHT_PATTERNS = ("right", "rigth", "r eye", "od", "this is the right eye", "right eye")


@dataclass
class LegacyImportWarning:
    warning_type: str
    legacy_patient_id: int
    legacy_visit_id: int | None
    detail: str


@dataclass
class LegacyImportReport:
    patients_created: int = 0
    patients_reused: int = 0
    sessions_created: int = 0
    sessions_reused: int = 0
    images_imported: int = 0
    images_reused: int = 0
    warnings: list[LegacyImportWarning] | None = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []

    def to_dict(self) -> dict[str, object]:
        return {
            "patients_created": self.patients_created,
            "patients_reused": self.patients_reused,
            "sessions_created": self.sessions_created,
            "sessions_reused": self.sessions_reused,
            "images_imported": self.images_imported,
            "images_reused": self.images_reused,
            "warnings": [asdict(warning) for warning in self.warnings or []],
        }


def parse_legacy_dob(value: str) -> date:
    match = LEGACY_DATE_RE.match(value.strip())
    if not match:
        raise ValueError(f"Invalid legacy DOB: {value}")
    return date(
        int(match.group("year")),
        int(match.group("month")),
        int(match.group("day")),
    )


def parse_legacy_visit_timestamp(value: str) -> datetime:
    match = LEGACY_VISIT_RE.match(value.strip())
    if not match:
        raise ValueError(f"Invalid legacy visit timestamp: {value}")
    return datetime(
        int(match.group("year")),
        int(match.group("month")),
        int(match.group("day")),
        int(match.group("hour")),
        int(match.group("minute")),
        int(match.group("second")),
        tzinfo=timezone.utc,
    )


def infer_laterality_from_note_text(note_text: str | None) -> tuple[str, bool]:
    if not note_text:
        return "unknown", False

    normalized = " ".join(note_text.strip().lower().split())
    if not normalized:
        return "unknown", False
    if normalized in {"l", "left"}:
        return "left", True
    if normalized in {"r", "right"}:
        return "right", True

    if any(pattern in normalized for pattern in LEFT_PATTERNS):
        return "left", True
    if any(pattern in normalized for pattern in RIGHT_PATTERNS):
        return "right", True
    return "unknown", False


def load_note_text(notes_path: Path) -> str | None:
    if not notes_path.exists():
        return None
    text = notes_path.read_text(encoding="utf-8", errors="replace").strip()
    return text or None


def import_warning(
    report: LegacyImportReport,
    *,
    warning_type: str,
    legacy_patient_id: int,
    legacy_visit_id: int | None,
    detail: str,
) -> None:
    report.warnings = report.warnings or []
    report.warnings.append(
        LegacyImportWarning(
            warning_type=warning_type,
            legacy_patient_id=legacy_patient_id,
            legacy_visit_id=legacy_visit_id,
            detail=detail,
        )
    )


def patient_for_legacy_row(db: Session, row: sqlite3.Row, report: LegacyImportReport) -> Patient:
    legacy_patient_id = int(row["patient_id"])
    patient = db.scalar(select(Patient).where(Patient.legacy_patient_id == legacy_patient_id))
    if patient is not None:
        report.patients_reused += 1
        return patient

    first_name = normalize_name(str(row["firstname"]))
    last_name = normalize_name(str(row["lastname"]))
    archived = bool(row["archived"])
    patient = Patient(
        legacy_patient_id=legacy_patient_id,
        first_name=first_name,
        last_name=last_name,
        normalized_first_name=normalize_upper(first_name),
        normalized_last_name=normalize_upper(last_name),
        display_name=f"{last_name}, {first_name}",
        date_of_birth=parse_legacy_dob(str(row["dob"])),
        gender_text=normalize_upper(str(row["gender"])) if row["gender"] else None,
        archived_at=utc_now() if archived else None,
    )
    db.add(patient)
    db.flush()
    report.patients_created += 1
    return patient


def session_for_legacy_visit(
    db: Session,
    *,
    patient: Patient,
    legacy_visit_id: int,
    captured_at: datetime,
    archived: bool,
    report: LegacyImportReport,
) -> StudySession:
    session_obj = db.scalar(
        select(StudySession).where(
            StudySession.patient_id == patient.id,
            StudySession.legacy_visit_id == legacy_visit_id,
        )
    )
    if session_obj is not None:
        report.sessions_reused += 1
        return session_obj

    session_obj = StudySession(
        patient_id=patient.id,
        legacy_visit_id=legacy_visit_id,
        session_date=captured_at.date(),
        captured_at=captured_at,
        operator_name=None,
        status="draft",
        source="legacy_import",
        notes="Imported from legacy visit" + (" (archived)." if archived else "."),
    )
    db.add(session_obj)
    db.flush()
    report.sessions_created += 1
    return session_obj


def image_for_legacy_visit(
    db: Session,
    *,
    session_obj: StudySession,
    patient: Patient,
    legacy_visit_id: int,
    legacy_image_filename: str,
    legacy_notes_filename: str,
    note_text: str | None,
    image_path: Path,
    report: LegacyImportReport,
) -> RetinalImage | None:
    existing = db.scalar(select(RetinalImage).where(RetinalImage.legacy_visit_id == legacy_visit_id))
    if existing is not None:
        report.images_reused += 1
        return existing

    if not image_path.exists():
        import_warning(
            report,
            warning_type="missing_image",
            legacy_patient_id=patient.legacy_patient_id or 0,
            legacy_visit_id=legacy_visit_id,
            detail=f"Missing legacy image file {legacy_image_filename}",
        )
        return None

    laterality, inferred = infer_laterality_from_note_text(note_text)
    try:
        stored = store_file_path(str(uuid4()), image_path)
    except StorageValidationError as exc:
        import_warning(
            report,
            warning_type="invalid_image",
            legacy_patient_id=patient.legacy_patient_id or 0,
            legacy_visit_id=legacy_visit_id,
            detail=f"Legacy image file {legacy_image_filename} could not be imported: {exc}",
        )
        return None
    image = RetinalImage(
        session_id=session_obj.id,
        patient_id=patient.id,
        laterality=laterality,
        image_type="other",
        captured_at=session_obj.captured_at,
        original_filename=legacy_image_filename,
        stored_filename=stored.stored_filename,
        storage_relpath=stored.storage_relpath,
        thumbnail_relpath=stored.thumbnail_relpath,
        mime_type=stored.mime_type,
        file_extension=stored.file_extension,
        file_size_bytes=stored.file_size_bytes,
        sha256=stored.sha256,
        width_px=stored.width_px,
        height_px=stored.height_px,
        thumbnail_width_px=stored.thumbnail_width_px,
        thumbnail_height_px=stored.thumbnail_height_px,
        notes=note_text,
        legacy_visit_id=legacy_visit_id,
        legacy_notes_filename=legacy_notes_filename,
        legacy_image_filename=legacy_image_filename,
    )
    db.add(image)
    db.flush()
    report.images_imported += 1

    warning_parts: list[str] = []
    if note_text is None:
        warning_parts.append(f"Missing legacy notes file {legacy_notes_filename}")
        import_warning(
            report,
            warning_type="missing_notes",
            legacy_patient_id=patient.legacy_patient_id or 0,
            legacy_visit_id=legacy_visit_id,
            detail=f"Missing legacy notes file {legacy_notes_filename}",
        )
    if inferred:
        warning_parts.append(f"Laterality inferred as {laterality} from note text")
    if warning_parts:
        session_obj.notes = "\n".join(warning_parts)

    return image


def import_legacy_dataset(legacy_root: Path, db: Session) -> LegacyImportReport:
    report = LegacyImportReport()
    database_path = legacy_root / "database_dir" / "patient_database.db"
    image_root = legacy_root / "image_data_dir"
    note_root = legacy_root / "text_data_dir"

    if not database_path.exists():
        raise FileNotFoundError(f"Legacy database not found: {database_path}")

    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        patient_rows = connection.execute(
            "SELECT patient_id, firstname, lastname, dob, gender, archived FROM patients ORDER BY patient_id"
        ).fetchall()

        patient_map: dict[int, Patient] = {}
        for row in patient_rows:
            patient = patient_for_legacy_row(db, row, report)
            patient_map[int(row["patient_id"])] = patient

        visit_rows = connection.execute(
            "SELECT visit_id, patient_id, d, image_path, notes, archived FROM visits ORDER BY patient_id, visit_id"
        ).fetchall()

        for row in visit_rows:
            legacy_patient_id = int(row["patient_id"])
            patient = patient_map[legacy_patient_id]
            legacy_visit_id = int(row["visit_id"])
            captured_at = parse_legacy_visit_timestamp(str(row["d"]))
            session_obj = session_for_legacy_visit(
                db,
                patient=patient,
                legacy_visit_id=legacy_visit_id,
                captured_at=captured_at,
                archived=bool(row["archived"]),
                report=report,
            )

            legacy_image_filename = str(row["image_path"])
            legacy_notes_filename = str(row["notes"])
            note_text = load_note_text(note_root / legacy_notes_filename)
            image = image_for_legacy_visit(
                db,
                session_obj=session_obj,
                patient=patient,
                legacy_visit_id=legacy_visit_id,
                legacy_image_filename=legacy_image_filename,
                legacy_notes_filename=legacy_notes_filename,
                note_text=note_text,
                image_path=image_root / legacy_image_filename,
                report=report,
            )

            session_obj.status = "completed" if image is not None else "draft"
            warning_parts = []
            if not (image_root / legacy_image_filename).exists():
                warning_parts.append(f"Missing legacy image file {legacy_image_filename}")
            if note_text is None:
                warning_parts.append(f"Missing legacy notes file {legacy_notes_filename}")
                if image is None:
                    import_warning(
                        report,
                        warning_type="missing_notes",
                        legacy_patient_id=legacy_patient_id,
                        legacy_visit_id=legacy_visit_id,
                        detail=f"Missing legacy notes file {legacy_notes_filename}",
                    )
            laterality, inferred = infer_laterality_from_note_text(note_text)
            if inferred:
                warning_parts.append(f"Laterality inferred as {laterality} from note text")
                import_warning(
                    report,
                    warning_type="laterality_inferred",
                    legacy_patient_id=legacy_patient_id,
                    legacy_visit_id=legacy_visit_id,
                    detail=f"Laterality inferred as {laterality} from note text",
                )
            if warning_parts:
                session_obj.notes = "\n".join(warning_parts)

            if bool(row["archived"]):
                import_warning(
                    report,
                    warning_type="archived_visit",
                    legacy_patient_id=legacy_patient_id,
                    legacy_visit_id=legacy_visit_id,
                    detail="Legacy visit was archived.",
                )

    log_audit_event(
        db,
        action="legacy_import_completed",
        entity_type="system",
        entity_id=str(database_path),
        source="legacy_import",
        summary=(
            f"Imported legacy dataset from {legacy_root.name}: "
            f"{report.patients_created} patients, {report.sessions_created} sessions, {report.images_imported} images created"
        ),
        payload=report.to_dict(),
    )
    db.commit()
    return report
