import sqlalchemy as sa
from alembic import op

revision = "0012_video_short_codes"
down_revision = "0011_annotation_order"
branch_labels = None
depends_on = None


def _create_video_limit_trigger() -> None:
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


def upgrade() -> None:
    op.add_column("videos", sa.Column("short_code", sa.String(8), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, project_id FROM videos ORDER BY project_id, created_at, id")
    ).mappings()
    counters: dict[str, int] = {}
    for row in rows:
        project_id = str(row["project_id"])
        counters[project_id] = counters.get(project_id, 0) + 1
        connection.execute(
            sa.text("UPDATE videos SET short_code = :code WHERE id = :id"),
            {"code": f"{counters[project_id]:08d}", "id": row["id"]},
        )

    op.execute("DROP TRIGGER IF EXISTS trg_videos_project_limit")
    with op.batch_alter_table("videos", recreate="always") as batch:
        batch.alter_column(
            "short_code", existing_type=sa.String(8), nullable=False
        )
        batch.create_check_constraint(
            "ck_videos_short_code",
            "length(short_code) = 8 AND "
            "short_code NOT GLOB '*[^0123456789ABCDEFGHJKMNPQRSTVWXYZ]*'",
        )
    op.create_index(
        "uq_videos_project_short_code",
        "videos",
        ["project_id", "short_code"],
        unique=True,
    )
    _create_video_limit_trigger()
    op.drop_index("ix_frames_video_id", table_name="frames")
    op.drop_index("ix_frames_enabled", table_name="frames")


def downgrade() -> None:
    op.create_index("ix_frames_video_id", "frames", ["video_id"])
    op.create_index("ix_frames_enabled", "frames", ["enabled"])
    op.drop_index("uq_videos_project_short_code", table_name="videos")
    op.execute("DROP TRIGGER IF EXISTS trg_videos_project_limit")
    with op.batch_alter_table("videos", recreate="always") as batch:
        batch.drop_constraint("ck_videos_short_code", type_="check")
        batch.drop_column("short_code")
    _create_video_limit_trigger()
