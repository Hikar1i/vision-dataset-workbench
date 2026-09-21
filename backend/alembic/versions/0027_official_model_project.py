import json
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0027_official_model_project"
down_revision = "0026_access_control_refactor"
branch_labels = None
depends_on = None

TEMPORARY_PROJECT_ID = "00000000-0000-0000-0000-000000000001"
OFFICIAL_PROJECT_ID = "00000100-0000-4000-8000-000000000001"
OFFICIAL_PROJECT_NAME = "YOLO11目标检测官方模型"
OFFICIAL_SYSTEM_KEY = "official_yolo11"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _contains_model_id(value: object, model_ids: set[str]) -> bool:
    if isinstance(value, str):
        return value in model_ids
    if isinstance(value, list):
        return any(_contains_model_id(item, model_ids) for item in value)
    if isinstance(value, dict):
        return any(_contains_model_id(item, model_ids) for item in value.values())
    return False


def _validate_temporary_references(connection) -> None:
    model_ids = set(
        connection.execute(
            sa.text(
                "SELECT id FROM inference_models WHERE model_project_id=:project_id"
            ),
            {"project_id": TEMPORARY_PROJECT_ID},
        ).scalars()
    )
    if not model_ids:
        return

    training_references = connection.execute(
        sa.text(
            "SELECT "
            "(SELECT count(*) FROM training_tasks WHERE default_base_model_id IN "
            " (SELECT id FROM inference_models WHERE model_project_id=:project_id)) + "
            "(SELECT count(*) FROM training_models WHERE base_model_id IN "
            " (SELECT id FROM inference_models WHERE model_project_id=:project_id)) + "
            "(SELECT count(*) FROM inference_models WHERE model_project_id=:project_id "
            " AND training_model_id IS NOT NULL)"
        ),
        {"project_id": TEMPORARY_PROJECT_ID},
    ).scalar_one()
    if training_references:
        raise RuntimeError("temporary model project is referenced by a training resource")

    evaluation_references = connection.execute(
        sa.text(
            "SELECT count(*) FROM model_evaluations "
            "WHERE model_id IN (SELECT id FROM inference_models "
            " WHERE model_project_id=:project_id) "
            "AND model_project_id<>:project_id"
        ),
        {"project_id": TEMPORARY_PROJECT_ID},
    ).scalar_one()
    if evaluation_references:
        raise RuntimeError("temporary model project is referenced by an external evaluation")

    for row in connection.execute(
        sa.text(
            "SELECT id, payload FROM tasks "
            "WHERE model_project_id IS NULL OR model_project_id<>:project_id"
        ),
        {"project_id": TEMPORARY_PROJECT_ID},
    ).mappings():
        try:
            payload = json.loads(row["payload"] or "{}")
        except (TypeError, ValueError):
            continue
        if _contains_model_id(payload, model_ids):
            raise RuntimeError(
                f"temporary model project is referenced by external task {row['id']}"
            )


def _validate_temporary_templates(connection) -> None:
    references = connection.execute(
        sa.text(
            "SELECT "
            "(SELECT count(*) FROM training_tasks WHERE default_template_id IN "
            " (SELECT id FROM hyperparameter_templates WHERE model_project_id=:project_id)) + "
            "(SELECT count(*) FROM training_models WHERE template_id IN "
            " (SELECT id FROM hyperparameter_templates WHERE model_project_id=:project_id)) + "
            "(SELECT count(*) FROM hyperparameter_templates "
            " WHERE model_project_id IS NOT :project_id AND derived_from_id IN "
            " (SELECT id FROM hyperparameter_templates WHERE model_project_id=:project_id))"
        ),
        {"project_id": TEMPORARY_PROJECT_ID},
    ).scalar_one()
    if references:
        raise RuntimeError("temporary model project template is referenced externally")


