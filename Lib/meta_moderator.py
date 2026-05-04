"""Process-level meta moderator for the CMM pipeline."""

from __future__ import annotations

import json
from typing import Any

from Lib.AI_request import send_to_AI
from Lib.json_utils import safe_json_loads, to_number, to_string_list


_ALLOWED_DECISIONS = {"SYNTHESIZE", "ADD_EXPERT", "DEEPEN", "REPLAN", "FINALIZE"}


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _normalize_decision(payload: dict | None, fallback: dict) -> dict:
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
        "parse_warnings": [],
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

    raw = send_to_AI(
        user_prompt="Оцени состояние CMM процесса:\n" + json.dumps(state, ensure_ascii=False),
        system_prompt=system_prompt,
        temp=0.2,
        tokens=550,
        model=model,
    )

    parsed = safe_json_loads(raw)
    decision = _normalize_decision(parsed, fallback=fallback)
    if decision is fallback:
        decision = dict(fallback)
        decision["raw"] = raw or ""
    else:
        decision["raw"] = raw or ""

    return decision
