import sqlalchemy as sa
from alembic import op

revision = "0008_label_description_zh"
down_revision = "0007_labels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "labels",
        sa.Column(
            "description_zh",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("labels") as batch_op:
        batch_op.drop_column("description_zh")
