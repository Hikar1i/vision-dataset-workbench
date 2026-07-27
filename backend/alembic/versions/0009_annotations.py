import sqlalchemy as sa
from alembic import op

revision = "0009_annotations"
down_revision = "0008_label_description_zh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "frames",
        sa.Column(
            "annotation_revision",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.create_table(
        "annotations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "frame_id",
            sa.String(36),
            sa.ForeignKey("frames.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "label_id",
            sa.String(36),
            sa.ForeignKey("labels.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("x_min", sa.Integer(), nullable=False),
        sa.Column("y_min", sa.Integer(), nullable=False),
        sa.Column("x_max", sa.Integer(), nullable=False),
        sa.Column("y_max", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "x_min >= 0 AND y_min >= 0 AND x_max > x_min AND y_max > y_min",
            name="ck_annotations_bounds",
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'model')",
            name="ck_annotations_source",
        ),
    )
    op.create_index("ix_annotations_frame_id", "annotations", ["frame_id"])
    op.create_index("ix_annotations_label_id", "annotations", ["label_id"])


def downgrade() -> None:
    op.drop_table("annotations")
    with op.batch_alter_table("frames") as batch_op:
        batch_op.drop_column("annotation_revision")
