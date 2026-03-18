"""Add audit events table"""

from alembic import op
import sqlalchemy as sa


revision = "20260318_0004"
down_revision = "20260318_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=True),
        sa.Column("patient_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("image_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("actor_name", sa.String(length=120), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "action IN ('patient_created', 'session_created', 'session_updated', 'image_imported', 'image_updated', 'legacy_import_completed', 'backup_created')",
            name="ck_audit_events_action",
        ),
        sa.CheckConstraint(
            "entity_type IN ('patient', 'session', 'image', 'system', 'backup')",
            name="ck_audit_events_entity_type",
        ),
        sa.CheckConstraint(
            "source IN ('api', 'legacy_import', 'backup')",
            name="ck_audit_events_source",
        ),
        sa.ForeignKeyConstraint(["image_id"], ["retinal_images.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["study_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"], unique=False)
    op.create_index(
        "ix_audit_events_patient_occurred_at",
        "audit_events",
        ["patient_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_patient_occurred_at", table_name="audit_events")
    op.drop_index("ix_audit_events_occurred_at", table_name="audit_events")
    op.drop_table("audit_events")
