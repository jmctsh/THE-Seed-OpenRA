"""Runtime NLU adapter that reuses the old Phase-2 NLU front-half only.

This module intentionally does NOT execute the old code templates / SimpleExecutor.
It only consumes:
  - PortableIntentModel
  - CommandRouter
  - runtime_gateway.yaml thresholds / guardrails

Then converts accepted routes into current-runtime direct actions that Adjutant can
translate into Kernel task/job creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Optional

import yaml

from models import DeployJobConfig, EconomyJobConfig, ReconJobConfig
from nlu_pipeline.rules import CommandRouter, RouteResult
from nlu_pipeline.runtime import PortableIntentModel
from openra_api.production_names import normalize_production_name
from unit_registry import UnitRegistry


_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONFIG_PATH = _ROOT / "nlu_pipeline" / "configs" / "runtime_gateway.yaml"
_DEFAULT_MODEL_PATH = _ROOT / "nlu_pipeline" / "artifacts" / "intent_model_runtime.json"


@dataclass(frozen=True)
class DirectNLUStep:
    intent: str
    expert_type: str
    config: Any
    reason: str
    source_text: str


@dataclass(frozen=True)
class RuntimeNLUDecision:
    source: str
    reason: str
    intent: Optional[str]
    confidence: float
    route_intent: Optional[str]
    matched: bool
    risk_level: str
    steps: list[DirectNLUStep]


class RuntimeNLURouter:
    """Adapter over the old tested NLU front-half for current runtime actions."""

    SUPPORTED_DIRECT_INTENTS = {"deploy_mcv", "produce", "explore"}

    def __init__(
        self,
        *,
        unit_registry: UnitRegistry,
        config_path: Path | str = _DEFAULT_CONFIG_PATH,
        model_path: Path | str = _DEFAULT_MODEL_PATH,
    ) -> None:
        self.unit_registry = unit_registry
        self.config_path = Path(config_path)
        self.model_path = Path(model_path)
        self.config = self._load_config()
        self.router = CommandRouter()
        self.model = self._load_model()
        self.safe_intents = {str(x) for x in self.config.get("safe_intents", []) if str(x).strip()}
        self.high_risk_intents = {
            str(x) for x in self.config.get("high_risk", {}).get("intents", []) if str(x).strip()
        }
        self._blocked_patterns = self._compile_blocked_patterns()

    def is_enabled(self) -> bool:
        return bool(self.config.get("enabled", False)) and self.model is not None

    def route(self, text: str) -> Optional[RuntimeNLUDecision]:
        normalized = str(text or "").strip()
        if not normalized or not self.is_enabled():
            return None
        if self._is_blocked(normalized):
            return None

        pred = self.model.predict_one(normalized)
        route_result = self.router.route(normalized)
        route_intent = route_result.intent
        risk_level = "high" if (pred.intent in self.high_risk_intents or route_intent in self.high_risk_intents) else "low"

        if not route_result.matched or not route_intent:
            return None

        if route_intent == "query_actor":
            # Keep queries in the current Adjutant query path.
            return None
        if route_intent not in self.safe_intents and route_intent != "composite_sequence":
            return None

        min_conf = float(self.config.get("min_confidence_by_intent", {}).get(pred.intent, 0.75))
        min_router_score = float(self.config.get("min_router_score", 0.8))

        if route_intent == "composite_sequence":
            return self._route_sequence(
                text=normalized,
                pred_intent=pred.intent,
                pred_conf=pred.confidence,
                route_result=route_result,
                min_router_score=min_router_score,
            )

        if route_intent not in self.SUPPORTED_DIRECT_INTENTS:
            return None
        if pred.intent != route_intent and not self._allow_safe_router_override(route_intent, normalized):
            return None
        if pred.confidence < min_conf and not self._allow_safe_router_override(route_intent, normalized):
            return None
        if float(route_result.score or 0.0) < min_router_score:
            return None

        steps = self._steps_from_intent(route_intent, route_result.entities or {}, normalized)
        if not steps:
            return None
        return RuntimeNLUDecision(
            source="nlu_route",
            reason="safe_intent_routed",
            intent=pred.intent,
            confidence=float(pred.confidence),
            route_intent=route_intent,
            matched=True,
            risk_level=risk_level,
            steps=steps,
        )

    def _route_sequence(
        self,
        *,
        text: str,
        pred_intent: str,
        pred_conf: float,
        route_result: RouteResult,
        min_router_score: float,
    ) -> Optional[RuntimeNLUDecision]:
        cfg = self.config.get("composite_gated", {})
        if not bool(cfg.get("enabled", False)):
            return None
        min_conf = float(cfg.get("min_confidence", 0.9))
        min_steps = int(cfg.get("min_steps", 2))
        max_steps = int(cfg.get("max_steps", self.config.get("max_steps_for_composite", 3)))
        allow_router_override = self._allow_safe_composite_router_override(route_result, text)
        router_score_threshold = max(min_router_score, float(cfg.get("min_router_score", 0.9)))
        if allow_router_override:
            router_score_threshold = min(
                router_score_threshold,
                float(cfg.get("router_override_score", 0.85)),
            )
        if pred_intent != "composite_sequence" and not allow_router_override:
            return None
        if pred_conf < min_conf and not allow_router_override:
            return None
        if float(route_result.score or 0.0) < router_score_threshold:
            return None

        entities = route_result.entities or {}
        step_intents = [str(x) for x in entities.get("step_intents") or [] if str(x).strip()]
        step_entities = list(entities.get("step_entities") or [])
        clauses = list(entities.get("clauses") or [])
        step_count = int(entities.get("step_count") or len(step_intents))
        if step_count < min_steps or step_count > max_steps:
            return None
        if len(step_intents) != len(step_entities) or len(step_intents) != len(clauses):
            return None
        if any(intent not in self.SUPPORTED_DIRECT_INTENTS for intent in step_intents):
            return None

        steps: list[DirectNLUStep] = []
        for step_intent, step_entity, clause in zip(step_intents, step_entities, clauses, strict=True):
            step_group = self._steps_from_intent(step_intent, dict(step_entity), str(clause))
            if not step_group:
                return None
            steps.extend(step_group)

        return RuntimeNLUDecision(
            source="nlu_route",
            reason="composite_gated_routed",
            intent=pred_intent,
            confidence=float(pred_conf),
            route_intent="composite_sequence",
            matched=True,
            risk_level="high",
            steps=steps,
        )

    def _steps_from_intent(
        self,
        intent: str,
        entities: dict[str, Any],
        source_text: str,
    ) -> list[DirectNLUStep]:
        if intent == "deploy_mcv":
            return [
                DirectNLUStep(
                    intent=intent,
                    expert_type="DeployExpert",
                    config=DeployJobConfig(actor_id=-1, target_position=(0, 0)),
                    reason="nlu_deploy_mcv",
                    source_text=source_text,
                )
            ]
        if intent == "explore":
            return [
                DirectNLUStep(
                    intent=intent,
                    expert_type="ReconExpert",
                    config=ReconJobConfig(
                        search_region="enemy_half",
                        target_type="base",
                        target_owner="enemy",
                        retreat_hp_pct=0.3,
                        avoid_combat=True,
                    ),
                    reason="nlu_explore",
                    source_text=source_text,
                )
            ]
        if intent == "produce":
            items = list(entities.get("production_items") or [])
            if not items and entities.get("unit"):
                items = [{"unit": entities.get("unit"), "count": entities.get("count") or 1}]
            steps: list[DirectNLUStep] = []
            for item in items:
                entry = self.unit_registry.resolve_name(item.get("unit"))
                if entry is None:
                    return []
                steps.append(
                    DirectNLUStep(
                        intent=intent,
                        expert_type="EconomyExpert",
                        config=EconomyJobConfig(
                            unit_type=normalize_production_name(entry.unit_id),
                            count=max(1, int(item.get("count") or 1)),
                            queue_type=entry.queue_type,
                            repeat=False,
                        ),
                        reason="nlu_produce",
                        source_text=source_text,
                    )
                )
            return steps
        return []

    def _allow_safe_composite_router_override(self, route_result: RouteResult, text: str) -> bool:
        entities = route_result.entities or {}
        step_intents = [str(x) for x in entities.get("step_intents") or [] if str(x).strip()]
        if not step_intents:
            return False
        if any(intent not in self.SUPPORTED_DIRECT_INTENTS for intent in step_intents):
            return False
        clauses = list(entities.get("clauses") or [])
        if not clauses:
            return False
        if any(not clause.strip() for clause in clauses):
            return False
        return True

    def _allow_safe_router_override(self, route_intent: str, text: str) -> bool:
        if not bool(self.config.get("allow_safe_router_override", True)):
            return False
        if route_intent == "produce":
            return self._looks_like_produce(text) or self._looks_like_implicit_produce(text)
        if route_intent == "explore":
            return True
        if route_intent == "deploy_mcv":
            return True
        return False

    def _is_blocked(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self._blocked_patterns)

    def _compile_blocked_patterns(self) -> list[re.Pattern[str]]:
        compiled: list[re.Pattern[str]] = []
        for item in self.config.get("blocked_regex", []):
            try:
                compiled.append(re.compile(str(item)))
            except re.error:
                continue
        return compiled

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {"enabled": False}
        data = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return {"enabled": False}
        return data

    def _load_model(self) -> Optional[PortableIntentModel]:
        if not self.model_path.exists():
            return None
        try:
            return PortableIntentModel.load(self.model_path)
        except Exception:
            return None

    @staticmethod
    def _looks_like_produce(command: str) -> bool:
        return bool(
            re.search(
                r"(建造|生产|训练|制造|造|补(?!给)|爆兵|出兵|起兵|来一个|来一辆|搞一个|整一个|下电|补电|下兵营|下车间|开车间|拍兵)",
                command,
            )
        )

    @staticmethod
    def _looks_like_implicit_produce(command: str) -> bool:
        if re.search(r"(展开|部署|下基地|开基地|基地车|建造车|mcv)", command):
            return False
        if re.search(r"(采矿|挖矿|采集|矿车干活|矿车采矿|去矿区|拉钱|采钱)", command):
            return False
        if re.search(r"(侦察|侦查|探索|探路|探图|开图)", command):
            return False
        if re.search(r"(查询|查看|列出|查下|看下|看看|有多少|多少|几辆|几只|几架|兵力)", command):
            return False
        if re.search(r"(攻击|进攻|突袭|集火|停火|停止攻击|停止进攻|取消攻击)", command):
            return False
        if re.search(r"^([0-9一二三四五六七八九十两]+)(个|辆|座|架|名|只|台)?", command):
            return True
        return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]{1,8}", command))
