"""
THE-Seed OpenRA - 简化版主入口

单一流程：玩家输入 → 观测 → 代码生成 → 执行
"""
from __future__ import annotations

import signal
import subprocess
import sys
import threading
import time
import os
from pathlib import Path

import yaml

from agents.enemy_agent import EnemyAgent
from agents.nlu_gateway import Phase2NLUGateway
from nlu_pipeline.interaction_logger import append_interaction_event
from adapter.openra_env import OpenRAEnv
from openra_api.game_api import GameAPI
from openra_api.jobs import JobManager, ExploreJob, AttackJob
from openra_api.models import (
    Location,
    TargetsQueryParam,
    Actor,
    MapQueryResult,
    FrozenActor,
    ControlPoint,
    ControlPointQueryResult,
    MatchInfoQueryResult,
    PlayerBaseInfo,
    ScreenInfoResult,
)
from openra_api.rts_middle_layer import RTSMiddleLayer

from the_seed.core import CodeGenNode, SimpleExecutor, ExecutorContext, ExecutionResult
from the_seed.model import ModelFactory
from the_seed.config import load_config
from the_seed.utils import LogManager, build_def_style_prompt, DashboardBridge

from event_feed import append_event

logger = LogManager.get_logger()

# Console Bridge 端口 (与 nginx 反代配置一致)
DASHBOARD_PORT = 8092

# 玩家标识
HUMAN_PLAYER_ID = "Multi0"
ENEMY_PLAYER_ID = "Multi1"

# 敌方 AI 配置
ENEMY_TICK_INTERVAL = 45.0  # 敌方决策间隔（秒）


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


def resolve_model_config():
    cfg = load_config()
    template_name = getattr(cfg.node_models, "action", "default")
    model_cfg = cfg.model_templates.get(template_name) or cfg.model_templates.get("default")
    if model_cfg is None:
        raise RuntimeError("model_templates is empty in the-seed config")
    return model_cfg


def _sync_default_runtime() -> None:
    """Copy files from default_runtime/ to runtime/ if they don't exist."""
    src = Path(__file__).resolve().parent / "default_runtime"
    dst = Path(__file__).resolve().parent / "runtime"
    if not src.exists():
        return
    for root, _dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        target_dir = dst / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for fname in files:
            if fname == ".gitkeep":
                continue
            target_file = target_dir / fname
            if not target_file.exists():
                import shutil
                shutil.copy2(Path(root) / fname, target_file)
                logger.info("Synced default_runtime/%s → runtime/%s", rel / fname, rel / fname)


def setup_jobs(api: GameAPI, mid: RTSMiddleLayer) -> JobManager:
    """为 MacroActions 设置 JobManager"""
    mgr = JobManager(api=api, intel=mid.intel_service)
    mgr.add_job(ExploreJob(job_id="explore", base_radius=28))
    mgr.add_job(AttackJob(job_id="attack", step=8))
    mid.skills.jobs = mgr
    return mgr


def create_executor(api: GameAPI, mid: RTSMiddleLayer) -> SimpleExecutor:
    """创建执行器"""
    model_cfg = resolve_model_config()
    model = ModelFactory.build("codegen", model_cfg)
    logger.info("使用模型: %s @ %s", model_cfg.model, model_cfg.base_url)
    
    codegen = CodeGenNode(model)
    
    # 创建环境
    env = OpenRAEnv(api)
    
    # 构建 API 文档
    api_rules = build_def_style_prompt(
        mid.skills,
        [
            "produce_wait",
            "ensure_can_produce_unit",
            "deploy_mcv_and_wait",
            "harvester_mine",
            "dispatch_explore",
            "dispatch_attack",
            "form_group",
            "select_units",
            "query_actor",
            "query_combat_units",
            "query_actor_with_frozen",
            "unit_attribute_query",
            "query_production_queue",
            "place_building",
            "manage_production",
            "move_units",
            "attack_move",
            "attack_target",
            "stop_units",
            "repair",
            "set_rally_point",
            "player_base_info",
        ],
        title="Available functions on OpenRA midlayer API (MacroActions):",
        include_doc_first_line=True,
        include_doc_block=False,
    )
    
    # 运行时全局变量
    runtime_globals = {
        "api": mid.skills,
        "gameapi": mid.skills,
        "raw_api": api,
        "Location": Location,
        "TargetsQueryParam": TargetsQueryParam,
        "Actor": Actor,
        "MapQueryResult": MapQueryResult,
        "FrozenActor": FrozenActor,
        "ControlPoint": ControlPoint,
        "ControlPointQueryResult": ControlPointQueryResult,
        "MatchInfoQueryResult": MatchInfoQueryResult,
        "PlayerBaseInfo": PlayerBaseInfo,
        "ScreenInfoResult": ScreenInfoResult,
    }
    
    ctx = ExecutorContext(
        api=mid.skills,
        raw_api=api,
        api_rules=api_rules,
        runtime_globals=runtime_globals,
        observe_fn=env.observe,
    )
    
    return SimpleExecutor(codegen, ctx)


