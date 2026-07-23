from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..config import RuntimeSettings
from ..models import Project, ProjectMembership, User
from .auth import normalize_username

ProjectRole = Literal["owner", "editor", "viewer"]
MemberRole = Literal["editor", "viewer"]


class ProjectNotFound(ValueError):
    pass


class ProjectForbidden(ValueError):
    pass


class ProjectConflict(ValueError):
    pass


class InvalidProjectMember(ValueError):
    pass


@dataclass(frozen=True)
class ProjectView:
    project: Project
    role: ProjectRole
    creator_username: str


@dataclass(frozen=True)
class MemberView:
    user: User
    role: ProjectRole
    created_at: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _project_text(name: str, description: str) -> tuple[str, str]:
    clean_name = name.strip()
    clean_description = description.strip()
    if not 1 <= len(clean_name) <= 128:
        raise ValueError("project name must be 1-128 characters")
    if len(clean_description) > 2000:
        raise ValueError("project description must not exceed 2000 characters")
    return clean_name, clean_description


def _member_role(role: str) -> MemberRole:
    if role not in {"editor", "viewer"}:
        raise InvalidProjectMember("role must be editor or viewer")
    return role


class ProjectService:
    def __init__(
        self,
        engine: Engine,
        settings: RuntimeSettings,
        workspace: Path,
        *,
        now: Callable[[], datetime] = _utc_now,
    ):
        self.settings = settings
        self.workspace = workspace
        self._now = now
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    def create_project(self, actor: User, name: str, description: str) -> ProjectView:
        name, description = _project_text(name, description)
        project_id = str(uuid4())
        directory = self.workspace / "projects" / project_id
        directory.mkdir()
        now = self._now()
        project = Project(
            id=project_id,
            name=name,
            description=description,
            creator_id=actor.id,
            version=1,
            created_at=now,
            updated_at=now,
        )
        try:
            with self._session_factory() as database:
                database.add(project)
                database.commit()
        except Exception:
            directory.rmdir()
            raise
        return ProjectView(project=project, role="owner", creator_username=actor.username)

    def list_projects(
        self, actor: User, *, page: int, page_size: int
    ) -> tuple[list[ProjectView], int]:
        with self._session_factory() as database:
            projects_query = select(Project)
            total_query = select(func.count()).select_from(Project)
            if not (self.settings.app_mode == "single" and actor.is_system_admin):
                membership_ids = select(ProjectMembership.project_id).where(
                    ProjectMembership.user_id == actor.id
                )
                visible = or_(
                    Project.creator_id == actor.id, Project.id.in_(membership_ids)
                )
                projects_query = projects_query.where(visible)
                total_query = total_query.where(visible)
            total = database.scalar(total_query) or 0
            projects = database.scalars(
                projects_query
                .order_by(Project.updated_at.desc(), Project.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return [self._view(database, actor, project) for project in projects], total

    def get_project(self, actor: User, project_id: str) -> ProjectView:
        with self._session_factory() as database:
            return self._authorized_view(database, actor, project_id)

    def update_project(
        self,
        actor: User,
        project_id: str,
        name: str,
        description: str,
        *,
        version: int,
    ) -> ProjectView:
        name, description = _project_text(name, description)
        with self._session_factory() as database:
            current = self._authorized_view(database, actor, project_id)
            if current.role == "viewer":
                raise ProjectForbidden("project edit permission required")
            result = database.execute(
                update(Project)
                .where(Project.id == project_id, Project.version == version)
                .values(
                    name=name,
                    description=description,
                    version=Project.version + 1,
                    updated_at=self._now(),
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                database.rollback()
                raise ProjectConflict("project was modified by another user")
            database.commit()
            database.expire_all()
            project = database.get(Project, project_id)
            assert project is not None
            return self._view(database, actor, project)

    def list_members(self, actor: User, project_id: str) -> list[MemberView]:
        with self._session_factory() as database:
            project_view = self._authorized_view(database, actor, project_id)
            creator = database.get(User, project_view.project.creator_id)
            assert creator is not None
            members = [
                MemberView(
                    user=creator,
                    role="owner",
                    created_at=project_view.project.created_at,
                )
            ]
            rows = database.execute(
                select(ProjectMembership, User)
                .join(User, User.id == ProjectMembership.user_id)
                .where(ProjectMembership.project_id == project_id)
                .order_by(User.username_normalized)
            )
            members.extend(
                MemberView(user=user, role=membership.role, created_at=membership.created_at)
                for membership, user in rows
            )
            return members

    def add_member(
        self,
        actor: User,
        project_id: str,
        username: str,
        role: str,
    ) -> MemberView:
        accepted_role = _member_role(role)
        try:
            normalized = normalize_username(username)
        except ValueError:
            raise InvalidProjectMember("active user not found") from None
        with self._session_factory() as database:
            project = self._require_owner(database, actor, project_id)
            user = database.scalar(
                select(User).where(User.username_normalized == normalized)
            )
            if user is None or user.status != "active":
                raise InvalidProjectMember("active user not found")
            if user.id == project.creator_id:
                raise InvalidProjectMember("project creator is already the owner")
            membership = ProjectMembership(
                project_id=project_id,
                user_id=user.id,
                role=accepted_role,
                created_at=self._now(),
            )
            try:
                database.add(membership)
                database.commit()
            except IntegrityError as exc:
                database.rollback()
                raise ProjectConflict("user is already a project member") from exc
            return MemberView(user=user, role=accepted_role, created_at=membership.created_at)

    def change_member_role(
        self,
        actor: User,
        project_id: str,
        user_id: str,
        role: str,
    ) -> MemberView:
        accepted_role = _member_role(role)
        with self._session_factory() as database:
            project = self._require_owner(database, actor, project_id)
            if user_id == project.creator_id:
                raise InvalidProjectMember("project owner cannot be changed")
            membership = database.get(ProjectMembership, (project_id, user_id))
            user = database.get(User, user_id)
            if membership is None or user is None:
                raise InvalidProjectMember("project member not found")
            membership.role = accepted_role
            database.commit()
            return MemberView(
                user=user, role=accepted_role, created_at=membership.created_at
            )

    def remove_member(self, actor: User, project_id: str, user_id: str) -> None:
        with self._session_factory() as database:
            project = self._require_owner(database, actor, project_id)
            if user_id == project.creator_id:
                raise InvalidProjectMember("project owner cannot be removed")
            membership = database.get(ProjectMembership, (project_id, user_id))
            if membership is None:
                raise InvalidProjectMember("project member not found")
            database.delete(membership)
            database.commit()

    def _require_owner(self, database: Session, actor: User, project_id: str) -> Project:
        view = self._authorized_view(database, actor, project_id)
        if view.role != "owner":
            raise ProjectForbidden("project owner permission required")
        return view.project

    def _authorized_view(
        self, database: Session, actor: User, project_id: str
    ) -> ProjectView:
        project = database.get(Project, project_id)
        if project is None:
            raise ProjectNotFound("project not found")
        role = self._role(database, actor, project)
        if role is None:
            raise ProjectNotFound("project not found")
        creator_username = database.scalar(
            select(User.username).where(User.id == project.creator_id)
        )
        assert creator_username is not None
        return ProjectView(
            project=project, role=role, creator_username=creator_username
        )

    def _view(self, database: Session, actor: User, project: Project) -> ProjectView:
        role = self._role(database, actor, project)
        assert role is not None
        creator_username = database.scalar(
            select(User.username).where(User.id == project.creator_id)
        )
        assert creator_username is not None
        return ProjectView(
            project=project, role=role, creator_username=creator_username
        )

    def _role(
        self, database: Session, actor: User, project: Project
    ) -> ProjectRole | None:
        if self.settings.app_mode == "single" and actor.is_system_admin:
            return "owner"
        if project.creator_id == actor.id:
            return "owner"
        membership = database.get(ProjectMembership, (project.id, actor.id))
        if membership is None:
            return None
        return membership.role
