"""Process-level OpenRA game lifecycle control."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

from openra_api.game_api import GameAPI


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class GameControlConfig:
    openra_dir: Path = Path(__file__).resolve().parent / "OpenCodeAlert"
    host: str = os.environ.get("OPENRA_HOST", "localhost")
    port: int = int(os.environ.get("OPENRA_PORT", "7445"))
    language: str = os.environ.get("OPENRA_LANGUAGE", "zh")
    mod: str = os.environ.get("OPENRA_MOD", "copilot")
    display: str = os.environ.get("DISPLAY", ":99")
    debug: bool = _env_bool("OPENRA_COPILOT_DEBUG", True)
    agent_mode: bool = _env_bool("OPENRA_AGENT_MODE", True)
    log_path: Path = Path(os.environ.get("OPENRA_LOG_PATH", "/tmp/openra.log"))
    process_pattern: str = os.environ.get("OPENRA_PROCESS_PATTERN", "OpenRA.dll")
    startup_poll_interval: float = float(os.environ.get("OPENRA_STARTUP_POLL_INTERVAL", "0.5"))
    stop_timeout: float = float(os.environ.get("OPENRA_STOP_TIMEOUT", "10.0"))

    def launch_args(self, save_path: Optional[str] = None) -> list[str]:
        args = [
            "./start.sh",
            f"Game.Mod={self.mod}",
            f"Game.CopilotPort={self.port}",
            f"Game.CopilotDebug={'True' if self.debug else 'False'}",
            f"Game.IsAgentMode={'True' if self.agent_mode else 'False'}",
        ]
        if save_path:
            args.append(f"Game.LoadSave={save_path}")
        return args

    def launch_env(self) -> dict[str, str]:
        env = os.environ.copy()
        dotnet_root = str(Path.home() / ".dotnet")
        env["DISPLAY"] = self.display
        env["PATH"] = f"{dotnet_root}:{env.get('PATH', '')}"
        env["DOTNET_ROOT"] = dotnet_root
        return env


def is_game_running(config: Optional[GameControlConfig] = None) -> bool:
    cfg = config or GameControlConfig()
    result = subprocess.run(
        ["pgrep", "-f", cfg.process_pattern],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def stop_game(config: Optional[GameControlConfig] = None) -> bool:
    cfg = config or GameControlConfig()
    if not is_game_running(cfg):
        return True
    subprocess.run(
        ["pkill", "-f", cfg.process_pattern],
        capture_output=True,
        text=True,
        check=False,
    )
    deadline = time.time() + max(cfg.stop_timeout, 0.0)
    while time.time() <= deadline:
        if not is_game_running(cfg):
            return True
        time.sleep(cfg.startup_poll_interval)
    return not is_game_running(cfg)


def start_game(save_path: Optional[str] = None, config: Optional[GameControlConfig] = None) -> int:
    cfg = config or GameControlConfig()
    cfg.log_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg.log_path.open("ab") as log_file:
        process = subprocess.Popen(
            cfg.launch_args(save_path),
            cwd=cfg.openra_dir,
            env=cfg.launch_env(),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return int(process.pid)


def restart_game(save_path: Optional[str] = None, config: Optional[GameControlConfig] = None) -> int:
    cfg = config or GameControlConfig()
    if not stop_game(cfg):
        raise RuntimeError("Failed to stop OpenRA process before restart.")
    time.sleep(cfg.startup_poll_interval)
    return start_game(save_path=save_path, config=cfg)


def wait_for_api(
    timeout: float = 30.0,
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
    language: str = "zh",
    poll_interval: float = 0.5,
) -> bool:
    del language
    target_host = host or os.environ.get("OPENRA_HOST", "localhost")
    target_port = int(port or os.environ.get("OPENRA_PORT", "7445"))
    deadline = time.time() + max(timeout, 0.0)
    while time.time() <= deadline:
        if GameAPI.is_server_running(target_host, target_port, timeout=min(poll_interval, 2.0)):
            return True
        time.sleep(poll_interval)
    return GameAPI.is_server_running(target_host, target_port, timeout=min(poll_interval, 2.0))


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenRA game process control")
    parser.add_argument("action", choices=("start", "stop", "restart", "status"))
    parser.add_argument("--save", default=None, help="Optional baseline save to load on start/restart")
    parser.add_argument("--host", default=os.environ.get("OPENRA_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("OPENRA_PORT", "7445")))
    parser.add_argument("--display", default=os.environ.get("DISPLAY", ":99"))
    parser.add_argument("--mod", default=os.environ.get("OPENRA_MOD", "copilot"))
    parser.add_argument("--wait-timeout", type=float, default=30.0)
    parser.add_argument("--log-path", default=os.environ.get("OPENRA_LOG_PATH", "/tmp/openra.log"))
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    config = GameControlConfig(
        host=args.host,
        port=args.port,
        display=args.display,
        mod=args.mod,
        log_path=Path(args.log_path),
    )

    if args.action == "status":
        running = is_game_running(config)
        print("running" if running else "stopped")
        return 0 if running else 1

    if args.action == "stop":
        ok = stop_game(config)
        print("stopped" if ok else "stop_failed")
        return 0 if ok else 1

    if args.action == "start":
        pid = start_game(save_path=args.save, config=config)
        ready = wait_for_api(args.wait_timeout, host=config.host, port=config.port, language=config.language)
        print(f"started pid={pid}")
        return 0 if ready else 1

    pid = restart_game(save_path=args.save, config=config)
    ready = wait_for_api(args.wait_timeout, host=config.host, port=config.port, language=config.language)
    print(f"restarted pid={pid}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
