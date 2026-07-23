from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.models import Project, ProjectMembership, User
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.services.projects import (
    InvalidProjectMember,
    ProjectConflict,
    ProjectForbidden,
    ProjectNotFound,
    ProjectService,
)


@pytest.fixture
def project_runtime(tmp_path):
    workspace = tmp_path / ".vision-dataset-workbench"
    (workspace / "projects").mkdir(parents=True)
    database_path = workspace / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    password_hash = hash_password("correct horse battery staple")
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    id="admin-id",
                    username="admin",
                    username_normalized="admin",
                    password_hash=password_hash,
                    status="active",
                    is_system_admin=True,
                ),
                User(
                    id="creator-id",
                    username="creator",
                    username_normalized="creator",
                    password_hash=password_hash,
                    status="active",
                    is_system_admin=False,
                ),
                User(
                    id="editor-id",
                    username="editor",
                    username_normalized="editor",
                    password_hash=password_hash,
                    status="active",
                    is_system_admin=False,
                ),
                User(
                    id="viewer-id",
                    username="viewer",
                    username_normalized="viewer",
                    password_hash=password_hash,
                    status="active",
                    is_system_admin=False,
                ),
                User(
                    id="outsider-id",
                    username="outsider",
                    username_normalized="outsider",
                    password_hash=password_hash,
                    status="active",
                    is_system_admin=False,
                ),
                User(
                    id="disabled-id",
                    username="disabled",
                    username_normalized="disabled",
                    password_hash=password_hash,
                    status="disabled",
                    is_system_admin=False,
                ),
            ]
        )
        session.commit()
    users = {}
    with Session(engine) as session:
        for user in session.scalars(select(User)):
            session.expunge(user)
            users[user.id] = user
    yield engine, workspace, users
    engine.dispose()


def make_service(project_runtime, mode="multi"):
    engine, workspace, _ = project_runtime
    settings = RuntimeSettings(
        home=workspace.parent, workspace=workspace, app_mode=mode
    )
    return ProjectService(
        engine,
        settings,
        workspace,
        now=lambda: datetime(2026, 7, 23, 0, 0, 0),
    )


def test_create_projects_allows_duplicate_names_and_lists_visible_projects(
    project_runtime,
):
    service = make_service(project_runtime)
    _, workspace, users = project_runtime

    first = service.create_project(users["creator-id"], " Shared name ", " first ")
    second = service.create_project(users["creator-id"], "Shared name", "second")

    assert first.project.name == second.project.name == "Shared name"
    assert first.project.description == "first"
    assert first.role == "owner"
    assert (workspace / "projects" / first.project.id).is_dir()
    items, total = service.list_projects(users["creator-id"], page=1, page_size=1)
    assert total == 2
    assert len(items) == 1
    assert service.list_projects(users["outsider-id"], page=1, page_size=50)[1] == 0


def test_roles_control_read_update_and_version_conflicts(project_runtime):
    service = make_service(project_runtime)
    users = project_runtime[2]
    project = service.create_project(users["creator-id"], "Project", "").project
    service.add_member(users["creator-id"], project.id, "editor", "editor")
    service.add_member(users["creator-id"], project.id, "viewer", "viewer")

    assert service.get_project(users["editor-id"], project.id).role == "editor"
    assert service.get_project(users["viewer-id"], project.id).role == "viewer"
    with pytest.raises(ProjectNotFound):
        service.get_project(users["outsider-id"], project.id)
    with pytest.raises(ProjectNotFound):
        service.get_project(users["admin-id"], project.id)

    updated = service.update_project(
        users["editor-id"], project.id, "Changed", "description", version=1
    )
    assert updated.project.version == 2
    with pytest.raises(ProjectForbidden):
        service.update_project(
            users["viewer-id"], project.id, "Viewer edit", "", version=2
        )
    with pytest.raises(ProjectConflict):
        service.update_project(
            users["creator-id"], project.id, "Stale", "", version=1
        )


def test_owner_manages_members_but_creator_is_immutable(project_runtime):
    service = make_service(project_runtime)
    users = project_runtime[2]
    project = service.create_project(users["creator-id"], "Project", "").project

    added = service.add_member(users["creator-id"], project.id, "editor", "editor")
    assert added.role == "editor"
    members = service.list_members(users["editor-id"], project.id)
    assert [(item.user.username, item.role) for item in members] == [
        ("creator", "owner"),
        ("editor", "editor"),
    ]
    changed = service.change_member_role(
        users["creator-id"], project.id, "editor-id", "viewer"
    )
    assert changed.role == "viewer"

    with pytest.raises(ProjectConflict):
        service.add_member(users["creator-id"], project.id, "editor", "editor")
    with pytest.raises(InvalidProjectMember):
        service.add_member(users["creator-id"], project.id, "creator", "viewer")
    with pytest.raises(InvalidProjectMember):
        service.add_member(users["creator-id"], project.id, "disabled", "viewer")
    with pytest.raises(ProjectForbidden):
        service.add_member(users["editor-id"], project.id, "viewer", "viewer")

    service.remove_member(users["creator-id"], project.id, "editor-id")
    with pytest.raises(ProjectNotFound):
        service.get_project(users["editor-id"], project.id)
    with pytest.raises(InvalidProjectMember):
        service.remove_member(users["creator-id"], project.id, "creator-id")


def test_single_mode_admin_has_owner_access_without_membership(project_runtime):
    multi = make_service(project_runtime)
    users = project_runtime[2]
    project = multi.create_project(users["creator-id"], "Project", "").project
    single = make_service(project_runtime, mode="single")

    assert single.get_project(users["admin-id"], project.id).role == "owner"
    single.add_member(users["admin-id"], project.id, "viewer", "viewer")
    with Session(project_runtime[0]) as session:
        assert session.scalar(
            select(func.count())
            .select_from(ProjectMembership)
            .where(ProjectMembership.user_id == "admin-id")
        ) == 0


def test_directory_failure_does_not_create_project(project_runtime):
    service = make_service(project_runtime)
    engine, workspace, users = project_runtime
    (workspace / "projects").rmdir()
    (workspace / "projects").write_text("not a directory", encoding="utf-8")

    with pytest.raises(OSError):
        service.create_project(users["creator-id"], "Project", "")

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 0
