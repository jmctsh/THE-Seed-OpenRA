"""Unified event feed for the copilot agent.

Appends structured JSONL events to runtime/feed/events.jsonl so the
agent can reconstruct temporal context (what the player said, what NLU
did, what was forwarded, etc.).
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

_FEED_DIR = Path(__file__).resolve().parent / "runtime" / "feed"
_FEED_FILE = _FEED_DIR / "events.jsonl"
_lock = threading.Lock()


def append_event(
    event_type: str,
    payload: dict | None = None,
    *,
    cid: str = "",
) -> None:
    """Append one event to the feed.

    Parameters
    ----------
    event_type : str
        e.g. "player_command", "nlu_route", "nlu_miss", "agent_forward"
    payload : dict, optional
        Arbitrary key-value data merged into the record.
    cid : str, optional
        Command correlation ID — ties related events together.
    """
    record = {
        "ts": int(time.time() * 1000),
        "type": event_type or "unknown",
    }
    if cid:
        record["cid"] = cid
    if payload:
        record.update(payload)

    try:
        with _lock:
            _FEED_DIR.mkdir(parents=True, exist_ok=True)
            with _FEED_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Never block runtime
