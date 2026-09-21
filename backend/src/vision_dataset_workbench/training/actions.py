from dataclasses import dataclass


@dataclass(frozen=True)
class ActionAvailability:
    allowed: bool
    reason_code: str | None = None
    message: str | None = None


def model_actions(
    status: str, *, has_last: bool, has_best: bool, active_dependencies: bool = True
) -> dict[str, ActionAvailability]:
    inactive = status not in {"preparing", "queued", "running", "canceling"}
    deps = inactive and active_dependencies
    active = status in {"queued", "running", "canceling"}
    return {
        "cancel": ActionAvailability(active, None if active else "not_active", None if active else "模型当前未运行"),
        "retry": ActionAvailability(
            deps and status in {"failed", "canceled", "start_failed", "succeeded"},
            None if deps else "inactive_or_dependency",
            None if deps else "模型运行中或依赖资源不可用",
        ),
        "resume": ActionAvailability(
            deps and status in {"failed", "canceled"} and has_last,
            None if has_last else "missing_last",
            None if has_last else "没有可用的 last.pt",
        ),
        "derive": ActionAvailability(deps, None if deps else "inactive_or_dependency", None if deps else "活动模型不能派生"),
        "extend": ActionAvailability(
            deps and status == "succeeded" and (has_best or has_last),
            None if has_best or has_last else "missing_checkpoint",
            None if has_best or has_last else "没有可用的 best.pt 或 last.pt",
        ),
        "delete": ActionAvailability(inactive, None if inactive else "active", None if inactive else "活动模型不能删除"),
    }


def task_actions(status: str, model_statuses: list[str], *, has_resumable: bool) -> dict[str, ActionAvailability]:
    active = status in {"preparing", "queued", "running", "canceling"}
    failed = any(value in {"failed", "canceled", "start_failed"} for value in model_statuses)
    return {
        "start": ActionAvailability(status == "draft", None if status == "draft" else "not_draft", None if status == "draft" else "只有草稿可以启动"),
        "edit": ActionAvailability(status == "draft", None if status == "draft" else "immutable", None if status == "draft" else "已启动任务不可修改"),
        "retry": ActionAvailability(not active and status != "draft" and failed, None if not active and status != "draft" and failed else "no_failed_models", None if not active and status != "draft" and failed else "没有可重试的未成功模型"),
        "retry_preparation": ActionAvailability(
            status == "preparation_failed",
            None if status == "preparation_failed" else "not_preparation_failed",
            None if status == "preparation_failed" else "训练数据准备未失败",
        ),
        "resume": ActionAvailability(not active and has_resumable, None if not active and has_resumable else "missing_last", None if not active and has_resumable else "没有可恢复的 last.pt"),
        "derive": ActionAvailability(not active, None if not active else "active", None if not active else "活动任务不能派生"),
        "cancel": ActionAvailability(active, None if active else "not_active", None if active else "任务当前未运行"),
        "delete": ActionAvailability(not active, None if not active else "active", None if not active else "活动任务不能删除"),
    }
