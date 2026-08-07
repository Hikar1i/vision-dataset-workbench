from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ModelProject, Project, TrainingTask, User, Video
from .auth import current_user

router = APIRouter(prefix="/api/v1/overview", tags=["overview"])


@router.get("")
def overview(request: Request, user: Annotated[User, Depends(current_user)]) -> dict[str, object]:
    engine = request.app.state.auth_service.engine
    with Session(engine) as db:
        own_project_ids = select(Project.id).where(Project.creator_id == user.id)
        running_own = db.scalar(select(func.count()).select_from(TrainingTask).where(TrainingTask.created_by_id == user.id, TrainingTask.status == "running", TrainingTask.deleted_at.is_(None))) or 0
        running_global = db.scalar(select(func.count()).select_from(TrainingTask).where(TrainingTask.status == "running", TrainingTask.deleted_at.is_(None))) or 0
        return {
            "projects": db.scalar(select(func.count()).select_from(Project).where(Project.deleted_at.is_(None), Project.creator_id == user.id)) or 0,
            "videos": db.scalar(select(func.count()).select_from(Video).where(Video.project_id.in_(own_project_ids))) or 0,
            "model_projects": db.scalar(select(func.count()).select_from(ModelProject).where(ModelProject.deleted_at.is_(None))) or 0,
            "training_tasks": db.scalar(select(func.count()).select_from(TrainingTask).where(TrainingTask.created_by_id == user.id, TrainingTask.deleted_at.is_(None))) or 0,
            "running_tasks": {"own": running_own, "global": running_global},
            "task_status": [
                {"status": status, "count": db.scalar(select(func.count()).select_from(TrainingTask).where(TrainingTask.status == status, TrainingTask.deleted_at.is_(None))) or 0}
                for status in ("draft", "queued", "running", "failed", "succeeded")
            ],
            "host": {"hostname": request.app.state.settings.home.name, "note": "主机标识已脱敏"},
        }
