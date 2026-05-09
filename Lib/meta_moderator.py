"""Process-level meta moderator for the CMM pipeline."""

from __future__ import annotations

import json
from typing import Any

from Lib.config import get_stage_settings
from Lib.json_retry import call_json_model
from Lib.json_utils import to_number, to_string_list


_ALLOWED_DECISIONS = {"SYNTHESIZE", "ADD_EXPERT", "DEEPEN", "REPLAN", "FINALIZE"}


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _normalize_decision(
    payload: dict | None,
    fallback: dict,
    *,
    warnings: list[str] | None = None,
    json_attempts: int = 1,
    raw: str = "",
) -> dict:
    if not isinstance(payload, dict):
        return fallback

    decision = payload.get("decision")
    if not isinstance(decision, str):
        return fallback

    decision = decision.strip().upper()
    if decision not in _ALLOWED_DECISIONS:
        return fallback

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = fallback["reason"]

    return {
        "decision": decision,
        "reason": reason.strip(),
        "missing_perspectives": to_string_list(payload.get("missing_perspectives"), max_items=8),
        "conflicts_to_resolve": to_string_list(payload.get("conflicts_to_resolve"), max_items=10),
        "risks_to_address": to_string_list(payload.get("risks_to_address"), max_items=10),
        "questions_to_answer": to_string_list(payload.get("questions_to_answer"), max_items=10),
        "next_actions": to_string_list(payload.get("next_actions"), max_items=10),
        "confidence": to_number(payload.get("confidence"), default=fallback["confidence"], max_value=1.0),
        "parse_warnings": warnings or [],
        "json_attempts": int(json_attempts or 0),
        "raw": str(raw or "")[:2000],
        "source": "model",
    }


