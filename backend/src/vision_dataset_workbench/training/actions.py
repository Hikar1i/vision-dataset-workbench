from dataclasses import dataclass


@dataclass(frozen=True)
class ActionAvailability:
    allowed: bool
    reason_code: str | None = None
    message: str | None = None


def model_actions(
    status: str, *, has_last: bool, has_best: bool, active_dependencies: bool = True
) -> dict[str, ActionAvailability]:
    inactive = status not in {"queued", "running", "canceling"}
    deps = inactive and active_dependencies
    return {
        "retry": ActionAvailability(
            deps and status in {"failed", "canceled", "start_failed", "succeeded"},
            None if deps else "inactive_or_dependency",
            None,
        ),
        "resume": ActionAvailability(
            deps and status in {"failed", "canceled"} and has_last,
            None if has_last else "missing_last",
            None,
        ),
        "derive": ActionAvailability(deps, None if deps else "inactive_or_dependency", None),
        "extend": ActionAvailability(
            deps and status == "succeeded" and (has_best or has_last),
            None if has_best or has_last else "missing_checkpoint",
            None,
        ),
        "delete": ActionAvailability(inactive, None if inactive else "active", None),
    }
