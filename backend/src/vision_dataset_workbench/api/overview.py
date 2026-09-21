from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import User, Video
from .auth import current_user

router = APIRouter(prefix="/api/v1/overview", tags=["overview"])


@router.get("")
def overview(request: Request, user: Annotated[User, Depends(current_user)]) -> dict[str, object]:
    engine = request.app.state.auth_service.engine
    project_service = request.app.state.project_service
    model_service = request.app.state.model_service
    training_service = request.app.state.training_service
    projects, project_count = project_service.list_projects(user, page=1, page_size=10_000)
    model_projects = model_service.list_projects(user)
    training_tasks = training_service.list_tasks(user)
    project_ids = [item.project.id for item in projects]
    with Session(engine) as db:
        running = [task for task in training_tasks if task.status == "running"]
        return {
            "projects": project_count,
            "videos": db.scalar(
                select(func.count()).select_from(Video).where(Video.project_id.in_(project_ids))
            ) or 0,
            "model_projects": len(model_projects),
            "training_tasks": len(training_tasks),
            "running_tasks": {
                "own": sum(task.created_by_id == user.id for task in running),
                "global": len(running),
            },
            "task_status": [
                {
                    "status": status,
                    "count": sum(task.status == status for task in training_tasks),
                }
                for status in ("draft", "queued", "running", "failed", "succeeded")
            ],
            "host": {"hostname": request.app.state.settings.home.name, "note": "主机标识已脱敏"},
        }
