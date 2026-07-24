import sqlalchemy as sa
from alembic import op

revision = "0006_video_enabled_limit"
down_revision = "0005_sampling_frames"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute(
        """
        CREATE TRIGGER trg_videos_project_limit
        BEFORE INSERT ON videos
        WHEN (
            SELECT COUNT(*)
            FROM videos
            WHERE project_id = NEW.project_id
        ) >= 999
        BEGIN
            SELECT RAISE(ABORT, 'project video limit reached');
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_videos_project_limit")
    with op.batch_alter_table("videos", recreate="always") as batch:
        batch.drop_column("enabled")
