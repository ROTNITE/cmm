"""Compact context builders for CMM downstream agents.

Phase 7 goal:
- Do not pass the whole CMM state into prompts.
- Preserve stable legacy keys used by planner/critic/moderator tests.
- Keep original_query authoritative.
- Record context sizes for trace observability.
"""

from __future__ import annotations

import json
from typing import Any


_AUTHORITATIVE_QUERY_INSTRUCTION = (
    "Original query is authoritative. Cleaned/formalized query is helper text only. "
    "Do not ignore constraints from original_query."
)


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _string_list(value: Any, max_items: int = 8, max_chars: int = 300) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in _as_list(value):
        if not isinstance(item, str):
            item = str(item) if item is not None else ""
        text = item.strip()
        if not text:
            continue
        text = text[:max_chars]
        marker = text.lower()
        if marker in seen:
            continue
        seen.add(marker)
        out.append(text)
        if len(out) >= max_items:
            break
    return out


def _dict_list(value: Any, max_items: int = 6) -> list[dict]:
    out: list[dict] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            out.append(dict(item))
        if len(out) >= max_items:
            break
    return out


def _clip_string(value: Any, max_chars: int = 1000) -> str:
    if not isinstance(value, str):
        value = str(value) if value is not None else ""
    return value.strip()[:max_chars]


def _compact_jsonable(value: Any, *, max_string_chars: int = 1000, max_list_items: int = 12) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _compact_jsonable(item, max_string_chars=max_string_chars, max_list_items=max_list_items)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _compact_jsonable(item, max_string_chars=max_string_chars, max_list_items=max_list_items)
            for item in value[:max_list_items]
        ]
    if isinstance(value, str):
        return value[:max_string_chars]
    return value


def context_chars(context: Any) -> int:
    try:
        return len(json.dumps(context, ensure_ascii=False, sort_keys=True))
    except Exception:
        return len(str(context or ""))


def record_context_size(state: dict, name: str, context: Any) -> dict:
    """Record compact context size in state and return the context unchanged."""
    if isinstance(state, dict):
        state.setdefault("context_compression", {})[f"{name}_context_chars"] = context_chars(context)
    return context


def _latest_dict(items: Any) -> dict:
    values = _as_list(items)
    for item in reversed(values):
        if isinstance(item, dict):
            return item
    return {}


def _intake_summary(state: dict) -> dict:
    intake = _as_dict(state.get("query_intake"))
    original_query = state.get("original_query") or intake.get("original_query") or ""

    return {
        "original_query": _clip_string(original_query, 4000),
        "cleaned_query": _clip_string(intake.get("cleaned_query") or original_query, 1200),
        "task_goal": _clip_string(intake.get("task_goal"), 1200),
        "context": _string_list(intake.get("context"), max_items=8),
        "constraints": _string_list(intake.get("constraints"), max_items=10),
        "success_criteria": _string_list(intake.get("success_criteria"), max_items=8),
        "unknowns": _string_list(intake.get("unknowns"), max_items=8),
        "user_preferences": _string_list(intake.get("user_preferences"), max_items=8),
        "risk_level": _clip_string(intake.get("risk_level"), 50),
        "complexity": _clip_string(intake.get("complexity"), 50),
        "should_use_cmm": bool(intake.get("should_use_cmm", True)),
        "parse_warnings": _string_list(intake.get("parse_warnings"), max_items=6),
        "source": _clip_string(intake.get("source"), 80),
    }


def _balance_summary(state: dict) -> dict:
    balance = _as_dict(state.get("balance_report"))
    return {
        "dominant_perspective_found": bool(balance.get("dominant_perspective_found", False)),
        "dominant_perspective": balance.get("dominant_perspective"),
        "missing_perspectives": _string_list(balance.get("missing_perspectives"), max_items=8),
        "notes": _string_list(balance.get("notes"), max_items=6),
        "perspective_coverage": _as_dict(balance.get("perspective_coverage")),
        "stakeholder_coverage": _dict_list(balance.get("stakeholder_coverage"), max_items=8),
        "constraint_coverage": _dict_list(balance.get("constraint_coverage"), max_items=8),
        "risk_severity_distribution": _as_dict(balance.get("risk_severity_distribution")),
        "argument_quality": _as_dict(balance.get("argument_quality")),
        "dominance": _as_dict(balance.get("dominance")),
        "blind_spots": _string_list(balance.get("blind_spots"), max_items=8),
        "recommended_action": balance.get("recommended_action") or "SYNTHESIZE",
    }


