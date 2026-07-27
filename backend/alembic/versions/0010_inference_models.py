import sqlalchemy as sa
from alembic import op

revision = "0010_inference_models"
down_revision = "0009_annotations"
branch_labels = None
depends_on = None


def _task_type_constraint(values: str) -> None:
    with op.batch_alter_table("tasks", recreate="always") as batch:
        batch.drop_constraint("ck_tasks_type", type_="check")
        batch.create_check_constraint("ck_tasks_type", f"type IN ({values})")


def upgrade() -> None:
    op.create_table(
        "inference_models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="copying"),
        sa.Column("storage_path", sa.Text()),
        sa.Column("source_name", sa.String(512), nullable=False),
        sa.Column(
            "created_by_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('yolo', 'grounding_dino')",
            name="ck_inference_models_kind",
        ),
        sa.CheckConstraint(
            "status IN ('copying', 'ready', 'failed')",
            name="ck_inference_models_status",
        ),
    )
    op.create_index("ix_inference_models_status", "inference_models", ["status"])
    op.create_index(
        "ix_inference_models_created_by_id", "inference_models", ["created_by_id"]
    )
    _task_type_constraint(
        "'copy_video', 'download_video', 'extract_frames', "
        "'import_model', 'auto_annotate'"
    )


def downgrade() -> None:
    _task_type_constraint("'copy_video', 'download_video', 'extract_frames'")
    op.drop_table("inference_models")
