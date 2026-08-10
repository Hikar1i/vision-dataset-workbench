ACTIVE = {"queued", "running", "canceling"}


def aggregate_progress(models: list[object]) -> float:
    if not models:
        return 0.0
    return round(sum(float(getattr(item, "progress", 0)) for item in models) / len(models), 2)


def aggregate_task_state(models: list[object]) -> str:
    states = [str(getattr(item, "status")) for item in models]
    if any(state == "canceling" for state in states):
        return "canceling"
    if any(state == "running" for state in states):
        return "running"
    if any(state == "queued" for state in states):
        return "queued"
    succeeded = states.count("succeeded")
    if succeeded == len(states) and states:
        return "succeeded"
    if succeeded:
        return "partial"
    if states and all(state == "canceled" for state in states):
        return "canceled"
    if states and all(state == "start_failed" for state in states):
        return "start_failed"
    return "failed"
