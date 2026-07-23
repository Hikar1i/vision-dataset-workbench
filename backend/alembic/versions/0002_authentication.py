import sqlalchemy as sa
from alembic import op

revision = "0002_authentication"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username_normalized", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("reviewed_by_id", sa.String(36), nullable=True))
    op.execute("UPDATE users SET username_normalized = lower(username), updated_at = created_at")
    with op.batch_alter_table("users") as batch:
        batch.alter_column("username_normalized", existing_type=sa.String(64), nullable=False)
        batch.alter_column(
            "updated_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )
        batch.drop_index("ix_users_username")
        batch.create_index(
            "ix_users_username_normalized", ["username_normalized"], unique=True
        )
        batch.create_foreign_key(
            "fk_users_reviewed_by_id_users", "users", ["reviewed_by_id"], ["id"]
        )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)
    op.create_index("ix_sessions_idle_expires_at", "sessions", ["idle_expires_at"])
    op.create_index(
        "ix_sessions_absolute_expires_at", "sessions", ["absolute_expires_at"]
    )


def downgrade() -> None:
    op.drop_table("sessions")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_users_reviewed_by_id_users", type_="foreignkey")
        batch.drop_index("ix_users_username_normalized")
        batch.create_index("ix_users_username", ["username"], unique=True)
        batch.drop_column("reviewed_by_id")
        batch.drop_column("reviewed_at")
        batch.drop_column("updated_at")
        batch.drop_column("username_normalized")
