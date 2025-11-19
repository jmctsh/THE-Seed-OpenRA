from __future__ import annotations
from typing import Any, Dict, List, Optional
import json

# —— the-seed 组件 ——
from the_seed.core.agent import Agent, AgentConfig
from the_seed.core.planning import Planner, PlannerConfig
from the_seed.core.model import ModelAdapter
from the_seed.core.model_openai import OpenAIModelAdapter, OpenAIModelConfig
from the_seed.core.memory import SimpleMemory
from the_seed.core.registry import ActionRegistry
from the_seed.core.runtime import SeedRuntime
from the_seed.utils.log_manager import LogManager
from the_seed.config import load_config, SeedConfig
from the_seed.config.schema import OpenAISection

# —— OpenRA 环境适配 ——
from adapter.openra_env import OpenRAEnv

# —— 一个简单的模型适配器（示例：把 prompt->规则 生成 tool_calls），实际替换为你的 LLM 服务 —— 
class RuleBasedDemoModel(ModelAdapter):
    """仅用于演示：当现金不足就生产电厂；有两个单位就向(20,20)移动。实际请替换为 OpenAI/本地 LLM。"""
    def complete(self, prompt: str, *, tools_schema: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        data = json.loads(prompt)
        obs = data.get("observation", {})
        base = obs.get("base", {})
        units = obs.get("visible_units", [])
        calls: List[Dict[str, Any]] = []

        if base.get("power") is not None and base.get("powerProvided") is not None:
            if base["powerProvided"] - base["powerDrained"] < 20:
                calls.append({"name":"Produce", "arguments":{"unit_type":"电厂","quantity":1,"auto_place_building":True}})

        first_two = [u["id"] for u in units[:2]] if units else []
        if first_two:
            calls.append({"name":"MoveTo","arguments":{"unit_ids":first_two,"x":20,"y":20,"attack_move":False}})

        return {"thoughts":"demo rules", "tool_calls": calls}

logger = LogManager.get_logger()

def build_commander(env: OpenRAEnv, config: Optional[SeedConfig] = None) -> SeedRuntime:
    cfg = config or load_config()
    LogManager.configure(
        log_level=cfg.logging.level,
        debug_mode=cfg.logging.debug_mode,
        log_dir=cfg.logging.log_dir,
    )
    logger.info(
        "加载配置完成：logging=%s debug=%s log_dir=%s",
        cfg.logging.level,
        cfg.logging.debug_mode,
        cfg.logging.log_dir,
    )
    # 注册动作
    reg = ActionRegistry()
    env.register_actions(reg)
    logger.info("Commander 注册完所有动作")

    # 准备 Planner/Agent/Memory
    model = _init_model(cfg)
    planner = Planner(
        model,
        PlannerConfig(
            json_mode=cfg.planner.json_mode,
            max_tools_per_tick=cfg.planner.max_tools_per_tick,
        ),
    )
    memory = SimpleMemory()
    agent = Agent(planner, reg, memory, AgentConfig(role_prompt=cfg.agent.role_prompt))

    runtime = SeedRuntime(
        env_observe=env.observe,
        agent=agent,
        cfg=cfg.runtime,
    )
    return runtime


def _init_model(cfg: SeedConfig) -> ModelAdapter:
    """优先使用 OpenAI 适配器，若缺少配置则退回规则模型。"""
    try:
        if cfg.openai.enabled:
            return _build_openai_model(cfg.openai)
        logger.info("OpenAI 配置未启用，采用 RuleBasedDemoModel")
        return RuleBasedDemoModel()
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenAI 模型初始化失败：%s，使用 RuleBasedDemoModel", exc)
        return RuleBasedDemoModel()


def _build_openai_model(openai_cfg: OpenAISection) -> ModelAdapter:
    api_key = openai_cfg.api_key or None
    if not api_key:
        raise ValueError("OpenAI 配置启用但缺少 api_key")
    cfg = OpenAIModelConfig(
        api_key=api_key,
        base_url=openai_cfg.base_url,
        organization=openai_cfg.organization,
        model=openai_cfg.model,
        use_responses_api=openai_cfg.use_responses_api or openai_cfg.reasoning,
        reasoning=openai_cfg.reasoning,
        reasoning_effort=openai_cfg.reasoning_effort,
        max_output_tokens=openai_cfg.max_output_tokens,
        temperature=openai_cfg.temperature,
        top_p=openai_cfg.top_p,
        response_format=openai_cfg.response_format,
    )
    logger.info(
        "初始化 OpenAIModelAdapter：model=%s, responses=%s, reasoning=%s",
        cfg.model,
        cfg.use_responses_api,
        cfg.reasoning,
    )
    return OpenAIModelAdapter(cfg)