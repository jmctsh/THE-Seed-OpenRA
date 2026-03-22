"""Regression tests for persistent GameAPI socket reuse."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openra_api.game_api import GameAPI


class _PersistentJsonServer:
    def __init__(self, *, close_after_requests: Optional[int] = None) -> None:
        self.close_after_requests = close_after_requests
        self.accept_count = 0
        self.commands: list[str] = []
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen()
        self._server.settimeout(0.1)
        self.port = self._server.getsockname()[1]
        self._accept_thread = threading.Thread(target=self._serve, daemon=True)
        self._accept_thread.start()

    def close(self) -> None:
        self._stop.set()
        try:
            self._server.close()
        except OSError:
            pass
        self._accept_thread.join(timeout=1.0)
        for thread in self._threads:
            thread.join(timeout=1.0)

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                client, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return

            self.accept_count += 1
            thread = threading.Thread(target=self._handle_client, args=(client,), daemon=True)
            self._threads.append(thread)
            thread.start()

    def _handle_client(self, client: socket.socket) -> None:
        handled = 0
        with client:
            client.settimeout(0.2)
            while not self._stop.is_set():
                message = self._read_message(client)
                if message is None:
                    return

                request = json.loads(message)
                self.commands.append(request["command"])
                response = {
                    "status": 1,
                    "requestId": request["requestId"],
                    "data": {"echo": request["command"], "handled": handled},
                }
                client.sendall((json.dumps(response) + "\n").encode("utf-8"))
                handled += 1
                if self.close_after_requests is not None and handled >= self.close_after_requests:
                    return

    def _read_message(self, client: socket.socket) -> Optional[str]:
        chunks: list[str] = []
        while not self._stop.is_set():
            try:
                chunk = client.recv(4096)
            except socket.timeout:
                candidate = self._try_parse("".join(chunks))
                if candidate is not None:
                    return candidate
                continue

            if not chunk:
                candidate = self._try_parse("".join(chunks))
                return candidate

            chunks.append(chunk.decode("utf-8"))
            payload = "".join(chunks)
            newline_index = payload.find("\n")
            if newline_index >= 0:
                return payload[:newline_index].rstrip("\r")

            candidate = self._try_parse(payload)
            if candidate is not None:
                return candidate

        return None

    @staticmethod
    def _try_parse(payload: str) -> Optional[str]:
        candidate = payload.strip()
        if not candidate:
            return None
        try:
            json.loads(candidate)
        except json.JSONDecodeError:
            return None
        return candidate


def test_game_api_reuses_single_connection() -> None:
    server = _PersistentJsonServer()
    api = GameAPI("127.0.0.1", port=server.port)
    try:
        first = api._send_request("ping", {})
        second = api._send_request("query_actor", {})
        assert first["data"]["echo"] == "ping"
        assert second["data"]["echo"] == "query_actor"
        assert server.accept_count == 1
        assert server.commands == ["ping", "query_actor"]
        print("  PASS: game_api_reuses_single_connection")
    finally:
        api.close()
        server.close()


def test_game_api_reconnects_after_server_side_close() -> None:
    server = _PersistentJsonServer(close_after_requests=1)
    api = GameAPI("127.0.0.1", port=server.port)
    try:
        first = api._send_request("ping", {})
        second = api._send_request("query_actor", {})
        assert first["data"]["echo"] == "ping"
        assert second["data"]["echo"] == "query_actor"
        assert server.accept_count == 2
        print("  PASS: game_api_reconnects_after_server_side_close")
    finally:
        api.close()
        server.close()


def test_game_api_serializes_concurrent_requests() -> None:
    server = _PersistentJsonServer()
    api = GameAPI("127.0.0.1", port=server.port)
    try:
        def call(index: int) -> str:
            response = api._send_request(f"cmd_{index}", {"index": index})
            return response["data"]["echo"]

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(call, range(5)))

        deadline = time.time() + 1.0
        while len(server.commands) < 5 and time.time() < deadline:
            time.sleep(0.01)

        assert results == [f"cmd_{index}" for index in range(5)]
        assert server.accept_count == 1
        assert len(server.commands) == 5
        print("  PASS: game_api_serializes_concurrent_requests")
    finally:
        api.close()
        server.close()


if __name__ == "__main__":
    print("Running GameAPI tests...\n")
    test_game_api_reuses_single_connection()
    test_game_api_reconnects_after_server_side_close()
    test_game_api_serializes_concurrent_requests()
    print("\nAll 3 tests passed!")