def _brief_summary(state: dict) -> dict:
    brief = _as_dict(state.get("deliberation_brief"))
    intake = _intake_summary(state)

    compact = {
        "summary": _clip_string(brief.get("summary"), 1000),
        "expert_recommendations": _string_list(brief.get("expert_recommendations"), max_items=10),
        "expert_risks": _string_list(brief.get("expert_risks"), max_items=10),
        "expert_questions": _string_list(brief.get("expert_questions"), max_items=8),
        "perspective_counts": _as_dict(brief.get("perspective_counts")),
        "missing_perspectives": _string_list(brief.get("missing_perspectives"), max_items=8),
        "dominant_perspective_found": bool(brief.get("dominant_perspective_found", False)),
        "balance_notes": _string_list(brief.get("balance_notes"), max_items=6),
        "balance_quality": _as_dict(brief.get("balance_quality")),
        "constraint_coverage": _dict_list(brief.get("constraint_coverage"), max_items=8),
        "stakeholder_coverage": _dict_list(brief.get("stakeholder_coverage"), max_items=8),
        "balance_blind_spots": _string_list(brief.get("balance_blind_spots"), max_items=8),
        "recommended_balance_action": brief.get("recommended_balance_action") or "SYNTHESIZE",
        "must_address": _string_list(brief.get("must_address"), max_items=14),
        "agreements": _dict_list(brief.get("agreements"), max_items=5),
        "disagreements": _dict_list(brief.get("disagreements"), max_items=5),
        "unresolved_tradeoffs": _dict_list(brief.get("unresolved_tradeoffs"), max_items=5),
        "premature_consensus_risks": _string_list(brief.get("premature_consensus_risks"), max_items=5),
        "blind_spots": _string_list(brief.get("blind_spots"), max_items=6),
        "deliberation_agreements": _string_list(brief.get("deliberation_agreements"), max_items=5),
        "deliberation_disagreements": _string_list(brief.get("deliberation_disagreements"), max_items=5),
        "revised_recommendations": _string_list(brief.get("revised_recommendations"), max_items=8),
        "new_risks": _string_list(brief.get("new_risks"), max_items=8),
        "questions_for_group": _string_list(brief.get("questions_for_group"), max_items=8),
        "meta_process_notes": _string_list(brief.get("meta_process_notes"), max_items=8),
        "task_goal": intake.get("task_goal"),
        "constraints": intake.get("constraints"),
        "success_criteria": intake.get("success_criteria"),
        "unknowns": intake.get("unknowns"),
        "user_preferences": intake.get("user_preferences"),
        "complexity": intake.get("complexity"),
        "risk_level": intake.get("risk_level"),
    }
    return compact


def _conflict_summary(state: dict) -> dict:
    conflict = _as_dict(state.get("conflict_report"))
    return {
        "agreements": _dict_list(conflict.get("agreements"), max_items=5),
        "disagreements": _dict_list(conflict.get("disagreements"), max_items=6),
        "unresolved_tradeoffs": _dict_list(conflict.get("unresolved_tradeoffs"), max_items=6),
        "premature_consensus_risks": _string_list(conflict.get("premature_consensus_risks"), max_items=6),
        "blind_spots": _string_list(conflict.get("blind_spots"), max_items=8),
        "minority_positions": _string_list(conflict.get("minority_positions"), max_items=6),
        "questions_for_next_round": _string_list(conflict.get("questions_for_next_round"), max_items=6),
        "confidence": conflict.get("confidence", 0.0),
        "parse_warnings": _string_list(conflict.get("parse_warnings"), max_items=6),
        "source": conflict.get("source") or "",
    }


