import sqlalchemy as sa
from alembic import op

revision = "0013_dataset_exports"
down_revision = "0012_video_short_codes"
branch_labels = None
depends_on = None


def _task_type_constraint(values: str) -> None:
    with op.batch_alter_table("tasks", recreate="always") as batch:
        batch.drop_constraint("ck_tasks_type", type_="check")
        batch.create_check_constraint("ck_tasks_type", f"type IN ({values})")


def upgrade() -> None:
    _task_type_constraint(
        "'copy_video', 'download_video', 'extract_frames', "
        "'import_model', 'auto_annotate', 'export_dataset'"
    )
    op.create_table(
        "dataset_exports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column(
            "created_by_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("train_ratio", sa.Float(), nullable=False),
        sa.Column("actual_train_ratio", sa.Float(), nullable=True),
        sa.Column("total_frames", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("train_frames", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("val_frames", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label_snapshot", sa.Text(), nullable=False),
        sa.Column("source_snapshot", sa.Text(), nullable=False),
        sa.Column("manifest", sa.Text(), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'failed', 'canceled')",
            name="ck_dataset_exports_status",
        ),
        sa.CheckConstraint(
            "train_ratio >= 0 AND train_ratio <= 1",
            name="ck_dataset_exports_train_ratio",
        ),
        sa.CheckConstraint(
            "actual_train_ratio IS NULL OR "
            "(actual_train_ratio >= 0 AND actual_train_ratio <= 1)",
            name="ck_dataset_exports_actual_train_ratio",
        ),
        sa.CheckConstraint(
            "total_frames >= 0 AND train_frames >= 0 AND val_frames >= 0",
            name="ck_dataset_exports_frame_counts",
        ),
    )
    op.create_index("ix_dataset_exports_project_id", "dataset_exports", ["project_id"])
    op.create_index(
        "ix_dataset_exports_created_by_id", "dataset_exports", ["created_by_id"]
    )
    op.create_index(
        "ix_dataset_exports_project_created",
        "dataset_exports",
        ["project_id", "created_at"],
    )
    op.create_index(
        "uq_dataset_exports_active_project",
        "dataset_exports",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_table("dataset_exports")
    _task_type_constraint(
        "'copy_video', 'download_video', 'extract_frames', "
        "'import_model', 'auto_annotate'"
    )
