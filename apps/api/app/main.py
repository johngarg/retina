from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from .config import DATA_DIR, ensure_app_dirs
from .database import SessionLocal, get_db
from .maintenance import backfill_missing_thumbnails
from .migrations import run_migrations
from .models import Patient, RetinalImage, StudySession
from .schemas import (
    HealthResponse,
    ImageDetail,
    ImageImportForm,
    ImageUpdate,
    PatientCreate,
    PatientDetail,
    PatientSummary,
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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def patient_query() -> select:
    return select(Patient).options(
        selectinload(Patient.sessions).selectinload(StudySession.images)
    )


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
    return HealthResponse(status="ok")


@app.get("/patients", response_model=list[PatientSummary])
def list_patients(
    q: str | None = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
) -> list[Patient]:
    stmt = select(Patient).where(Patient.archived_at.is_(None))
    if q:
        like = f"%{q.strip().upper()}%"
        conditions = [func.upper(Patient.display_name).like(like)]
        if q.strip().isdigit():
            conditions.append(cast(Patient.legacy_patient_id, String).like(f"%{q.strip()}%"))
        stmt = stmt.where(or_(*conditions))
    stmt = stmt.order_by(Patient.last_name.asc(), Patient.first_name.asc())
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
    db.commit()
    db.refresh(patient)
    return patient


@app.get("/patients/{patient_id}", response_model=PatientDetail)
def get_patient(patient_id: str, db: Session = Depends(get_db)) -> Patient:
    return get_patient_or_404(db, patient_id)


@app.get("/patients/{patient_id}/sessions", response_model=list[SessionSummary])
def list_patient_sessions(patient_id: str, db: Session = Depends(get_db)) -> list[StudySession]:
    patient = get_patient_or_404(db, patient_id)
    return patient.sessions


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


@app.get("/images/{image_id}/thumbnail")
def get_image_thumbnail(image_id: str, db: Session = Depends(get_db)) -> FileResponse:
    image = get_image_or_404(db, image_id)
    if not image.thumbnail_relpath:
        raise HTTPException(status_code=404, detail="Thumbnail is not available")

    path = DATA_DIR / Path(image.thumbnail_relpath)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored thumbnail file is missing")
    return FileResponse(path, media_type="image/png", filename=f"{image.id}-thumbnail.png")
