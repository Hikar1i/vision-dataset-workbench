import sqlalchemy as sa
from alembic import op

revision = "0011_annotation_order"
down_revision = "0010_inference_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("annotations", recreate="always") as batch:
        batch.add_column(
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0")
        )
        batch.create_check_constraint(
            "ck_annotations_sort_order", "sort_order >= 0"
        )
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY frame_id ORDER BY created_at, id
                   ) - 1 AS position
            FROM annotations
        )
        UPDATE annotations
        SET sort_order = (
            SELECT position FROM ranked WHERE ranked.id = annotations.id
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("annotations", recreate="always") as batch:
        batch.drop_constraint("ck_annotations_sort_order", type_="check")
        batch.drop_column("sort_order")