def _deliberation_revisions(state: dict) -> list[dict]:
    out: list[dict] = []
    for bundle in _as_list(state.get("deliberation_rounds")):
        if not isinstance(bundle, dict):
            continue
        for response in _as_list(bundle.get("responses")):
            if not isinstance(response, dict):
                continue
            item = {
                "role_key": response.get("role_key") or "unknown",
                "revised_recommendations": _string_list(response.get("revised_recommendations"), max_items=5),
                "new_risks": _string_list(response.get("new_risks"), max_items=5),
                "disagreements": _string_list(response.get("disagreements"), max_items=5),
            }
            if item not in out:
                out.append(item)
            if len(out) >= 10:
                return out
    return out


def _dynamic_roles_generated(state: dict) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for report in _as_list(state.get("dynamic_role_reports")):
        if not isinstance(report, dict):
            continue
        round_name = str(report.get("round") or "")
        for view in _as_list(report.get("role_views")):
            if not isinstance(view, dict):
                continue
            key = str(view.get("key") or "").strip()
            if not key:
                continue
            marker = (round_name, key)
            if marker in seen:
                continue
            seen.add(marker)
            out.append(
                {
                    "key": key,
                    "name": view.get("name") or "",
                    "perspective_tag": view.get("perspective_tag") or "",
                    "why_needed": view.get("why_needed") or "",
                    "round": round_name,
                }
            )
    return out


def _dynamic_roles_executed(state: dict) -> list[dict]:
    generated = {role.get("key"): role for role in _dynamic_roles_generated(state) if role.get("key")}
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for index, bundle in enumerate(_as_list(state.get("expert_rounds"))):
        if not isinstance(bundle, dict):
            continue
        round_name = "initial" if index == 0 else "extra"
        for view in _as_list(bundle.get("roles")):
            if not isinstance(view, dict):
                continue
            key = str(view.get("key") or "").strip()
            if not key:
                continue
            is_dynamic = bool(view.get("dynamic")) or key in generated
            if not is_dynamic:
                continue
            marker = (round_name, key)
            if marker in seen:
                continue
            seen.add(marker)
            base = generated.get(key, {})
            out.append(
                {
                    "key": key,
                    "name": view.get("name") or base.get("name") or "",
                    "perspective_tag": view.get("perspective_tag") or base.get("perspective_tag") or "",
                    "why_needed": view.get("why_needed") or base.get("why_needed") or "",
                    "round": round_name,
                }
            )

    return out


def _roles_compact(state: dict) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for bundle in _as_list(state.get("expert_rounds")):
        if not isinstance(bundle, dict):
            continue
        for role in _as_list(bundle.get("roles")):
            if not isinstance(role, dict):
                continue
            key = str(role.get("key") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "key": key,
                    "name": role.get("name") or "",
                    "perspective_tag": role.get("perspective_tag") or "",
                    "dynamic": bool(role.get("dynamic", False)),
                }
            )
            if len(out) >= 12:
                return out
    return out


def _expert_bundle_compact(state: dict) -> dict:
    bundle = _as_dict(state.get("expert_bundle"))
    synthesis = _as_dict(bundle.get("synthesis"))

    contributions: list[dict] = []
    for item in _as_list(bundle.get("contributions")):
        if not isinstance(item, dict):
            continue
        contributions.append(
            {
                "role_key": item.get("role_key") or "",
                "perspective_tag": item.get("perspective_tag") or "",
                "recommendations": _string_list(item.get("recommendations"), max_items=4),
                "risks": _string_list(item.get("risks"), max_items=4),
                "questions": _string_list(item.get("questions"), max_items=3),
                "insights": _string_list(item.get("insights"), max_items=3),
                "source": item.get("source") or "",
                "parse_warnings": _string_list(item.get("parse_warnings"), max_items=3),
            }
        )
        if len(contributions) >= 10:
            break

    return {
        "roles": _roles_compact(state),
        "contributions": contributions,
        "synthesis": {
            "recommendations": _string_list(synthesis.get("recommendations"), max_items=10),
            "risks": _string_list(synthesis.get("risks"), max_items=10),
            "questions": _string_list(synthesis.get("questions"), max_items=8),
            "perspective_counts": _as_dict(synthesis.get("perspective_counts")),
        },
    }


