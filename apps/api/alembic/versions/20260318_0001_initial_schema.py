"""Initial schema"""

from alembic import op
import sqlalchemy as sa


revision = "20260318_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("legacy_patient_id", sa.Integer(), nullable=True),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("normalized_first_name", sa.String(length=120), nullable=False),
        sa.Column("normalized_last_name", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("gender_text", sa.String(length=32), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patients_legacy_patient_id", "patients", ["legacy_patient_id"], unique=False)
    op.create_index("ix_patients_normalized_first_name", "patients", ["normalized_first_name"], unique=False)
    op.create_index("ix_patients_normalized_last_name", "patients", ["normalized_last_name"], unique=False)
    op.create_index("ix_patients_display_name", "patients", ["display_name"], unique=False)
    op.create_index(
        "ix_patients_lookup",
        "patients",
        ["normalized_last_name", "normalized_first_name", "date_of_birth"],
        unique=False,
    )

    op.create_table(
        "study_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("operator_name", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source IN ('filesystem_import', 'legacy_import')", name="ck_study_sessions_source"),
        sa.CheckConstraint("status IN ('draft', 'completed')", name="ck_study_sessions_status"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_study_sessions_patient_id", "study_sessions", ["patient_id"], unique=False)
    op.create_index("ix_study_sessions_session_date", "study_sessions", ["session_date"], unique=False)
    op.create_index("ix_study_sessions_patient_date", "study_sessions", ["patient_id", "session_date"], unique=False)

    op.create_table(
        "retinal_images",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("laterality", sa.String(length=16), nullable=False),
        sa.Column("image_type", sa.String(length=32), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_relpath", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("file_extension", sa.String(length=32), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("legacy_visit_id", sa.Integer(), nullable=True),
        sa.Column("legacy_notes_filename", sa.String(length=255), nullable=True),
        sa.Column("legacy_image_filename", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "file_size_bytes >= 0",
            name="ck_retinal_images_file_size_nonnegative",
        ),
        sa.CheckConstraint(
            "height_px IS NULL OR height_px >= 1",
            name="ck_retinal_images_height_positive",
        ),
        sa.CheckConstraint(
            "image_type IN ('color_fundus', 'red_free', 'fluorescein', 'autofluorescence', 'oct', 'external_photo', 'other')",
            name="ck_retinal_images_image_type",
        ),
        sa.CheckConstraint(
            "laterality IN ('left', 'right', 'both', 'unknown')",
            name="ck_retinal_images_laterality",
        ),
        sa.CheckConstraint(
            "width_px IS NULL OR width_px >= 1",
            name="ck_retinal_images_width_positive",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["study_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_relpath"),
    )
    op.create_index("ix_retinal_images_session_id", "retinal_images", ["session_id"], unique=False)
    op.create_index("ix_retinal_images_patient_id", "retinal_images", ["patient_id"], unique=False)
    op.create_index("ix_retinal_images_imported_at", "retinal_images", ["imported_at"], unique=False)
    op.create_index("ix_retinal_images_sha256", "retinal_images", ["sha256"], unique=False)
    op.create_index("ix_retinal_images_legacy_visit_id", "retinal_images", ["legacy_visit_id"], unique=False)
    op.create_index(
        "ix_retinal_images_session_laterality",
        "retinal_images",
        ["session_id", "laterality"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_retinal_images_session_laterality", table_name="retinal_images")
    op.drop_index("ix_retinal_images_legacy_visit_id", table_name="retinal_images")
    op.drop_index("ix_retinal_images_sha256", table_name="retinal_images")
    op.drop_index("ix_retinal_images_imported_at", table_name="retinal_images")
    op.drop_index("ix_retinal_images_patient_id", table_name="retinal_images")
    op.drop_index("ix_retinal_images_session_id", table_name="retinal_images")
    op.drop_table("retinal_images")

    op.drop_index("ix_study_sessions_patient_date", table_name="study_sessions")
    op.drop_index("ix_study_sessions_session_date", table_name="study_sessions")
    op.drop_index("ix_study_sessions_patient_id", table_name="study_sessions")
    op.drop_table("study_sessions")

    op.drop_index("ix_patients_lookup", table_name="patients")
    op.drop_index("ix_patients_display_name", table_name="patients")
    op.drop_index("ix_patients_normalized_last_name", table_name="patients")
    op.drop_index("ix_patients_normalized_first_name", table_name="patients")
    op.drop_index("ix_patients_legacy_patient_id", table_name="patients")
    op.drop_table("patients")