def handle_command(
    executor: SimpleExecutor,
    command: str,
    nlu_gateway: Phase2NLUGateway | None = None,
    *,
    actor: str = "human",
) -> dict:
    """处理单条命令"""
    logger.info(f"[{actor}] Processing command: {command}")

    nlu_meta = None
    if nlu_gateway is not None:
        result, nlu_meta = nlu_gateway.run(executor, command, rollout_key=actor)
    else:
        result = executor.run(command)

    logger.info(
        "[%s] Command result: success=%s, message=%s%s",
        actor,
        result.success,
        result.message,
        f", source={nlu_meta.get('source')}, reason={nlu_meta.get('reason')}" if nlu_meta else "",
    )

    payload = result.to_dict()
    if nlu_meta:
        payload["nlu"] = nlu_meta
    return payload


def main() -> None:
    """主函数"""
    _sync_default_runtime()

    # ========== 人类玩家 (Multi0) ==========
    api = GameAPI(host="localhost", port=7445, language="zh", player_id=HUMAN_PLAYER_ID)
    mid = RTSMiddleLayer(api)
    human_jobs = setup_jobs(api, mid)
    executor = create_executor(api, mid)

    # Disable DeepSeek LLM for human side — NLU misses get forwarded to copilot agent
    def _human_run_stub(command: str, **kw) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            message="NLU未匹配，已转发给copilot agent",
            error="nlu_miss_forwarded",
        )
    executor.run = _human_run_stub

    human_nlu_gateway = Phase2NLUGateway(name="human")
    logger.info("Human NLU status: %s", human_nlu_gateway.status())
    logger.info(f"Human player initialized: {HUMAN_PLAYER_ID}")
    human_status_callback_lock = threading.Lock()
    human_status_callback_by_thread: dict[int, callable] = {}

    def human_status_dispatch(stage: str, detail: str) -> None:
        callback = None
        thread_id = threading.get_ident()
        with human_status_callback_lock:
            callback = human_status_callback_by_thread.get(thread_id)
        if callback is None:
            return
        try:
            callback(stage, detail)
        except Exception:
            pass

    executor.ctx.status_callback = human_status_dispatch

    # ========== 敌方 AI (Multi1) ==========
    enemy_api = GameAPI(host="localhost", port=7445, language="zh", player_id=ENEMY_PLAYER_ID)
    enemy_mid = RTSMiddleLayer(enemy_api)
    enemy_jobs = setup_jobs(enemy_api, enemy_mid)
    enemy_executor = create_executor(enemy_api, enemy_mid)
    enemy_nlu_gateway = Phase2NLUGateway(name="enemy")
    logger.info("Enemy NLU status: %s", enemy_nlu_gateway.status())
    runtime_gateway_cfg_path = Path("nlu_pipeline/configs/runtime_gateway.yaml")
    project_root = Path(__file__).resolve().parent

    def enemy_command_runner(command: str):
        if not _is_game_online():
            return ExecutionResult(
                success=False,
                message="OpenRA 未运行，Enemy指令已跳过（未调用LLM）",
                error="openra_offline",
            )
        result, _ = enemy_nlu_gateway.run(enemy_executor, command, rollout_key="enemy_agent")
        return result

    def mutate_runtime_gateway_config(mutator) -> dict:
        cfg = {}
        if runtime_gateway_cfg_path.exists():
            with runtime_gateway_cfg_path.open("r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        mutator(cfg)
        runtime_gateway_cfg_path.write_text(
            yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return cfg

    def broadcast_nlu_status() -> None:
        bridge = DashboardBridge()
        bridge.broadcast(
            "nlu_status",
            {
                "human": human_nlu_gateway.status(),
                "enemy": enemy_nlu_gateway.status(),
            },
        )

    def run_nlu_job(
        *,
        action: str,
        script: str,
        report_path: str,
        extra_args: list[str] | None = None,
    ) -> None:
        bridge = DashboardBridge()
        extra_args = extra_args or []
        cmd = [sys.executable, script, *extra_args]
        bridge.broadcast(
            "nlu_job_status",
            {
                "action": action,
                "stage": "start",
                "cmd": cmd,
                "timestamp": int(time.time() * 1000),
            },
        )
        try:
            proc = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
            )
            payload = {
                "action": action,
                "stage": "done",
                "returncode": int(proc.returncode),
                "stdout_tail": (proc.stdout or "")[-4000:],
                "stderr_tail": (proc.stderr or "")[-4000:],
                "report_path": report_path,
                "timestamp": int(time.time() * 1000),
            }
            report_file = project_root / report_path
            if report_file.exists():
                try:
                    payload["report"] = yaml.safe_load(report_file.read_text(encoding="utf-8"))
                except Exception:
                    payload["report_raw"] = report_file.read_text(encoding="utf-8", errors="ignore")[-4000:]
            bridge.broadcast("nlu_job_status", payload)
        except Exception as e:
            bridge.broadcast(
                "nlu_job_status",
                {
                    "action": action,
                    "stage": "error",
                    "error": str(e),
                    "timestamp": int(time.time() * 1000),
                },
            )

    runtime_model_cfg = resolve_model_config()
    dialogue_model = ModelFactory.build("enemy_dialogue", runtime_model_cfg)
    enemy_agent = EnemyAgent(
        executor=enemy_executor,
        dialogue_model=dialogue_model,
        bridge=DashboardBridge(),
        interval=ENEMY_TICK_INTERVAL,
        command_runner=enemy_command_runner,
    )
    logger.info(f"Enemy AI initialized: {ENEMY_PLAYER_ID}, interval={ENEMY_TICK_INTERVAL}s")

    # ========== Game Runtime State ==========
    game_runtime_lock = threading.RLock()
    game_runtime_online = False
    game_runtime_last_reason = "init"
    game_runtime_last_change_ms = int(time.time() * 1000)

    def _probe_game_online() -> bool:
        try:
            return bool(GameAPI.is_server_running(host="localhost", port=7445, timeout=0.6))
        except Exception:
            return False

    def _is_game_online() -> bool:
        with game_runtime_lock:
            return bool(game_runtime_online)

    def _broadcast_game_runtime_state(reason: str = "") -> None:
        with game_runtime_lock:
            payload = {
                "online": bool(game_runtime_online),
                "reason": str(reason or game_runtime_last_reason),
                "changed_at": int(game_runtime_last_change_ms),
                "timestamp": int(time.time() * 1000),
            }
        DashboardBridge().broadcast("game_runtime_state", payload)

    def _refresh_game_runtime_state(*, reason: str = "periodic_probe", force_broadcast: bool = False) -> bool:
        nonlocal game_runtime_online, game_runtime_last_reason, game_runtime_last_change_ms

        online = _probe_game_online()
        changed = False
        with game_runtime_lock:
            prev = bool(game_runtime_online)
            changed = online != prev
            if changed:
                game_runtime_online = online
                game_runtime_last_change_ms = int(time.time() * 1000)
            game_runtime_last_reason = str(reason or game_runtime_last_reason)

        if changed:
            if online:
                logger.info("OpenRA 连接已恢复，系统解除离线闸门")
            else:
                logger.warning("OpenRA 未运行/不可达，系统进入离线闸门（停止后台代理与任务）")
                if bool(getattr(enemy_agent, "running", False)):
                    enemy_agent.stop()

        if changed or force_broadcast:
            _broadcast_game_runtime_state(reason=reason)

        return online

    # ========== Jobs State ==========
    _last_jobs_state_key = ""

    def _serialize_job_manager_state(mgr: JobManager, side: str) -> dict:
        jobs_payload: list[dict] = []
        for job in mgr.jobs:
            actor_ids = mgr.get_actor_ids_for_job(job.job_id, alive_only=True)
            jobs_payload.append(
                {
                    "job_id": str(job.job_id),
                    "name": str(getattr(job, "NAME", job.job_id)),
                    "status": str(getattr(job, "status", "")),
                    "actor_count": len(actor_ids),
                    "actor_ids": actor_ids[:256],
                    "last_summary": str(getattr(job, "last_summary", "") or ""),
                    "last_error": str(getattr(job, "last_error", "") or ""),
                }
            )
        return {
            "side": side,
            "jobs": jobs_payload,
            "actor_job": {str(k): v for k, v in sorted(mgr.actor_job.items())},
        }

    def broadcast_jobs_state(*, force: bool = False) -> None:
        nonlocal _last_jobs_state_key
        payload = {
            "timestamp": int(time.time() * 1000),
            "human": _serialize_job_manager_state(human_jobs, "human"),
            "enemy": _serialize_job_manager_state(enemy_jobs, "enemy"),
        }
        state_key = str(payload.get("human")) + "|" + str(payload.get("enemy"))
        if not force and state_key == _last_jobs_state_key:
            return
        _last_jobs_state_key = state_key
        DashboardBridge().broadcast("jobs_state", payload)

    # ========== Agent 转发 ==========
    COPILOT_AGENT_TMUX = "openra-copilot"

    def _forward_to_agent(command: str) -> None:
        """Forward a web player command to the copilot agent tmux session."""
        try:
            # Check if the agent session exists
            check = subprocess.run(
                ["tmux", "has-session", "-t", COPILOT_AGENT_TMUX],
                capture_output=True, timeout=2,
            )
            if check.returncode != 0:
                logger.debug("Agent session '%s' not found, skip forward", COPILOT_AGENT_TMUX)
                return

            # Send with [WEB_PLAYER] header so the agent knows the source
            text = f"[WEB_PLAYER] {command}"
            subprocess.run(
                ["tmux", "send-keys", "-t", COPILOT_AGENT_TMUX, "-l", text],
                capture_output=True, timeout=2,
            )
            subprocess.run(
                ["tmux", "send-keys", "-t", COPILOT_AGENT_TMUX, "Enter"],
                capture_output=True, timeout=2,
            )
            logger.info("Forwarded to agent: %s", text)
        except Exception as e:
            logger.warning("Agent forward failed: %s", e)

    # ========== Console 命令处理器 ==========
    def copilot_command_handler(command: str, meta: dict | None = None) -> None:
        bridge = DashboardBridge()
        start_ts = int(time.time() * 1000)
        thread_id = threading.get_ident()
        payload_meta = meta or {}
        command_id = str(payload_meta.get("command_id") or f"cmd_{start_ts}_{thread_id}")

        def status_callback(stage: str, detail: str):
            bridge.broadcast("status", {
                "stage": stage,
                "detail": detail,
                "command_id": command_id,
                "timestamp": int(time.time() * 1000)
            })

        with human_status_callback_lock:
            human_status_callback_by_thread[thread_id] = status_callback

        # Record player command in event feed
        append_event("player_command", {"command": command}, cid=command_id)

        status_callback("received", f"收到指令: {command[:50]}...")

        try:
            if not _refresh_game_runtime_state(reason="human_command_precheck"):
                blocked_msg = "OpenRA 未运行，指令已拦截（未执行、未调用LLM）"
                status_callback("error", blocked_msg)
                append_interaction_event(
                    "dashboard_command_blocked",
                    {
                        "actor": "human",
                        "channel": "dashboard_command",
                        "command_id": command_id,
                        "utterance": command,
                        "response_message": blocked_msg,
                        "success": False,
                    },
                    timestamp_ms=start_ts,
                )
                bridge.broadcast(
                    "result",
                    {
                        "success": False,
                        "message": blocked_msg,
                        "code": "",
                        "observations": "",
                        "nlu": {"source": "game_gate", "reason": "openra_offline"},
                        "command_id": command_id,
                    },
                )
                bridge.send_log("warning", blocked_msg)
                return

            result = handle_command(
                executor,
                command,
                nlu_gateway=human_nlu_gateway,
                actor="human",
            )

            nlu_meta = result.get("nlu", {}) or {}
            nlu_source = nlu_meta.get("source", "")

            append_interaction_event(
                "dashboard_command",
                {
                    "actor": "human",
                    "channel": "dashboard_command",
                    "command_id": command_id,
                    "utterance": command,
                    "response_message": result.get("message", ""),
                    "success": bool(result.get("success", False)),
                    "observations": result.get("observations", ""),
                    "nlu": nlu_meta,
                },
                timestamp_ms=start_ts,
            )

            if nlu_source == "nlu_route":
                # NLU handled it — record in feed, do NOT forward to agent
                append_event("nlu_route", {
                    "command": command,
                    "intent": nlu_meta.get("intent", ""),
                    "confidence": nlu_meta.get("confidence", 0),
                    "message": result.get("message", ""),
                    "success": bool(result.get("success", False)),
                }, cid=command_id)
            else:
                # NLU missed — record in feed and forward to copilot agent
                append_event("nlu_miss", {
                    "command": command,
                    "reason": nlu_meta.get("reason", ""),
                }, cid=command_id)
                append_event("agent_forward", {"command": command}, cid=command_id)
                threading.Thread(
                    target=_forward_to_agent, args=(command,), daemon=True
                ).start()

            bridge.broadcast("result", {
                "success": result.get("success"),
                "message": result.get("message", ""),
                "code": result.get("code", ""),
                "observations": result.get("observations", ""),
                "nlu": nlu_meta,
                "command_id": command_id,
            })

            bridge.send_log(
                "info" if result.get("success") else "error",
                result.get("message", "")
            )
        except Exception as e:
            logger.error(f"Command failed: {e}", exc_info=True)
            append_interaction_event(
                "dashboard_command_error",
                {
                    "actor": "human",
                    "channel": "dashboard_command",
                    "command_id": command_id,
                    "utterance": command,
                    "error": str(e),
                },
                timestamp_ms=start_ts,
            )
            bridge.broadcast("status", {"stage": "error", "detail": str(e), "command_id": command_id})
            bridge.broadcast(
                "result",
                {
                    "success": False,
                    "message": f"执行失败: {e}",
                    "code": "",
                    "observations": "",
                    "nlu": {},
                    "command_id": command_id,
                },
            )
            bridge.send_log("error", f"Command failed: {str(e)}")
        finally:
            with human_status_callback_lock:
                human_status_callback_by_thread.pop(thread_id, None)

    # ========== 敌方控制处理器 ==========
    def enemy_control_handler(action: str, params: dict) -> None:
        if action == "start":
            if not _refresh_game_runtime_state(reason="enemy_start_precheck"):
                msg = "OpenRA 未运行，已阻止启动敌方AI"
                DashboardBridge().broadcast(
                    "enemy_status",
                    {"stage": "offline", "detail": msg, "timestamp": int(time.time() * 1000)},
                )
                DashboardBridge().broadcast("enemy_agent_state", enemy_agent.get_state())
                logger.warning(msg)
                return
            enemy_agent.start()
        elif action == "stop":
            enemy_agent.stop()
        elif action == "status":
            DashboardBridge().broadcast("enemy_agent_state", enemy_agent.get_state())
        elif action == "set_interval":
            interval = params.get("interval", 45.0)
            try:
                enemy_agent.set_interval(float(interval))
            except (ValueError, TypeError):
                logger.warning(f"Invalid interval value: {interval}")
        elif action == "reset_all":
            logger.info("Reset all: clearing context and restarting enemy agent")
            enemy_agent.stop()
            enemy_agent.reset()
            enemy_executor.ctx.history.clear()
            bridge = DashboardBridge()
            bridge.clear_chat_history()
            bridge.broadcast("reset_done", {"message": "上下文已清空"})
            if _refresh_game_runtime_state(reason="reset_all_postcheck"):
                enemy_agent.start()
            else:
                DashboardBridge().broadcast(
                    "enemy_status",
                    {"stage": "offline", "detail": "OpenRA 未运行，已跳过敌方重启", "timestamp": int(time.time() * 1000)},
                )
        elif action == "nlu_reload":
            human_nlu_gateway.reload()
            enemy_nlu_gateway.reload()
            broadcast_nlu_status()
        elif action == "nlu_set_rollout":
            try:
                target_agent = str(params.get("agent", "")).strip()
                percentage_raw = params.get("percentage")
                enabled_raw = params.get("enabled")
                bucket_key = params.get("bucket_key")

                def _mutator(cfg: dict) -> None:
                    rollout = cfg.setdefault("rollout", {})
                    if enabled_raw is not None:
                        rollout["enabled"] = bool(enabled_raw)
                    if percentage_raw is not None:
                        pct = max(0.0, min(100.0, float(percentage_raw)))
                        if target_agent:
                            by_agent = rollout.setdefault("percentages_by_agent", {})
                            if isinstance(by_agent, dict):
                                by_agent[target_agent] = pct
                        else:
                            rollout["default_percentage"] = pct
                    if bucket_key is not None:
                        rollout["bucket_key"] = str(bucket_key)

                cfg = mutate_runtime_gateway_config(_mutator)
                human_nlu_gateway.reload()
                enemy_nlu_gateway.reload()
                DashboardBridge().broadcast(
                    "nlu_rollout_updated",
                    {
                        "agent": target_agent,
                        "runtime_config_path": str(runtime_gateway_cfg_path),
                        "rollout": cfg.get("rollout", {}),
                    },
                )
                broadcast_nlu_status()
            except Exception as e:
                logger.error("nlu_set_rollout failed: %s", e, exc_info=True)
                DashboardBridge().broadcast("nlu_rollout_updated", {"error": str(e)})
        elif action == "nlu_set_shadow":
            try:
                shadow_mode = bool(params.get("shadow_mode", True))
                enabled_raw = params.get("enabled")

                def _mutator(cfg: dict) -> None:
                    cfg["shadow_mode"] = shadow_mode
                    if enabled_raw is not None:
                        cfg["enabled"] = bool(enabled_raw)

                mutate_runtime_gateway_config(_mutator)
                human_nlu_gateway.reload()
                enemy_nlu_gateway.reload()
                broadcast_nlu_status()
            except Exception as e:
                logger.error("nlu_set_shadow failed: %s", e, exc_info=True)
                DashboardBridge().broadcast("nlu_status", {"error": str(e)})
        elif action == "nlu_emergency_rollback":
            try:
                def _mutator(cfg: dict) -> None:
                    cfg["enabled"] = False
                    cfg["shadow_mode"] = False
                    cfg["phase"] = "phase4_manual_rollback"
                    rollout = cfg.setdefault("rollout", {})
                    rollout["enabled"] = True
                    rollout["default_percentage"] = 0
                    by_agent = rollout.get("percentages_by_agent", {})
                    if isinstance(by_agent, dict):
                        for k in list(by_agent.keys()):
                            by_agent[k] = 0
                        rollout["percentages_by_agent"] = by_agent

                mutate_runtime_gateway_config(_mutator)
                human_nlu_gateway.reload()
                enemy_nlu_gateway.reload()
                DashboardBridge().broadcast(
                    "nlu_rollback_done",
                    {
                        "phase": "phase4_manual_rollback",
                        "runtime_config_path": str(runtime_gateway_cfg_path),
                    },
                )
                broadcast_nlu_status()
            except Exception as e:
                logger.error("nlu_emergency_rollback failed: %s", e, exc_info=True)
                DashboardBridge().broadcast("nlu_rollback_done", {"error": str(e)})
        elif action == "nlu_status":
            broadcast_nlu_status()
        elif action == "nlu_phase6_runtest":
            run_nlu_job(
                action=action,
                script="nlu_pipeline/scripts/runtime_runtest.py",
                report_path="nlu_pipeline/reports/phase6_runtest_report.json",
            )
        elif action == "nlu_release_bundle":
            run_nlu_job(
                action=action,
                script="nlu_pipeline/scripts/release_bundle.py",
                report_path="nlu_pipeline/reports/phase5_release_report.json",
            )
        elif action == "nlu_smoke":
            run_nlu_job(
                action=action,
                script="nlu_pipeline/scripts/run_smoke.py",
                report_path="nlu_pipeline/reports/smoke_report.json",
            )
        elif action == "jobs_status":
            broadcast_jobs_state(force=True)

    # ========== 启动服务 ==========
    def enemy_chat_handler(message: str) -> None:
        if not _refresh_game_runtime_state(reason="enemy_chat_precheck"):
            DashboardBridge().broadcast(
                "enemy_chat",
                {"message": "OpenRA 未运行，敌方聊天已禁用（未调用LLM）", "type": "system"},
            )
            return
        enemy_agent.receive_player_message(message)

    DashboardBridge().start(
        port=DASHBOARD_PORT,
        command_handler=copilot_command_handler,
        enemy_chat_handler=enemy_chat_handler,
        enemy_control_handler=enemy_control_handler,
    )
    # 敌方代理不自动启动，通过 Web 控制台手动启动
    _refresh_game_runtime_state(reason="startup_probe", force_broadcast=True)
    broadcast_jobs_state(force=True)

    # ========== Job tick 后台线程 ==========
    _jobs_running = True
    _last_human_explore_summary = ""

    def _job_tick_loop():
        nonlocal _last_human_explore_summary
        while _jobs_running:
            if not _refresh_game_runtime_state(reason="job_tick_probe"):
                try:
                    broadcast_jobs_state(force=True)
                except Exception:
                    pass
                time.sleep(1.0)
                continue
            try:
                human_jobs.tick_jobs()
                explore_job = human_jobs.get_job("explore")
                if explore_job is not None:
                    summary = str(getattr(explore_job, "last_summary", "") or "")
                    if summary and summary != _last_human_explore_summary:
                        logger.info("ExploreJob[h] %s", summary)
                        _last_human_explore_summary = summary
            except Exception as e:
                logger.warning("human_jobs.tick_jobs failed: %s", e, exc_info=True)
            try:
                enemy_jobs.tick_jobs()
            except Exception as e:
                logger.warning("enemy_jobs.tick_jobs failed: %s", e, exc_info=True)
            try:
                broadcast_jobs_state()
            except Exception:
                pass
            time.sleep(1.0)

    job_thread = threading.Thread(target=_job_tick_loop, daemon=True)
    job_thread.start()

    logger.info("=" * 50)
    logger.info("System ready")
    logger.info(f"  Console WebSocket: ws://localhost:{DASHBOARD_PORT}")
    logger.info("  Model: %s", runtime_model_cfg.model)
    logger.info(f"  Human: {HUMAN_PLAYER_ID}")
    logger.info(f"  Enemy: {ENEMY_PLAYER_ID} (interval={ENEMY_TICK_INTERVAL}s)")
    logger.info("  Press Ctrl+C to stop")
    logger.info("=" * 50)

    # 保持运行
    def signal_handler(sig, frame):
        logger.info("Shutting down...")
        enemy_agent.stop()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        enemy_agent.stop()
        logger.info("Backend stopped.")


def main_cli() -> None:
    """CLI 模式 - 用于测试"""
    api = GameAPI(host="localhost", port=7445, language="zh")
    mid = RTSMiddleLayer(api)
    executor = create_executor(api, mid)
    human_nlu_gateway = Phase2NLUGateway(name="human_cli")
    
    logger.info("✓ CLI mode ready. Type commands or 'quit' to exit.")
    
    while True:
        try:
            command = input("\n> ").strip()
            
            if not command:
                continue
            
            if command.lower() in ("quit", "exit", "q"):
                break

            if not GameAPI.is_server_running(host="localhost", port=7445, timeout=0.6):
                print("\n✗ OpenRA 未运行，指令已拦截（未执行、未调用LLM）")
                continue
            
            result = handle_command(executor, command, nlu_gateway=human_nlu_gateway, actor="human")
            
            print(f"\n{'✓' if result.get('success') else '✗'} {result.get('message', '')}")
            
            if result.get("observations"):
                print(f"观测: {result.get('observations')}")

            nlu_meta = result.get("nlu", {})
            if nlu_meta:
                print(
                    f"NLU: {nlu_meta.get('source')} / {nlu_meta.get('reason')} "
                    f"(intent={nlu_meta.get('intent')}, conf={nlu_meta.get('confidence', 0):.3f})"
                )
            
            if not result.get("success") and result.get("error"):
                print(f"错误: {result.get('error')}")
        
        except EOFError:
            break
        except KeyboardInterrupt:
            print("\n")
            break
    
    logger.info("CLI stopped.")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        main_cli()
    else:
        main()
