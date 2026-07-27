from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ..capabilities import SystemCapabilities
from ..models import User
from .auth import current_user

router = APIRouter(prefix="/api/v1/capabilities", tags=["capabilities"])


@router.get("", response_model=SystemCapabilities)
def capabilities(
    request: Request,
    _user: Annotated[User, Depends(current_user)],
) -> SystemCapabilities:
    return request.app.state.capabilities
