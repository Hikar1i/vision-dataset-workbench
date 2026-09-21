import sqlalchemy as sa
from alembic import op

revision = "0023_editable_hyperparameter_templates"
down_revision = "0022_multi_dataset_training"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("hyperparameter_templates", recreate="always") as batch:
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
    op.execute("UPDATE hyperparameter_templates SET updated_at = created_at")

    with op.batch_alter_table("training_tasks", recreate="always") as batch:
        batch.add_column(sa.Column("default_epochs_override", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("default_batch_mode_override", sa.String(16), nullable=True))
        batch.add_column(sa.Column("default_batch_value_override", sa.Float(), nullable=True))
        batch.add_column(sa.Column("default_image_size_override", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("default_extra_parameters_override", sa.Text(), nullable=True))

    with op.batch_alter_table("training_models", recreate="always") as batch:
        batch.add_column(sa.Column("extra_parameters_override", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("training_models", recreate="always") as batch:
        batch.drop_column("extra_parameters_override")
    with op.batch_alter_table("training_tasks", recreate="always") as batch:
        batch.drop_column("default_extra_parameters_override")
        batch.drop_column("default_image_size_override")
        batch.drop_column("default_batch_value_override")
        batch.drop_column("default_batch_mode_override")
        batch.drop_column("default_epochs_override")
    with op.batch_alter_table("hyperparameter_templates", recreate="always") as batch:
        batch.drop_column("updated_at")
        batch.drop_column("version")
