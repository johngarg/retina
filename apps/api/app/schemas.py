from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PatientCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    date_of_birth: date
    gender_text: str | None = Field(default=None, max_length=32)


class PatientSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    legacy_patient_id: int | None
    first_name: str
    last_name: str
    display_name: str
    date_of_birth: date
    gender_text: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SessionCreate(BaseModel):
    session_date: date
    captured_at: datetime | None = None
    operator_name: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class ImageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    patient_id: str
    laterality: str
    image_type: str
    captured_at: datetime | None
    imported_at: datetime
    original_filename: str
    stored_filename: str
    file_size_bytes: int
    width_px: int | None
    height_px: int | None
    notes: str | None
    legacy_visit_id: int | None


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    session_date: date
    captured_at: datetime | None
    operator_name: str | None
    status: str
    source: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    images: list[ImageSummary] = []


class PatientDetail(PatientSummary):
    sessions: list[SessionSummary] = []


class ImageDetail(ImageSummary):
    storage_relpath: str
    mime_type: str | None
    file_extension: str | None
    sha256: str
    legacy_notes_filename: str | None
    legacy_image_filename: str | None


class HealthResponse(BaseModel):
    status: str
