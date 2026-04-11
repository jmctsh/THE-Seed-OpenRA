"""Kernel-side helpers for session/game reset flows."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, MutableSequence, MutableSet
from typing import Any, Protocol

from models import JobStatus


class RuntimeLike(Protocol):
    ...


class JobLike(Protocol):
    status: JobStatus
    resources: list[str]

    def abort(self) -> None:
        ...


def stop_all_task_runtimes(
    task_runtimes: Mapping[str, RuntimeLike],
    *,
    stop_task_runtime_fn: Callable[[Mapping[str, RuntimeLike], str], None],
) -> None:
    for task_id in list(task_runtimes):
        stop_task_runtime_fn(task_runtimes, task_id)


def abort_and_release_all_jobs(
    jobs: Mapping[str, JobLike],
    *,
    is_terminal_status: Callable[[JobStatus], bool],
    release_job_resources_fn: Callable[[JobLike], None],
) -> None:
    for controller in list(jobs.values()):
        if not is_terminal_status(controller.status):
            controller.abort()
        if controller.resources:
            release_job_resources_fn(controller)


def clear_kernel_runtime_collections(
    *,
    tasks: MutableMapping[str, Any],
    task_runtimes: MutableMapping[str, Any],
    jobs: MutableMapping[str, Any],
    constraints: MutableMapping[str, Any],
    resource_needs: MutableMapping[str, Any],
    resource_loss_notified: MutableSet[str],
    player_notifications: MutableSequence[dict[str, Any]],
    task_messages: MutableSequence[Any],
    reset_questions: Callable[[], None],
    delivered_player_responses: MutableMapping[str, Any],
    unit_requests: MutableMapping[str, Any],
    unit_reservations: MutableMapping[str, Any],
    request_reservations: MutableMapping[str, Any],
    task_actor_groups: MutableMapping[str, Any],
    direct_managed_tasks: MutableSet[str],
    capability_recent_inputs: MutableSequence[Any],
    clear_player_notifications: bool,
    clear_task_messages: bool,
) -> None:
    tasks.clear()
    task_runtimes.clear()
    jobs.clear()
    constraints.clear()
    resource_needs.clear()
    resource_loss_notified.clear()
    if clear_player_notifications:
        player_notifications.clear()
    if clear_task_messages:
        task_messages.clear()
    reset_questions()
    delivered_player_responses.clear()
    unit_requests.clear()
    unit_reservations.clear()
    request_reservations.clear()
    task_actor_groups.clear()
    direct_managed_tasks.clear()
    capability_recent_inputs.clear()


def reset_kernel_session(
    *,
    task_runtimes: MutableMapping[str, Any],
    jobs: MutableMapping[str, Any],
    tasks: MutableMapping[str, Any],
    constraints: MutableMapping[str, Any],
    resource_needs: MutableMapping[str, Any],
    resource_loss_notified: MutableSet[str],
    player_notifications: MutableSequence[dict[str, Any]],
    task_messages: MutableSequence[Any],
    reset_questions: Callable[[], None],
    delivered_player_responses: MutableMapping[str, Any],
    unit_requests: MutableMapping[str, Any],
    unit_reservations: MutableMapping[str, Any],
    request_reservations: MutableMapping[str, Any],
    task_actor_groups: MutableMapping[str, Any],
    direct_managed_tasks: MutableSet[str],
    capability_recent_inputs: MutableSequence[Any],
    stop_task_runtime_fn: Callable[[Mapping[str, RuntimeLike], str], None],
    is_terminal_status: Callable[[JobStatus], bool],
    release_job_resources_fn: Callable[[JobLike], None],
    set_capability_task_id: Callable[[Any], None],
    sync_world_runtime: Callable[[], None],
    ensure_capability_task: Callable[[], Any],
) -> None:
    stop_all_task_runtimes(
        task_runtimes,
        stop_task_runtime_fn=stop_task_runtime_fn,
    )
    abort_and_release_all_jobs(
        jobs,
        is_terminal_status=is_terminal_status,
        release_job_resources_fn=release_job_resources_fn,
    )
    clear_kernel_runtime_collections(
        tasks=tasks,
        task_runtimes=task_runtimes,
        jobs=jobs,
        constraints=constraints,
        resource_needs=resource_needs,
        resource_loss_notified=resource_loss_notified,
        player_notifications=player_notifications,
        task_messages=task_messages,
        reset_questions=reset_questions,
        delivered_player_responses=delivered_player_responses,
        unit_requests=unit_requests,
        unit_reservations=unit_reservations,
        request_reservations=request_reservations,
        task_actor_groups=task_actor_groups,
        direct_managed_tasks=direct_managed_tasks,
        capability_recent_inputs=capability_recent_inputs,
        clear_player_notifications=True,
        clear_task_messages=True,
    )
    set_capability_task_id(None)
    sync_world_runtime()
    ensure_capability_task()
