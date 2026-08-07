import sqlalchemy as sa
from alembic import op

revision = "0019_add_dfl_loss"
down_revision = "0018_training_action_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("training_metrics", sa.Column("dfl_loss", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("training_metrics", "dfl_loss")