def _rule_based_decision(
    *,
    balance_report: dict | None,
    deliberation_brief: dict | None,
    conflict_report: dict | None = None,
) -> dict:
    balance = _as_dict(balance_report)
    brief = _as_dict(deliberation_brief)
    conflict = _as_dict(conflict_report)

    missing = to_string_list(balance.get("missing_perspectives"), max_items=8)
    dominant_found = bool(balance.get("dominant_perspective_found", False))
    recommended_balance_action = balance.get("recommended_action")
    balance_blind_spots = to_string_list(balance.get("blind_spots"), max_items=8)
    argument_quality = balance.get("argument_quality") if isinstance(balance.get("argument_quality"), dict) else {}
    perspective_coverage = balance.get("perspective_coverage") if isinstance(balance.get("perspective_coverage"), dict) else {}
    constraint_coverage = balance.get("constraint_coverage") if isinstance(balance.get("constraint_coverage"), list) else []
    stakeholder_coverage = balance.get("stakeholder_coverage") if isinstance(balance.get("stakeholder_coverage"), list) else []
    risks = to_string_list(brief.get("expert_risks"), max_items=10)
    must_address = to_string_list(brief.get("must_address"), max_items=12)
    questions = to_string_list(brief.get("expert_questions"), max_items=10)
    unresolved_tradeoffs = conflict.get("unresolved_tradeoffs") if isinstance(conflict.get("unresolved_tradeoffs"), list) else []
    premature_consensus = to_string_list(conflict.get("premature_consensus_risks"), max_items=8)
    blind_spots = to_string_list(conflict.get("blind_spots"), max_items=8)
    disagreements = conflict.get("disagreements") if isinstance(conflict.get("disagreements"), list) else []
    serious_disagreements = [
        item
        for item in disagreements
        if isinstance(item, dict) and item.get("severity") in {"medium", "high"}
    ]
    complexity = str(brief.get("complexity") or "").lower()
    complex_query = complexity in {"moderate", "complex"}

    uncovered_constraints = [
        str(item.get("constraint") or "Uncovered constraint")
        for item in constraint_coverage
        if isinstance(item, dict) and not item.get("covered")
    ]
    uncovered_stakeholders = [
        str(item.get("stakeholder") or "Uncovered stakeholder")
        for item in stakeholder_coverage
        if isinstance(item, dict) and not item.get("covered")
    ]
    weak_quality_keys = [
        key
        for key, value in argument_quality.items()
        if key in {"specificity", "actionability", "novelty"}
        and isinstance(value, (int, float))
        and float(value) < 0.35
    ]
    weak_base_coverage = [
        key
        for key in ("strategy", "engineering", "risk", "user")
        if isinstance(perspective_coverage.get(key), (int, float)) and float(perspective_coverage.get(key)) < 0.35
    ]

    if recommended_balance_action == "ADD_EXPERT":
        return {
            "decision": "ADD_EXPERT",
            "reason": "Balance Analyzer 2.0 recommends adding expertise for missing or weakly covered perspectives.",
            "missing_perspectives": missing or weak_base_coverage[:5],
            "conflicts_to_resolve": balance_blind_spots[:5],
            "risks_to_address": risks[:5],
            "questions_to_answer": questions[:5],
            "next_actions": ["Add targeted expertise before synthesis."],
            "confidence": 0.76,
            "parse_warnings": ["meta_moderator_rule_fallback"],
            "source": "rules",
        }

    if unresolved_tradeoffs:
        return {
            "decision": "DEEPEN",
            "reason": "Unresolved semantic trade-offs should be addressed before synthesis.",
            "missing_perspectives": [],
            "conflicts_to_resolve": [
                str(item.get("tradeoff") or "Unresolved trade-off")
                for item in unresolved_tradeoffs[:5]
                if isinstance(item, dict)
            ],
            "risks_to_address": risks[:5],
            "questions_to_answer": questions[:5],
            "next_actions": ["Deepen analysis of unresolved trade-offs before planning."],
            "confidence": 0.78,
            "parse_warnings": ["meta_moderator_rule_fallback"],
            "source": "rules",
        }

    if serious_disagreements:
        return {
            "decision": "DEEPEN",
            "reason": "Semantic disagreements require resolution before synthesis.",
            "missing_perspectives": [],
            "conflicts_to_resolve": [
                str(item.get("issue") or "Semantic disagreement")
                for item in serious_disagreements[:5]
            ],
            "risks_to_address": risks[:5],
            "questions_to_answer": questions[:5],
            "next_actions": ["Deepen the discussion around high/medium severity disagreements."],
            "confidence": 0.76,
            "parse_warnings": ["meta_moderator_rule_fallback"],
            "source": "rules",
        }

    if premature_consensus:
        return {
            "decision": "DEEPEN",
            "reason": "Premature consensus risk detected.",
            "missing_perspectives": [],
            "conflicts_to_resolve": premature_consensus[:5],
            "risks_to_address": risks[:5],
            "questions_to_answer": questions[:5],
            "next_actions": ["Challenge the apparent consensus before synthesis."],
            "confidence": 0.74,
            "parse_warnings": ["meta_moderator_rule_fallback"],
            "source": "rules",
        }

    if blind_spots and complex_query:
        return {
            "decision": "DEEPEN",
            "reason": "Blind spots remain in a moderate/complex query.",
            "missing_perspectives": [],
            "conflicts_to_resolve": blind_spots[:5],
            "risks_to_address": risks[:5],
            "questions_to_answer": questions[:5],
            "next_actions": ["Address semantic blind spots before synthesis."],
            "confidence": 0.72,
            "parse_warnings": ["meta_moderator_rule_fallback"],
            "source": "rules",
        }

    if recommended_balance_action == "DEEPEN" or uncovered_constraints or uncovered_stakeholders or balance_blind_spots or weak_quality_keys:
        return {
            "decision": "DEEPEN",
            "reason": "Balance Analyzer 2.0 found weak coverage or argument-quality gaps.",
            "missing_perspectives": [],
            "conflicts_to_resolve": (balance_blind_spots + uncovered_constraints + uncovered_stakeholders + weak_quality_keys)[:8],
            "risks_to_address": risks[:5],
            "questions_to_answer": questions[:5],
            "next_actions": ["Deepen expert synthesis around balance-quality gaps."],
            "confidence": 0.73,
            "parse_warnings": ["meta_moderator_rule_fallback"],
            "source": "rules",
        }

    if missing:
        return {
            "decision": "DEEPEN",
            "reason": "Missing expert perspectives should be addressed before synthesis.",
            "missing_perspectives": missing,
            "conflicts_to_resolve": [],
            "risks_to_address": risks[:5],
            "questions_to_answer": questions[:5],
            "next_actions": ["Address missing perspectives in the deliberation brief."],
            "confidence": 0.75,
            "parse_warnings": ["meta_moderator_rule_fallback"],
            "source": "rules",
        }

    if dominant_found:
        dominant = balance.get("dominant_perspective") or "unknown"
        return {
            "decision": "DEEPEN",
            "reason": f"Perspective dominance detected: {dominant}.",
            "missing_perspectives": [],
            "conflicts_to_resolve": [f"Mitigate dominant perspective: {dominant}"],
            "risks_to_address": risks[:5],
            "questions_to_answer": questions[:5],
            "next_actions": ["Rebalance the deliberation before synthesis."],
            "confidence": 0.75,
            "parse_warnings": ["meta_moderator_rule_fallback"],
            "source": "rules",
        }

    if risks and not must_address:
        return {
            "decision": "DEEPEN",
            "reason": "Expert risks exist but no must-address items were carried forward.",
            "missing_perspectives": [],
            "conflicts_to_resolve": [],
            "risks_to_address": risks[:5],
            "questions_to_answer": questions[:5],
            "next_actions": ["Carry critical expert risks into the brief before planning."],
            "confidence": 0.7,
            "parse_warnings": ["meta_moderator_rule_fallback"],
            "source": "rules",
        }

    return {
        "decision": "SYNTHESIZE",
        "reason": "Expert perspectives are sufficient for synthesis.",
        "missing_perspectives": [],
        "conflicts_to_resolve": [],
        "risks_to_address": risks[:5],
        "questions_to_answer": questions[:5],
        "next_actions": ["Proceed to planning and synthesis."],
        "confidence": 0.8,
        "parse_warnings": ["meta_moderator_rule_fallback"],
        "source": "rules",
    }


