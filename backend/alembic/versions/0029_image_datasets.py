"""Image dataset projects and rectangle annotations."""

import sqlalchemy as sa
from alembic import op

revision = "0029_image_datasets"
down_revision = "0028_resource_activity_timestamps"
branch_labels = None
depends_on = None

PROJECT_TASKS = "'copy_video','download_video','extract_frames','auto_annotate','export_dataset'"
MODEL_TASKS = (
    "'import_model','convert_model','infer_video','import_evaluation_dataset','evaluate_model'"
)


def _tasks(project_types: str) -> None:
    with op.batch_alter_table("tasks", recreate="always") as batch:
        batch.drop_constraint("ck_tasks_type", type_="check")
        batch.drop_constraint("ck_tasks_resource", type_="check")
        batch.create_check_constraint("ck_tasks_type", f"type IN ({project_types},{MODEL_TASKS})")
        batch.create_check_constraint(
            "ck_tasks_resource",
            f"(type IN ({MODEL_TASKS}) AND model_project_id IS NOT NULL AND project_id IS NULL) OR "
            f"(type IN ({project_types}) AND project_id IS NOT NULL AND model_project_id IS NULL)",
        )


def _id():
    return sa.Column("id", sa.String(36), primary_key=True)


def _time(name):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def _fk(name, table, *, ondelete="CASCADE", nullable=False, **kwargs):
    return sa.Column(
        name,
        sa.String(36),
        sa.ForeignKey(f"{table}.id", ondelete=ondelete),
        nullable=nullable,
        **kwargs,
    )


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "project_type",
            sa.String(16),
            sa.CheckConstraint("project_type IN ('video','image')", name="ck_projects_type"),
            nullable=False,
            server_default="video",
        ),
    )
    _tasks(f"{PROJECT_TASKS},'import_images'")
    op.create_table(
        "image_imports",
        _id(),
        _fk("project_id", "projects"),
        _fk("task_id", "tasks", ondelete="SET NULL", nullable=True, unique=True),
        _fk("created_by_id", "users", ondelete="RESTRICT"),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("root_name", sa.String(512), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("class_mapping", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        _time("created_at"),
        _time("updated_at"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("format IN ('images','yolo_detect')", name="ck_image_imports_format"),
        sa.CheckConstraint(
            "status IN ('queued','running','ready','failed','canceled')",
            name="ck_image_imports_status",
        ),
    )
    for field in ("project_id", "status"):
        op.create_index(f"ix_image_imports_{field}", "image_imports", [field])
    op.create_table(
        "image_directories",
        _id(),
        _fk("project_id", "projects"),
        _fk("import_id", "image_imports"),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("source_relative_path", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        _time("created_at"),
        sa.UniqueConstraint("project_id", "name", name="uq_image_directories_name"),
        sa.UniqueConstraint(
            "import_id", "source_relative_path", name="uq_image_directories_source"
        ),
        sa.CheckConstraint("sort_order >= 0", name="ck_image_directories_order"),
    )
    for field in ("project_id", "import_id"):
        op.create_index(f"ix_image_directories_{field}", "image_directories", [field])
    op.create_table(
        "images",
        _id(),
        _fk("directory_id", "image_directories"),
        *[
            sa.Column(name, sa.Text(), nullable=False)
            for name in ("source_relative_path", "file_path", "thumbnail_path")
        ],
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        *[
            sa.Column(name, sa.Integer(), nullable=False)
            for name in ("width", "height", "file_size")
        ],
        sa.Column("materialization", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("annotation_status", sa.String(16), nullable=False),
        sa.Column("annotation_revision", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("last_auto_operation_id", sa.String(36), nullable=True),
        _time("created_at"),
        _time("updated_at"),
        sa.UniqueConstraint("directory_id", "source_relative_path", name="uq_images_source"),
        sa.CheckConstraint(
            "width > 0 AND height > 0 AND file_size >= 0", name="ck_images_dimensions"
        ),
        sa.CheckConstraint(
            "annotation_status IN ('pending','labeled')", name="ck_images_annotation_status"
        ),
        sa.CheckConstraint("annotation_revision >= 1 AND version >= 1", name="ck_images_revisions"),
        sa.CheckConstraint(
            "materialization IN ('reflink','hardlink','copy')", name="ck_images_materialization"
        ),
    )
    op.create_index("ix_images_content_sha256", "images", ["content_sha256"])
    op.create_index(
        "ix_images_directory_order", "images", ["directory_id", "source_relative_path", "id"]
    )
    op.create_table(
        "image_annotations",
        _id(),
        _fk("image_id", "images"),
        _fk("label_id", "labels", ondelete="RESTRICT"),
        *[
            sa.Column(name, sa.Float(), nullable=False)
            for name in ("x_min", "y_min", "x_max", "y_max")
        ],
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        _time("created_at"),
        sa.CheckConstraint(
            "x_min >= 0 AND y_min >= 0 AND x_max > x_min AND y_max > y_min",
            name="ck_image_annotations_bounds",
        ),
        sa.CheckConstraint(
            "source IN ('import','manual','model')", name="ck_image_annotations_source"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_image_annotations_confidence",
        ),
        sa.CheckConstraint("sort_order >= 0", name="ck_image_annotations_order"),
    )
    op.create_index("ix_image_annotations_label_id", "image_annotations", ["label_id"])
    op.create_index(
        "ix_image_annotations_order", "image_annotations", ["image_id", "sort_order", "id"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT COUNT(*) FROM projects WHERE project_type='image'")
    ) or connection.scalar(sa.text("SELECT COUNT(*) FROM image_imports")):
        raise RuntimeError(
            "Remove image projects and imports before downgrading; data will not be discarded."
        )
    if connection.scalar(sa.text("SELECT COUNT(*) FROM tasks WHERE type='import_images'")):
        raise RuntimeError("Image import task history must be removed before downgrading.")
    for table in ("image_annotations", "images", "image_directories", "image_imports"):
        op.drop_table(table)
    _tasks(PROJECT_TASKS)
    with op.batch_alter_table("projects") as batch:
        batch.drop_constraint("ck_projects_type", type_="check")
        batch.drop_column("project_type")
