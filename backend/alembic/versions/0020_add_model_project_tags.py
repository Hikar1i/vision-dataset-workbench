from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0020_add_model_project_tags"
down_revision = "0019_add_dfl_loss"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_project_tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(24), nullable=False),
        sa.Column("name_normalized", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name_normalized", name="uq_model_project_tags_name_normalized"),
    )
    op.create_index("ix_model_project_tags_name_normalized", "model_project_tags", ["name_normalized"])
    op.create_table(
        "model_project_tag_links",
        sa.Column(
            "model_project_id",
            sa.String(36),
            sa.ForeignKey("model_projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.String(36),
            sa.ForeignKey("model_project_tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    connection = op.get_bind()
    tag_id = str(uuid4())
    connection.execute(
        sa.text(
            "INSERT INTO model_project_tags (id, name, name_normalized, created_at) "
            "VALUES (:id, '未分类', '未分类', CURRENT_TIMESTAMP)"
        ),
        {"id": tag_id},
    )
    connection.execute(
        sa.text(
            "INSERT INTO model_project_tag_links (model_project_id, tag_id) "
            "SELECT id, :tag_id FROM model_projects"
        ),
        {"tag_id": tag_id},
    )


def downgrade() -> None:
    op.drop_table("model_project_tag_links")
    op.drop_index("ix_model_project_tags_name_normalized", table_name="model_project_tags")
    op.drop_table("model_project_tags")
