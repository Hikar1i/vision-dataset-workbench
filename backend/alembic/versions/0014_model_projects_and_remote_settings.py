from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0014_model_projects"
down_revision = "0013_dataset_exports"
branch_labels = None
depends_on = None

TEMPORARY_MODEL_PROJECT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "model_projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("series_type", sa.String(16), nullable=False),
        sa.Column("system_key", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "series_type IN ('archive', 'training')",
            name="ck_model_projects_series_type",
        ),
        sa.UniqueConstraint("system_key", name="uq_model_projects_system_key"),
    )
    op.bulk_insert(
        sa.table(
            "model_projects",
            sa.column("id", sa.String),
            sa.column("name", sa.String),
            sa.column("series_type", sa.String),
            sa.column("system_key", sa.String),
            sa.column("created_at", sa.DateTime),
        ),
        [
            {
                "id": TEMPORARY_MODEL_PROJECT_ID,
                "name": "临时模型项目",
                "series_type": "archive",
                "system_key": "temporary",
                "created_at": datetime.now(timezone.utc),
            }
        ],
    )
    op.create_table(
        "user_xanylabeling_settings",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("server_url", sa.Text(), nullable=False),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.add_column(
        "inference_models",
        sa.Column("model_project_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "inference_models",
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "inference_models",
        sa.Column("parameters", sa.Text(), nullable=False, server_default="{}"),
    )
    op.execute(
        sa.text("UPDATE inference_models SET model_project_id = :project_id").bindparams(
            project_id=TEMPORARY_MODEL_PROJECT_ID
        )
    )
    with op.batch_alter_table("inference_models", recreate="always") as batch:
        batch.drop_constraint("ck_inference_models_kind", type_="check")
        batch.alter_column("model_project_id", existing_type=sa.String(36), nullable=False)
        batch.create_foreign_key(
            "fk_inference_models_model_project_id",
            "model_projects",
            ["model_project_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint("ck_inference_models_kind", "kind = 'yolo'")
    op.create_index(
        "ix_inference_models_model_project_id",
        "inference_models",
        ["model_project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_inference_models_model_project_id", table_name="inference_models")
    with op.batch_alter_table("inference_models", recreate="always") as batch:
        batch.drop_constraint("fk_inference_models_model_project_id", type_="foreignkey")
        batch.drop_constraint("ck_inference_models_kind", type_="check")
        batch.create_check_constraint(
            "ck_inference_models_kind", "kind IN ('yolo', 'grounding_dino')"
        )
        batch.drop_column("parameters")
        batch.drop_column("description")
        batch.drop_column("model_project_id")
    op.drop_table("user_xanylabeling_settings")
    op.drop_table("model_projects")
