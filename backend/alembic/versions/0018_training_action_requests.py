import sqlalchemy as sa
from alembic import op

revision = "0018_training_action_requests"
down_revision = "0017_training_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_action_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("result_type", sa.String(16), nullable=False),
        sa.Column("result_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "actor_id", "action", "idempotency_key", name="uq_training_action_request"
        ),
    )


def downgrade() -> None:
    op.drop_table("training_action_requests")
