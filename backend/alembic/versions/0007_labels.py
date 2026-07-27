import sqlalchemy as sa
from alembic import op

revision = "0007_labels"
down_revision = "0006_video_enabled_limit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "labels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("name_normalized", sa.String(64), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sort_order >= 0", name="ck_labels_sort_order"),
    )
    op.create_index("ix_labels_project_id", "labels", ["project_id"])
    op.create_index(
        "uq_labels_project_name",
        "labels",
        ["project_id", "name_normalized"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("labels")
