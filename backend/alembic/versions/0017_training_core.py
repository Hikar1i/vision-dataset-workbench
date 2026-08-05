import sqlalchemy as sa
from alembic import op

revision = "0017_training_core"
down_revision = "0016_hyperparameter_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "default_dataset_export_id",
            sa.String(36),
            sa.ForeignKey("dataset_exports.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "default_template_id",
            sa.String(36),
            sa.ForeignKey("hyperparameter_templates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "default_base_model_id",
            sa.String(36),
            sa.ForeignKey("inference_models.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_by_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft','queued','running','canceling','canceled','start_failed','failed','partial','succeeded')",
            name="ck_training_tasks_status",
        ),
        sa.CheckConstraint(
            "mode IN ('single_model','single_device_serial','custom_sequence')",
            name="ck_training_tasks_mode",
        ),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_training_tasks_progress"),
    )
    op.create_index("ix_training_tasks_created_by", "training_tasks", ["created_by_id"])
    op.create_index("ix_training_tasks_last_run", "training_tasks", ["last_run_at"])

    op.create_table(
        "training_models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "training_task_id",
            sa.String(36),
            sa.ForeignKey("training_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("artifact_code", sa.String(160), nullable=True, unique=True),
        sa.Column(
            "dataset_export_id",
            sa.String(36),
            sa.ForeignKey("dataset_exports.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "template_id",
            sa.String(36),
            sa.ForeignKey("hyperparameter_templates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "base_model_id",
            sa.String(36),
            sa.ForeignKey("inference_models.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("epochs_override", sa.Integer(), nullable=True),
        sa.Column("batch_mode_override", sa.String(16), nullable=True),
        sa.Column("batch_value_override", sa.Float(), nullable=True),
        sa.Column("image_size_override", sa.Integer(), nullable=True),
        sa.Column("dataset_snapshot", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("template_snapshot", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("base_model_snapshot", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("gpu_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queue_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "derived_from_id",
            sa.String(36),
            sa.ForeignKey("training_models.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "continuation_of_id",
            sa.String(36),
            sa.ForeignKey("training_models.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("continuation_checkpoint", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft','queued','running','canceling','canceled','start_failed','failed','succeeded')",
            name="ck_training_models_status",
        ),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_training_models_progress"),
        sa.CheckConstraint(
            "gpu_index >= 0 AND queue_order BETWEEN 1 AND 10", name="ck_training_models_lane"
        ),
        sa.UniqueConstraint(
            "training_task_id", "gpu_index", "queue_order", name="uq_training_models_lane_order"
        ),
    )
    op.create_index("ix_training_models_task", "training_models", ["training_task_id"])

    op.create_table(
        "training_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "training_model_id",
            sa.String(36),
            sa.ForeignKey("training_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("gpu_index", sa.Integer(), nullable=False),
        sa.Column("queue_order", sa.Integer(), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("run_token", sa.String(64), nullable=False, unique=True),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_epochs", sa.Integer(), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("best_path", sa.Text(), nullable=True),
        sa.Column("last_path", sa.Text(), nullable=True),
        sa.Column("host_snapshot", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("warning", sa.Text(), nullable=True),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('initial','retry','resume','extend')", name="ck_training_runs_kind"
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','canceling','canceled','start_failed','failed','succeeded')",
            name="ck_training_runs_status",
        ),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_training_runs_progress"),
        sa.UniqueConstraint("training_model_id", "attempt_no", name="uq_training_runs_attempt"),
    )
    op.create_index("ix_training_runs_model", "training_runs", ["training_model_id"])
    op.create_index("ix_training_runs_queue", "training_runs", ["status", "enqueued_at"])
    op.create_index(
        "uq_training_runs_active_gpu",
        "training_runs",
        ["gpu_index"],
        unique=True,
        sqlite_where=sa.text("status IN ('running','canceling')"),
    )

    op.create_table(
        "training_metrics",
        sa.Column(
            "training_run_id",
            sa.String(36),
            sa.ForeignKey("training_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("epoch", sa.Integer(), primary_key=True),
        sa.Column("box_loss", sa.Float(), nullable=True),
        sa.Column("cls_loss", sa.Float(), nullable=True),
        sa.Column("learning_rate", sa.Float(), nullable=True),
        sa.Column("precision", sa.Float(), nullable=True),
        sa.Column("recall", sa.Float(), nullable=True),
        sa.Column("map50", sa.Float(), nullable=True),
        sa.Column("map50_95", sa.Float(), nullable=True),
        sa.Column("pr_curve", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("epoch >= 1", name="ck_training_metrics_epoch"),
    )

    with op.batch_alter_table("model_projects") as batch:
        batch.add_column(sa.Column("training_task_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_model_projects_training_task",
            "training_tasks",
            ["training_task_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint("uq_model_projects_training_task", ["training_task_id"])
    with op.batch_alter_table("inference_models") as batch:
        batch.add_column(sa.Column("training_model_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_inference_models_training_model",
            "training_models",
            ["training_model_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint("uq_inference_models_training_model", ["training_model_id"])


def downgrade() -> None:
    with op.batch_alter_table("inference_models") as batch:
        batch.drop_constraint("fk_inference_models_training_model", type_="foreignkey")
        batch.drop_constraint("uq_inference_models_training_model", type_="unique")
        batch.drop_column("training_model_id")
    with op.batch_alter_table("model_projects") as batch:
        batch.drop_constraint("fk_model_projects_training_task", type_="foreignkey")
        batch.drop_constraint("uq_model_projects_training_task", type_="unique")
        batch.drop_column("training_task_id")
    op.drop_table("training_metrics")
    op.drop_table("training_runs")
    op.drop_table("training_models")
    op.drop_table("training_tasks")
