import sqlalchemy as sa
from alembic import op

revision = "0024_xanylabeling_availability"
down_revision = "0023_editable_hyperparameter_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_xanylabeling_settings", recreate="always") as batch:
        batch.add_column(sa.Column("available", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_xanylabeling_settings", recreate="always") as batch:
        batch.drop_column("available")