def _all_expert_contributions_empty(expert_bundle: dict | None) -> bool:
    bundle = _as_dict(expert_bundle)
    contributions = bundle.get("contributions") if isinstance(bundle.get("contributions"), list) else []
    if not contributions:
        return False
    for contribution in contributions:
        if not isinstance(contribution, dict):
            continue
        for key in ("insights", "risks", "questions", "recommendations"):
            values = contribution.get(key)
            if isinstance(values, list) and any(str(item).strip() for item in values):
                if values != ["invalid_json_from_model"]:
                    return False
    return True


def _guard_should_override_model(
    *,
    fallback: dict,
    model_decision: dict,
    expert_bundle: dict | None,
    balance_report: dict | None,
    conflict_report: dict | None,
) -> bool:
    fallback_decision = fallback.get("decision")
    model_choice = model_decision.get("decision")
    if fallback_decision not in {"ADD_EXPERT", "DEEPEN"} or model_choice not in {"SYNTHESIZE", "FINALIZE"}:
        return False
    if float(fallback.get("confidence") or 0.0) >= 0.65:
        return True
    balance = _as_dict(balance_report)
    conflict = _as_dict(conflict_report)
    if balance.get("recommended_action") in {"ADD_EXPERT", "DEEPEN"}:
        return True
    if conflict.get("premature_consensus_risks") or conflict.get("blind_spots"):
        return True
    if _all_expert_contributions_empty(expert_bundle):
        return True
    return False


def run_meta_moderator(
    query: str,
    expert_bundle: dict | None,
    balance_report: dict | None,
    deliberation_brief: dict | None,
    plan: dict | None = None,
    answer: str | None = None,
    moderation_reports: list | None = None,
    conflict_report: dict | None = None,
    model: str = "deepseek-chat",
) -> dict:
    """Return a stable process-control decision for the current CMM state."""
    stage = get_stage_settings("meta", {"tokens": 550, "temp": 0.2})
    fallback = _rule_based_decision(
        balance_report=balance_report,
        deliberation_brief=deliberation_brief,
        conflict_report=conflict_report,
    )

    system_prompt = (
        "Ты meta_moderator коллективного мышления.\n"
        "Оцени процесс, а не финальный ответ. Верни СТРОГО JSON без markdown и пояснений.\n"
        "Схема:\n"
        "{\n"
        '  "decision": "SYNTHESIZE|ADD_EXPERT|DEEPEN|REPLAN|FINALIZE",\n'
        '  "reason": "string",\n'
        '  "missing_perspectives": ["string"],\n'
        '  "conflicts_to_resolve": ["string"],\n'
        '  "risks_to_address": ["string"],\n'
        '  "questions_to_answer": ["string"],\n'
        '  "next_actions": ["string"],\n'
        '  "confidence": 0.0\n'
        "}"
    )

    state = {
        "query": query,
        "expert_bundle": expert_bundle,
        "balance_report": balance_report,
        "deliberation_brief": deliberation_brief,
        "conflict_report": conflict_report,
        "plan": plan,
        "answer": answer,
        "moderation_reports": moderation_reports or [],
    }

    result = call_json_model(
        user_prompt="Оцени состояние CMM процесса:\n" + json.dumps(state, ensure_ascii=False),
        system_prompt=system_prompt,
        temp=float(stage.get("temp") or 0.2),
        tokens=int(stage.get("tokens") or 550),
        model=model,
        max_retries=1,
        log_purpose="meta_moderator",
    )

    parsed = result.get("payload") if isinstance(result, dict) else None
    retry_warnings = result.get("warnings") if isinstance(result, dict) and isinstance(result.get("warnings"), list) else []
    attempts = result.get("attempts") if isinstance(result, dict) and isinstance(result.get("attempts"), int) else 0
    raw = result.get("raw") if isinstance(result, dict) and isinstance(result.get("raw"), str) else ""
    decision = _normalize_decision(
        parsed,
        fallback=fallback,
        warnings=retry_warnings,
        json_attempts=attempts,
        raw=raw,
    )
    if decision is fallback:
        decision = dict(fallback)
        decision["parse_warnings"] = list(decision.get("parse_warnings", [])) + retry_warnings + [
            "meta_moderator_model_invalid_json"
        ]
        decision["json_attempts"] = attempts
        decision["raw"] = raw or ""
    else:
        if _guard_should_override_model(
            fallback=fallback,
            model_decision=decision,
            expert_bundle=expert_bundle,
            balance_report=balance_report,
            conflict_report=conflict_report,
        ):
            guarded = dict(fallback)
            guarded["parse_warnings"] = list(guarded.get("parse_warnings", [])) + retry_warnings + [
                "model_decision_overridden_by_rule_guard"
            ]
            guarded["json_attempts"] = attempts
            guarded["raw"] = raw or ""
            return guarded

    return decision
