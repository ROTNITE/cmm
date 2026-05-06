"""Deterministic routing for choosing DIRECT, LIGHT_CMM, or FULL_CMM."""

from __future__ import annotations

import re
from typing import Any


MODES = {"DIRECT", "LIGHT_CMM", "FULL_CMM"}
_COMPLEXITY_MAP = {"simple": "low", "moderate": "medium", "complex": "high", "low": "low", "medium": "medium", "high": "high"}

_HIGH_RISK_MARKERS = (
    "legal",
    "law",
    "compliance",
    "medical",
    "health",
    "financial",
    "finance",
    "security",
    "safety",
    "privacy",
    "harm",
    "vulnerable",
    "закон",
    "право",
    "комплаенс",
    "медиц",
    "здоров",
    "финанс",
    "безопас",
    "приват",
    "вред",
    "уязвим",
)
_FULL_MARKERS = (
    "strategy",
    "architecture",
    "governance",
    "evaluation",
    "tradeoff",
    "trade-off",
    "conflict",
    "stakeholder",
    "policy",
    "risk",
    "roadmap",
    "multi-stakeholder",
    "разбери подробно",
    "стратег",
    "архитект",
    "управлен",
    "оцен",
    "риски",
    "концепц",
    "компромисс",
    "конфликт",
    "стейкхолдер",
)
_LIGHT_MARKERS = (
    "plan",
    "steps",
    "compare",
    "choose",
    "improve",
    "metrics",
    "implementation",
    "план",
    "шаг",
    "сравн",
    "выбрать",
    "улучш",
    "метрик",
    "внедр",
)
_OPERATIONAL_PLAN_MARKERS = (
    "launch",
    "rollout",
    "deploy",
    "setup",
    "implement",
    "tool",
    "platform",
    "service",
    "knowledge base",
    "wiki",
    "documentation",
    "internal",
    "team",
    "small team",
    "запуск",
    "внедрен",
    "развертыван",
    "настройк",
    "инструмент",
    "платформ",
    "сервис",
    "база знаний",
    "вики",
    "документац",
    "внутренн",
    "команд",
    "небольш",
)
_SMALL_SCOPE_MARKERS = (
    "small",
    "quick",
    "simple",
    "lightweight",
    "недорого",
    "быстро",
    "просто",
    "легк",
    "небольш",
    "за месяц",
    "за неделю",
    "в течение месяца",
)
_DIRECT_MARKERS = (
    "what is",
    "define",
    "explain",
    "briefly",
    "short answer",
    "что такое",
    "объясни",
    "кратко",
    "дай определение",
)
_FORMAT_ONLY_MARKERS = (
    "brief",
    "briefly",
    "concise",
    "short",
    "simple language",
    "plain language",
    "sentences",
    "words",
    "keep it concise",
    "кратко",
    "коротко",
    "простым языком",
    "до 5 предлож",
    "до пяти предлож",
    "в пределах 5 предлож",
    "не более 5 предлож",
    "без деталей",
)
_STAKEHOLDER_MARKERS = (
    "stakeholder",
    "multi-stakeholder",
    "governance",
    "team",
    "organization",
    "university",
    "students",
    "users",
    "residents",
    "стейкхолдер",
    "заинтересован",
    "управлен",
    "организац",
    "университет",
    "студент",
    "жител",
    "пользовател",
)
_TRADEOFF_MARKERS = (
    "tradeoff",
    "trade-off",
    "trade off",
    "compromise",
    "tension",
    "conflict",
    "balance between",
    "компромисс",
    "конфликт",
    "баланс между",
    "противореч",
)


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"[^\w\sа-яё]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _format_only_items(items: list) -> bool:
    """Return True when constraints are just answer-shape preferences.

    Real eval datasets often include DIRECT cases with constraints like
    "keep it concise" or "answer in 5 sentences". Those should not promote a
    definition/explanation request into LIGHT/FULL CMM.
    """
    if not items:
        return True
    for item in items:
        text = _normalize_text(item)
        if not text or not _contains_any(text, _FORMAT_ONLY_MARKERS):
            return False
    return True


