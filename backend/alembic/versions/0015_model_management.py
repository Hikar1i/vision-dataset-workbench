import json
import re
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0015_model_management"
down_revision = "0014_model_projects"
branch_labels = None
depends_on = None


def _normalized(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _model_code(value: str) -> str:
    code = re.sub(r"[^a-z0-9]+", "-", value.rsplit(".", 1)[0].lower()).strip("-")
    return (code or "model")[:48]


def upgrade() -> None:
    op.add_column("model_projects", sa.Column("name_normalized", sa.String(128)))
    op.add_column(
        "model_projects", sa.Column("description", sa.Text(), nullable=False, server_default="")
    )
    op.add_column(
        "model_projects",
        sa.Column("created_by_id", sa.String(36)),
    )
    op.add_column(
        "model_projects", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("model_projects", sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.add_column("model_projects", sa.Column("deleted_at", sa.DateTime(timezone=True)))

    op.add_column("inference_models", sa.Column("model_code", sa.String(64)))
    op.add_column("inference_models", sa.Column("file_size", sa.Integer()))
    op.add_column("inference_models", sa.Column("sha256", sa.String(64)))
    op.add_column(
        "inference_models", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column("inference_models", sa.Column("deleted_at", sa.DateTime(timezone=True)))

    op.add_column(
        "tasks",
        sa.Column("model_project_id", sa.String(36)),
    )

    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    for row in connection.execute(sa.text("SELECT id, name, created_at FROM model_projects")):
        connection.execute(
            sa.text(
                "UPDATE model_projects SET name_normalized=:normalized, updated_at=:updated "
                "WHERE id=:id"
            ),
            {"normalized": _normalized(row.name), "updated": row.created_at or now, "id": row.id},
        )

    used: dict[str, set[str]] = {}
    model_rows = connection.execute(
        sa.text(
            "SELECT id, model_project_id, source_name, name, storage_path FROM inference_models "
            "ORDER BY created_at, id"
        )
    ).all()
    for row in model_rows:
        project_codes = used.setdefault(row.model_project_id, set())
        base = _model_code(row.source_name or row.name)
        code = base
        suffix = 2
        while code in project_codes:
            code = f"{base[:55]}-{suffix}"
            suffix += 1
        project_codes.add(code)
        file_size = None
        connection.execute(
            sa.text(
                "UPDATE inference_models SET model_code=:code, file_size=:file_size WHERE id=:id"
            ),
            {"code": code, "file_size": file_size, "id": row.id},
        )

    for row in connection.execute(
        sa.text("SELECT id, payload FROM tasks WHERE type='import_model'")
    ):
        try:
            model_id = json.loads(row.payload).get("model_id")
        except (TypeError, ValueError):
            model_id = None
        project_id = connection.scalar(
            sa.text("SELECT model_project_id FROM inference_models WHERE id=:id"),
            {"id": model_id},
        )
        if project_id:
            connection.execute(
                sa.text(
                    "UPDATE tasks SET model_project_id=:model_project_id, project_id=NULL "
                    "WHERE id=:id"
                ),
                {"model_project_id": project_id, "id": row.id},
            )

    with op.batch_alter_table("model_projects", recreate="always") as batch:
        batch.alter_column("name_normalized", existing_type=sa.String(128), nullable=False)
        batch.create_foreign_key(
            "fk_model_projects_created_by_id",
            "users",
            ["created_by_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    with op.batch_alter_table("inference_models", recreate="always") as batch:
        batch.alter_column("model_code", existing_type=sa.String(64), nullable=False)
        batch.create_check_constraint(
            "ck_inference_models_file_size", "file_size IS NULL OR file_size >= 0"
        )
    with op.batch_alter_table("tasks", recreate="always") as batch:
        batch.drop_constraint("ck_tasks_type", type_="check")
        batch.create_check_constraint(
            "ck_tasks_type",
            "type IN ('copy_video', 'download_video', 'extract_frames', 'import_model', "
            "'auto_annotate', 'export_dataset')",
        )
        batch.alter_column("project_id", existing_type=sa.String(36), nullable=True)
        batch.create_foreign_key(
            "fk_tasks_model_project_id",
            "model_projects",
            ["model_project_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "ck_tasks_resource",
            "(type = 'import_model' AND model_project_id IS NOT NULL AND project_id IS NULL) "
            "OR (type <> 'import_model' AND project_id IS NOT NULL AND model_project_id IS NULL)",
        )

    op.create_index(
        "uq_model_projects_active_name",
        "model_projects",
        ["name_normalized"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_inference_models_active_code",
        "inference_models",
        ["model_project_id", "model_code"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_tasks_model_project_id", "tasks", ["model_project_id"])
    op.create_index("ix_model_projects_created_by_id", "model_projects", ["created_by_id"])


def downgrade() -> None:
    connection = op.get_bind()
    temporary_id = "00000000-0000-0000-0000-000000000001"
    fallback_project_id = connection.scalar(
        sa.text("SELECT id FROM projects ORDER BY created_at LIMIT 1")
    )
    if fallback_project_id is not None:
        connection.execute(
            sa.text(
                "UPDATE tasks SET project_id=:project_id WHERE type='import_model' AND project_id IS NULL"
            ),
            {"project_id": fallback_project_id},
        )
    connection.execute(
        sa.text(
            "UPDATE inference_models SET model_project_id=:temporary WHERE model_project_id IN "
            "(SELECT id FROM model_projects WHERE deleted_at IS NOT NULL)"
        ),
        {"temporary": temporary_id},
    )
    op.drop_index("ix_model_projects_created_by_id", table_name="model_projects")
    op.drop_index("ix_tasks_model_project_id", table_name="tasks")
    op.drop_index("uq_inference_models_active_code", table_name="inference_models")
    op.drop_index("uq_model_projects_active_name", table_name="model_projects")
    with op.batch_alter_table("tasks", recreate="always") as batch:
        batch.drop_constraint("ck_tasks_resource", type_="check")
        batch.drop_constraint("fk_tasks_model_project_id", type_="foreignkey")
        batch.alter_column("project_id", existing_type=sa.String(36), nullable=False)
        batch.drop_column("model_project_id")
    with op.batch_alter_table("inference_models", recreate="always") as batch:
        batch.drop_constraint("ck_inference_models_file_size", type_="check")
        batch.drop_column("deleted_at")
        batch.drop_column("version")
        batch.drop_column("sha256")
        batch.drop_column("file_size")
        batch.drop_column("model_code")
    with op.batch_alter_table("model_projects", recreate="always") as batch:
        batch.drop_constraint("fk_model_projects_created_by_id", type_="foreignkey")
        batch.drop_column("deleted_at")
        batch.drop_column("updated_at")
        batch.drop_column("version")
        batch.drop_column("created_by_id")
        batch.drop_column("description")
        batch.drop_column("name_normalized")