def _delete_temporary_project(connection) -> None:
    parameters = {"project_id": TEMPORARY_PROJECT_ID}
    temp_models = "SELECT id FROM inference_models WHERE model_project_id=:project_id"
    temp_datasets = (
        "SELECT id FROM evaluation_datasets WHERE model_project_id=:project_id"
    )
    connection.execute(
        sa.text(
            "DELETE FROM model_evaluations WHERE model_project_id=:project_id "
            f"OR model_id IN ({temp_models}) OR evaluation_dataset_id IN ({temp_datasets})"
        ),
        parameters,
    )
    connection.execute(
        sa.text(f"DELETE FROM model_inference_runs WHERE model_id IN ({temp_models})"),
        parameters,
    )
    connection.execute(
        sa.text(f"DELETE FROM model_artifacts WHERE model_id IN ({temp_models})"),
        parameters,
    )
    connection.execute(
        sa.text("DELETE FROM evaluation_datasets WHERE model_project_id=:project_id"),
        parameters,
    )
    connection.execute(
        sa.text("DELETE FROM tasks WHERE model_project_id=:project_id"), parameters
    )
    connection.execute(
        sa.text("DELETE FROM inference_models WHERE model_project_id=:project_id"),
        parameters,
    )
    connection.execute(
        sa.text(
            "UPDATE hyperparameter_templates SET derived_from_id=NULL "
            "WHERE model_project_id=:project_id"
        ),
        parameters,
    )
    connection.execute(
        sa.text(
            "DELETE FROM hyperparameter_templates WHERE model_project_id=:project_id"
        ),
        parameters,
    )
    connection.execute(
        sa.text(
            "DELETE FROM model_project_memberships WHERE model_project_id=:project_id"
        ),
        parameters,
    )
    connection.execute(
        sa.text(
            "DELETE FROM model_project_tag_links WHERE model_project_id=:project_id"
        ),
        parameters,
    )
    connection.execute(
        sa.text("DELETE FROM model_projects WHERE id=:project_id"), parameters
    )
    connection.execute(
        sa.text(
            "DELETE FROM model_project_tags WHERE NOT EXISTS "
            "(SELECT 1 FROM model_project_tag_links "
            " WHERE model_project_tag_links.tag_id=model_project_tags.id)"
        )
    )


def _install_official_project(connection) -> None:
    candidates = list(
        connection.execute(
            sa.text(
                "SELECT id FROM model_projects "
                "WHERE name=:name AND deleted_at IS NULL"
            ),
            {"name": OFFICIAL_PROJECT_NAME},
        ).scalars()
    )
    if len(candidates) > 1:
        raise RuntimeError("multiple active YOLO11 official model project candidates")
    system_project = connection.execute(
        sa.text("SELECT id FROM model_projects WHERE system_key=:system_key"),
        {"system_key": OFFICIAL_SYSTEM_KEY},
    ).scalar_one_or_none()
    candidate_id = candidates[0] if candidates else OFFICIAL_PROJECT_ID
    if system_project is not None and system_project != candidate_id:
        raise RuntimeError("official_yolo11 system key belongs to another model project")

    now = _utc_now()
    if candidates:
        connection.execute(
            sa.text(
                "UPDATE model_projects SET system_key=:system_key, created_by_id=NULL, "
                "name_normalized=:normalized, version=version+1, updated_at=:updated_at "
                "WHERE id=:project_id"
            ),
            {
                "system_key": OFFICIAL_SYSTEM_KEY,
                "normalized": OFFICIAL_PROJECT_NAME.lower(),
                "updated_at": now,
                "project_id": candidate_id,
            },
        )
    else:
        occupied = connection.execute(
            sa.text("SELECT name FROM model_projects WHERE id=:project_id"),
            {"project_id": OFFICIAL_PROJECT_ID},
        ).scalar_one_or_none()
        if occupied is not None:
            raise RuntimeError("fixed official model project id is already occupied")
        connection.execute(
            sa.text(
                "INSERT INTO model_projects "
                "(id, name, name_normalized, description, series_type, system_key, "
                "created_by_id, version, created_at, updated_at, deleted_at, training_task_id) "
                "VALUES (:id, :name, :normalized, :description, 'archive', :system_key, "
                "NULL, 1, :created_at, :updated_at, NULL, NULL)"
            ),
            {
                "id": OFFICIAL_PROJECT_ID,
                "name": OFFICIAL_PROJECT_NAME,
                "normalized": OFFICIAL_PROJECT_NAME.lower(),
                "description": "系统内置的 YOLO11 目标检测官方模型项目。",
                "system_key": OFFICIAL_SYSTEM_KEY,
                "created_at": now,
                "updated_at": now,
            },
        )

    connection.execute(
        sa.text(
            "DELETE FROM model_project_memberships WHERE model_project_id=:project_id"
        ),
        {"project_id": candidate_id},
    )
    tag_id = connection.execute(
        sa.text(
            "SELECT id FROM model_project_tags WHERE name_normalized=:normalized"
        ),
        {"normalized": "内置"},
    ).scalar_one_or_none()
    if tag_id is None:
        tag_id = str(uuid4())
        connection.execute(
            sa.text(
                "INSERT INTO model_project_tags (id, name, name_normalized, created_at) "
                "VALUES (:id, :name, :normalized, :created_at)"
            ),
            {
                "id": tag_id,
                "name": "内置",
                "normalized": "内置",
                "created_at": now,
            },
        )
    connection.execute(
        sa.text(
            "INSERT OR IGNORE INTO model_project_tag_links (model_project_id, tag_id) "
            "VALUES (:project_id, :tag_id)"
        ),
        {"project_id": candidate_id, "tag_id": tag_id},
    )


def upgrade() -> None:
    connection = op.get_bind()
    _validate_temporary_references(connection)
    _validate_temporary_templates(connection)
    _install_official_project(connection)
    _delete_temporary_project(connection)


def downgrade() -> None:
    raise RuntimeError("0027 cannot restore the deleted temporary model project")
