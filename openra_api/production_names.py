"""Helpers for normalizing production names across LLM/GameAPI layers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SPACE_RUN = re.compile(r"\s+")
_COPILOT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "OpenCodeAlert" / "mods" / "common" / "Copilot.yaml"
_ALIAS_GROUPS: dict[str, set[str]] = {}


def _load_alias_groups() -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    if not _COPILOT_CONFIG_PATH.exists():
        return groups

    current_key: str | None = None
    in_units = False
    for raw_line in _COPILOT_CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw_line.startswith(" "):
            in_units = stripped == "units:"
            current_key = None
            continue
        if not in_units:
            continue
        if raw_line.startswith("    ") and stripped.endswith(":") and not raw_line.startswith("        "):
            current_key = stripped[:-1]
            groups.setdefault(current_key, {current_key})
            continue
        if current_key and raw_line.startswith("        "):
            groups[current_key].add(stripped)
    return groups


def _ensure_alias_groups() -> dict[str, set[str]]:
    global _ALIAS_GROUPS
    if not _ALIAS_GROUPS:
        _ALIAS_GROUPS = _load_alias_groups()
    return _ALIAS_GROUPS


def normalize_production_name(name: str | None) -> str:
    """Normalize a production alias to a server-friendly lookup form.

    The game-side alias table already understands Chinese names, internal codes
    like ``powr``, and lowercase English phrases like ``power plant``. What it
    does *not* handle well is LLM-style CamelCase such as ``PowerPlant``.

    This helper only normalizes the surface form; it doesn't force a single
    internal code, which keeps ambiguous aliases like ``barracks`` faction-safe.
    """

    raw = (name or "").strip()
    if not raw:
        return ""

    if raw.isascii():
        raw = raw.replace("_", " ").replace("-", " ")
        raw = _CAMEL_BOUNDARY.sub(" ", raw)
        raw = _SPACE_RUN.sub(" ", raw).strip().lower()
    return raw


def production_name_variants(name: str | None) -> list[str]:
    """Return unique lookup variants in preferred order."""

    raw = (name or "").strip()
    if not raw:
        return []

    variants: list[str] = []
    for candidate in (raw, normalize_production_name(raw)):
        if candidate and candidate not in variants:
            variants.append(candidate)

    groups = _ensure_alias_groups()
    normalized_inputs = {normalize_production_name(candidate) for candidate in variants}
    for canonical, aliases in groups.items():
        all_aliases = aliases | {canonical}
        normalized_aliases = {normalize_production_name(alias) for alias in all_aliases}
        if normalized_aliases & normalized_inputs:
            for alias in [canonical, *sorted(aliases)]:
                if alias and alias not in variants:
                    variants.append(alias)
    return variants


def production_name_matches(expected: str | None, *observed: str | None) -> bool:
    """Return True when any observed name matches the expected alias."""

    expected_variants = set(production_name_variants(expected))
    if not expected_variants:
        return False
    for name in observed:
        if set(production_name_variants(name)) & expected_variants:
            return True
    return False


def first_matching_production_name(
    expected: str | None,
    candidates: Iterable[str | None],
) -> str | None:
    """Return the first candidate that matches the expected alias."""

    for candidate in candidates:
        if production_name_matches(expected, candidate):
            return candidate
    return None
