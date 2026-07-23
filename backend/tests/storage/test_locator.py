from vision_dataset_workbench.storage.locator import WorkspaceLocator


def test_locator_round_trip(tmp_path):
    locator = WorkspaceLocator(tmp_path / "config" / "instance.json")
    workspace = tmp_path / "data" / ".vision-dataset-workbench"

    locator.write(workspace)

    assert locator.read() == workspace.resolve()
