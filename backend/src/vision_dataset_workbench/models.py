import secrets
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


VIDEO_SHORT_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
VIDEO_SHORT_CODE_LENGTH = 8


def generate_video_short_code() -> str:
    return "".join(
        secrets.choice(VIDEO_SHORT_CODE_ALPHABET)
        for _ in range(VIDEO_SHORT_CODE_LENGTH)
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String(64))
    username_normalized: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active")
    is_system_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    creator_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ProjectMembership(Base):
    __tablename__ = "project_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('editor', 'viewer')", name="ck_project_memberships_role"
        ),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ProjectLabel(Base):
    __tablename__ = "labels"
    __table_args__ = (
        Index(
            "uq_labels_project_name",
            "project_id",
            "name_normalized",
            unique=True,
        ),
        CheckConstraint("sort_order >= 0", name="ck_labels_sort_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    name_normalized: Mapped[str] = mapped_column(String(64))
    description_zh: Mapped[str] = mapped_column(String(64), default="")
    color: Mapped[str] = mapped_column(String(7))
    sort_order: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('local', 'remote')", name="ck_videos_source_type"
        ),
        CheckConstraint(
            "status IN ('pending', 'ready', 'unavailable')",
            name="ck_videos_status",
        ),
        Index(
            "uq_videos_local_hash",
            "project_id",
            "content_sha256",
            unique=True,
            sqlite_where=text("content_sha256 IS NOT NULL"),
        ),
        Index(
            "uq_videos_remote_identity",
            "project_id",
            "extractor",
            "external_id",
            unique=True,
            sqlite_where=text("extractor IS NOT NULL AND external_id IS NOT NULL"),
        ),
        Index(
            "uq_videos_project_short_code",
            "project_id",
            "short_code",
            unique=True,
        ),
        CheckConstraint(
            "length(short_code) = 8 AND "
            "short_code NOT GLOB '*[^0123456789ABCDEFGHJKMNPQRSTVWXYZ]*'",
            name="ck_videos_short_code",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    short_code: Mapped[str] = mapped_column(String(8), default=generate_video_short_code)
    source_type: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(512))
    source_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    extractor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[float] = mapped_column(Float, default=0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    fps: Mapped[float] = mapped_column(Float, default=0)
    total_frames: Mapped[int] = mapped_column(Integer, default=0)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SamplingPlan(Base):
    __tablename__ = "sampling_plans"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('target_frames', 'frame_interval', 'time_interval')",
            name="ck_sampling_plans_mode",
        ),
        CheckConstraint(
            "output_format IN ('jpg', 'png')",
            name="ck_sampling_plans_output_format",
        ),
        CheckConstraint(
            "(output_format = 'jpg' AND output_quality BETWEEN 1 AND 31) OR "
            "(output_format = 'png' AND output_quality BETWEEN 0 AND 9)",
            name="ck_sampling_plans_output_quality",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), unique=True, index=True
    )
    mode: Mapped[str] = mapped_column(String(32))
    parameters: Mapped[str] = mapped_column(Text)
    output_format: Mapped[str] = mapped_column(String(8))
    output_quality: Mapped[int] = mapped_column(Integer)
    computed_interval: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_frames: Mapped[int] = mapped_column(Integer)
    extracted_frames: Mapped[int] = mapped_column(Integer, default=0)
    enabled_frames: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    applied_version: Mapped[int] = mapped_column(Integer, default=0)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    frame_revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Frame(Base):
    __tablename__ = "frames"
    __table_args__ = (
        Index("uq_frames_video_sequence", "video_id", "sequence", unique=True),
        CheckConstraint("sequence >= 1", name="ck_frames_sequence"),
        CheckConstraint("source_frame_index >= 0", name="ck_frames_source_index"),
        CheckConstraint("time_offset >= 0", name="ck_frames_time_offset"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE")
    )
    generation: Mapped[int] = mapped_column(Integer)
    sequence: Mapped[int] = mapped_column(Integer)
    source_frame_index: Mapped[int] = mapped_column(Integer)
    time_offset: Mapped[float] = mapped_column(Float)
    file_path: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    annotation_revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class FrameAnnotation(Base):
    __tablename__ = "annotations"
    __table_args__ = (
        CheckConstraint(
            "x_min >= 0 AND y_min >= 0 AND x_max > x_min AND y_max > y_min",
            name="ck_annotations_bounds",
        ),
        CheckConstraint(
            "source IN ('manual', 'model')", name="ck_annotations_source"
        ),
        CheckConstraint("sort_order >= 0", name="ck_annotations_sort_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    frame_id: Mapped[str] = mapped_column(
        ForeignKey("frames.id", ondelete="CASCADE"), index=True
    )
    label_id: Mapped[str] = mapped_column(
        ForeignKey("labels.id", ondelete="RESTRICT"), index=True
    )
    x_min: Mapped[int] = mapped_column(Integer)
    y_min: Mapped[int] = mapped_column(Integer)
    x_max: Mapped[int] = mapped_column(Integer)
    y_max: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class InferenceModel(Base):
    __tablename__ = "inference_models"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('yolo', 'grounding_dino')",
            name="ck_inference_models_kind",
        ),
        CheckConstraint(
            "status IN ('copying', 'ready', 'failed')",
            name="ck_inference_models_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="copying", index=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(String(512))
    created_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "type IN ('copy_video', 'download_video', 'extract_frames', "
            "'import_model', 'auto_annotate')",
            name="ck_tasks_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')",
            name="ck_tasks_status",
        ),
        CheckConstraint(
            "progress >= 0 AND progress <= 100", name="ck_tasks_progress"
        ),
        Index(
            "uq_tasks_active_video",
            "video_id",
            unique=True,
            sqlite_where=text(
                "video_id IS NOT NULL AND status IN ('queued', 'running')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    submitted_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    video_id: Mapped[str | None] = mapped_column(
        ForeignKey("videos.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retry_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class DatasetExport(Base):
    __tablename__ = "dataset_exports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'failed', 'canceled')",
            name="ck_dataset_exports_status",
        ),
        CheckConstraint(
            "train_ratio >= 0 AND train_ratio <= 1",
            name="ck_dataset_exports_train_ratio",
        ),
        CheckConstraint(
            "actual_train_ratio IS NULL OR "
            "(actual_train_ratio >= 0 AND actual_train_ratio <= 1)",
            name="ck_dataset_exports_actual_train_ratio",
        ),
        CheckConstraint(
            "total_frames >= 0 AND train_frames >= 0 AND val_frames >= 0",
            name="ck_dataset_exports_frame_counts",
        ),
        Index(
            "uq_dataset_exports_active_project",
            "project_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
        Index(
            "ix_dataset_exports_project_created",
            "project_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    created_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    train_ratio: Mapped[float] = mapped_column(Float)
    actual_train_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_frames: Mapped[int] = mapped_column(Integer, default=0)
    train_frames: Mapped[int] = mapped_column(Integer, default=0)
    val_frames: Mapped[int] = mapped_column(Integer, default=0)
    label_snapshot: Mapped[str] = mapped_column(Text, default="[]")
    source_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    manifest: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
