import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ..models import HyperparameterTemplate, User
from ..training.hyperparameters import CATALOG_VERSION, effective_parameters, validate_values


class TemplateNotFound(ValueError):
    pass


class TemplateForbidden(ValueError):
    pass


class TemplateConflict(ValueError):
    pass


class InvalidTemplate(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _text(value: str, maximum: int, field: str, required: bool = False) -> str:
    clean = " ".join(value.strip().split())
    if (required and not clean) or len(clean) > maximum:
        raise InvalidTemplate(f"invalid {field}")
    return clean


class HyperparameterTemplateService:
    def __init__(self, engine: Engine):
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    @staticmethod
    def can_manage(actor: User, template: HyperparameterTemplate) -> bool:
        return template.system_key is None and (
            actor.is_system_admin or template.created_by_id == actor.id
        )

    def list(self, actor: User) -> list[HyperparameterTemplate]:
        with self._session_factory() as database:
            items = list(
                database.scalars(
                    select(HyperparameterTemplate)
                    .where(HyperparameterTemplate.deleted_at.is_(None))
                    .order_by(HyperparameterTemplate.created_at.desc(), HyperparameterTemplate.id)
                )
            )
            for item in items:
                database.expunge(item)
            return items

    def get(self, actor: User, template_id: str) -> HyperparameterTemplate:
        with self._session_factory() as database:
            item = database.get(HyperparameterTemplate, template_id)
            if item is None or item.deleted_at is not None:
                raise TemplateNotFound("hyperparameter template not found")
            database.expunge(item)
            return item

    def create(
        self,
        actor: User,
        *,
        name: str,
        description: str,
        epochs: int,
        batch_mode: str,
        batch_value: float | None,
        image_size: int,
        extra_parameters: dict[str, object],
        derived_from_id: str | None = None,
    ) -> HyperparameterTemplate:
        fields = self._validated_fields(
            name=name,
            description=description,
            epochs=epochs,
            batch_mode=batch_mode,
            batch_value=batch_value,
            image_size=image_size,
            extra_parameters=extra_parameters,
        )
        if derived_from_id:
            self.get(actor, derived_from_id)
        now = _now()
        template = HyperparameterTemplate(
            id=str(uuid4()),
            **fields,
            derived_from_id=derived_from_id,
            created_by_id=actor.id,
            version=1,
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as database:
            try:
                database.add(template)
                database.commit()
            except IntegrityError as exc:
                database.rollback()
                raise TemplateConflict("active template name already exists") from exc
            database.expunge(template)
            return template

    @staticmethod
    def _validated_fields(
        *,
        name: str,
        description: str,
        epochs: int,
        batch_mode: str,
        batch_value: float | None,
        image_size: int,
        extra_parameters: dict[str, object],
    ) -> dict[str, object]:
        if batch_mode == "auto":
            batch: int | float = -1
        elif batch_mode == "fixed" and batch_value is not None:
            batch = int(batch_value)
        elif batch_mode == "fraction" and batch_value is not None:
            batch = float(batch_value)
        else:
            raise InvalidTemplate("invalid batch configuration")
        normalized = validate_values(
            {
                "epochs": epochs,
                "batch": batch,
                "imgsz": image_size,
                **extra_parameters,
            }
        )
        if normalized["batch_mode"] != batch_mode:
            raise InvalidTemplate("invalid batch configuration")
        clean_name = _text(name, 128, "template name", True)
        return {
            "name": clean_name,
            "name_normalized": clean_name.lower(),
            "description": _text(description, 2000, "description"),
            "epochs": normalized["epochs"],
            "batch_mode": normalized["batch_mode"],
            "batch_value": normalized["batch_value"],
            "image_size": normalized["image_size"],
            "extra_parameters": json.dumps(normalized["extra_parameters"], ensure_ascii=False),
            "catalog_version": CATALOG_VERSION,
        }

    def update(
        self,
        actor: User,
        template_id: str,
        *,
        version: int,
        name: str,
        description: str,
        epochs: int,
        batch_mode: str,
        batch_value: float | None,
        image_size: int,
        extra_parameters: dict[str, object],
    ) -> HyperparameterTemplate:
        fields = self._validated_fields(
            name=name,
            description=description,
            epochs=epochs,
            batch_mode=batch_mode,
            batch_value=batch_value,
            image_size=image_size,
            extra_parameters=extra_parameters,
        )
        with self._session_factory() as database:
            template = database.get(HyperparameterTemplate, template_id)
            if template is None or template.deleted_at is not None:
                raise TemplateNotFound("hyperparameter template not found")
            if not self.can_manage(actor, template):
                raise TemplateForbidden("hyperparameter template is read-only")
            if template.version != version:
                raise TemplateConflict("hyperparameter template version changed")
            try:
                result = database.execute(
                    update(HyperparameterTemplate)
                    .where(
                        HyperparameterTemplate.id == template_id,
                        HyperparameterTemplate.version == version,
                        HyperparameterTemplate.deleted_at.is_(None),
                    )
                    .values(**fields, version=version + 1, updated_at=_now())
                )
                if result.rowcount != 1:
                    database.rollback()
                    raise TemplateConflict("hyperparameter template version changed")
                database.commit()
            except IntegrityError as exc:
                database.rollback()
                raise TemplateConflict("active template name already exists") from exc
            updated_template = database.get(HyperparameterTemplate, template_id)
            assert updated_template is not None
            database.expunge(updated_template)
            return updated_template

    def delete(self, actor: User, template_id: str) -> None:
        with self._session_factory() as database:
            template = database.get(HyperparameterTemplate, template_id)
            if template is None or template.deleted_at is not None:
                raise TemplateNotFound("hyperparameter template not found")
            if not self.can_manage(actor, template):
                raise TemplateForbidden("hyperparameter template is read-only")
            template.deleted_at = _now()
            database.commit()

    @staticmethod
    def values(template: HyperparameterTemplate) -> dict[str, object]:
        return effective_parameters(
            template.epochs,
            template.batch_mode,
            template.batch_value,
            template.image_size,
            json.loads(template.extra_parameters),
        )
