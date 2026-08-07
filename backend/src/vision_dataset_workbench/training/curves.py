import math
from collections.abc import Iterable


def _finite(values: Iterable[object]) -> list[float]:
    result: list[float] = []
    for value in values:
        number = float(value)
        if math.isfinite(number):
            result.append(number)
    return result


def precision_recall_payload(
    validator: object, *, maximum_points: int = 500
) -> dict[str, object] | None:
    metrics = getattr(validator, "metrics", validator)
    names = list(getattr(metrics, "curves", []) or [])
    results = list(getattr(metrics, "curves_results", []) or [])
    for name, result in zip(names, results, strict=False):
        if "precision-recall" not in str(name).lower() and "pr" not in str(name).lower():
            continue
        if not isinstance(result, (list, tuple)) or len(result) < 2:
            continue
        recall = _finite(result[0])
        raw_precision = result[1]
        rows = list(raw_precision) if isinstance(raw_precision, Iterable) else []
        if rows and not isinstance(rows[0], Iterable):
            rows = [rows]
        series: list[dict[str, object]] = []
        step = max(1, len(recall) // maximum_points)
        class_names = getattr(validator, "names", {}) or getattr(metrics, "names", {}) or {}
        class_indexes = list(getattr(metrics, "ap_class_index", []) or [])
        for index, row in enumerate(rows):
            precision = _finite(row)
            count = min(len(recall), len(precision))
            points = [[recall[i], precision[i]] for i in range(0, count, step)]
            if points:
                class_index = class_indexes[index] if index < len(class_indexes) else index
                label = (
                    class_names.get(class_index, str(class_index))
                    if isinstance(class_names, dict)
                    else str(class_index)
                )
                series.append({"name": str(label), "points": points[:maximum_points]})
        if series:
            return {"version": 1, "kind": "interactive", "series": series}
    return None
