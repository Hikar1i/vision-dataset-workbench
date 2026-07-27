from vision_dataset_workbench.inference import Detection, non_maximum_suppression


def test_non_maximum_suppression_keeps_classes_independent():
    detections = [
        Detection("helmet", 0, 0, 100, 100, 0.9),
        Detection("helmet", 5, 5, 95, 95, 0.8),
        Detection("person", 5, 5, 95, 95, 0.7),
    ]

    kept = non_maximum_suppression(detections, 0.5)

    assert [(item.label, item.confidence) for item in kept] == [
        ("helmet", 0.9),
        ("person", 0.7),
    ]
