from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from ..capabilities import SystemCapabilities
from ..models import User
from .auth import current_user

router = APIRouter(prefix="/api/v1/capabilities", tags=["capabilities"])


def require_model_runtime(request: Request, model_format: str) -> None:
    status = request.app.state.capabilities
    checks = [status.gpu, status.features.yolo_auto_annotation]
    if model_format == "onnx":
        checks.append(status.features.onnx_inference)
    elif model_format == "engine":
        checks.append(status.features.tensorrt)
    for check in checks:
        if not check.available:
            raise HTTPException(409, check.reason or "本地模型运行能力不可用")


@router.get("", response_model=SystemCapabilities)
def capabilities(
    request: Request,
    _user: Annotated[User, Depends(current_user)],
) -> SystemCapabilities:
    return request.app.state.capabilities
