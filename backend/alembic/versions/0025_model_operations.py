import sqlalchemy as sa
from alembic import op

revision = "0025_model_operations"
down_revision = "0024_xanylabeling_availability"
branch_labels = None
depends_on = None


MODEL_PROJECT_TASK_TYPES = (
    "'import_model','convert_model','infer_video',"
    "'import_evaluation_dataset','evaluate_model'"
)
PROJECT_TASK_TYPES = (
    "'copy_video','download_video','extract_frames','auto_annotate','export_dataset'"
)


def _id() -> sa.Column:
    return sa.Column("id", sa.String(36), primary_key=True)


def _timestamps(*, updated: bool = False) -> list[sa.Column]:
    columns = [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]
    if updated:
        columns.append(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    return columns


def upgrade() -> None:
    with op.batch_alter_table("tasks", recreate="always") as batch:
        batch.drop_constraint("ck_tasks_type", type_="check")
        batch.drop_constraint("ck_tasks_resource", type_="check")
        batch.create_check_constraint(
            "ck_tasks_type",
            f"type IN ({PROJECT_TASK_TYPES},{MODEL_PROJECT_TASK_TYPES})",
        )
        batch.create_check_constraint(
            "ck_tasks_resource",
            f"(type IN ({MODEL_PROJECT_TASK_TYPES}) AND model_project_id IS NOT NULL "
            "AND project_id IS NULL) OR "
            f"(type IN ({PROJECT_TASK_TYPES}) AND project_id IS NOT NULL "
            "AND model_project_id IS NULL)",
        )

    op.create_table(
        "model_artifacts",
        _id(),
        sa.Column(
            "model_id",
            sa.String(36),
            sa.ForeignKey("inference_models.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_model_sha256", sa.String(64), nullable=False),
        sa.Column("export_config", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("environment_fingerprint", sa.Text(), nullable=True),
        sa.Column("gpu_uuid", sa.String(80), nullable=True),
        sa.Column("gpu_index", sa.Integer(), nullable=True),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_by_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *_timestamps(updated=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("format IN ('onnx','engine')", name="ck_model_artifacts_format"),
        sa.CheckConstraint(
            "status IN ('queued','converting','ready','failed','stale')",
            name="ck_model_artifacts_status",
        ),
        sa.CheckConstraint(
            "file_size IS NULL OR file_size >= 0", name="ck_model_artifacts_file_size"
        ),
    )
    op.create_index("ix_model_artifacts_model_id", "model_artifacts", ["model_id"])
    op.create_index("ix_model_artifacts_status", "model_artifacts", ["status"])
    op.create_index(
        "ix_model_artifacts_created_by_id", "model_artifacts", ["created_by_id"]
    )
    op.create_index(
        "uq_model_artifacts_active_format",
        "model_artifacts",
        ["model_id", "format"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "model_inference_runs",
        _id(),
        sa.Column(
            "model_id",
            sa.String(36),
            sa.ForeignKey("inference_models.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_model_sha256", sa.String(64), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=True),
        sa.Column(
            "created_by_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("input_type", sa.String(16), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("result_path", sa.Text(), nullable=True),
        sa.Column("parameters", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("statistics", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("format IN ('pt','onnx','engine')", name="ck_model_inference_format"),
        sa.CheckConstraint("input_type IN ('image','video')", name="ck_model_inference_input"),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','canceled')",
            name="ck_model_inference_status",
        ),
    )
    op.create_index("ix_model_inference_runs_model_id", "model_inference_runs", ["model_id"])
    op.create_index("ix_model_inference_runs_status", "model_inference_runs", ["status"])
    op.create_index(
        "ix_model_inference_runs_created_by_id", "model_inference_runs", ["created_by_id"]
    )
    op.create_index(
        "ix_model_inference_runs_expires_at", "model_inference_runs", ["expires_at"]
    )
    op.create_index(
        "uq_model_inference_runs_active_session",
        "model_inference_runs",
        ["model_id", "created_by_id"],
        unique=True,
        sqlite_where=sa.text("saved_at IS NULL AND deleted_at IS NULL"),
    )

    op.create_table(
        "evaluation_datasets",
        _id(),
        sa.Column(
            "model_project_id",
            sa.String(36),
            sa.ForeignKey("model_projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("classes", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("image_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("negative_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_by_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *_timestamps(),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued','validating','ready','failed')",
            name="ck_evaluation_datasets_status",
        ),
        sa.CheckConstraint(
            "image_count >= 0 AND label_count >= 0 AND negative_count >= 0 "
            "AND total_bytes >= 0",
            name="ck_evaluation_datasets_counts",
        ),
    )
    op.create_index(
        "ix_evaluation_datasets_model_project_id",
        "evaluation_datasets",
        ["model_project_id"],
    )
    op.create_index("ix_evaluation_datasets_status", "evaluation_datasets", ["status"])
    op.create_index(
        "ix_evaluation_datasets_created_by_id", "evaluation_datasets", ["created_by_id"]
    )
    op.create_index(
        "uq_evaluation_datasets_active_hash",
        "evaluation_datasets",
        ["model_project_id", "content_sha256"],
        unique=True,
        sqlite_where=sa.text("status = 'ready' AND deleted_at IS NULL"),
    )

    op.create_table(
        "model_evaluations",
        _id(),
        sa.Column(
            "model_project_id",
            sa.String(36),
            sa.ForeignKey("model_projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "model_id",
            sa.String(36),
            sa.ForeignKey("inference_models.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("source_model_sha256", sa.String(64), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=True),
        sa.Column(
            "evaluation_dataset_id",
            sa.String(36),
            sa.ForeignKey("evaluation_datasets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("dataset_name", sa.String(128), nullable=False),
        sa.Column("dataset_sha256", sa.String(64), nullable=False),
        sa.Column("class_mapping", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("config", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metrics", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("per_class_metrics", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("confusion_matrix_path", sa.Text(), nullable=True),
        sa.Column("pr_curve_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_by_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *_timestamps(),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("format IN ('pt','onnx','engine')", name="ck_model_evaluations_format"),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','canceled')",
            name="ck_model_evaluations_status",
        ),
    )
    op.create_index(
        "ix_model_evaluations_model_project_id", "model_evaluations", ["model_project_id"]
    )
    op.create_index("ix_model_evaluations_model_id", "model_evaluations", ["model_id"])
    op.create_index(
        "ix_model_evaluations_evaluation_dataset_id",
        "model_evaluations",
        ["evaluation_dataset_id"],
    )
    op.create_index("ix_model_evaluations_status", "model_evaluations", ["status"])
    op.create_index(
        "ix_model_evaluations_created_by_id", "model_evaluations", ["created_by_id"]
    )

    op.create_table(
        "gpu_leases",
        sa.Column("gpu_uuid", sa.String(80), primary_key=True),
        sa.Column("gpu_index", sa.Integer(), nullable=False),
        sa.Column("owner_type", sa.String(32), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(updated=True),
        sa.UniqueConstraint("owner_type", "owner_id", name="uq_gpu_leases_owner"),
    )
    op.create_index("ix_gpu_leases_expires_at", "gpu_leases", ["expires_at"])


def downgrade() -> None:
    op.drop_table("gpu_leases")
    op.drop_table("model_evaluations")
    op.drop_table("evaluation_datasets")
    op.drop_table("model_inference_runs")
    op.drop_table("model_artifacts")
    with op.batch_alter_table("tasks", recreate="always") as batch:
        batch.drop_constraint("ck_tasks_type", type_="check")
        batch.drop_constraint("ck_tasks_resource", type_="check")
        batch.create_check_constraint(
            "ck_tasks_type",
            "type IN ('copy_video','download_video','extract_frames','import_model',"
            "'auto_annotate','export_dataset')",
        )
        batch.create_check_constraint(
            "ck_tasks_resource",
            "(type = 'import_model' AND model_project_id IS NOT NULL AND project_id IS NULL) "
            "OR (type <> 'import_model' AND project_id IS NOT NULL AND model_project_id IS NULL)",
        )
