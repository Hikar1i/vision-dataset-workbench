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
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


VIDEO_SHORT_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
VIDEO_SHORT_CODE_LENGTH = 8
TEMPORARY_MODEL_PROJECT_ID = "00000000-0000-0000-0000-000000000001"


def generate_video_short_code() -> str:
    return "".join(
        secrets.choice(VIDEO_SHORT_CODE_ALPHABET) for _ in range(VIDEO_SHORT_CODE_LENGTH)
    )


def generate_model_code() -> str:
    return f"model-{secrets.token_hex(4)}"


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
    reviewed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
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
    creator_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
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
        CheckConstraint("role IN ('editor', 'viewer')", name="ck_project_memberships_role"),
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
        CheckConstraint("source_type IN ('local', 'remote')", name="ck_videos_source_type"),
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
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
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
        CheckConstraint("source IN ('manual', 'model')", name="ck_annotations_source"),
        CheckConstraint("sort_order >= 0", name="ck_annotations_sort_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    frame_id: Mapped[str] = mapped_column(ForeignKey("frames.id", ondelete="CASCADE"), index=True)
    label_id: Mapped[str] = mapped_column(ForeignKey("labels.id", ondelete="RESTRICT"), index=True)
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


class ModelProject(Base):
    __tablename__ = "model_projects"
    __table_args__ = (
        CheckConstraint(
            "series_type IN ('archive', 'training')",
            name="ck_model_projects_series_type",
        ),
        UniqueConstraint("system_key", name="uq_model_projects_system_key"),
        Index(
            "uq_model_projects_active_name",
            "name_normalized",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128))
    name_normalized: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    series_type: Mapped[str] = mapped_column(String(16))
    system_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    training_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_tasks.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InferenceModel(Base):
    __tablename__ = "inference_models"
    __table_args__ = (
        CheckConstraint(
            "kind = 'yolo'",
            name="ck_inference_models_kind",
        ),
        CheckConstraint(
            "status IN ('copying', 'ready', 'failed')",
            name="ck_inference_models_status",
        ),
        CheckConstraint(
            "file_size IS NULL OR file_size >= 0", name="ck_inference_models_file_size"
        ),
        Index(
            "uq_inference_models_active_code",
            "model_project_id",
            "model_code",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    model_project_id: Mapped[str] = mapped_column(
        ForeignKey("model_projects.id", ondelete="RESTRICT"),
        default=TEMPORARY_MODEL_PROJECT_ID,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128))
    model_code: Mapped[str] = mapped_column(String(64), default=generate_model_code)
    kind: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text, default="")
    parameters: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="copying", index=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_name: Mapped[str] = mapped_column(String(512))
    created_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    training_model_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_models.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserXAnyLabelingSetting(Base):
    __tablename__ = "user_xanylabeling_settings"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    server_url: Mapped[str] = mapped_column(Text)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class HyperparameterTemplate(Base):
    __tablename__ = "hyperparameter_templates"
    __table_args__ = (
        CheckConstraint("epochs BETWEEN 1 AND 100000", name="ck_templates_epochs"),
        CheckConstraint(
            "image_size BETWEEN 32 AND 8192 AND image_size % 32 = 0",
            name="ck_templates_image_size",
        ),
        CheckConstraint(
            "(batch_mode = 'auto' AND batch_value IS NULL) OR "
            "(batch_mode = 'fixed' AND batch_value BETWEEN 1 AND 4096) OR "
            "(batch_mode = 'fraction' AND batch_value > 0 AND batch_value <= 1)",
            name="ck_templates_batch",
        ),
        Index(
            "uq_templates_active_name",
            "name_normalized",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128))
    name_normalized: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    epochs: Mapped[int] = mapped_column(Integer)
    batch_mode: Mapped[str] = mapped_column(String(16))
    batch_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_size: Mapped[int] = mapped_column(Integer)
    extra_parameters: Mapped[str] = mapped_column(Text, default="{}")
    catalog_version: Mapped[str] = mapped_column(String(32))
    system_key: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    derived_from_id: Mapped[str | None] = mapped_column(
        ForeignKey("hyperparameter_templates.id", ondelete="RESTRICT"), nullable=True
    )
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrainingTask(Base):
    __tablename__ = "training_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','queued','running','canceling','canceled','start_failed','failed','partial','succeeded')",
            name="ck_training_tasks_status",
        ),
        CheckConstraint(
            "mode IN ('single_model','single_device_serial','custom_sequence')",
            name="ck_training_tasks_mode",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_training_tasks_progress"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    mode: Mapped[str] = mapped_column(String(32), default="single_model")
    progress: Mapped[float] = mapped_column(Float, default=0)
    default_dataset_export_id: Mapped[str | None] = mapped_column(
        ForeignKey("dataset_exports.id", ondelete="RESTRICT"), nullable=True
    )
    default_template_id: Mapped[str | None] = mapped_column(
        ForeignKey("hyperparameter_templates.id", ondelete="RESTRICT"), nullable=True
    )
    default_base_model_id: Mapped[str | None] = mapped_column(
        ForeignKey("inference_models.id", ondelete="RESTRICT"), nullable=True
    )
    created_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrainingModel(Base):
    __tablename__ = "training_models"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','queued','running','canceling','canceled','start_failed','failed','succeeded')",
            name="ck_training_models_status",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_training_models_progress"),
        CheckConstraint(
            "gpu_index >= 0 AND queue_order BETWEEN 1 AND 10", name="ck_training_models_lane"
        ),
        UniqueConstraint(
            "training_task_id", "gpu_index", "queue_order", name="uq_training_models_lane_order"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    training_task_id: Mapped[str] = mapped_column(
        ForeignKey("training_tasks.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    artifact_code: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)
    dataset_export_id: Mapped[str | None] = mapped_column(
        ForeignKey("dataset_exports.id", ondelete="RESTRICT"), nullable=True
    )
    template_id: Mapped[str | None] = mapped_column(
        ForeignKey("hyperparameter_templates.id", ondelete="RESTRICT"), nullable=True
    )
    base_model_id: Mapped[str | None] = mapped_column(
        ForeignKey("inference_models.id", ondelete="RESTRICT"), nullable=True
    )
    epochs_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    batch_mode_override: Mapped[str | None] = mapped_column(String(16), nullable=True)
    batch_value_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_size_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dataset_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    template_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    base_model_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    gpu_index: Mapped[int] = mapped_column(Integer, default=0)
    queue_order: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0)
    derived_from_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_models.id", ondelete="RESTRICT"), nullable=True
    )
    continuation_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("training_models.id", ondelete="RESTRICT"), nullable=True
    )
    continuation_checkpoint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrainingRun(Base):
    __tablename__ = "training_runs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('initial','retry','resume','extend')", name="ck_training_runs_kind"
        ),
        CheckConstraint(
            "status IN ('queued','running','canceling','canceled','start_failed','failed','succeeded')",
            name="ck_training_runs_status",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_training_runs_progress"),
        UniqueConstraint("training_model_id", "attempt_no", name="uq_training_runs_attempt"),
        Index(
            "uq_training_runs_active_gpu",
            "gpu_index",
            unique=True,
            sqlite_where=text("status IN ('running','canceling')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    training_model_id: Mapped[str] = mapped_column(
        ForeignKey("training_models.id", ondelete="CASCADE"), index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), index=True)
    gpu_index: Mapped[int] = mapped_column(Integer)
    queue_order: Mapped[int] = mapped_column(Integer)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_token: Mapped[str] = mapped_column(String(64), unique=True)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    event_offset: Mapped[int] = mapped_column(Integer, default=0)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)
    current_epoch: Mapped[int] = mapped_column(Integer, default=0)
    target_epochs: Mapped[int] = mapped_column(Integer)
    progress: Mapped[float] = mapped_column(Float, default=0)
    storage_path: Mapped[str] = mapped_column(Text)
    best_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    host_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrainingMetric(Base):
    __tablename__ = "training_metrics"
    __table_args__ = (CheckConstraint("epoch >= 1", name="ck_training_metrics_epoch"),)

    training_run_id: Mapped[str] = mapped_column(
        ForeignKey("training_runs.id", ondelete="CASCADE"), primary_key=True
    )
    epoch: Mapped[int] = mapped_column(Integer, primary_key=True)
    box_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    cls_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    learning_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    map50: Mapped[float | None] = mapped_column(Float, nullable=True)
    map50_95: Mapped[float | None] = mapped_column(Float, nullable=True)
    pr_curve: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TrainingActionRequest(Base):
    __tablename__ = "training_action_requests"
    __table_args__ = (
        UniqueConstraint(
            "actor_id", "action", "idempotency_key", name="uq_training_action_request"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    result_type: Mapped[str] = mapped_column(String(16))
    result_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "type IN ('copy_video', 'download_video', 'extract_frames', "
            "'import_model', 'auto_annotate', 'export_dataset')",
            name="ck_tasks_type",
        ),
        CheckConstraint(
            "(type = 'import_model' AND model_project_id IS NOT NULL AND project_id IS NULL) "
            "OR (type <> 'import_model' AND project_id IS NOT NULL AND model_project_id IS NULL)",
            name="ck_tasks_resource",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')",
            name="ck_tasks_status",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_tasks_progress"),
        Index(
            "uq_tasks_active_video",
            "video_id",
            unique=True,
            sqlite_where=text("video_id IS NOT NULL AND status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    model_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_projects.id", ondelete="RESTRICT"), index=True, nullable=True
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
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
            "actual_train_ratio IS NULL OR (actual_train_ratio >= 0 AND actual_train_ratio <= 1)",
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
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
