from vision_dataset_workbench.services.authorization import (
    ALL_PROJECT_PERMISSIONS,
    VIEWER_PERMISSIONS,
    access_for_role,
    administrator_access,
)


def test_fixed_project_role_permissions():
    assert access_for_role("owner").permissions == ALL_PROJECT_PERMISSIONS
    assert access_for_role("editor").allows("task.execute")
    assert not access_for_role("editor").allows("project.members.manage")
    assert access_for_role("viewer").permissions == VIEWER_PERMISSIONS
    assert administrator_access().role is None
