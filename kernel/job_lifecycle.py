"""Helpers for kernel job lifecycle mutations."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, MutableSet
from typing import Any, Protocol

from benchmark import span as bm_span
from logging_system import get_logger
from models import ExpertConfig, Job, JobStatus, Task, TaskStatus, validate_job_config

from .resource_need_inference import build_resource_needs

slog = get_logger("kernel")


class ControllerLike(Protocol):
    job_id: str
    task_id: str
    expert_type: str
    status: JobStatus
    resources: list[str]

    def to_model(self) -> Job:
        ...

    def abort(self) -> None:
        ...

    def patch(self, params: dict[str, Any]) -> None:
        ...

    def pause(self) -> None:
        ...

    def resume(self) -> None:
        ...


def require_job(
    job_id: str,
    *,
    jobs: Mapping[str, ControllerLike],
) -> ControllerLike:
    controller = jobs.get(job_id)
    if controller is None:
        raise KeyError(f"Unknown job_id: {job_id}")
    return controller


def start_job(
    *,
    task_id: str,
    expert_type: str,
    config: ExpertConfig,
    tasks: Mapping[str, Task],
    jobs: MutableMapping[str, ControllerLike],
    resource_needs: MutableMapping[str, Any],
    make_job_controller: Callable[[str, str, ExpertConfig], ControllerLike],
    now: Callable[[], float],
    rebalance_resources: Callable[[], None],
    sync_world_runtime: Callable[[], None],
) -> Job:
    with bm_span("tool_exec", name="kernel:start_job", metadata={"expert_type": expert_type}):
        task = tasks.get(task_id)
        if task is None:
            raise KeyError(f"Unknown task_id: {task_id}")
        validate_job_config(expert_type, config)
        controller = make_job_controller(task_id, expert_type, config)
        jobs[controller.job_id] = controller
        resource_needs[controller.job_id] = build_resource_needs(controller, config)
        task.status = TaskStatus.RUNNING
        task.timestamp = now()
        slog.info(
            "Job started",
            event="job_started",
            task_id=task_id,
            job_id=controller.job_id,
            expert_type=expert_type,
            config=config,
        )
        rebalance_resources()
        sync_world_runtime()
        return controller.to_model()


def abort_job(
    *,
    job_id: str,
    jobs: Mapping[str, ControllerLike],
    resource_loss_notified: MutableSet[str],
    release_job_resources: Callable[[ControllerLike], None],
    rebalance_resources: Callable[[], None],
    sync_world_runtime: Callable[[], None],
) -> bool:
    with bm_span("tool_exec", name="kernel:abort_job"):
        controller = jobs.get(job_id)
        if controller is None:
            return False
        controller.abort()
        release_job_resources(controller)
        resource_loss_notified.discard(job_id)
        rebalance_resources()
        sync_world_runtime()
        slog.warn(
            "Job aborted by Kernel",
            event="job_aborted",
            job_id=job_id,
            task_id=controller.task_id,
        )
        return True


def patch_job(
    *,
    job_id: str,
    params: dict[str, Any],
    jobs: Mapping[str, ControllerLike],
    resource_needs: MutableMapping[str, Any],
    rebalance_resources: Callable[[], None],
    sync_world_runtime: Callable[[], None],
) -> bool:
    with bm_span("tool_exec", name="kernel:patch_job"):
        controller = require_job(job_id, jobs=jobs)
        controller.patch(params)
        config = getattr(controller, "config", None)
        if config is not None:
            resource_needs[job_id] = build_resource_needs(controller, config)
        rebalance_resources()
        sync_world_runtime()
        return True


def pause_job(
    *,
    job_id: str,
    jobs: Mapping[str, ControllerLike],
    is_terminal_status: Callable[[JobStatus], bool],
    sync_world_runtime: Callable[[], None],
) -> bool:
    with bm_span("tool_exec", name="kernel:pause_job"):
        controller = require_job(job_id, jobs=jobs)
        if is_terminal_status(controller.status):
            return False
        controller.pause()
        sync_world_runtime()
        return True


def resume_job(
    *,
    job_id: str,
    jobs: Mapping[str, ControllerLike],
    is_terminal_status: Callable[[JobStatus], bool],
    rebalance_resources: Callable[[], None],
    sync_world_runtime: Callable[[], None],
) -> bool:
    with bm_span("tool_exec", name="kernel:resume_job"):
        controller = require_job(job_id, jobs=jobs)
        if is_terminal_status(controller.status):
            return False
        controller.resume()
        rebalance_resources()
        sync_world_runtime()
        slog.info(
            "Job resumed by Kernel",
            event="job_resumed",
            job_id=job_id,
            task_id=controller.task_id,
        )
        return True
