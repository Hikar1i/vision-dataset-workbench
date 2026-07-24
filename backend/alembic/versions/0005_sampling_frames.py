import sqlalchemy as sa
from alembic import op

revision = "0005_sampling_frames"
down_revision = "0004_media_tasks"
branch_labels = None
depends_on = None


def _task_type_constraint(values: str) -> None:
    with op.batch_alter_table("tasks", recreate="always") as batch:
        batch.drop_constraint("ck_tasks_type", type_="check")
        batch.create_check_constraint("ck_tasks_type", f"type IN ({values})")


def upgrade() -> None:
    _task_type_constraint("'copy_video', 'download_video', 'extract_frames'")
    op.create_table(
        "sampling_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "video_id",
            sa.String(36),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("parameters", sa.Text(), nullable=False),
        sa.Column("output_format", sa.String(8), nullable=False),
        sa.Column("output_quality", sa.Integer(), nullable=False),
        sa.Column("computed_interval", sa.Integer()),
        sa.Column("expected_frames", sa.Integer(), nullable=False),
        sa.Column("extracted_frames", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled_frames", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("applied_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("frame_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mode IN ('target_frames', 'frame_interval', 'time_interval')",
            name="ck_sampling_plans_mode",
        ),
        sa.CheckConstraint(
            "output_format IN ('jpg', 'png')",
            name="ck_sampling_plans_output_format",
        ),
        sa.CheckConstraint(
            "(output_format = 'jpg' AND output_quality BETWEEN 1 AND 31) OR "
            "(output_format = 'png' AND output_quality BETWEEN 0 AND 9)",
            name="ck_sampling_plans_output_quality",
        ),
    )
    op.create_index(
        "ix_sampling_plans_video_id",
        "sampling_plans",
        ["video_id"],
        unique=True,
    )
    op.create_table(
        "frames",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "video_id",
            sa.String(36),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("source_frame_index", sa.Integer(), nullable=False),
        sa.Column("time_offset", sa.Float(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_frames_sequence"),
        sa.CheckConstraint("source_frame_index >= 0", name="ck_frames_source_index"),
        sa.CheckConstraint("time_offset >= 0", name="ck_frames_time_offset"),
    )
    op.create_index("ix_frames_video_id", "frames", ["video_id"])
    op.create_index("ix_frames_enabled", "frames", ["enabled"])
    op.create_index(
        "uq_frames_video_sequence", "frames", ["video_id", "sequence"], unique=True
    )


def downgrade() -> None:
    op.drop_table("frames")
    op.drop_table("sampling_plans")
    _task_type_constraint("'copy_video', 'download_video'")