def _direct_request_text(query_intake: dict, original_query: str) -> str:
    parts = [original_query]
    for key in ("original_query", "cleaned_query", "task_goal"):
        value = query_intake.get(key)
        if isinstance(value, str):
            parts.append(value)
    return _normalize_text(" ".join(parts))


def _intake_text(query_intake: dict, original_query: str) -> str:
    parts = [original_query]
    for key in ("original_query", "cleaned_query", "task_goal"):
        value = query_intake.get(key)
        if isinstance(value, str):
            parts.append(value)
    for key in ("context", "constraints", "success_criteria", "unknowns", "user_preferences"):
        for item in _safe_list(query_intake.get(key)):
            parts.append(str(item))
    return _normalize_text(" ".join(parts))


def _router_complexity(query_intake: dict, text: str) -> str:
    raw = str(query_intake.get("complexity") or "").strip().lower()
    if raw in _COMPLEXITY_MAP:
        return _COMPLEXITY_MAP[raw]
    words = text.split()
    if len(words) <= 12:
        return "low"
    if len(words) > 80 or _contains_any(text, _FULL_MARKERS):
        return "high"
    return "medium"


def _normalize_decision(mode: str, reason: str, complexity: str, signals: dict, warnings: list[str] | None = None) -> dict:
    mode = mode if mode in MODES else "LIGHT_CMM"
    cost = {"DIRECT": "S", "LIGHT_CMM": "M", "FULL_CMM": "L"}[mode]
    return {
        "mode": mode,
        "reason": reason,
        "complexity": complexity if complexity in {"low", "medium", "high"} else "medium",
        "needs_expert_panel": mode in {"LIGHT_CMM", "FULL_CMM"},
        "needs_second_round": mode == "FULL_CMM" and bool(signals.get("needs_second_round")),
        "estimated_cost_class": cost,
        "signals": dict(signals),
        "warnings": list(warnings or []),
    }


