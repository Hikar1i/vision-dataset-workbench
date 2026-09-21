from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0026_access_control_refactor"
down_revision = "0025_model_operations"
branch_labels = None
depends_on = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _backfill_training_projects() -> None:
    connection = op.get_bind()
    tasks = connection.execute(
        sa.text(
            "SELECT t.id, t.code, t.name, t.description, t.created_by_id, "
            "t.created_at, t.updated_at FROM training_tasks AS t "
            "LEFT JOIN model_projects AS p ON p.training_task_id = t.id "
            "WHERE p.id IS NULL"
        )
    ).mappings()
    active_names = set(
        connection.execute(
            sa.text("SELECT name_normalized FROM model_projects WHERE deleted_at IS NULL")
        ).scalars()
    )
    tag_id = connection.execute(
        sa.text(
            "SELECT id FROM model_project_tags WHERE name_normalized = :name"
        ),
        {"name": "训练"},
    ).scalar_one_or_none()
    if tag_id is None:
        tag_id = str(uuid4())
        connection.execute(
            sa.text(
                "INSERT INTO model_project_tags "
                "(id, name, name_normalized, created_at) "
                "VALUES (:id, :name, :normalized, :created_at)"
            ),
            {
                "id": tag_id,
                "name": "训练",
                "normalized": "训练",
                "created_at": _utc_now(),
            },
        )

    for task in tasks:
        suffix = f" · {task['code']}"
        name = f"{task['name'][: 128 - len(suffix)]}{suffix}"
        normalized = name.lower()
        if normalized in active_names:
            collision = f"-{task['id'][:8]}"
            name = f"{name[: 128 - len(collision)]}{collision}"
            normalized = name.lower()
        active_names.add(normalized)
        project_id = str(uuid4())
        connection.execute(
            sa.text(
                "INSERT INTO model_projects "
                "(id, name, name_normalized, description, series_type, system_key, "
                "training_task_id, created_by_id, version, created_at, updated_at, deleted_at) "
                "VALUES (:id, :name, :normalized, :description, 'training', NULL, "
                ":task_id, :creator_id, 1, :created_at, :updated_at, NULL)"
            ),
            {
                "id": project_id,
                "name": name,
                "normalized": normalized,
                "description": task["description"],
                "task_id": task["id"],
                "creator_id": task["created_by_id"],
                "created_at": task["created_at"],
                "updated_at": task["updated_at"],
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO model_project_tag_links (model_project_id, tag_id) "
                "VALUES (:project_id, :tag_id)"
            ),
            {"project_id": project_id, "tag_id": tag_id},
        )


def upgrade() -> None:
    op.execute("UPDATE users SET status = 'disabled' WHERE status IN ('pending', 'rejected')")
    with op.batch_alter_table("users", recreate="always") as batch:
        batch.drop_constraint("fk_users_reviewed_by_id_users", type_="foreignkey")
        batch.drop_column("reviewed_by_id")
        batch.drop_column("reviewed_at")
        batch.add_column(
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.create_check_constraint(
            "ck_users_status", "status IN ('active', 'disabled')"
        )
    op.create_index(
        "uq_users_single_system_admin",
        "users",
        ["is_system_admin"],
        unique=True,
        sqlite_where=sa.text("is_system_admin = 1"),
    )

    op.create_table(
        "model_project_memberships",
        sa.Column(
            "model_project_id",
            sa.String(36),
            sa.ForeignKey("model_projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('editor', 'viewer')", name="ck_model_memberships_role"
        ),
    )
    op.create_index(
        "ix_model_project_memberships_user_id",
        "model_project_memberships",
        ["user_id"],
    )

    with op.batch_alter_table("hyperparameter_templates") as batch:
        batch.add_column(sa.Column("model_project_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_templates_model_project_id",
            "model_projects",
            ["model_project_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index(
            "ix_templates_model_project_id", ["model_project_id"], unique=False
        )

    _backfill_training_projects()


def downgrade() -> None:
    with op.batch_alter_table("hyperparameter_templates") as batch:
        batch.drop_index("ix_templates_model_project_id")
        batch.drop_constraint("fk_templates_model_project_id", type_="foreignkey")
        batch.drop_column("model_project_id")
    op.drop_table("model_project_memberships")
    op.drop_index("uq_users_single_system_admin", table_name="users")
    with op.batch_alter_table("users", recreate="always") as batch:
        batch.drop_constraint("ck_users_status", type_="check")
        batch.drop_column("must_change_password")
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("reviewed_by_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_users_reviewed_by_id_users", "users", ["reviewed_by_id"], ["id"]
        )
