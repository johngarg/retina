"""Add retinal image thumbnails"""

from alembic import op
import sqlalchemy as sa


revision = "20260318_0002"
down_revision = "20260318_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("retinal_images", sa.Column("thumbnail_relpath", sa.String(length=512), nullable=True))
    op.add_column("retinal_images", sa.Column("thumbnail_width_px", sa.Integer(), nullable=True))
    op.add_column("retinal_images", sa.Column("thumbnail_height_px", sa.Integer(), nullable=True))
    op.create_index(
        "ux_retinal_images_thumbnail_relpath",
        "retinal_images",
        ["thumbnail_relpath"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_retinal_images_thumbnail_relpath", table_name="retinal_images")
    op.drop_column("retinal_images", "thumbnail_height_px")
    op.drop_column("retinal_images", "thumbnail_width_px")
    op.drop_column("retinal_images", "thumbnail_relpath")