def route_query(query_intake: dict, *, original_query: str = "") -> dict:
    """Route a query to DIRECT, LIGHT_CMM, or FULL_CMM without model calls."""
    warnings: list[str] = []
    intake = _safe_dict(query_intake)
    if not intake:
        warnings.append("router_empty_intake")
    text = _intake_text(intake, original_query)
    complexity = _router_complexity(intake, text)
    risk_level = str(intake.get("risk_level") or "").strip().lower()
    should_use_cmm = intake.get("should_use_cmm")
    constraints = _safe_list(intake.get("constraints"))
    success_criteria = _safe_list(intake.get("success_criteria"))
    context = _safe_list(intake.get("context"))
    unknowns = _safe_list(intake.get("unknowns"))
    preferences = _safe_list(intake.get("user_preferences"))
    word_count = len(text.split())

    signals = {
        "risk_level": risk_level or "unknown",
        "intake_complexity": str(intake.get("complexity") or "").strip().lower() or "unknown",
        "word_count": word_count,
        "constraints_count": len(constraints),
        "success_criteria_count": len(success_criteria),
        "context_count": len(context),
        "unknowns_count": len(unknowns),
        "preferences_count": len(preferences),
        "has_constraints": bool(constraints),
        "has_success_criteria": bool(success_criteria),
        "should_use_cmm": bool(should_use_cmm) if isinstance(should_use_cmm, bool) else None,
        "has_high_risk_markers": _contains_any(text, _HIGH_RISK_MARKERS),
        "has_risk_markers": _contains_any(text, _HIGH_RISK_MARKERS) or "risk" in text or "рис" in text,
        "has_stakeholder_markers": _contains_any(text, _STAKEHOLDER_MARKERS),
        "has_tradeoff_markers": _contains_any(text, _TRADEOFF_MARKERS),
        "has_full_markers": _contains_any(text, _FULL_MARKERS),
        "has_light_markers": _contains_any(text, _LIGHT_MARKERS),
        "has_direct_markers": _contains_any(text, _DIRECT_MARKERS),
        "has_operational_plan_markers": _contains_any(text, _OPERATIONAL_PLAN_MARKERS),
        "has_small_scope_markers": _contains_any(text, _SMALL_SCOPE_MARKERS),
        "needs_second_round": False,
    }

    high_risk = risk_level == "high" or signals["has_high_risk_markers"]
    direct_text = _direct_request_text(intake, original_query)

    # Check if this is a definition/explanation question (e.g., "What is X?", "Explain Y")
    # These should go DIRECT even if they mention stakeholders/tradeoffs in the question itself
    is_definition_question = (
        _contains_any(direct_text, _DIRECT_MARKERS)
        and complexity == "low"
        and not high_risk
        and word_count <= 80
        and _format_only_items(constraints)
        and _format_only_items(success_criteria)
        and not unknowns
        and not preferences
    )

    direct_explanation = (
        complexity == "low"
        and not high_risk
        and risk_level in {"", "low", "unknown"}
        and (should_use_cmm is False or _contains_any(direct_text, _DIRECT_MARKERS))
        and _contains_any(direct_text, _DIRECT_MARKERS)
        and _format_only_items(constraints)
        and _format_only_items(success_criteria)
        and not unknowns
        and not preferences
    )
    if direct_explanation or is_definition_question:
        return _normalize_decision(
            "DIRECT",
            "Simple low-risk explanation request has only formatting constraints.",
            complexity,
            signals,
            warnings,
        )

    many_constraints = len(constraints) >= 3 or len(success_criteria) >= 3
    constrained_plan = len(constraints) >= 2 and len(success_criteria) >= 1

    # Define multi_stakeholder early for use in operational_plan check
    # For operational plans, "team" alone doesn't mean multi-stakeholder governance
    # Multi-stakeholder means multiple conflicting groups, not just "a team"
    has_multi_stakeholder_markers = (
        signals["has_stakeholder_markers"]
        and not (
            # Single team operational plans are not multi-stakeholder
            signals["has_operational_plan_markers"]
            and signals["has_small_scope_markers"]
            and len(context) < 2
        )
    )
    multi_stakeholder = (len(context) >= 2 or has_multi_stakeholder_markers) and not is_definition_question

    # Check for operational plan: implementation/tool/process for small team
    # These should go LIGHT_CMM, not FULL_CMM, unless they have true high-risk or multi-stakeholder governance
    is_operational_plan = (
        signals["has_operational_plan_markers"]
        and (signals["has_small_scope_markers"] or len(constraints) >= 1)
        and not high_risk
        and not multi_stakeholder
        and complexity in {"low", "medium"}
    )

    if is_operational_plan:
        return _normalize_decision(
            "LIGHT_CMM",
            "Operational plan for small team without high-risk or multi-stakeholder governance.",
            complexity,
            signals,
            warnings,
        )

    # Only consider stakeholder/tradeoff markers if NOT a definition question
    conflict_heavy = (signals["has_tradeoff_markers"] or signals["has_full_markers"]) and not is_definition_question
    full_signals = high_risk or complexity == "high" or many_constraints or multi_stakeholder or conflict_heavy
    if full_signals:
        signals["needs_second_round"] = high_risk or complexity == "high" or many_constraints or multi_stakeholder
        return _normalize_decision("FULL_CMM", "Complex, high-risk, or multi-stakeholder signals require full CMM.", complexity, signals, warnings)

    simple_direct = (
        complexity == "low"
        and risk_level in {"", "low", "unknown"}
        and (should_use_cmm is False or signals["has_direct_markers"])
        and not constraints
        and not success_criteria
        and not context
        and not unknowns
        and not preferences
        and word_count <= 24
        and not signals["has_light_markers"]
    )
    if simple_direct:
        return _normalize_decision("DIRECT", "Simple low-risk request does not need CMM.", complexity, signals, warnings)

    if should_use_cmm is False and not high_risk and complexity == "low" and not constraints and not success_criteria:
        return _normalize_decision("DIRECT", "Intake indicates CMM is unnecessary and no risk markers were found.", complexity, signals, warnings)

    if constrained_plan:
        return _normalize_decision("LIGHT_CMM", "Constrained request with success criteria needs a light CMM pass.", complexity, signals, warnings)

    return _normalize_decision("LIGHT_CMM", "Moderate or mildly constrained request benefits from a light CMM pass.", complexity, signals, warnings)


__all__ = ["route_query"]
