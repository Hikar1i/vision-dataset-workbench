from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..models import User
from ..services.images import ImageConflict, ImageNotFound
from ..services.auto_annotations import AutoAnnotationConflict, AutoAnnotationUnavailable
from ..services.models import ModelForbidden, ModelNotFound
from ..services.projects import ProjectConflict, ProjectForbidden, ProjectNotFound
from .auto_annotations import (
    RunAutoAnnotationRequest,
    RunBatchAutoAnnotationRequest,
    auto_annotation_service,
)
from .labels import _label_response
from .auth import current_user, require_same_origin
from .media import _task_response

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["images"])


def image_service(request: Request):
    service = request.app.state.image_service
    if service is None:
        raise HTTPException(503, "workspace is not initialized")
    return service


def raise_image_error(exc):
    code = (
        404
        if isinstance(exc, (ImageNotFound, ProjectNotFound, ModelNotFound, FileNotFoundError))
        else (
            403
            if isinstance(exc, (ProjectForbidden, ModelForbidden))
            else (
                409
                if isinstance(exc, (ImageConflict, ProjectConflict, AutoAnnotationConflict))
                else 422
            )
        )
    )
    if isinstance(exc, AutoAnnotationUnavailable):
        code = 503
    raise HTTPException(
        code, str(exc) if not isinstance(exc, OSError) else "来源文件无法读取"
    ) from exc


def annotation_response(a):
    return {
        k: getattr(a, k)
        for k in ("id", "label_id", "x_min", "y_min", "x_max", "y_max", "source", "confidence")
    }


def image_response(image, annotations=()):
    return {
        **{
            k: getattr(image, k)
            for k in (
                "id",
                "directory_id",
                "source_relative_path",
                "file_name",
                "content_sha256",
                "width",
                "height",
                "file_size",
                "materialization",
                "enabled",
                "annotation_status",
                "annotation_revision",
                "version",
                "created_at",
                "updated_at",
            )
        },
        "annotations": [annotation_response(a) for a in annotations if a.image_id == image.id],
    }


class PreviewRequest(BaseModel):
    root_path: str = Field(min_length=1, max_length=2048)
    format: Literal["auto", "images", "yolo_detect"] | None = None
    ignore_annotations: bool = False


class ClassMapping(BaseModel):
    source_id: int = Field(ge=0)
    project_label_id: str | None = None
    new_label_name: str | None = None


class ImportRequest(PreviewRequest):
    fingerprint: str = Field(min_length=64, max_length=64)
    class_mapping: list[ClassMapping] = Field(default_factory=list, max_length=10000)
    confirm_warnings: bool = False


class ImageAnnotationItem(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    label_id: str = Field(min_length=1, max_length=36)
    x_min: float = Field(ge=0, allow_inf_nan=False)
    y_min: float = Field(ge=0, allow_inf_nan=False)
    x_max: float = Field(gt=0, allow_inf_nan=False)
    y_max: float = Field(gt=0, allow_inf_nan=False)
    source: Literal["import", "manual", "model"] = "manual"
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class ReplaceRequest(BaseModel):
    annotation_revision: int = Field(ge=1)
    items: list[ImageAnnotationItem] = Field(max_length=10000)


class EnabledChange(BaseModel):
    image_id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)
    enabled: bool


class EnabledRequest(BaseModel):
    changes: list[EnabledChange] = Field(min_length=1)


class ImageVersionItem(BaseModel):
    image_id: str = Field(min_length=1, max_length=36)
    version: int = Field(ge=1)


class ImageItemsRequest(BaseModel):
    items: list[ImageVersionItem] = Field(min_length=1, max_length=200)


class DuplicateRequest(BaseModel):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def image_filters(
    directory_id: str | None = None,
    search: str | None = Query(default=None, max_length=512),
    annotation_status: Literal["pending", "labeled"] | None = None,
    enabled: bool | None = None,
    label_id: str | None = None,
):
    return dict(
        directory_id=directory_id,
        search=search,
        annotation_status=annotation_status,
        enabled=enabled,
        label_id=label_id,
    )


@router.post("/image-imports/preview")
def preview(
    project_id: str,
    payload: PreviewRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
):
    require_same_origin(request)
    try:
        return image_service(request).preview(
            user, project_id, payload.root_path, payload.format, payload.ignore_annotations
        )
    except (ValueError, OSError) as exc:
        raise_image_error(exc)


@router.post("/image-imports", status_code=202)
def create_import(
    project_id: str,
    payload: ImportRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
):
    require_same_origin(request)
    try:
        batch, task = image_service(request).create_import(
            user,
            project_id,
            payload.root_path,
            payload.format,
            payload.fingerprint,
            [m.model_dump() for m in payload.class_mapping],
            payload.confirm_warnings,
            payload.ignore_annotations,
        )
        return {"import_id": batch.id, "task": _task_response(task)}
    except (ValueError, OSError) as exc:
        raise_image_error(exc)


@router.get("/image-directories")
def directories(project_id: str, request: Request, user: Annotated[User, Depends(current_user)]):
    try:
        return image_service(request).directories(user, project_id)
    except ValueError as exc:
        raise_image_error(exc)


