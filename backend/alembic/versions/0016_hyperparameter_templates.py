from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0016_hyperparameter_templates"
down_revision = "0015_model_management"
branch_labels = None
depends_on = None

DEFAULT_TEMPLATE_ID = "00000000-0000-0000-0000-000000000002"


def upgrade() -> None:
    op.create_table(
        "hyperparameter_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("name_normalized", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("epochs", sa.Integer(), nullable=False),
        sa.Column("batch_mode", sa.String(16), nullable=False),
        sa.Column("batch_value", sa.Float(), nullable=True),
        sa.Column("image_size", sa.Integer(), nullable=False),
        sa.Column("extra_parameters", sa.Text(), nullable=False),
        sa.Column("catalog_version", sa.String(32), nullable=False),
        sa.Column("system_key", sa.String(32), nullable=True, unique=True),
        sa.Column(
            "derived_from_id",
            sa.String(36),
            sa.ForeignKey("hyperparameter_templates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_by_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("epochs BETWEEN 1 AND 100000", name="ck_templates_epochs"),
        sa.CheckConstraint(
            "image_size BETWEEN 32 AND 8192 AND image_size % 32 = 0",
            name="ck_templates_image_size",
        ),
        sa.CheckConstraint(
            "(batch_mode = 'auto' AND batch_value IS NULL) OR "
            "(batch_mode = 'fixed' AND batch_value BETWEEN 1 AND 4096) OR "
            "(batch_mode = 'fraction' AND batch_value > 0 AND batch_value <= 1)",
            name="ck_templates_batch",
        ),
    )
    op.create_index(
        "uq_templates_active_name",
        "hyperparameter_templates",
        ["name_normalized"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_templates_created_by_id", "hyperparameter_templates", ["created_by_id"])
    op.bulk_insert(
        sa.table(
            "hyperparameter_templates",
            sa.column("id", sa.String),
            sa.column("name", sa.String),
            sa.column("name_normalized", sa.String),
            sa.column("description", sa.Text),
            sa.column("epochs", sa.Integer),
            sa.column("batch_mode", sa.String),
            sa.column("batch_value", sa.Float),
            sa.column("image_size", sa.Integer),
            sa.column("extra_parameters", sa.Text),
            sa.column("catalog_version", sa.String),
            sa.column("system_key", sa.String),
            sa.column("created_at", sa.DateTime),
        ),
        [
            {
                "id": DEFAULT_TEMPLATE_ID,
                "name": "Ultralytics Detect 默认模板",
                "name_normalized": "ultralytics detect 默认模板",
                "description": "系统内置的 YOLO Detect 基础训练参数。",
                "epochs": 100,
                "batch_mode": "auto",
                "batch_value": None,
                "image_size": 640,
                "extra_parameters": "{}",
                "catalog_version": "detect-v1",
                "system_key": "ultralytics-detect-default",
                "created_at": datetime.now(timezone.utc),
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("hyperparameter_templates")
