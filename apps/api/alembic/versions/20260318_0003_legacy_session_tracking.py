"""Track legacy visit ids on study sessions"""

from alembic import op
import sqlalchemy as sa


revision = "20260318_0003"
down_revision = "20260318_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("study_sessions", sa.Column("legacy_visit_id", sa.Integer(), nullable=True))
    op.create_index("ix_study_sessions_legacy_visit_id", "study_sessions", ["legacy_visit_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_study_sessions_legacy_visit_id", table_name="study_sessions")
    op.drop_column("study_sessions", "legacy_visit_id")
