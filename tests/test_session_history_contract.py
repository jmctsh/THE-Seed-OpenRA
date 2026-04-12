from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging_system
from session_browser import build_session_history_payload


def setup_function() -> None:
    logging_system.clear()
    logging_system.stop_persistence_session()


def test_session_history_payload_includes_structured_query_response_entries() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = logging_system.start_persistence_session(tmpdir, session_name="query-history")
        logger = logging_system.get_logger("dashboard_publish")
        logger.info(
            "历史副官回复",
            event="adjutant_response_sent",
            content="历史副官回复",
            response_type="command",
            ok=True,
            task_id="t_cap",
            existing_task_id="t_cap",
        )
        logger.info(
            "历史追问回复",
            event="query_response_sent",
            response_text="历史追问回复",
            response_type="reply",
            ok=False,
            task_id="t_task",
            message_id="m_1",
        )
        logging_system.stop_persistence_session()

        payload = build_session_history_payload(tmpdir, session_dir=session_dir)

    query_responses = payload["query_response_entries"]
    assert [item["answer"] for item in query_responses] == ["历史副官回复", "历史追问回复"]
    assert query_responses[0]["response_type"] == "command"
    assert query_responses[0]["ok"] is True
    assert query_responses[0]["task_id"] == "t_cap"
    assert query_responses[0]["existing_task_id"] == "t_cap"
    assert query_responses[1]["response_type"] == "reply"
    assert query_responses[1]["ok"] is False
    assert query_responses[1]["task_id"] == "t_task"
    assert query_responses[1]["message_id"] == "m_1"


def test_session_history_payload_returns_empty_structured_lists_without_session() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        payload = build_session_history_payload(tmpdir, session_dir=None)

    assert payload["log_entries"] == []
    assert payload["benchmark_records"] == []
    assert payload["player_visible_entries"] == []
    assert payload["query_response_entries"] == []