def _latest_critique_summary(state: dict) -> dict:
    result = _latest_dict(state.get("plan_critiques"))
    critique = result.get("critique") if isinstance(result.get("critique"), dict) else {}

    return {
        "status": result.get("status") or "",
        "decision": result.get("decision") or "",
        "reason": result.get("reason") or "",
        "feedback": _string_list(result.get("feedback"), max_items=8),
        "critical_blockers": _string_list(critique.get("critical_blockers"), max_items=8),
        "ignored_must_address": _string_list(critique.get("ignored_must_address"), max_items=8),
        "ignored_risks": _string_list(critique.get("ignored_risks"), max_items=8),
        "ignored_tradeoffs": _string_list(critique.get("ignored_tradeoffs"), max_items=8),
        "recommendations": _string_list(critique.get("recommendations"), max_items=8),
    }


def _state_history_compact(state: dict) -> list[dict]:
    out: list[dict] = []
    for item in _as_list(state.get("history"))[-12:]:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "from": item.get("from") or "",
                "to": item.get("to") or "",
                "reason": _clip_string(item.get("reason"), 240),
            }
        )
    return out


def _relevant_warnings(state: dict) -> list[str]:
    warnings = _string_list(state.get("warnings"), max_items=12, max_chars=260)
    # Prefer warnings that usually matter for downstream quality.
    priority_markers = (
        "invalid_json",
        "fallback",
        "critical",
        "replan",
        "moderation",
        "expert",
        "plan",
    )
    priority = [item for item in warnings if any(marker in item.lower() for marker in priority_markers)]
    rest = [item for item in warnings if item not in priority]
    return (priority + rest)[:10]


def _brief_summary_for_planner(state: dict) -> dict:
    """Ultra-compact brief for planner to avoid context overload.

    Planner needs: must_address, key risks, key recommendations, constraints.
    Reduced from 26 fields to 14 essential fields with tighter limits.
    """
    brief = _as_dict(state.get("deliberation_brief"))
    intake = _intake_summary(state)

    return {
        "summary": _clip_string(brief.get("summary"), 400),
        "expert_recommendations": _string_list(brief.get("expert_recommendations"), max_items=5),
        "expert_risks": _string_list(brief.get("expert_risks"), max_items=5),
        "expert_questions": _string_list(brief.get("expert_questions"), max_items=4),
        "must_address": _string_list(brief.get("must_address"), max_items=8),
        "revised_recommendations": _string_list(brief.get("revised_recommendations"), max_items=4),
        "new_risks": _string_list(brief.get("new_risks"), max_items=4),
        "questions_for_group": _string_list(brief.get("questions_for_group"), max_items=4),
        "unresolved_tradeoffs": _dict_list(brief.get("unresolved_tradeoffs"), max_items=3),
        "constraints": intake.get("constraints", [])[:5],
        "success_criteria": intake.get("success_criteria", [])[:5],
        "task_goal": _clip_string(intake.get("task_goal"), 300),
        "complexity": intake.get("complexity"),
        "risk_level": intake.get("risk_level"),
        "missing_perspectives": _string_list(brief.get("missing_perspectives"), max_items=4),
    }


