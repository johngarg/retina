from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import IMAGE_TYPE_VALUES, LATERALITY_VALUES


class PatientCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    date_of_birth: date
    gender_text: str | None = Field(default=None, max_length=32)

    @field_validator("first_name", "last_name", "gender_text")
    @classmethod
    def strip_string_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized


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

    @field_validator("operator_name", "notes")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        return normalized or None


class SessionUpdate(BaseModel):
    session_date: date | None = None
    captured_at: datetime | None = None
    operator_name: str | None = Field(default=None, max_length=120)
    notes: str | None = None

    @field_validator("operator_name", "notes")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        return normalized or None


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
    thumbnail_width_px: int | None
    thumbnail_height_px: int | None
    notes: str | None
    legacy_visit_id: int | None


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    legacy_visit_id: int | None = None
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
    thumbnail_relpath: str | None
    mime_type: str | None
    file_extension: str | None
    sha256: str
    legacy_notes_filename: str | None
    legacy_image_filename: str | None


class HealthResponse(BaseModel):
    status: str
    version: str
    backup_restore: bool


class BackupSummary(BaseModel):
    archive_path: str
    created_at: datetime
    patients: int
    sessions: int
    images: int
    audit_events: int
    original_files: int
    thumbnail_files: int
    size_bytes: int


class RestoreSummary(BaseModel):
    restored_at: datetime
    source_archive_name: str
    safety_backup_path: str
    patients: int
    sessions: int
    images: int
    audit_events: int
    original_files: int
    thumbnail_files: int


LateralityLiteral = Literal["left", "right", "both", "unknown"]
ImageTypeLiteral = Literal[
    "color_fundus",
    "red_free",
    "fluorescein",
    "autofluorescence",
    "oct",
    "external_photo",
    "other",
]


class ImageImportForm(BaseModel):
    laterality: LateralityLiteral
    image_type: ImageTypeLiteral = "color_fundus"
    notes: str | None = None
    captured_at: datetime | None = None

    @field_validator("laterality")
    @classmethod
    def validate_laterality(cls, value: str) -> str:
        if value not in LATERALITY_VALUES:
            raise ValueError("invalid laterality")
        return value

    @field_validator("image_type")
    @classmethod
    def validate_image_type(cls, value: str) -> str:
        if value not in IMAGE_TYPE_VALUES:
            raise ValueError("invalid image_type")
        return value

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ImageUpdate(BaseModel):
    laterality: LateralityLiteral | None = None
    image_type: ImageTypeLiteral | None = None
    notes: str | None = None
    captured_at: datetime | None = None

    @field_validator("laterality")
    @classmethod
    def validate_optional_laterality(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in LATERALITY_VALUES:
            raise ValueError("invalid laterality")
        return value

    @field_validator("image_type")
    @classmethod
    def validate_optional_image_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in IMAGE_TYPE_VALUES:
            raise ValueError("invalid image_type")
        return value

    @field_validator("notes")
    @classmethod
    def normalize_optional_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None
