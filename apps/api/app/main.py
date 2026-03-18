from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import platform
import subprocess
import tempfile
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from .audit import log_audit_event
from .backup import BackupValidationError, create_backup_archive, restore_backup_archive
from .config import DATA_DIR, ensure_app_dirs
from .constants import IMAGE_TYPE_VALUES, LATERALITY_VALUES
from .database import SessionLocal, get_db
from .maintenance import backfill_missing_thumbnails
from .migrations import run_migrations
from .models import Patient, RetinalImage, StudySession
from .schemas import (
    HealthResponse,
    BackupSummary,
    ImageDetail,
    ImageImportForm,
    ImageSummary,
    ImageUpdate,
    PatientCreate,
    PatientDetail,
    PatientSummary,
    RestoreSummary,
    SessionCreate,
    SessionSummary,
    SessionUpdate,
)
from .storage import (
    StorageValidationError,
    normalize_name,
    normalize_upper,
    remove_storage_artifacts,
    store_upload,
)


ensure_app_dirs()
run_migrations()
with SessionLocal() as startup_session:
    backfill_missing_thumbnails(startup_session)

app = FastAPI(title="Retina API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_origin_regex=r"^https?://[a-z0-9-]+\.localhost$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def patient_query() -> select:
    return select(Patient).options(
        selectinload(Patient.sessions).selectinload(StudySession.images)
    )


def normalize_optional_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def validate_optional_choice(name: str, value: str | None, allowed_values: tuple[str, ...]) -> str | None:
    normalized = normalize_optional_filter(value)
    if normalized is None:
        return None
    if normalized not in allowed_values:
        allowed_text = ", ".join(allowed_values)
        raise HTTPException(status_code=400, detail=f"{name} must be one of: {allowed_text}")
    return normalized


def filtered_images(
    session_obj: StudySession,
    *,
    laterality: str | None,
    image_type: str | None,
) -> list[RetinalImage]:
    return [
        image
        for image in session_obj.images
        if (laterality is None or image.laterality == laterality)
        and (image_type is None or image.image_type == image_type)
    ]


def filtered_session_summaries(
    patient: Patient,
    *,
    session_date_from: date | None,
    session_date_to: date | None,
    laterality: str | None,
    image_type: str | None,
) -> list[SessionSummary]:
    filtered_sessions: list[SessionSummary] = []
    image_filters_active = laterality is not None or image_type is not None

    for session_obj in patient.sessions:
        if session_date_from and session_obj.session_date < session_date_from:
            continue
        if session_date_to and session_obj.session_date > session_date_to:
            continue

        matching_images = filtered_images(session_obj, laterality=laterality, image_type=image_type)
        if image_filters_active and not matching_images:
            continue

        session_summary = SessionSummary.model_validate(session_obj, from_attributes=True)
        session_summary.images = [
            ImageSummary.model_validate(image, from_attributes=True) for image in matching_images
        ]
        filtered_sessions.append(session_summary)

    return filtered_sessions


def patient_detail_response(
    patient: Patient,
    *,
    session_date_from: date | None,
    session_date_to: date | None,
    laterality: str | None,
    image_type: str | None,
) -> PatientDetail:
    detail = PatientDetail.model_validate(patient, from_attributes=True)
    detail.sessions = filtered_session_summaries(
        patient,
        session_date_from=session_date_from,
        session_date_to=session_date_to,
        laterality=laterality,
        image_type=image_type,
    )
    return detail


def get_patient_or_404(db: Session, patient_id: str) -> Patient:
    patient = db.scalar(
        patient_query().where(
            Patient.id == patient_id,
            Patient.archived_at.is_(None),
        )
    )
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


def get_session_or_404(db: Session, session_id: str) -> StudySession:
    session_obj = db.scalar(
        select(StudySession)
        .options(selectinload(StudySession.images))
        .where(StudySession.id == session_id)
    )
    if session_obj is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session_obj


def get_image_or_404(db: Session, image_id: str) -> RetinalImage:
    image = db.scalar(select(RetinalImage).where(RetinalImage.id == image_id))
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return image


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version="0.1.0", backup_restore=True)