def build_compact_planner_context(state: dict) -> dict:
    """Context passed to develop_plan(...). Preserve legacy keys used by fallback/tests.

    CRITICAL: Planner context was 29KB causing JSON failures. Aggressively compressed.
    Target: reduce from 29KB to ~10-15KB by cutting item limits, not removing fields.
    """
    context = {
        "original_query": _clip_string(state.get("original_query"), 2000),
        "cleaned_query": _clip_string(state.get("formalized_query") or state.get("original_query"), 800),
        "query_intake": _intake_summary(state),
        "deliberation_brief": _brief_summary_for_planner(state),
        "conflict_report": {
            "agreements": _dict_list(_as_dict(state.get("conflict_report")).get("agreements"), max_items=3),
            "disagreements": _dict_list(_as_dict(state.get("conflict_report")).get("disagreements"), max_items=3),
            "unresolved_tradeoffs": _dict_list(_as_dict(state.get("conflict_report")).get("unresolved_tradeoffs"), max_items=3),
            "premature_consensus_risks": _string_list(_as_dict(state.get("conflict_report")).get("premature_consensus_risks"), max_items=3),
            "blind_spots": _string_list(_as_dict(state.get("conflict_report")).get("blind_spots"), max_items=4),
            "minority_positions": _string_list(_as_dict(state.get("conflict_report")).get("minority_positions"), max_items=2),
            "questions_for_next_round": _string_list(_as_dict(state.get("conflict_report")).get("questions_for_next_round"), max_items=3),
            "confidence": _as_dict(state.get("conflict_report")).get("confidence", 0.0),
            "parse_warnings": _string_list(_as_dict(state.get("conflict_report")).get("parse_warnings"), max_items=6),
            "source": _as_dict(state.get("conflict_report")).get("source", ""),
        },
        "balance_report": {
            "missing_perspectives": _string_list(_as_dict(state.get("balance_report")).get("missing_perspectives"), max_items=4),
            "recommended_action": _as_dict(state.get("balance_report")).get("recommended_action", "SYNTHESIZE"),
            "dominant_perspective_found": _as_dict(state.get("balance_report")).get("dominant_perspective_found", False),
        },
        "dynamic_roles_executed": _dynamic_roles_executed(state)[:5],
        "deliberation_revisions": _deliberation_revisions(state)[:4],
        "meta_decision": {
            "decision": _as_dict(state.get("meta_decision")).get("decision", "SYNTHESIZE"),
            "risks_to_address": _string_list(_as_dict(state.get("meta_decision")).get("risks_to_address"), max_items=3),
        },
        "latest_critique": _latest_critique_summary(state),
        "original_query_is_authoritative": True,
        "instruction": _AUTHORITATIVE_QUERY_INSTRUCTION,
    }

    replan_context = _as_dict(state.get("replan_context"))
    if replan_context:
        context["replan_context"] = _compact_jsonable(replan_context, max_string_chars=400, max_list_items=5)

    return context


def build_compact_critic_context(state: dict) -> dict:
    """Context kwargs passed to check_plan_and_act(...)."""
    return {
        "query_intake": _intake_summary(state),
        "deliberation_brief": _brief_summary(state),
        "conflict_report": _conflict_summary(state),
        "dynamic_roles_used": _dynamic_roles_executed(state),
        "deliberation_revisions": _deliberation_revisions(state),
        "meta_decision": _as_dict(state.get("meta_decision")),
        "state_history": _state_history_compact(state),
        "replan_context": _compact_jsonable(_as_dict(state.get("replan_context")), max_string_chars=800, max_list_items=8),
    }


def build_compact_answer_context(state: dict) -> dict:
    """Context passed to answer generation/moderation.

    run_moderated_loop still receives its legacy arguments, but those arguments
    are compact versions.
    """
    return {
        "expert_bundle": _expert_bundle_compact(state),
        "balance_report": _balance_summary(state),
        "deliberation_brief": _brief_summary(state),
        "latest_critique": _latest_critique_summary(state),
        "dynamic_roles_executed": _dynamic_roles_executed(state),
        "relevant_warnings": _relevant_warnings(state),
    }


def build_compact_meta_context(state: dict) -> dict:
    """Context passed to run_meta_moderator(...)."""
    return {
        "query": _clip_string(state.get("original_query"), 4000),
        "original_query": _clip_string(state.get("original_query"), 4000),
        "expert_bundle": _expert_bundle_compact(state),
        "balance_report": _balance_summary(state),
        "deliberation_brief": _brief_summary(state),
        "conflict_report": _conflict_summary(state),
        "plan": _compact_jsonable(_as_dict(state.get("plan")), max_string_chars=800, max_list_items=8),
        "answer": _clip_string(state.get("final_answer"), 1200),
        "moderation_reports": _compact_jsonable(_as_list(state.get("moderation_reports"))[-3:], max_string_chars=800, max_list_items=6),
        "state_history": _state_history_compact(state),
    }


def build_context_compression_report(state: dict) -> dict:
    report = dict(_as_dict(state.get("context_compression")))
    for key in (
        "planner_context_chars",
        "critic_context_chars",
        "answer_context_chars",
        "meta_context_chars",
    ):
        report.setdefault(key, 0)
    return report