from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .constants import IMAGE_TYPE_VALUES, LATERALITY_VALUES, SESSION_SOURCE_VALUES, SESSION_STATUS_VALUES
from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        Index("ix_patients_lookup", "normalized_last_name", "normalized_first_name", "date_of_birth"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    legacy_patient_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120))
    normalized_first_name: Mapped[str] = mapped_column(String(120), index=True)
    normalized_last_name: Mapped[str] = mapped_column(String(120), index=True)
    display_name: Mapped[str] = mapped_column(String(255), index=True)
    date_of_birth: Mapped[date]
    gender_text: Mapped[str | None] = mapped_column(String(32), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    sessions: Mapped[list[StudySession]] = relationship(
        back_populates="patient",
        cascade="all, delete-orphan",
        order_by="desc(StudySession.session_date)",
    )


class StudySession(Base):
    __tablename__ = "study_sessions"
    __table_args__ = (
        CheckConstraint(
            f"status IN {SESSION_STATUS_VALUES}",
            name="ck_study_sessions_status",
        ),
        CheckConstraint(
            f"source IN {SESSION_SOURCE_VALUES}",
            name="ck_study_sessions_source",
        ),
        Index("ix_study_sessions_patient_date", "patient_id", "session_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("patients.id"), index=True)
    session_date: Mapped[date] = mapped_column(Date, index=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operator_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    source: Mapped[str] = mapped_column(String(32), default="filesystem_import")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    patient: Mapped[Patient] = relationship(back_populates="sessions")
    images: Mapped[list[RetinalImage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="desc(RetinalImage.imported_at)",
    )


class RetinalImage(Base):
    __tablename__ = "retinal_images"
    __table_args__ = (
        CheckConstraint(
            f"laterality IN {LATERALITY_VALUES}",
            name="ck_retinal_images_laterality",
        ),
        CheckConstraint(
            f"image_type IN {IMAGE_TYPE_VALUES}",
            name="ck_retinal_images_image_type",
        ),
        CheckConstraint("file_size_bytes >= 0", name="ck_retinal_images_file_size_nonnegative"),
        CheckConstraint("width_px IS NULL OR width_px >= 1", name="ck_retinal_images_width_positive"),
        CheckConstraint("height_px IS NULL OR height_px >= 1", name="ck_retinal_images_height_positive"),
        Index("ix_retinal_images_session_laterality", "session_id", "laterality"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("study_sessions.id"), index=True)
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("patients.id"), index=True)
    laterality: Mapped[str] = mapped_column(String(16), default="unknown")
    image_type: Mapped[str] = mapped_column(String(32), default="color_fundus")
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    storage_relpath: Mapped[str] = mapped_column(String(512), unique=True)
    thumbnail_relpath: Mapped[str | None] = mapped_column(String(512), unique=True, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_extension: Mapped[str | None] = mapped_column(String(32), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_visit_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    legacy_notes_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legacy_image_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    session: Mapped[StudySession] = relationship(back_populates="images")
