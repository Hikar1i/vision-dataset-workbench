import sqlalchemy as sa
from alembic import op

revision = "0021_user_llm_configs"
down_revision = "0020_add_model_project_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_llm_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_type", sa.String(16), nullable=False, server_default="openai"),
        sa.Column("model_name", sa.String(256), nullable=False),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_test_status", sa.String(32), nullable=False, server_default="untested"),
        sa.Column("last_test_latency_ms", sa.Integer(), nullable=True),
        sa.Column("advanced_options", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_llm_configs_user_id", "user_llm_configs", ["user_id"])
    op.create_table(
        "user_llm_defaults",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("options", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_llm_defaults")
    op.drop_index("ix_user_llm_configs_user_id", table_name="user_llm_configs")
    op.drop_table("user_llm_configs")
