from dataclasses import dataclass
from typing import Literal

Permission = Literal[
    "project.read",
    "project.update",
    "project.members.manage",
    "project.delete",
    "artifact.read",
    "artifact.download",
    "artifact.consume",
    "task.read",
    "task.execute",
]
ProjectRole = Literal["owner", "editor", "viewer"]
AccessSource = Literal["system_admin", "owner", "membership", "system_resource"]

ALL_PROJECT_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        "project.read",
        "project.update",
        "project.members.manage",
        "project.delete",
        "artifact.read",
        "artifact.download",
        "artifact.consume",
        "task.read",
        "task.execute",
    }
)
EDITOR_PERMISSIONS = ALL_PROJECT_PERMISSIONS - {
    "project.members.manage",
    "project.delete",
}
VIEWER_PERMISSIONS: frozenset[Permission] = frozenset(
    {"project.read", "artifact.read", "artifact.download", "task.read"}
)


@dataclass(frozen=True)
class AccessContext:
    role: ProjectRole | None
    source: AccessSource
    permissions: frozenset[Permission]

    def allows(self, permission: Permission) -> bool:
        return permission in self.permissions


def access_for_role(role: ProjectRole) -> AccessContext:
    if role == "owner":
        return AccessContext(role, "owner", ALL_PROJECT_PERMISSIONS)
    if role == "editor":
        return AccessContext(role, "membership", EDITOR_PERMISSIONS)
    return AccessContext(role, "membership", VIEWER_PERMISSIONS)


def administrator_access() -> AccessContext:
    return AccessContext(None, "system_admin", ALL_PROJECT_PERMISSIONS)


def system_resource_access() -> AccessContext:
    return AccessContext("viewer", "system_resource", VIEWER_PERMISSIONS)


def require_permission(
    access: AccessContext, permission: Permission, error: Exception
) -> None:
    if not access.allows(permission):
        raise error
