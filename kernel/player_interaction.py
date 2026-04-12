"""Helpers for kernel player notifications, task messages, and question flow."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, MutableSequence
from typing import Any

from benchmark import span as bm_span
from logging_system import get_logger
from models import PlayerResponse, Task, TaskMessage, TaskStatus

from .event_delivery import deliver_player_response

slog = get_logger("kernel")

_TERMINAL_TASK_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.ABORTED,
    TaskStatus.PARTIAL,
}


def push_player_notification(
    *,
    notification_type: str,
    content: str,
    data: dict[str, Any] | None,
    timestamp: float | None,
    player_notifications: MutableSequence[dict[str, Any]],
    now: Callable[[], float],
) -> None:
    payload = {
        "type": notification_type,
        "content": content,
        "data": dict(data or {}),
        "timestamp": now() if timestamp is None else timestamp,
    }
    player_notifications.append(payload)
    slog.info(
        "Player notification queued",
        event="player_notification",
        notification_type=notification_type,
        content=content,
        data=data or {},
    )


def register_task_message(
    message: TaskMessage,
    *,
    tasks: Mapping[str, Task],
    task_messages: MutableSequence[TaskMessage],
    question_store: Any,
) -> bool:
    with bm_span("tool_exec", name=f"kernel:register_task_message:{message.type.value}"):
        task = tasks.get(message.task_id)
        if task is None or task.status in _TERMINAL_TASK_STATUSES:
            return False
        task_messages.append(message)
        slog.info(
            "Task message registered",
            event="task_message_registered",
            task_id=message.task_id,
            message_id=message.message_id,
            message_type=message.type.value,
            content=message.content,
            priority=message.priority,
        )
        question_store.register(message)
        return True


def submit_player_response(
    response: PlayerResponse,
    *,
    now: float | None,
    current_time: Callable[[], float],
    question_store: Any,
    delivered_player_responses: MutableMapping[str, list[PlayerResponse]],
    task_runtimes: Mapping[str, Any],
) -> dict[str, Any]:
    with bm_span("tool_exec", name="kernel:submit_player_response"):
        timestamp = current_time() if now is None else now
        result = question_store.submit(response, timestamp)
        if result.delivered_response is not None:
            deliver_player_response(
                delivered_player_responses,
                task_runtimes,
                result.delivered_response,
            )
        return result.to_payload()


def tick_question_timeouts(
    *,
    now: float | None,
    current_time: Callable[[], float],
    question_store: Any,
    delivered_player_responses: MutableMapping[str, list[PlayerResponse]],
    task_runtimes: Mapping[str, Any],
) -> int:
    with bm_span("tool_exec", name="kernel:tick"):
        timestamp = current_time() if now is None else now
        expired_responses = question_store.expire_due(timestamp)
        for response in expired_responses:
            deliver_player_response(
                delivered_player_responses,
                task_runtimes,
                response,
            )
        return len(expired_responses)
