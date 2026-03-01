#!/usr/bin/env python3
"""Read the event timeline from the feed.

Shows recent events so the copilot agent understands what happened
before a command was forwarded to it.

Usage:
    python3 read_timeline.py              # last 20 events
    python3 read_timeline.py --last 5     # last 5 events
    python3 read_timeline.py --tail       # unread events since last --tail
    python3 read_timeline.py --since CID  # events with matching cid
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

FEED_FILE = Path(__file__).resolve().parent.parent / "feed" / "events.jsonl"
CURSOR_FILE = Path(__file__).resolve().parent.parent / "feed" / ".cursor"

_TYPE_LABELS = {
    "player_command": "PLAYER",
    "nlu_route":      "NLU-OK",
    "nlu_miss":       "NLU-MISS",
    "agent_forward":  "→AGENT",
    "agent_reply":    "AGENT→",
}


def _load_events() -> list[dict]:
    if not FEED_FILE.exists():
        return []
    events = []
    with FEED_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _read_cursor() -> int:
    """Return the byte offset stored in the cursor file, or 0."""
    if not CURSOR_FILE.exists():
        return 0
    try:
        return int(CURSOR_FILE.read_text().strip())
    except (ValueError, OSError):
        return 0


def _write_cursor(offset: int) -> None:
    try:
        CURSOR_FILE.write_text(str(offset))
    except OSError:
        pass


def _fmt_ts(ts_ms: int) -> str:
    t = time.localtime(ts_ms / 1000)
    return time.strftime("%H:%M:%S", t)


def _fmt_event(ev: dict) -> str:
    ts = _fmt_ts(ev.get("ts", 0))
    etype = ev.get("type", "?")
    label = _TYPE_LABELS.get(etype, etype.upper())
    cid = ev.get("cid", "")
    cid_str = f" [{cid[:8]}]" if cid else ""

    parts = [f"{ts} {label}{cid_str}"]

    # Show key fields based on event type
    cmd = ev.get("command")
    if cmd:
        parts.append(f'  "{cmd}"')

    msg = ev.get("message")
    if msg:
        parts.append(f"  → {msg}")

    intent = ev.get("intent")
    if intent:
        conf = ev.get("confidence", 0)
        parts.append(f"  intent={intent} conf={conf:.2f}")

    reason = ev.get("reason")
    if reason and not intent:
        parts.append(f"  reason={reason}")

    return "\n".join(parts)


def cmd_last(n: int) -> None:
    events = _load_events()
    for ev in events[-n:]:
        print(_fmt_event(ev))
        print()


def cmd_tail() -> None:
    if not FEED_FILE.exists():
        print("(no events yet)")
        return

    cursor = _read_cursor()
    file_size = FEED_FILE.stat().st_size

    if cursor >= file_size:
        print("(no new events)")
        _write_cursor(file_size)
        return

    events = []
    with FEED_FILE.open("r", encoding="utf-8") as f:
        f.seek(cursor)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    _write_cursor(file_size)

    if not events:
        print("(no new events)")
        return

    for ev in events:
        print(_fmt_event(ev))
        print()

    print(f"--- {len(events)} new event(s) ---")


def cmd_since(cid: str) -> None:
    events = _load_events()
    found = False
    for ev in events:
        if not found:
            if ev.get("cid", "").startswith(cid):
                found = True
            else:
                continue
        print(_fmt_event(ev))
        print()
    if not found:
        print(f"(no events matching cid={cid})")


def main():
    parser = argparse.ArgumentParser(description="Read event timeline")
    parser.add_argument("--last", type=int, default=0, help="Show last N events")
    parser.add_argument("--tail", action="store_true", help="Show unread events since last --tail")
    parser.add_argument("--since", type=str, default="", help="Show events since command ID")
    args = parser.parse_args()

    if args.tail:
        cmd_tail()
    elif args.since:
        cmd_since(args.since)
    else:
        cmd_last(args.last or 20)


if __name__ == "__main__":
    main()
