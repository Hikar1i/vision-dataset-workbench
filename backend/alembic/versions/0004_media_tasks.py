import sqlalchemy as sa
from alembic import op

revision = "0004_media_tasks"
down_revision = "0003_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "videos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("source_name", sa.String(512)),
        sa.Column("source_url", sa.Text()),
        sa.Column("extractor", sa.String(128)),
        sa.Column("external_id", sa.String(255)),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column("file_path", sa.Text()),
        sa.Column("thumbnail_path", sa.Text()),
        sa.Column("duration", sa.Float(), nullable=False, server_default="0"),
        sa.Column("width", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fps", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_frames", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('local', 'remote')", name="ck_videos_source_type"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'unavailable')",
            name="ck_videos_status",
        ),
    )
    op.create_index("ix_videos_project_id", "videos", ["project_id"])
    op.create_index(
        "uq_videos_local_hash",
        "videos",
        ["project_id", "content_sha256"],
        unique=True,
        sqlite_where=sa.text("content_sha256 IS NOT NULL"),
    )
    op.create_index(
        "uq_videos_remote_identity",
        "videos",
        ["project_id", "extractor", "external_id"],
        unique=True,
        sqlite_where=sa.text("extractor IS NOT NULL AND external_id IS NOT NULL"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "submitted_by_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "video_id",
            sa.String(36),
            sa.ForeignKey("videos.id", ondelete="SET NULL"),
        ),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("result", sa.Text()),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        sa.Column(
            "cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "retry_of_id",
            sa.String(36),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
        ),
        sa.Column("lease_owner", sa.String(64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "type IN ('copy_video', 'download_video')", name="ck_tasks_type"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')",
            name="ck_tasks_status",
        ),
        sa.CheckConstraint(
            "progress >= 0 AND progress <= 100", name="ck_tasks_progress"
        ),
    )
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_submitted_by_id", "tasks", ["submitted_by_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_lease_expires_at", "tasks", ["lease_expires_at"])
    op.create_index(
        "uq_tasks_active_video",
        "tasks",
        ["video_id"],
        unique=True,
        sqlite_where=sa.text(
            "video_id IS NOT NULL AND status IN ('queued', 'running')"
        ),
    )


def downgrade() -> None:
    op.drop_table("tasks")
    op.drop_table("videos")
