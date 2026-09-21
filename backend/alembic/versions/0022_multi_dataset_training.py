import sqlalchemy as sa
from alembic import op

revision = "0022_multi_dataset_training"
down_revision = "0021_user_llm_configs"
branch_labels = None
depends_on = None


TASK_STATUSES = (
    "'draft','preparing','preparation_failed','queued','running','canceling',"
    "'canceled','start_failed','failed','partial','succeeded'"
)
MODEL_STATUSES = (
    "'draft','preparing','preparation_failed','queued','running','canceling',"
    "'canceled','start_failed','failed','succeeded'"
)


def upgrade() -> None:
    with op.batch_alter_table("training_tasks", recreate="always") as batch:
        batch.add_column(
            sa.Column(
                "default_dataset_mode", sa.String(16), nullable=False, server_default="single"
            )
        )
        batch.add_column(sa.Column("default_multi_dataset_config", sa.Text(), nullable=True))
        batch.drop_constraint("ck_training_tasks_status", type_="check")
        batch.create_check_constraint(
            "ck_training_tasks_status", f"status IN ({TASK_STATUSES})"
        )
    with op.batch_alter_table("training_models", recreate="always") as batch:
        batch.add_column(
            sa.Column("dataset_mode", sa.String(16), nullable=False, server_default="inherit")
        )
        batch.add_column(sa.Column("multi_dataset_config", sa.Text(), nullable=True))
        batch.drop_constraint("ck_training_models_status", type_="check")
        batch.create_check_constraint(
            "ck_training_models_status", f"status IN ({MODEL_STATUSES})"
        )
    op.create_table(
        "training_preparations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "training_task_id",
            sa.String(36),
            sa.ForeignKey("training_tasks.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("phase", sa.String(32), nullable=False, server_default="waiting"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("run_token", sa.String(64), nullable=False, unique=True),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued','running','canceling','canceled','failed','succeeded')",
            name="ck_training_preparations_status",
        ),
        sa.CheckConstraint(
            "progress >= 0 AND progress <= 100", name="ck_training_preparations_progress"
        ),
        sa.CheckConstraint(
            "processed >= 0 AND total >= 0", name="ck_training_preparations_counts"
        ),
    )
    op.create_index(
        "ix_training_preparations_training_task_id",
        "training_preparations",
        ["training_task_id"],
        unique=True,
    )
    op.create_index(
        "ix_training_preparations_status", "training_preparations", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_training_preparations_status", table_name="training_preparations")
    op.drop_index(
        "ix_training_preparations_training_task_id", table_name="training_preparations"
    )
    op.drop_table("training_preparations")
    with op.batch_alter_table("training_models", recreate="always") as batch:
        batch.drop_column("multi_dataset_config")
        batch.drop_column("dataset_mode")
        batch.drop_constraint("ck_training_models_status", type_="check")
        batch.create_check_constraint(
            "ck_training_models_status",
            "status IN ('draft','queued','running','canceling','canceled','start_failed','failed','succeeded')",
        )
    with op.batch_alter_table("training_tasks", recreate="always") as batch:
        batch.drop_column("default_multi_dataset_config")
        batch.drop_column("default_dataset_mode")
        batch.drop_constraint("ck_training_tasks_status", type_="check")
        batch.create_check_constraint(
            "ck_training_tasks_status",
            "status IN ('draft','queued','running','canceling','canceled','start_failed','failed','partial','succeeded')",
        )