@router.get("/images")
def images(
    project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    filters: Annotated[dict, Depends(image_filters)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=50, le=200),
):
    try:
        if page_size not in {50, 100, 200}:
            raise ValueError("page_size 必须为 50、100 或 200")
        items, annotations, total = image_service(request).list_images(
            user, project_id, page=page, page_size=page_size, **filters
        )
        return {
            "items": [image_response(i, annotations) for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except ValueError as exc:
        raise_image_error(exc)


@router.post("/images/enabled")
def enabled(
    project_id: str,
    payload: EnabledRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
):
    require_same_origin(request)
    try:
        return [
            {"id": i.id, "enabled": i.enabled, "version": i.version}
            for i in image_service(request).change_enabled(
                user, project_id, [c.model_dump() for c in payload.changes]
            )
        ]
    except ValueError as exc:
        raise_image_error(exc)


@router.get("/images/duplicates")
def duplicates(project_id: str, request: Request, user: Annotated[User, Depends(current_user)]):
    try:
        return image_service(request).duplicates(user, project_id)
    except ValueError as exc:
        raise_image_error(exc)


@router.post("/images/duplicates/disable")
def disable_duplicates(
    project_id: str,
    payload: DuplicateRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
):
    require_same_origin(request)
    try:
        return image_service(request).disable_duplicates(user, project_id, payload.fingerprint)
    except ValueError as exc:
        raise_image_error(exc)


@router.post("/images/delete")
def delete_images(
    project_id: str,
    payload: ImageItemsRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
):
    require_same_origin(request)
    try:
        return image_service(request).delete(
            user, project_id, [i.model_dump() for i in payload.items]
        )
    except (ValueError, OSError) as exc:
        raise_image_error(exc)


@router.post("/images/enabled-by-annotations")
def enabled_by_annotations(
    project_id: str,
    payload: ImageItemsRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
):
    require_same_origin(request)
    try:
        return {
            "changes": [
                {"id": i.id, "enabled": i.enabled, "version": i.version}
                for i in image_service(request).change_enabled(
                    user, project_id, [i.model_dump() for i in payload.items], by_annotations=True
                )
            ]
        }
    except ValueError as exc:
        raise_image_error(exc)


@router.get("/images/{image_id}")
def get_image(
    project_id: str, image_id: str, request: Request, user: Annotated[User, Depends(current_user)]
):
    try:
        return image_response(*image_service(request).get(user, project_id, image_id))
    except ValueError as exc:
        raise_image_error(exc)


@router.get("/images/{image_id}/neighbors")
def neighbors(
    project_id: str,
    image_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    filters: Annotated[dict, Depends(image_filters)],
):
    try:
        return image_service(request).neighbors(user, project_id, image_id, **filters)
    except ValueError as exc:
        raise_image_error(exc)


@router.get("/images/{image_id}/file")
def file(
    project_id: str, image_id: str, request: Request, user: Annotated[User, Depends(current_user)]
):
    try:
        return FileResponse(image_service(request).file(user, project_id, image_id))
    except ValueError as exc:
        raise_image_error(exc)


@router.get("/images/{image_id}/thumbnail")
def thumbnail(
    project_id: str, image_id: str, request: Request, user: Annotated[User, Depends(current_user)]
):
    try:
        return FileResponse(image_service(request).file(user, project_id, image_id, thumbnail=True))
    except ValueError as exc:
        raise_image_error(exc)


@router.get("/images/{image_id}/annotations")
def annotations(
    project_id: str, image_id: str, request: Request, user: Annotated[User, Depends(current_user)]
):
    try:
        image, items = image_service(request).get(user, project_id, image_id)
        return {
            "image_id": image.id,
            "annotation_revision": image.annotation_revision,
            "annotation_status": image.annotation_status,
            "items": [annotation_response(a) for a in items],
        }
    except ValueError as exc:
        raise_image_error(exc)


@router.put("/images/{image_id}/annotations")
def replace(
    project_id: str,
    image_id: str,
    payload: ReplaceRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
):
    require_same_origin(request)
    try:
        image, items = image_service(request).replace(
            user,
            project_id,
            image_id,
            payload.annotation_revision,
            [i.model_dump() for i in payload.items],
        )
        return {
            "image_id": image.id,
            "annotation_revision": image.annotation_revision,
            "annotation_status": image.annotation_status,
            "items": [annotation_response(a) for a in items],
        }
    except ValueError as exc:
        raise_image_error(exc)


class ImageBatchRequest(RunBatchAutoAnnotationRequest):
    image_ids: list[str] = Field(min_length=1, max_length=200)
    scope: Literal["all", "unannotated"] = "all"


@router.post("/images/{image_id}/auto-annotations")
def auto_image(
    project_id: str,
    image_id: str,
    payload: RunAutoAnnotationRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
):
    require_same_origin(request)
    try:
        result = auto_annotation_service(request).run_image(
            user, project_id, image_id, **payload.model_dump()
        )
        return {
            "items": [{**i.annotation.__dict__, "label_name": i.label_name} for i in result.items],
            "created_labels": [_label_response(i) for i in result.created_labels],
        }
    except ValueError as exc:
        raise_image_error(exc)


@router.post("/images/auto-annotations", status_code=202)
def auto_batch(
    project_id: str,
    payload: ImageBatchRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
):
    require_same_origin(request)
    try:
        return _task_response(
            auto_annotation_service(request).create_image_batch(
                user, project_id, **payload.model_dump()
            )
        )
    except ValueError as exc:
        raise_image_error(exc)