@app.post("/backups/export", response_model=BackupSummary, status_code=201)
def export_backup(db: Session = Depends(get_db)) -> BackupSummary:
    result = create_backup_archive(db)
    return BackupSummary.model_validate(result.to_dict())


@app.post("/backups/restore", response_model=RestoreSummary)
def restore_backup(file: UploadFile = File(...)) -> RestoreSummary:
    suffix = Path(file.filename or "backup.zip").suffix or ".zip"
    with tempfile.NamedTemporaryFile(prefix="retina-restore-upload-", suffix=suffix, delete=False) as temp_file:
        temp_path = Path(temp_file.name)
        temp_file.write(file.file.read())

    try:
        result = restore_backup_archive(temp_path, source_archive_name=file.filename)
    except BackupValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        file.file.close()
        if temp_path.exists():
            temp_path.unlink()

    return RestoreSummary.model_validate(result.to_dict())


@app.get("/patients", response_model=list[PatientSummary])
def list_patients(
    q: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[Patient]:
    stmt = select(Patient).where(Patient.archived_at.is_(None))
    if q:
        tokens = [token.upper() for token in q.replace(",", " ").split() if token.strip()]
        token_conditions = []
        for token in tokens:
            like = f"%{token}%"
            conditions = [
                Patient.normalized_first_name.like(like),
                Patient.normalized_last_name.like(like),
                func.upper(Patient.display_name).like(like),
            ]
            if token.isdigit():
                conditions.append(cast(Patient.legacy_patient_id, String).like(f"%{token}%"))
            token_conditions.append(or_(*conditions))
        if token_conditions:
            stmt = stmt.where(and_(*token_conditions))
    stmt = stmt.order_by(Patient.last_name.asc(), Patient.first_name.asc()).limit(limit)
    return list(db.scalars(stmt))


@app.post("/patients", response_model=PatientSummary, status_code=201)
def create_patient(payload: PatientCreate, db: Session = Depends(get_db)) -> Patient:
    first_name = normalize_name(payload.first_name)
    last_name = normalize_name(payload.last_name)
    normalized_first = normalize_upper(payload.first_name)
    normalized_last = normalize_upper(payload.last_name)
    gender_text = normalize_upper(payload.gender_text) if payload.gender_text else None

    existing = db.scalar(
        select(Patient).where(
            Patient.archived_at.is_(None),
            Patient.normalized_first_name == normalized_first,
            Patient.normalized_last_name == normalized_last,
            Patient.date_of_birth == payload.date_of_birth,
            Patient.gender_text == gender_text,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Patient already exists")

    patient = Patient(
        first_name=first_name,
        last_name=last_name,
        normalized_first_name=normalized_first,
        normalized_last_name=normalized_last,
        display_name=f"{last_name}, {first_name}",
        date_of_birth=payload.date_of_birth,
        gender_text=gender_text,
    )
    db.add(patient)
    db.flush()
    log_audit_event(
        db,
        action="patient_created",
        entity_type="patient",
        entity_id=patient.id,
        patient_id=patient.id,
        source="api",
        summary=f"Created patient {patient.display_name}",
        payload={
            "date_of_birth": payload.date_of_birth.isoformat(),
            "gender_text": gender_text,
        },
    )
    db.commit()
    db.refresh(patient)
    return patient


@app.get("/patients/{patient_id}", response_model=PatientDetail)
def get_patient(
    patient_id: str,
    session_date_from: date | None = Query(default=None),
    session_date_to: date | None = Query(default=None),
    laterality: str | None = Query(default=None),
    image_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PatientDetail:
    patient = get_patient_or_404(db, patient_id)
    normalized_laterality = validate_optional_choice(
        "laterality",
        laterality,
        LATERALITY_VALUES,
    )
    normalized_image_type = validate_optional_choice(
        "image_type",
        image_type,
        IMAGE_TYPE_VALUES,
    )
    return patient_detail_response(
        patient,
        session_date_from=session_date_from,
        session_date_to=session_date_to,
        laterality=normalized_laterality,
        image_type=normalized_image_type,
    )


@app.get("/patients/{patient_id}/sessions", response_model=list[SessionSummary])
def list_patient_sessions(
    patient_id: str,
    session_date_from: date | None = Query(default=None),
    session_date_to: date | None = Query(default=None),
    laterality: str | None = Query(default=None),
    image_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[SessionSummary]:
    patient = get_patient_or_404(db, patient_id)
    normalized_laterality = validate_optional_choice(
        "laterality",
        laterality,
        LATERALITY_VALUES,
    )
    normalized_image_type = validate_optional_choice(
        "image_type",
        image_type,
        IMAGE_TYPE_VALUES,
    )
    return filtered_session_summaries(
        patient,
        session_date_from=session_date_from,
        session_date_to=session_date_to,
        laterality=normalized_laterality,
        image_type=normalized_image_type,
    )


@app.post("/patients/{patient_id}/sessions", response_model=SessionSummary, status_code=201)
def create_session(
    patient_id: str,
    payload: SessionCreate,
    db: Session = Depends(get_db),
) -> StudySession:
    patient = get_patient_or_404(db, patient_id)
    session_obj = StudySession(
        patient_id=patient.id,
        session_date=payload.session_date,
        captured_at=payload.captured_at,
        operator_name=normalize_name(payload.operator_name) if payload.operator_name else None,
        notes=payload.notes.strip() if payload.notes else None,
        status="draft",
        source="filesystem_import",
    )
    db.add(session_obj)
    db.flush()
    log_audit_event(
        db,
        action="session_created",
        entity_type="session",
        entity_id=session_obj.id,
        patient_id=patient.id,
        session_id=session_obj.id,
        source="api",
        actor_name=session_obj.operator_name,
        summary=f"Created session for {patient.display_name} on {session_obj.session_date.isoformat()}",
        payload={
            "session_date": session_obj.session_date.isoformat(),
            "captured_at": session_obj.captured_at.isoformat() if session_obj.captured_at else None,
        },
    )
    db.commit()
    db.refresh(session_obj)
    return session_obj


@app.get("/sessions/{session_id}", response_model=SessionSummary)
def get_session(session_id: str, db: Session = Depends(get_db)) -> StudySession:
    return get_session_or_404(db, session_id)


@app.patch("/sessions/{session_id}", response_model=SessionSummary)
def update_session(
    session_id: str,
    payload: SessionUpdate,
    db: Session = Depends(get_db),
) -> StudySession:
    session_obj = get_session_or_404(db, session_id)

    if "session_date" in payload.model_fields_set:
        session_obj.session_date = payload.session_date or session_obj.session_date
    if "captured_at" in payload.model_fields_set:
        session_obj.captured_at = payload.captured_at
    if "operator_name" in payload.model_fields_set:
        session_obj.operator_name = (
            normalize_name(payload.operator_name) if payload.operator_name else None
        )
    if "notes" in payload.model_fields_set:
        session_obj.notes = payload.notes

    log_audit_event(
        db,
        action="session_updated",
        entity_type="session",
        entity_id=session_obj.id,
        patient_id=session_obj.patient_id,
        session_id=session_obj.id,
        source="api",
        actor_name=session_obj.operator_name,
        summary=f"Updated session {session_obj.id}",
        payload={field: getattr(session_obj, field) for field in sorted(payload.model_fields_set)},
    )
    db.commit()
    db.refresh(session_obj)
    return session_obj


@app.post("/sessions/{session_id}/images/import", response_model=ImageDetail, status_code=201)
def import_image(
    session_id: str,
    laterality: str = Form(...),
    image_type: str = Form("color_fundus"),
    notes: str | None = Form(default=None),
    captured_at: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> RetinalImage:
    session_obj = get_session_or_404(db, session_id)
    image_id = str(uuid4())

    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file is missing a filename")

    parsed_captured_at = None
    if captured_at:
        try:
            parsed_captured_at = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="captured_at must be ISO 8601") from exc

    try:
        form = ImageImportForm(
            laterality=laterality.strip().lower(),
            image_type=image_type.strip().lower(),
            notes=notes,
            captured_at=parsed_captured_at,
        )
    except ValidationError as exc:
        first_error = exc.errors()[0]
        field_name = ".".join(str(part) for part in first_error["loc"])
        raise HTTPException(status_code=400, detail=f"{field_name}: {first_error['msg']}") from exc

    stored = None
    try:
        stored = store_upload(image_id, file)
        image = RetinalImage(
            id=image_id,
            session_id=session_obj.id,
            patient_id=session_obj.patient_id,
            laterality=form.laterality,
            image_type=form.image_type,
            captured_at=form.captured_at,
            original_filename=file.filename,
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
            notes=form.notes,
        )
        session_obj.status = "completed"
        db.add(image)
        db.flush()
        log_audit_event(
            db,
            action="image_imported",
            entity_type="image",
            entity_id=image.id,
            patient_id=session_obj.patient_id,
            session_id=session_obj.id,
            image_id=image.id,
            source="api",
            actor_name=session_obj.operator_name,
            summary=f"Imported {image.laterality} {image.image_type} image into session {session_obj.id}",
            payload={
                "original_filename": image.original_filename,
                "laterality": image.laterality,
                "image_type": image.image_type,
            },
        )
        db.commit()
        db.refresh(image)
        return image
    except StorageValidationError as exc:
        db.rollback()
        if stored is not None:
            remove_storage_artifacts(stored.storage_relpath, stored.thumbnail_relpath)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        if stored is not None:
            remove_storage_artifacts(stored.storage_relpath, stored.thumbnail_relpath)
        raise HTTPException(status_code=500, detail=f"Image import failed: {exc}") from exc
    finally:
        file.file.close()


@app.get("/images/{image_id}", response_model=ImageDetail)
def get_image(image_id: str, db: Session = Depends(get_db)) -> RetinalImage:
    return get_image_or_404(db, image_id)


@app.patch("/images/{image_id}", response_model=ImageDetail)
def update_image(
    image_id: str,
    payload: ImageUpdate,
    db: Session = Depends(get_db),
) -> RetinalImage:
    image = get_image_or_404(db, image_id)

    if "laterality" in payload.model_fields_set:
        image.laterality = payload.laterality or image.laterality
    if "image_type" in payload.model_fields_set:
        image.image_type = payload.image_type or image.image_type
    if "captured_at" in payload.model_fields_set:
        image.captured_at = payload.captured_at
    if "notes" in payload.model_fields_set:
        image.notes = payload.notes

    log_audit_event(
        db,
        action="image_updated",
        entity_type="image",
        entity_id=image.id,
        patient_id=image.patient_id,
        session_id=image.session_id,
        image_id=image.id,
        source="api",
        summary=f"Updated image {image.id}",
        payload={field: getattr(image, field) for field in sorted(payload.model_fields_set)},
    )
    db.commit()
    db.refresh(image)
    return image


@app.get("/images/{image_id}/file")
def get_image_file(image_id: str, db: Session = Depends(get_db)) -> FileResponse:
    image = get_image_or_404(db, image_id)
    path = DATA_DIR / Path(image.storage_relpath)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored image file is missing")
    return FileResponse(path, media_type=image.mime_type, filename=image.original_filename)


def open_path_in_default_application(path: Path) -> None:
    system_name = platform.system().lower()
    if system_name == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    if system_name == "windows":
        subprocess.Popen(["cmd", "/c", "start", "", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])


@app.post("/images/{image_id}/open-external", status_code=204)
def open_image_externally(image_id: str, db: Session = Depends(get_db)) -> None:
    image = get_image_or_404(db, image_id)
    path = DATA_DIR / Path(image.storage_relpath)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored image file is missing")

    try:
        open_path_in_default_application(path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to open image externally: {exc}") from exc


@app.get("/images/{image_id}/thumbnail")
def get_image_thumbnail(image_id: str, db: Session = Depends(get_db)) -> FileResponse:
    image = get_image_or_404(db, image_id)
    if not image.thumbnail_relpath:
        raise HTTPException(status_code=404, detail="Thumbnail is not available")

    path = DATA_DIR / Path(image.thumbnail_relpath)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored thumbnail file is missing")
    return FileResponse(path, media_type="image/png", filename=f"{image.id}-thumbnail.png")
