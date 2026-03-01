#!/usr/bin/env python3
"""Send a message to the player's web console via WebSocket.

No external dependencies — uses raw TCP WebSocket handshake.
"""
import base64
import json
import os
import socket
import struct
import sys
import time

WS_HOST = "127.0.0.1"
WS_PORT = 8092


def _ws_connect(host: str, port: int, timeout: float = 5.0) -> socket.socket:
    """Open a raw WebSocket connection and complete the handshake."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect((host, port))

    key = base64.b64encode(os.urandom(16)).decode()
    handshake = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    sock.sendall(handshake.encode())

    # Read response headers
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("Server closed during handshake")
        resp += chunk

    if b"101" not in resp:
        raise ConnectionError(f"Handshake failed: {resp.decode(errors='replace')}")

    # Drain server init frame(s)
    _ws_recv(sock)

    return sock


def _ws_send(sock: socket.socket, text: str) -> None:
    """Send a masked WebSocket text frame."""
    payload = text.encode()
    frame = bytearray([0x81])  # FIN + text opcode
    mask = os.urandom(4)
    plen = len(payload)
    if plen < 126:
        frame.append(0x80 | plen)
    elif plen < 65536:
        frame.append(0x80 | 126)
        frame.extend(struct.pack(">H", plen))
    else:
        frame.append(0x80 | 127)
        frame.extend(struct.pack(">Q", plen))
    frame.extend(mask)
    frame.extend(bytearray(b ^ mask[i % 4] for i, b in enumerate(payload)))
    sock.sendall(frame)


def _ws_recv(sock: socket.socket) -> str:
    """Read one WebSocket text frame."""
    header = sock.recv(2)
    if len(header) < 2:
        return ""
    length = header[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", sock.recv(8))[0]
    data = b""
    while len(data) < length:
        data += sock.recv(length - len(data))
    return data.decode(errors="replace")


def send(message: str, sender: str = "copilot") -> bool:
    """Send a chat message to the web console. Returns True on success."""
    try:
        sock = _ws_connect(WS_HOST, WS_PORT)
        _ws_send(sock, json.dumps({
            "type": "agent_message",
            "payload": {"message": message, "sender": sender},
        }))
        time.sleep(0.15)
        sock.close()
        return True
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: send_message.py <message> [sender]")
        print('  e.g.: send_message.py "Hello player!" copilot')
        sys.exit(1)

    message = sys.argv[1]
    sender = sys.argv[2] if len(sys.argv) > 2 else "copilot"
    ok = send(message, sender)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
