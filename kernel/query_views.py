"""Read-only query helpers for Kernel public view methods."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Optional, Protocol

from models import Task, TaskMessage


class WorldModelLike(Protocol):
    def runtime_state(self) -> dict[str, Any] | None:
        ...


def get_task_agent(task_id: str, *, task_runtimes: Mapping[str, Any]) -> Any | None:
    runtime = task_runtimes.get(task_id)
    return runtime.agent if runtime else None


def jobs_for_task(task_id: str, *, jobs: Iterable[Any]) -> list[Any]:
    models = [controller.to_model() for controller in jobs if controller.task_id == task_id]
    models.sort(key=lambda item: item.job_id)
    return models


def active_jobs(*, jobs: Iterable[Any], is_terminal_status: Any) -> tuple[Any, ...]:
    controllers = [controller for controller in jobs if not is_terminal_status(controller.status)]
    controllers.sort(key=lambda item: item.job_id)
    return tuple(controllers)


def list_tasks(*, tasks: Iterable[Task]) -> list[Task]:
    return sorted(tasks, key=lambda item: item.created_at)


def list_jobs(*, jobs: Iterable[Any]) -> list[Any]:
    models = [controller.to_model() for controller in jobs]
    models.sort(key=lambda item: item.job_id)
    return models


def list_player_notifications(*, player_notifications: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(player_notifications)


def runtime_state(*, world_model: WorldModelLike) -> dict[str, Any]:
    state = world_model.runtime_state()
    return dict(state or {})


def list_task_messages(
    task_id: Optional[str],
    *,
    task_messages: Sequence[TaskMessage],
) -> list[TaskMessage]:
    if task_id is None:
        return list(task_messages)
    return [message for message in task_messages if message.task_id == task_id]
