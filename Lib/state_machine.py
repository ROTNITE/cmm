"""Bounded state-machine orchestration for Collective Meta-Moderation."""

from __future__ import annotations

from typing import Any

from Lib.agent_moderator import run_moderated_loop
from Lib.answer_budget import derive_answer_budget, enforce_answer_budget
from Lib.balance_analyzer import analyze_balance
from Lib.conflict_analyzer import analyze_conflicts
from Lib.critic_decision import check_plan_and_act
from Lib.deliberation import (
    apply_conflict_report_to_brief,
    apply_deliberation_round_to_brief,
    apply_meta_decision_to_brief,
    build_deliberation_brief,
)
from Lib.quality_gates import (
    can_best_effort_finalize,
    has_critical_answer_blockers,
    has_critical_plan_blockers,
    normalize_moderated_result,
    plan_blockers,
)
from Lib.context_manager import (
    build_compact_answer_context,
    build_compact_critic_context,
    build_compact_meta_context,
    build_compact_planner_context,
    build_context_compression_report,
    record_context_size,
)
from Lib.deliberation_round import (
    merge_deliberation_into_bundle,
    run_deliberation_round,
    select_high_conflict_deliberation_roles,
)
from Lib.expert_panel import run_expert_panel
from Lib.expert_rounds import merge_expert_bundles, run_targeted_expert_round, select_targeted_roles
from Lib.meta_moderator import run_meta_moderator
from Lib.plan_development import develop_plan
from Lib.query_intake import build_query_intake
from Lib.direct_answer import run_direct_answer
from Lib.parallel_utils import normalize_max_workers, normalize_parallel_mode
from Lib.role_generator import generate_dynamic_roles
from Lib.router import route_query
from Lib import state_fallbacks
from Lib.state_trace import build_result_payload


INTAKE = "INTAKE"
ROUTE = "ROUTE"
DIRECT_ANSWER = "DIRECT_ANSWER"
PANEL_ROUND_1 = "PANEL_ROUND_1"
BALANCE = "BALANCE"
CONFLICT_ANALYSIS = "CONFLICT_ANALYSIS"
META_DECISION = "META_DECISION"
DELIBERATION_ROUND = "DELIBERATION_ROUND"
CONSENSUS_CHECK = "CONSENSUS_CHECK"
REBALANCE = "REBALANCE"
META_RECHECK = "META_RECHECK"
PANEL_ROUND_EXTRA = "PANEL_ROUND_EXTRA"
PLAN = "PLAN"
PLAN_CRITIQUE = "PLAN_CRITIQUE"
ANSWER = "ANSWER"
ANSWER_MODERATION = "ANSWER_MODERATION"
REPLAN = "REPLAN"
FINALIZE = "FINALIZE"
FAILED = "FAILED"

_AUTHORITATIVE_QUERY_INSTRUCTION = (
    "Original query is authoritative. Cleaned/formalized query is helper text only. "
    "Do not ignore constraints from original_query."
)


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _has_actionable_plan(plan: Any) -> bool:
    plan = _safe_dict(plan)
    if not plan or plan.get("error"):
        return False
    if isinstance(plan.get("main_idea"), str) and plan["main_idea"].strip():
        return True
    if isinstance(plan.get("result"), str) and plan["result"].strip():
        return True
    for step in _safe_list(plan.get("steps")):
        if not isinstance(step, dict):
            continue
        if isinstance(step.get("title"), str) and step["title"].strip():
            return True
        substeps = step.get("substeps")
        if isinstance(substeps, list) and any(str(item or "").strip() for item in substeps):
            return True
    return False


def _cyrillic_text(text: str) -> bool:
    return any("а" <= char.lower() <= "я" or char.lower() == "ё" for char in str(text or ""))


def _normalize_max_deliberation_rounds(value: Any) -> int:
    try:
        count = int(value)
    except Exception:
        count = 1
    return max(1, min(2, count))


def _empty_expert_bundle() -> dict:
    return state_fallbacks.empty_expert_bundle()


def _conservative_balance_report() -> dict:
    return state_fallbacks.conservative_balance_report()


def _empty_deliberation_brief(query: str) -> dict:
    return state_fallbacks.empty_deliberation_brief(query)


def _fallback_query_intake(original_query: str, warning: str) -> dict:
    return state_fallbacks.fallback_query_intake(original_query, warning)


def _fallback_conflict_report() -> dict:
    return state_fallbacks.fallback_conflict_report()


def _fallback_meta_decision(reason: str, warning: str) -> dict:
    return state_fallbacks.fallback_meta_decision(reason, warning)


def _build_intake_context(original_query: str, query_intake: dict) -> dict:
    return {
        "query_intake": query_intake,
        "original_query": original_query,
        "cleaned_query": query_intake.get("cleaned_query") or original_query,
        "instruction": _AUTHORITATIVE_QUERY_INSTRUCTION,
    }


def _build_best_effort_answer_from_plan(state: dict, reason: str) -> str:
    """Build a conservative non-empty answer from the latest actionable plan."""
    query = str(state.get("original_query") or "").strip()
    plan = _safe_dict(state.get("plan"))
    if not query or not _has_actionable_plan(plan):
        return ""
    if has_critical_plan_blockers(state.get("plan_critiques", [])[-1] if state.get("plan_critiques") else {}):
        return ""
    if has_critical_answer_blockers(state.get("moderated_result", {})):
        return ""

    intake = _safe_dict(state.get("query_intake"))
    brief = _safe_dict(state.get("deliberation_brief"))
    budget = derive_answer_budget(query, intake)
    russian = _cyrillic_text(query)
    heading = "Краткий ответ:" if russian else "Short answer:"
    steps_label = "Что сделать:" if russian else "What to do:"
    caveat_label = "Учесть:" if russian else "Account for:"

    lines: list[str] = []
    main = plan.get("main_idea") or plan.get("result") or intake.get("task_goal") or query
    if isinstance(main, str) and main.strip():
        lines.append(f"{heading} {main.strip()}")

    steps = []
    for step in _safe_list(plan.get("steps")):
        if not isinstance(step, dict):
            continue
        title = step.get("title")
        if isinstance(title, str) and title.strip():
            steps.append(title.strip())
        if len(steps) >= (3 if budget.get("concise") else 6):
            break
    if steps:
        lines.append("")
        lines.append(steps_label)
        for index, step in enumerate(steps, 1):
            lines.append(f"{index}. {step}")

    must_address = []
    for key in ("constraints", "success_criteria"):
        for item in _safe_list(intake.get(key)):
            if isinstance(item, str) and item.strip():
                must_address.append(item.strip())
    for item in _safe_list(brief.get("must_address"))[:3]:
        if isinstance(item, str) and item.strip():
            must_address.append(item.strip())
    if must_address and not budget.get("concise"):
        lines.append("")
        lines.append(caveat_label)
        for item in must_address[:4]:
            lines.append(f"- {item}")

    answer = "\n".join(lines).strip()
    answer = enforce_answer_budget(answer, budget)
    if answer:
        state["best_effort_answer_from_plan"] = True
        state["warnings"].append(f"best_effort_answer_from_plan: {reason}")
    return answer


def _apply_answer_rescue(state: dict, reason: str) -> bool:
    answer = _build_best_effort_answer_from_plan(state, reason)
    if not answer:
        return False
    state["final_answer"] = answer
    if not state.get("answers") or _safe_list(state.get("answers"))[-1] != answer:
        state["answers"].append(answer)
    state["answer_moderation_best_effort"] = True
    moderated = normalize_moderated_result(
        {
            "final_answer": answer,
            "reports": _safe_list(_safe_dict(state.get("moderated_result")).get("reports")),
            "final_decision": "ACCEPT",
            "critical_issues": [],
            "source": "best_effort_answer_from_plan",
        }
    )
    state["moderated_result"] = moderated
    state["moderation_reports"] = _safe_list(moderated.get("reports"))
    state["answer_moderation_final_decision"] = "ACCEPT"
    state["answer_moderation_critical_issues"] = []
    return True


def _enrich_brief_with_intake(deliberation_brief: dict, query_intake: dict) -> dict:
    brief = dict(deliberation_brief) if isinstance(deliberation_brief, dict) else {}
    intake = _safe_dict(query_intake)
    for key in (
        "task_goal",
        "constraints",
        "success_criteria",
        "unknowns",
        "user_preferences",
        "complexity",
        "risk_level",
    ):
        if key in intake:
            brief[key] = intake[key]
    return brief


def _build_planner_context(state: dict) -> dict:
    context = build_compact_planner_context(state)
    return record_context_size(state, "planner", context)


def _flatten_meta_field(meta_decisions: list | None, key: str) -> list[str]:
    out: list[str] = []
    for decision in _safe_list(meta_decisions):
        if not isinstance(decision, dict):
            continue
        for item in _safe_list(decision.get(key)):
            if isinstance(item, str):
                text = item.strip()
            else:
                continue
            if text and text not in out:
                out.append(text)
    return out


def _flatten_conflict_field(conflict_reports: list | None, key: str) -> list:
    out: list = []
    for report in _safe_list(conflict_reports):
        if not isinstance(report, dict):
            continue
        value = report.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if item not in out:
                out.append(item)
    return out


def _flatten_plan_critique_field(plan_critiques: list | None, key: str) -> list[str]:
    out: list[str] = []
    for item in _safe_list(plan_critiques):
        if not isinstance(item, dict):
            continue
        critique = item.get("critique") if isinstance(item.get("critique"), dict) else item
        for value in _safe_list(critique.get(key)):
            if not isinstance(value, str):
                continue
            text = value.strip()
            if text and text not in out:
                out.append(text)
    return out


def _flatten_plan_critique_decisions(plan_critiques: list | None) -> list[str]:
    out: list[str] = []
    for item in _safe_list(plan_critiques):
        if not isinstance(item, dict):
            continue
        decision = item.get("decision")
        if not decision:
            status = str(item.get("status") or "")
            decision = {"ready": "ACCEPT", "needs_revision": "REVISE", "rejected": "REJECT"}.get(status)
        if isinstance(decision, str) and decision and decision not in out:
            out.append(decision)
    return out


def _flatten_deliberation_revisions(deliberation_rounds: list | None) -> list[dict]:
    out: list[dict] = []
    for bundle in _safe_list(deliberation_rounds):
        if not isinstance(bundle, dict):
            continue
        for response in _safe_list(bundle.get("responses")):
            if not isinstance(response, dict):
                continue
            revision = {
                "role_key": response.get("role_key") or "unknown",
                "revised_recommendations": _safe_list(response.get("revised_recommendations")),
                "new_risks": _safe_list(response.get("new_risks")),
                "disagreements": _safe_list(response.get("disagreements")),
            }
            if revision not in out:
                out.append(revision)
    return out


def _sanitize_dynamic_role_report(report: dict) -> dict:
    if not isinstance(report, dict):
        return {
            "role_views": [],
            "rejected_suggestions": [],
            "warnings": ["invalid_dynamic_role_report"],
            "source": "fallback",
            "round": "",
            "model_called": False,
            "json_attempts": 0,
        }
    return {
        "role_views": _safe_list(report.get("role_views")),
        "rejected_suggestions": _safe_list(report.get("rejected_suggestions")),
        "warnings": _safe_list(report.get("warnings")),
        "source": report.get("source") or "fallback",
        "round": report.get("round") or "",
        "model_called": bool(report.get("model_called")),
        "json_attempts": int(report.get("json_attempts") or 0),
    }


def _flatten_dynamic_roles_generated(dynamic_role_reports: list | None) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for report in _safe_list(dynamic_role_reports):
        if not isinstance(report, dict):
            continue
        round_name = str(report.get("round") or "")
        for view in _safe_list(report.get("role_views")):
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


def _flatten_dynamic_roles_rejected(dynamic_role_reports: list | None) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for report in _safe_list(dynamic_role_reports):
        if not isinstance(report, dict):
            continue
        round_name = str(report.get("round") or "")
        for item in _safe_list(report.get("rejected_suggestions")):
            if not isinstance(item, dict):
                continue
            raw_key = str(item.get("raw_key") or item.get("key") or "").strip()
            reason = str(item.get("reason") or "").strip()
            marker = (round_name, raw_key, reason)
            if marker in seen:
                continue
            seen.add(marker)
            rejected = dict(item)
            rejected["round"] = round_name
            out.append(rejected)
    return out


def _flatten_dynamic_roles_executed(expert_rounds: list | None, dynamic_role_reports: list | None) -> list[dict]:
    generated_by_key: dict[str, dict] = {}
    for role in _flatten_dynamic_roles_generated(dynamic_role_reports):
        key = role.get("key")
        if isinstance(key, str) and key and key not in generated_by_key:
            generated_by_key[key] = role

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for index, bundle in enumerate(_safe_list(expert_rounds)):
        if not isinstance(bundle, dict):
            continue
        round_name = "initial" if index == 0 else "extra"
        for view in _safe_list(bundle.get("roles")):
            if not isinstance(view, dict):
                continue
            key = str(view.get("key") or "").strip()
            if not key:
                continue
            is_dynamic = bool(view.get("dynamic")) or key in generated_by_key
            if not is_dynamic:
                continue
            marker = (round_name, key)
            if marker in seen:
                continue
            seen.add(marker)
            generated = generated_by_key.get(key, {})
            out.append(
                {
                    "key": key,
                    "name": view.get("name") or generated.get("name") or "",
                    "perspective_tag": view.get("perspective_tag") or generated.get("perspective_tag") or "",
                    "why_needed": view.get("why_needed") or generated.get("why_needed") or "",
                    "round": round_name,
                }
            )
    return out


def _flatten_dynamic_roles_used(dynamic_role_reports: list | None) -> list[dict]:
    """Backward-compatible generated-role flattener for older internal tests.

    Trace/report generation now uses ``_flatten_dynamic_roles_executed`` for the
    public ``dynamic_roles_used`` compatibility field.
    """
    return _flatten_dynamic_roles_generated(dynamic_role_reports)


def _round_name_for_bundle(index: int) -> str:
    return "initial" if index == 0 else "extra"


def _roles_used_unique(expert_rounds: list | None, raw_roles: list | None) -> list[dict]:
    """Return a compact, deduplicated human/eval view of roles used."""
    by_key: dict[str, dict] = {}

    def add_role(view: dict, round_name: str) -> None:
        if not isinstance(view, dict):
            return
        key = str(view.get("key") or "").strip()
        if not key:
            return
        item = by_key.setdefault(
            key,
            {
                "key": key,
                "name": view.get("name") or "",
                "perspective_tag": view.get("perspective_tag") or "",
                "rounds": [],
                "dynamic": False,
            },
        )
        if not item.get("name") and view.get("name"):
            item["name"] = view.get("name")
        if not item.get("perspective_tag") and view.get("perspective_tag"):
            item["perspective_tag"] = view.get("perspective_tag")
        if round_name not in item["rounds"]:
            item["rounds"].append(round_name)
        item["dynamic"] = bool(item.get("dynamic") or view.get("dynamic"))

    rounds = _safe_list(expert_rounds)
    for index, bundle in enumerate(rounds):
        if not isinstance(bundle, dict):
            continue
        for view in _safe_list(bundle.get("roles")):
            add_role(view, _round_name_for_bundle(index))

    if not by_key:
        for view in _safe_list(raw_roles):
            add_role(view, "unknown")

    return list(by_key.values())


def _record_dynamic_role_report(state: dict, report: dict, round_name: str) -> list:
    safe_report = dict(report) if isinstance(report, dict) else {
        "roles": [],
        "role_views": [],
        "warnings": ["invalid_dynamic_role_report"],
        "source": "fallback",
    }
    safe_report["roles"] = list(_safe_list(safe_report.get("roles")))
    safe_report["role_views"] = list(_safe_list(safe_report.get("role_views")))
    safe_report["rejected_suggestions"] = list(_safe_list(safe_report.get("rejected_suggestions")))
    safe_report["warnings"] = list(_safe_list(safe_report.get("warnings")))
    safe_report["round"] = round_name
    state.setdefault("dynamic_role_reports", []).append(safe_report)
    for warning in _safe_list(safe_report.get("warnings")):
        if isinstance(warning, str):
            state.setdefault("warnings", []).append(f"dynamic_roles_{round_name}: {warning}")
    return _safe_list(safe_report.get("roles"))


def _extract_final_confidence(moderation_reports: list) -> float | None:
    if not moderation_reports:
        return None
    last_report = moderation_reports[-1]
    if not isinstance(last_report, dict):
        return None
    score = last_report.get("avg_score")
    if not isinstance(score, (int, float)):
        return None
    return float(score) / 10


def _has_warning(items: list | None, marker: str) -> bool:
    return any(marker in str(item) for item in _safe_list(items))


def _collect_json_health(trace_report: dict) -> dict:
    expert_contributions: list[dict] = []
    for bundle in _safe_list(trace_report.get("expert_rounds")):
        if isinstance(bundle, dict):
            expert_contributions.extend(
                item for item in _safe_list(bundle.get("contributions")) if isinstance(item, dict)
            )
    expert_invalid = [
        item
        for item in expert_contributions
        if item.get("source") == "fallback"
        or "invalid_json_from_model" in _safe_list(item.get("risks"))
        or _has_warning(item.get("parse_warnings"), "expert_json_parse_failed")
    ]
    expert_success = [
        item
        for item in expert_contributions
        if item.get("source") == "model" and item not in expert_invalid
    ]

    plans = _safe_list(trace_report.get("plans"))
    latest_plan = plans[-1] if plans and isinstance(plans[-1], dict) else _safe_dict(trace_report.get("plan"))
    moderation_reports = _safe_list(trace_report.get("moderation_reports"))
    conflict_reports = _safe_list(trace_report.get("conflict_reports"))
    meta_decisions = (
            _safe_list(trace_report.get("meta_moderation_decisions"))
            + _safe_list(trace_report.get("meta_recheck_decisions"))
    )

    return {
        "expert_agent": {
            "calls": len(expert_contributions),
            "success": len(expert_success),
            "fallbacks": len(expert_invalid),
            "retry_attempts": sum(max(0, int(item.get("json_attempts") or 0) - 1) for item in expert_contributions),
            "invalid_json_count": len(expert_invalid),
        },
        "planner": {
            "called": bool(latest_plan),
            "success": latest_plan.get("raw_format") == "json" or latest_plan.get("source") == "model",
            "raw_format": latest_plan.get("raw_format") or "",
            "source": latest_plan.get("source") or "",
            "json_attempts": int(latest_plan.get("json_attempts") or 0),
        },
        "moderator": {
            "invalid_json_count": sum(
                1 for item in moderation_reports if _has_warning(item.get("parse_warnings"), "moderation_json_parse_failed")
            ),
            "retry_attempts": sum(max(0, int(item.get("json_attempts") or 0) - 1) for item in moderation_reports if isinstance(item, dict)),
            "final_decision": trace_report.get("answer_moderation_final_decision") or "",
        },
        "conflict_analyzer": {
            "invalid_json_count": sum(
                1 for item in conflict_reports if _has_warning(item.get("parse_warnings"), "conflict_model_invalid_json")
            ),
            "retry_attempts": sum(max(0, int(item.get("json_attempts") or 0) - 1) for item in conflict_reports if isinstance(item, dict)),
        },
        "meta_moderator": {
            "invalid_json_count": sum(
                1 for item in meta_decisions if _has_warning(item.get("parse_warnings"), "meta_moderator_model_invalid_json")
            ),
            "retry_attempts": sum(max(0, int(item.get("json_attempts") or 0) - 1) for item in meta_decisions if isinstance(item, dict)),
        },
    }


def _int_attempts(value: Any) -> int:
    if isinstance(value, dict):
        attempts = value.get("json_attempts")
        if isinstance(attempts, int):
            return max(0, attempts)
        if value.get("source") == "model":
            return 1
    return 0


def _estimate_call_count(trace_report: dict) -> int:
    """Approximate model-call attempts from visible stage diagnostics."""
    total = _int_attempts(_safe_dict(trace_report.get("query_intake")))

    for report in _safe_list(trace_report.get("dynamic_role_reports")):
        total += _int_attempts(report)
    for bundle in _safe_list(trace_report.get("expert_rounds")):
        if not isinstance(bundle, dict):
            continue
        for contribution in _safe_list(bundle.get("contributions")):
            total += _int_attempts(contribution)
    for item in _safe_list(trace_report.get("conflict_reports")):
        total += _int_attempts(item)
    for item in _safe_list(trace_report.get("meta_moderation_decisions")):
        total += _int_attempts(item)
    for item in _safe_list(trace_report.get("plans")):
        total += _int_attempts(item)
    for item in _safe_list(trace_report.get("plan_critiques")):
        total += _int_attempts(item)
        total += _int_attempts(_safe_dict(item.get("critique")) if isinstance(item, dict) else {})
    for item in _safe_list(trace_report.get("moderation_reports")):
        total += _int_attempts(item)

    states = [item.get("from") for item in _safe_list(trace_report.get("state_history")) if isinstance(item, dict)]
    if DIRECT_ANSWER in states and total == _int_attempts(_safe_dict(trace_report.get("query_intake"))):
        total += 1
    if ANSWER in states:
        total += 1 + int(trace_report.get("revision_count") or 0)

    return int(total)


def _deliberation_needed(conflict_report: dict | None, meta_decision: dict | None) -> bool:
    conflict = _safe_dict(conflict_report)
    if conflict.get("source") == "fallback":
        return False
    meta = _safe_dict(meta_decision)
    if meta.get("decision") == "DEEPEN":
        return True
    for key in ("disagreements", "unresolved_tradeoffs", "premature_consensus_risks", "blind_spots"):
        if _safe_list(conflict.get(key)):
            return True
    return False


def _targeted_followup_still_useful(
    *,
    meta_decision: dict | None,
    balance_report: dict | None,
    deliberation_brief: dict | None,
    conflict_report: dict | None,
) -> bool:
    meta = _safe_dict(meta_decision)
    if meta.get("decision") not in {"DEEPEN", "ADD_EXPERT"}:
        return False
    balance = _safe_dict(balance_report)
    brief = _safe_dict(deliberation_brief)
    conflict = _safe_dict(conflict_report)
    return any(
        _safe_list(value)
        for value in (
            balance.get("missing_perspectives"),
            meta.get("missing_perspectives"),
            meta.get("conflicts_to_resolve"),
            meta.get("risks_to_address"),
            meta.get("questions_to_answer"),
            brief.get("expert_questions"),
            conflict.get("disagreements"),
            conflict.get("unresolved_tradeoffs"),
            conflict.get("premature_consensus_risks"),
            conflict.get("blind_spots"),
        )
    )

_CRITICAL_META_MARKERS = (
    "critical",
    "severe",
    "high severity",
    "safety",
    "security",
    "privacy",
    "legal",
    "compliance",
    "harm",
    "unsafe",
    "liability",
    "medical",
    "financial",
    "высок",
    "критическ",
    "безопас",
    "приват",
    "персональн",
    "закон",
    "юрид",
    "вред",
)


def _text_blob(value: Any) -> str:
    try:
        import json

        return json.dumps(value, ensure_ascii=False, sort_keys=True).lower()
    except Exception:
        return str(value or "").lower()


def _has_critical_marker(value: Any) -> bool:
    text = _text_blob(value)
    return any(marker in text for marker in _CRITICAL_META_MARKERS)


def _conflicts_cleared(conflict_report: dict | None, balance_report: dict | None = None) -> bool:
    """Return True when the rebalance pass leaves no process-level issues."""
    conflict = _safe_dict(conflict_report)
    balance = _safe_dict(balance_report)

    if conflict.get("source") == "fallback":
        return False

    conflict_keys = (
        "disagreements",
        "unresolved_tradeoffs",
        "premature_consensus_risks",
        "blind_spots",
        "questions_for_next_round",
    )
    if any(_safe_list(conflict.get(key)) for key in conflict_keys):
        return False

    if _safe_list(balance.get("missing_perspectives")):
        return False
    if _safe_list(balance.get("blind_spots")):
        return False
    if balance.get("recommended_action") in {"ADD_EXPERT", "DEEPEN"}:
        return False

    return True


def _new_or_critical_blind_spots_after_rebalance(state: dict) -> list[str]:
    """Find blind spots that justify ADD_EXPERT after REBALANCE.

    Prefer newly introduced blind spots, but still return critical existing ones
    if they remain after rebalance.
    """
    previous = _safe_dict(state.get("pre_rebalance_conflict_report"))
    current_conflict = _safe_dict(state.get("conflict_report"))
    current_balance = _safe_dict(state.get("balance_report"))

    previous_spots = {str(item).strip() for item in _safe_list(previous.get("blind_spots")) if str(item).strip()}

    current_spots: list[str] = []
    for item in _safe_list(current_conflict.get("blind_spots")):
        text = str(item).strip()
        if text:
            current_spots.append(text)
    for item in _safe_list(current_balance.get("blind_spots")):
        text = str(item).strip()
        if text:
            current_spots.append(text)

    missing = [str(item).strip() for item in _safe_list(current_balance.get("missing_perspectives")) if str(item).strip()]
    if missing:
        current_spots.extend(f"Missing perspective after rebalance: {item}" for item in missing)

    new_spots = [item for item in current_spots if item not in previous_spots]
    critical_spots = [item for item in current_spots if _has_critical_marker(item)]

    out: list[str] = []
    for item in new_spots + critical_spots:
        if item and item not in out:
            out.append(item)
    return out[:8]


def _has_high_severity_tradeoff(conflict_report: dict | None) -> bool:
    conflict = _safe_dict(conflict_report)

    for item in _safe_list(conflict.get("unresolved_tradeoffs")):
        if isinstance(item, dict):
            severity = str(item.get("severity") or "").lower()
            if severity == "high":
                return True
            if _has_critical_marker(item):
                return True
        elif _has_critical_marker(item):
            return True

    for item in _safe_list(conflict.get("disagreements")):
        if isinstance(item, dict):
            severity = str(item.get("severity") or "").lower()
            if severity == "high":
                return True
            if _has_critical_marker(item):
                return True
        elif _has_critical_marker(item):
            return True

    return False


def _high_conflict_role_keys(state: dict) -> list[str]:
    roles = select_high_conflict_deliberation_roles(
        state.get("expert_bundle", {}),
        state.get("conflict_report", {}),
        max_roles=4,
    )
    return [role.key for role in roles]


def _summarize_position_changes(deliberation_bundle: dict, round_number: int) -> list[dict]:
    changes: list[dict] = []
    for response in _safe_list(_safe_dict(deliberation_bundle).get("responses")):
        if not isinstance(response, dict):
            continue
        revised = _safe_list(response.get("revised_recommendations"))
        risks = _safe_list(response.get("new_risks"))
        disagreements = _safe_list(response.get("disagreements"))
        confidence_change = response.get("confidence_change")
        try:
            confidence_value = float(confidence_change)
        except Exception:
            confidence_value = 0.0
        changes.append(
            {
                "round": round_number,
                "role_key": response.get("role_key") or "unknown",
                "confidence_change": confidence_value,
                "revised_recommendations_count": len(revised),
                "new_risks_count": len(risks),
                "disagreements_count": len(disagreements),
                "position_changed": bool(revised or risks or disagreements or confidence_value != 0.0),
            }
        )
    return changes


def _run_meta_decision_with_context(state: dict, *, phase: str) -> dict:
    """Run meta moderator with compact context and stable fallback."""
    try:
        meta_context = build_compact_meta_context(state)
        context_name = "meta" if phase == "initial" else "meta_recheck"
        record_context_size(state, context_name, meta_context)

        meta_decision = run_meta_moderator(
            query=meta_context.get("query") or state["original_query"],
            expert_bundle=meta_context.get("expert_bundle", {}),
            balance_report=meta_context.get("balance_report", {}),
            deliberation_brief=meta_context.get("deliberation_brief", {}),
            plan=meta_context.get("plan", {}),
            answer=meta_context.get("answer", ""),
            moderation_reports=meta_context.get("moderation_reports", []),
            conflict_report=meta_context.get("conflict_report", {}),
            model=state["model"],
        )
        if not isinstance(meta_decision, dict):
            state["warnings"].append(f"{phase}_meta_moderator_invalid; continuing without process decision")
            meta_decision = _fallback_meta_decision(
                "Meta moderator returned invalid output.",
                f"{phase}_meta_moderator_invalid",
            )
    except Exception as exc:
        state["warnings"].append(f"{phase}_meta_moderator_failed; continuing with synthesis: {exc}")
        meta_decision = _fallback_meta_decision(
            "Meta moderator failed; proceed with existing deliberation brief.",
            f"{phase}_meta_moderator_failed",
        )

    state["meta_decision"] = meta_decision

    if phase == "recheck":
        state.setdefault("meta_recheck_decisions", []).append(meta_decision)
    else:
        state.setdefault("meta_decisions", []).append(meta_decision)

    return meta_decision

def init_cmm_state(
    query: str,
    *,
    max_iters: int = 2,
    model: str = "deepseek-chat",
    max_transitions: int = 40,
    route_mode: str = "AUTO",
    parallel_mode: str = "SEQUENTIAL",
    max_workers: int | None = None,
    max_deliberation_rounds: int = 1,
) -> dict:
    original_query = "" if query is None else str(query)
    normalized_parallel_mode = normalize_parallel_mode(parallel_mode)
    return {
        "original_query": original_query,
        "model": model,
        "max_iters": max(0, int(max_iters)),
        "max_transitions": max(1, int(max_transitions)),
        "current_state": INTAKE,
        "transition_count": 0,
        "iteration_count": 0,
        "query_intake": {},
        "formalized_query": original_query,
        "intake_context": {},
        "route_mode": str(route_mode or "AUTO").upper(),
        "parallel_mode": normalized_parallel_mode,
        "max_workers": normalize_max_workers(max_workers, 4) if normalized_parallel_mode == "THREADS" else None,
        "parallelized_stages": [],
        "router_decision": {},
        "cmm_mode": "",
        "routing_warnings": [],
        "expert_bundle": _empty_expert_bundle(),
        "expert_rounds": [],
        "dynamic_roles": [],
        "dynamic_role_reports": [],
        "balance_report": {},
        "balance_reports": [],
        "conflict_report": {},
        "conflict_reports": [],
        "deliberation_brief": {},
        "deliberation_rounds": [],
        "deliberation_round_count": 0,
        "max_deliberation_rounds": _normalize_max_deliberation_rounds(max_deliberation_rounds),
        "consensus_checks": [],
        "deliberation_position_changes": [],
        "meta_decisions": [],
        "meta_decision": {},
        "meta_recheck_count": 0,
        "max_meta_rechecks": 1,
        "meta_recheck_decisions": [],
        "pre_rebalance_conflict_report": {},
        "plans": [],
        "plan": {},
        "plan_critiques": [],
        "plan_critique": {},
        "answers": [],
        "moderated_result": {},
        "moderation_reports": [],
        "answer_moderation_final_decision": "",
        "answer_moderation_critical_issues": [],
        "answer_moderation_revision_count": 0,
        "quality_gate_decisions": [],
        "context_compression": {},
        "answer_moderation_best_effort": False,
        "best_effort_answer_from_plan": False,
        "warnings": [],
        "errors": [],
        "history": [],
        "final_answer": "",
        "deliberation_round_done": False,
        "extra_panel_done": False,
        "replan_context": {},
    }


def transition(state: dict, next_state: str, reason: str) -> None:
    old_state = state.get("current_state") or INTAKE
    state.setdefault("history", []).append({"from": old_state, "to": next_state, "reason": reason})
    state["current_state"] = next_state
    state["transition_count"] = int(state.get("transition_count", 0)) + 1


def handle_intake(state: dict) -> tuple[str, str]:
    original_query = state["original_query"]
    model = state["model"]
    try:
        query_intake = build_query_intake(original_query, model=model)
        if not isinstance(query_intake, dict):
            state["warnings"].append("query_intake_invalid; using fallback query intake")
            query_intake = _fallback_query_intake(original_query, "query_intake_invalid")
    except Exception as exc:
        state["warnings"].append(f"query_intake_failed; using fallback query intake: {exc}")
        query_intake = _fallback_query_intake(original_query, "query_intake_failed")

    state["query_intake"] = query_intake
    for warning in _safe_list(query_intake.get("parse_warnings")):
        if isinstance(warning, str):
            state["warnings"].append(f"query_intake: {warning}")
    formalized_query = query_intake.get("cleaned_query") if isinstance(query_intake.get("cleaned_query"), str) else ""
    state["formalized_query"] = formalized_query.strip() or original_query
    state["intake_context"] = _build_intake_context(original_query, query_intake)
    return ROUTE, "query intake complete"


def _forced_router_decision(mode: str) -> dict:
    cost = {"DIRECT": "S", "LIGHT_CMM": "M", "FULL_CMM": "L"}[mode]
    return {
        "mode": mode,
        "reason": f"Route mode forced to {mode}.",
        "complexity": {"DIRECT": "low", "LIGHT_CMM": "medium", "FULL_CMM": "high"}[mode],
        "needs_expert_panel": mode in {"LIGHT_CMM", "FULL_CMM"},
        "needs_second_round": mode == "FULL_CMM",
        "estimated_cost_class": cost,
        "signals": {"forced": True},
        "warnings": [],
    }


def handle_route(state: dict) -> tuple[str, str]:
    requested = str(state.get("route_mode") or "AUTO").upper()
    valid_modes = {"AUTO", "DIRECT", "LIGHT_CMM", "FULL_CMM"}
    if requested not in valid_modes:
        state["warnings"].append(f"invalid_route_mode_{requested}; falling back to AUTO")
        requested = "AUTO"
    try:
        router_decision = (
            _forced_router_decision(requested)
            if requested in {"DIRECT", "LIGHT_CMM", "FULL_CMM"}
            else route_query(state.get("query_intake", {}), original_query=state.get("original_query", ""))
        )
        if not isinstance(router_decision, dict):
            raise ValueError("invalid router decision")
    except Exception as exc:
        state["warnings"].append(f"router_failed; falling back to FULL_CMM: {exc}")
        router_decision = _forced_router_decision("FULL_CMM")
        router_decision["warnings"] = ["router_failed"]

    mode = str(router_decision.get("mode") or "FULL_CMM").upper()
    if mode not in {"DIRECT", "LIGHT_CMM", "FULL_CMM"}:
        state["warnings"].append(f"router_invalid_mode_{mode}; falling back to FULL_CMM")
        router_decision = _forced_router_decision("FULL_CMM")
        mode = "FULL_CMM"
    state["router_decision"] = router_decision
    state["cmm_mode"] = mode
    state["routing_warnings"] = _safe_list(router_decision.get("warnings"))
    for warning in state["routing_warnings"]:
        if isinstance(warning, str):
            state["warnings"].append(f"router: {warning}")

    if mode == "DIRECT":
        return DIRECT_ANSWER, "router selected direct answer"
    return PANEL_ROUND_1, f"router selected {mode}"


def handle_direct_answer(state: dict) -> tuple[str, str]:
    try:
        result = run_direct_answer(
            state["original_query"],
            query_intake=state.get("query_intake", {}),
            model=state["model"],
        )
        if not isinstance(result, dict):
            raise ValueError("invalid direct answer result")
    except Exception as exc:
        state["warnings"].append(f"direct_answer_failed: {exc}")
        state["errors"].append("direct_answer_failed")
        return FAILED, "direct answer generation failed"

    for warning in _safe_list(result.get("parse_warnings")):
        if isinstance(warning, str):
            state["warnings"].append(f"direct_answer: {warning}")
    final_answer = result.get("final_answer")
    if not isinstance(final_answer, str) or not final_answer.strip():
        state["errors"].append("direct_answer_empty")
        return FAILED, "direct answer returned empty final answer"
    state["final_answer"] = final_answer.strip()
    state["answers"].append(state["final_answer"])
    state["moderated_result"] = {
        "final_answer": state["final_answer"],
        "reports": [],
        "trace": {"direct_answer": True, "source": result.get("source") or "unknown"},
    }
    return FINALIZE, "direct answer finalized"


def handle_panel_round_1(state: dict) -> tuple[str, str]:
    initial_dynamic_roles: list = []
    try:
        dynamic_report = generate_dynamic_roles(
            query_intake=state.get("query_intake", {}),
            existing_roles=[],
            max_roles=2,
            model=state["model"],
        )
        initial_dynamic_roles = _record_dynamic_role_report(state, dynamic_report, "initial")
        state["dynamic_roles"] = _safe_list(state.get("dynamic_roles")) + initial_dynamic_roles
    except Exception as exc:
        state["warnings"].append(f"dynamic_roles_initial_failed; continuing_with_base_roles: {exc}")

    panel_context = dict(state.get("intake_context", {}))
    if state.get("dynamic_role_reports"):
        panel_context["dynamic_role_views"] = state["dynamic_role_reports"][-1].get("role_views", [])

    try:
        execution_kwargs = {"model": state["model"]}
        if state.get("parallel_mode") == "THREADS":
            execution_kwargs["execution_mode"] = "THREADS"
            execution_kwargs["max_workers"] = state.get("max_workers")
        expert_bundle = run_expert_panel(
            state["original_query"],
            context=panel_context,
            max_roles=max(5, 5 + len(initial_dynamic_roles)),
            dynamic_roles=initial_dynamic_roles,
            **execution_kwargs,
        )
        if not isinstance(expert_bundle, dict):
            state["warnings"].append("expert_panel_invalid; using empty expert bundle")
            expert_bundle = _empty_expert_bundle()
    except Exception as exc:
        state["warnings"].append(f"expert_panel_failed; using empty expert bundle: {exc}")
        expert_bundle = _empty_expert_bundle()

    # Check for degraded expert layer: model calls failed but deterministic
    # role-aware fallback may still provide usable expert evidence.
    contributions = _safe_list(expert_bundle.get("contributions"))
    valid_contributions = [c for c in contributions if isinstance(c, dict) and c.get("source") == "model"]
    fallback_contributions = [
        c for c in contributions
        if isinstance(c, dict) and c.get("source") in {"fallback", "rules_fallback", "rules_based_fallback"}
    ]

    if contributions and len(valid_contributions) == 0 and len(fallback_contributions) == len(contributions):
        state["warnings"].append(
            f"expert_panel_degraded: {len(fallback_contributions)}/{len(contributions)} experts used fallback contributions"
        )
        state["expert_panel_degraded"] = True
        empty_fallbacks = [
            c for c in fallback_contributions
            if not (_safe_list(c.get("recommendations")) or _safe_list(c.get("risks")) or _safe_list(c.get("questions")))
        ]
        if empty_fallbacks:
            state["warnings"].append("generating_role_aware_rules_expert_fallback")
            expert_bundle = state_fallbacks.rules_based_expert_bundle(
                state["original_query"],
                context={
                    "query_intake": state.get("query_intake", {}),
                    "roles": expert_bundle.get("roles", []),
                    "warnings": state.get("warnings", []),
                },
                roles=expert_bundle.get("roles", []),
            )
        # Mark CMM mode as degraded
        original_mode = state.get("cmm_mode", "")
        if original_mode and not original_mode.endswith("_DEGRADED"):
            state["cmm_mode"] = f"{original_mode}_DEGRADED"
            state["warnings"].append(f"cmm_mode_degraded: {original_mode} -> {state['cmm_mode']}")

    state["expert_bundle"] = expert_bundle
    state["expert_rounds"].append(expert_bundle)
    if state.get("parallel_mode") == "THREADS":
        state.setdefault("parallelized_stages", []).append("PANEL_ROUND_1")
    return BALANCE, "initial expert panel complete"


def _run_balance(state: dict, warning_prefix: str) -> None:
    try:
        balance_report = analyze_balance(
            state.get("expert_bundle", {}),
            query_intake=state.get("query_intake", {}),
            conflict_report=state.get("conflict_report", {}),
            dynamic_roles_used=_flatten_dynamic_roles_executed(
                state.get("expert_rounds"),
                state.get("dynamic_role_reports"),
            ),
            deliberation_revisions=_flatten_deliberation_revisions(state.get("deliberation_rounds")),
        )
        if not isinstance(balance_report, dict):
            state["warnings"].append(f"{warning_prefix}_invalid; using conservative balance report")
            balance_report = _conservative_balance_report()
    except Exception as exc:
        state["warnings"].append(f"{warning_prefix}_failed; using conservative balance report: {exc}")
        balance_report = _conservative_balance_report()
    state["balance_report"] = balance_report
    state["balance_reports"].append(balance_report)


def _rebuild_brief(state: dict, warning_prefix: str) -> None:
    try:
        deliberation_brief = build_deliberation_brief(
            query=state["original_query"],
            expert_bundle=state.get("expert_bundle", {}),
            balance_report=state.get("balance_report", {}),
        )
        if not isinstance(deliberation_brief, dict):
            state["warnings"].append(f"{warning_prefix}_invalid; using empty deliberation brief")
            deliberation_brief = _empty_deliberation_brief(state["original_query"])
        deliberation_brief = _enrich_brief_with_intake(deliberation_brief, state.get("query_intake", {}))
    except Exception as exc:
        state["warnings"].append(f"{warning_prefix}_failed; using empty deliberation brief: {exc}")
        deliberation_brief = _enrich_brief_with_intake(
            _empty_deliberation_brief(state["original_query"]),
            state.get("query_intake", {}),
        )

    if state.get("deliberation_rounds"):
        deliberation_brief = apply_deliberation_round_to_brief(deliberation_brief, state["deliberation_rounds"][-1])
    state["deliberation_brief"] = deliberation_brief


def handle_balance(state: dict) -> tuple[str, str]:
    _run_balance(state, "balance_report")
    _rebuild_brief(state, "deliberation_brief")
    if state.get("cmm_mode") == "LIGHT_CMM":
        return PLAN, "light CMM balance and brief complete"
    return CONFLICT_ANALYSIS, "balance and brief complete"


def _run_conflict_analysis(state: dict, warning_prefix: str) -> None:
    try:
        conflict_report = analyze_conflicts(
            state.get("query_intake", {}),
            state.get("expert_bundle", {}),
            state.get("deliberation_brief", {}),
            model=state["model"],
        )
        if not isinstance(conflict_report, dict):
            raise ValueError("invalid conflict report")
    except Exception as exc:
        state["warnings"].append(f"{warning_prefix}_failed; continuing_with_empty_conflict_report: {exc}")
        conflict_report = _fallback_conflict_report()
    state["conflict_report"] = conflict_report
    state["conflict_reports"].append(conflict_report)
    state["deliberation_brief"] = apply_conflict_report_to_brief(
        state.get("deliberation_brief", {}),
        conflict_report,
    )


def handle_conflict_analysis(state: dict) -> tuple[str, str]:
    _run_conflict_analysis(state, "conflict_analysis")
    return META_DECISION, "conflict analysis complete"


def handle_meta_decision(state: dict) -> tuple[str, str]:
    meta_decision = _run_meta_decision_with_context(state, phase="initial")
    decision = str(meta_decision.get("decision") or "SYNTHESIZE").upper()

    if decision == "FINALIZE":
        if not state.get("final_answer"):
            state["warnings"].append("meta_finalize_before_answer")
        return FINALIZE, "meta moderator requested finalize"

    if decision == "REPLAN":
        return PLAN, "meta moderator requested replan"

    if decision == "DEEPEN":
        if not state.get("deliberation_round_done") and _deliberation_needed(
            state.get("conflict_report"),
            meta_decision,
        ):
            return DELIBERATION_ROUND, "meta moderator requested deeper deliberation"

        if not state.get("extra_panel_done") and _targeted_followup_still_useful(
            meta_decision=meta_decision,
            balance_report=state.get("balance_report"),
            deliberation_brief=state.get("deliberation_brief"),
            conflict_report=state.get("conflict_report"),
        ):
            return PANEL_ROUND_EXTRA, "meta moderator requested targeted follow-up"

    if decision == "ADD_EXPERT":
        if not state.get("extra_panel_done") and _targeted_followup_still_useful(
            meta_decision=meta_decision,
            balance_report=state.get("balance_report"),
            deliberation_brief=state.get("deliberation_brief"),
            conflict_report=state.get("conflict_report"),
        ):
            return PANEL_ROUND_EXTRA, "meta moderator requested additional expert"

    return PLAN, "ready to plan"


def handle_deliberation_round(state: dict) -> tuple[str, str]:
    current_count = int(state.get("deliberation_round_count", 0))
    max_rounds = _normalize_max_deliberation_rounds(state.get("max_deliberation_rounds", 1))
    if current_count >= max_rounds:
        state["deliberation_round_done"] = True
        return CONSENSUS_CHECK, "deliberation already completed"
    round_number = current_count + 1
    try:
        deliberation_bundle = run_deliberation_round(
            query=state["original_query"],
            query_intake=state.get("query_intake", {}),
            expert_bundle=state.get("expert_bundle", {}),
            deliberation_brief=state.get("deliberation_brief", {}),
            conflict_report=state.get("conflict_report", {}),
            meta_decision=state.get("meta_decision", {}),
            model=state["model"],
            conflicting_only=round_number > 1,
        )
        if not isinstance(deliberation_bundle, dict):
            raise ValueError("invalid deliberation round bundle")
        deliberation_bundle["round"] = round_number
        state["deliberation_rounds"].append(deliberation_bundle)
        state["deliberation_position_changes"].extend(
            _summarize_position_changes(deliberation_bundle, round_number)
        )
        expert_bundle = merge_deliberation_into_bundle(state.get("expert_bundle", {}), deliberation_bundle)
        if not isinstance(expert_bundle, dict):
            raise ValueError("invalid deliberation merge result")
        state["expert_bundle"] = expert_bundle
        state["deliberation_round_count"] = round_number
    except Exception as exc:
        state["warnings"].append(f"deliberation_round_failed; continuing_without_deliberation: {exc}")
        state["deliberation_round_count"] = round_number
    return CONSENSUS_CHECK, "deliberation round handled"


def handle_consensus_check(state: dict) -> tuple[str, str]:
    """Bounded check between deliberation rounds and meta recheck."""
    _run_balance(state, "consensus_balance")
    _rebuild_brief(state, "consensus_brief")

    if state.get("meta_decision"):
        state["deliberation_brief"] = apply_meta_decision_to_brief(
            state.get("deliberation_brief", {}),
            state.get("meta_decision", {}),
        )

    _run_conflict_analysis(state, "consensus_conflict_analysis")

    round_count = int(state.get("deliberation_round_count", 0))
    max_rounds = _normalize_max_deliberation_rounds(state.get("max_deliberation_rounds", 1))
    high_unresolved = _has_high_severity_tradeoff(state.get("conflict_report"))
    conflicting_roles = _high_conflict_role_keys(state)
    can_run_second_round = bool(high_unresolved and conflicting_roles and round_count < max_rounds)

    check = {
        "after_round": round_count,
        "high_unresolved_conflict": bool(high_unresolved),
        "conflicting_roles": conflicting_roles,
        "remaining_disagreements": len(_safe_list(_safe_dict(state.get("conflict_report")).get("disagreements"))),
        "remaining_tradeoffs": len(_safe_list(_safe_dict(state.get("conflict_report")).get("unresolved_tradeoffs"))),
        "decision": "DELIBERATION_ROUND_2" if can_run_second_round else "META_RECHECK",
    }
    state.setdefault("consensus_checks", []).append(check)

    if can_run_second_round:
        return DELIBERATION_ROUND, "consensus check found unresolved high-severity conflict"

    state["deliberation_round_done"] = True
    if high_unresolved and not conflicting_roles and round_count < max_rounds:
        state["warnings"].append("consensus_check_high_conflict_without_identifiable_roles")

    if int(state.get("meta_recheck_count", 0)) >= int(state.get("max_meta_rechecks", 1)):
        state["warnings"].append("meta_recheck_budget_exhausted_after_consensus_check")
        return PLAN, "consensus check complete; meta recheck budget exhausted"

    return META_RECHECK, "consensus check complete"


def handle_panel_round_extra(state: dict) -> tuple[str, str]:
    if state.get("extra_panel_done"):
        return REBALANCE, "extra panel already completed"
    try:
        extra_dynamic_roles: list = []
        try:
            existing_roles = _safe_list(state.get("expert_bundle", {}).get("roles")) + _safe_list(
                state.get("dynamic_roles")
            )
            dynamic_report = generate_dynamic_roles(
                query_intake=state.get("query_intake", {}),
                meta_decision=state.get("meta_decision", {}),
                conflict_report=state.get("conflict_report", {}),
                balance_report=state.get("balance_report", {}),
                existing_roles=existing_roles,
                max_roles=2,
                model=state["model"],
            )
            extra_dynamic_roles = _record_dynamic_role_report(state, dynamic_report, "extra")
            state["dynamic_roles"] = _safe_list(state.get("dynamic_roles")) + extra_dynamic_roles
        except Exception as exc:
            state["warnings"].append(f"dynamic_roles_extra_failed; continuing_with_targeted_roles: {exc}")

        targeted_roles = select_targeted_roles(
            meta_decision=state.get("meta_decision", {}),
            balance_report=state.get("balance_report", {}),
            deliberation_brief=state.get("deliberation_brief", {}),
            dynamic_roles=extra_dynamic_roles,
            conflict_report=state.get("conflict_report", {}),
        )
        second_round_context = {
            "round": 2,
            "original_query": state["original_query"],
            "cleaned_query": state.get("formalized_query") or state["original_query"],
            "query_intake": state.get("query_intake", {}),
            "conflict_report": state.get("conflict_report", {}),
            "deliberation_round": state["deliberation_rounds"][-1] if state.get("deliberation_rounds") else {},
            "intake_context": state.get("intake_context", {}),
            "first_deliberation_brief": state.get("deliberation_brief", {}),
            "meta_decision": state.get("meta_decision", {}),
            "dynamic_role_views": state["dynamic_role_reports"][-1].get("role_views", [])
            if state.get("dynamic_role_reports")
            else [],
            "instruction": _AUTHORITATIVE_QUERY_INSTRUCTION,
            "follow_up_instruction": (
                "Address gaps, conflicts, risks, and unanswered questions identified by "
                "meta_moderator. Do not repeat round 1 unless necessary."
            ),
        }
        execution_kwargs = {}
        if state.get("parallel_mode") == "THREADS":
            execution_kwargs = {
                "execution_mode": "THREADS",
                "max_workers": state.get("max_workers"),
            }
        second_bundle = run_targeted_expert_round(
            query=state["original_query"],
            roles=targeted_roles,
            context=second_round_context,
            model=state["model"],
            **execution_kwargs,
        )
        if not isinstance(second_bundle, dict):
            raise ValueError("invalid second expert round bundle")
        state["expert_rounds"].append(second_bundle)
        state["expert_bundle"] = merge_expert_bundles(state.get("expert_bundle", {}), second_bundle)
        if state.get("parallel_mode") == "THREADS":
            state.setdefault("parallelized_stages", []).append("PANEL_ROUND_EXTRA")
    except Exception as exc:
        state["warnings"].append(f"second_expert_round_failed; continuing_with_current_bundle: {exc}")
    state["extra_panel_done"] = True
    return REBALANCE, "extra panel handled"


def handle_rebalance(state: dict) -> tuple[str, str]:
    state["pre_rebalance_conflict_report"] = dict(_safe_dict(state.get("conflict_report")))

    _run_balance(state, "rebalance")
    _rebuild_brief(state, "rebalance_brief")

    if state.get("meta_decision"):
        state["deliberation_brief"] = apply_meta_decision_to_brief(
            state.get("deliberation_brief", {}),
            state.get("meta_decision", {}),
        )

    _run_conflict_analysis(state, "rebalance_conflict_analysis")

    if int(state.get("meta_recheck_count", 0)) >= int(state.get("max_meta_rechecks", 1)):
        state["warnings"].append("meta_recheck_budget_exhausted_after_rebalance")
        return PLAN, "rebalance complete; meta recheck budget exhausted; synthesizing with decision rules"

    return META_RECHECK, "rebalance complete; meta recheck required"

def handle_meta_recheck(state: dict) -> tuple[str, str]:
    """Bounded process recheck after REBALANCE.

    This is intentionally one-shot. It makes the meta moderator accompany the
    process after deliberation/extra-panel changes without creating an
    unbounded autonomous loop.
    """
    current_count = int(state.get("meta_recheck_count", 0))
    max_count = int(state.get("max_meta_rechecks", 1))

    if current_count >= max_count:
        state["warnings"].append("meta_recheck_budget_exhausted")
        return PLAN, "meta recheck budget exhausted; synthesizing unresolved tradeoffs with decision rules"

    state["meta_recheck_count"] = current_count + 1

    if _conflicts_cleared(state.get("conflict_report"), state.get("balance_report")):
        state.setdefault("meta_recheck_decisions", []).append(
            {
                "decision": "SYNTHESIZE",
                "reason": "Rebalance cleared conflicts and balance gaps; planning can proceed.",
                "missing_perspectives": [],
                "conflicts_to_resolve": [],
                "risks_to_address": [],
                "questions_to_answer": [],
                "next_actions": ["Proceed to planning."],
                "confidence": 0.8,
                "parse_warnings": ["meta_recheck_rules"],
                "source": "rules",
            }
        )
        return PLAN, "meta recheck found no remaining process gaps"

    meta_decision = _run_meta_decision_with_context(state, phase="recheck")
    decision = str(meta_decision.get("decision") or "SYNTHESIZE").upper()

    if decision == "FINALIZE":
        if not state.get("final_answer"):
            state["warnings"].append("meta_recheck_finalize_before_answer")
        return FINALIZE, "meta recheck requested finalize"

    if decision == "REPLAN":
        return PLAN, "meta recheck requested planning"

    critical_blind_spots = _new_or_critical_blind_spots_after_rebalance(state)

    if decision == "ADD_EXPERT":
        if not state.get("extra_panel_done") and (
            critical_blind_spots
            or _targeted_followup_still_useful(
                meta_decision=meta_decision,
                balance_report=state.get("balance_report"),
                deliberation_brief=state.get("deliberation_brief"),
                conflict_report=state.get("conflict_report"),
            )
        ):
            return PANEL_ROUND_EXTRA, "meta recheck requested additional expert"

    if decision == "DEEPEN":
        if (
            not state.get("deliberation_round_done")
            and (
                _has_high_severity_tradeoff(state.get("conflict_report"))
                or _deliberation_needed(state.get("conflict_report"), meta_decision)
            )
        ):
            return DELIBERATION_ROUND, "meta recheck requested deeper deliberation"

        if not state.get("extra_panel_done") and _targeted_followup_still_useful(
            meta_decision=meta_decision,
            balance_report=state.get("balance_report"),
            deliberation_brief=state.get("deliberation_brief"),
            conflict_report=state.get("conflict_report"),
        ):
            return PANEL_ROUND_EXTRA, "meta recheck requested targeted follow-up"

    return PLAN, "meta recheck complete; ready to plan"

def handle_plan(state: dict) -> tuple[str, str]:
    try:
        planner_context = _build_planner_context(state)
        plan = develop_plan(
            state["original_query"],
            context=planner_context,
            depth="detailed",
            model=state["model"],
        )
        if not isinstance(plan, dict):
            state["warnings"].append("plan_invalid; stopping before moderation")
            plan = {"error": "plan_invalid"}
            state["plan"] = plan
            state["plans"].append(plan)
            state["errors"].append("plan_invalid")
            return FAILED, "plan generation returned invalid plan"
    except Exception as exc:
        state["warnings"].append(f"plan_generation_failed; stopping before moderation: {exc}")
        plan = {"error": "plan_generation_failed"}
        state["plan"] = plan
        state["plans"].append(plan)
        state["errors"].append(f"plan_generation_failed: {exc}")
        return FAILED, "plan generation failed"

    state["plan"] = plan
    state["plans"].append(plan)
    return PLAN_CRITIQUE, "plan generated"


def handle_plan_critique(state: dict) -> tuple[str, str]:
    try:
        critic_context = build_compact_critic_context(state)
        record_context_size(state, "critic", critic_context)
        critique_result = check_plan_and_act(
            state.get("plan", {}),
            state["original_query"],
            min_score=0.7,
            query_intake=critic_context.get("query_intake", {}),
            deliberation_brief=critic_context.get("deliberation_brief", {}),
            conflict_report=critic_context.get("conflict_report", {}),
            dynamic_roles_used=critic_context.get("dynamic_roles_used", []),
            deliberation_revisions=critic_context.get("deliberation_revisions", []),
            meta_decision=critic_context.get("meta_decision", {}),
            state_history=critic_context.get("state_history", []),
            replan_context=critic_context.get("replan_context", {}),
            model=state["model"],
        )
        if not isinstance(critique_result, dict):
            state["warnings"].append("plan_critique_invalid; continuing with empty critique")
            critique_result = {"status": "ready", "decision": "ACCEPT", "critique": {}}
    except Exception as exc:
        state["warnings"].append(f"plan_critique_failed; continuing with empty critique: {exc}")
        critique_result = {"status": "ready", "decision": "ACCEPT", "critique": {}}

    state["plan_critiques"].append(critique_result)
    state["plan_critique"] = (
        critique_result.get("critique") if isinstance(critique_result.get("critique"), dict) else {}
    )

    status = str(critique_result.get("status") or "").lower()
    decision = str(critique_result.get("decision") or "").upper()
    critical_blockers = plan_blockers(critique_result)

    if status == "ready" and has_critical_plan_blockers(critique_result):
        state.setdefault("quality_gate_decisions", []).append(
            {
                "gate": "plan_critique",
                "decision": "BLOCK",
                "reason": "ready_plan_contains_critical_blockers",
                "critical_blockers": critical_blockers,
            }
        )
        state["warnings"].append("critical_plan_blockers_detected_after_ready_status")
        state["errors"].append("critical_plan_blockers")
        return FAILED, "quality gate blocked ready plan with critical blockers"

    if status == "ready" or decision == "ACCEPT":
        state.setdefault("quality_gate_decisions", []).append(
            {
                "gate": "plan_critique",
                "decision": "ALLOW",
                "reason": "plan accepted",
                "critical_blockers": [],
            }
        )
        state["replan_context"] = {}
        return ANSWER, "plan critique accepted plan"

    if status in {"needs_revision", "rejected"} or decision in {"REVISE", "REJECT"}:
        if int(state.get("iteration_count", 0)) < int(state.get("max_iters", 0)):
            reason = critique_result.get("reason") or "plan needs revision"
            state["replan_context"] = {
                "previous_plan": state.get("plan", {}),
                "plan_critique": state.get("plan_critique", {}),
                "feedback": _safe_list(critique_result.get("feedback")),
                "reason": reason,
                "instruction": "Regenerate the plan and address the critique feedback.",
            }
            state.setdefault("quality_gate_decisions", []).append(
                {
                    "gate": "plan_critique",
                    "decision": "REPLAN",
                    "reason": reason,
                    "critical_blockers": critical_blockers,
                }
            )
            return REPLAN, f"plan critique requested {status or decision}"

        message = f"plan_{status or decision.lower()}_after_max_iters"

        # Check if we can proceed with best-effort answer despite plan issues
        # This applies to both needs_revision and rejected status when there are no critical blockers
        if can_best_effort_finalize(critique_result=critique_result, plan=state.get("plan", {})):
            state["warnings"].append(f"{message}; proceeding_with_best_effort_plan")
            state.setdefault("quality_gate_decisions", []).append(
                {
                    "gate": "plan_critique",
                    "decision": "BEST_EFFORT",
                    "reason": f"non-critical plan {status or decision.lower()} exhausted; no safety/legal/privacy blockers",
                    "critical_blockers": [],
                }
            )
            state["replan_context"] = {}
            return ANSWER, f"plan critique exhausted non-critical {status or decision.lower()}; proceeding best effort"

        # Only block if there are actual critical blockers (safety/legal/privacy/security)
        state["warnings"].append(message)
        state["errors"].append(message)
        if critical_blockers and "critical_plan_blockers" not in state["errors"]:
            state["errors"].append("critical_plan_blockers")
        state.setdefault("quality_gate_decisions", []).append(
            {
                "gate": "plan_critique",
                "decision": "BLOCK",
                "reason": message,
                "critical_blockers": critical_blockers,
            }
        )
        return FAILED, "plan quality gate blocked answer generation"

    state.setdefault("quality_gate_decisions", []).append(
        {
            "gate": "plan_critique",
            "decision": "BEST_EFFORT",
            "reason": "unknown critique status treated as non-critical",
            "critical_blockers": critical_blockers,
        }
    )
    return ANSWER, "plan critique status treated as ready"


def handle_replan(state: dict) -> tuple[str, str]:
    state["iteration_count"] = int(state.get("iteration_count", 0)) + 1
    return PLAN, "replanning with latest context and critique feedback"


def handle_answer(state: dict) -> tuple[str, str]:
    try:
        answer_context = build_compact_answer_context(state)
        record_context_size(state, "answer", answer_context)
        moderated_result = run_moderated_loop(
            state["original_query"],
            state.get("plan", {}),
            state.get("plan_critique", {}),
            expert_bundle=answer_context.get("expert_bundle", {}),
            balance_report=answer_context.get("balance_report", {}),
            deliberation_brief=answer_context.get("deliberation_brief", {}),
            max_iters=state.get("max_iters", 2),
            model=state["model"],
        )
        if not isinstance(moderated_result, dict):
            state["warnings"].append("moderated_result_invalid; returning empty final_answer")
            moderated_result = {}
    except Exception as exc:
        state["warnings"].append(f"moderated_loop_failed; returning empty final_answer: {exc}")
        moderated_result = {}

    moderated_result = normalize_moderated_result(moderated_result)

    state["moderated_result"] = moderated_result
    state["moderation_reports"] = _safe_list(moderated_result.get("reports"))
    state["answer_moderation_final_decision"] = moderated_result.get("final_decision") or ""
    state["answer_moderation_critical_issues"] = _safe_list(moderated_result.get("critical_issues"))
    state["answer_moderation_revision_count"] = int(moderated_result.get("revision_count") or 0)
    state["answer_moderation_best_effort"] = False

    final_answer = moderated_result.get("final_answer") if isinstance(moderated_result, dict) else ""
    if (not isinstance(final_answer, str) or not final_answer.strip()) and _apply_answer_rescue(
        state,
        "moderated_loop_empty_or_rejected_noncritical",
    ):
        moderated_result = normalize_moderated_result(state.get("moderated_result", {}))
        final_answer = moderated_result.get("final_answer", "")

    state["final_answer"] = final_answer if isinstance(final_answer, str) else ""
    if state["final_answer"] and (
        not state.get("answers") or _safe_list(state.get("answers"))[-1] != state["final_answer"]
    ):
        state["answers"].append(state["final_answer"])

    return ANSWER_MODERATION, "answer moderation component completed"


def handle_answer_moderation(state: dict) -> tuple[str, str]:
    moderated_result = normalize_moderated_result(state.get("moderated_result", {}))
    state["moderated_result"] = moderated_result

    decision = str(moderated_result.get("final_decision") or "").upper()
    critical_issues = _safe_list(moderated_result.get("critical_issues"))

    state["answer_moderation_final_decision"] = decision
    state["answer_moderation_critical_issues"] = critical_issues
    state["answer_moderation_revision_count"] = int(moderated_result.get("revision_count") or 0)
    state["answer_moderation_best_effort"] = False

    if has_critical_answer_blockers(moderated_result):
        state["errors"].append("critical_answer_moderation_issues")
        state.setdefault("quality_gate_decisions", []).append(
            {
                "gate": "answer_moderation",
                "decision": "BLOCK",
                "reason": "critical answer moderation issues",
                "critical_issues": critical_issues,
            }
        )
        return FAILED, "answer moderation found critical blockers"

    if decision == "REJECT" or moderated_result.get("rejected"):
        if _apply_answer_rescue(state, "answer_moderation_rejected_noncritical"):
            state.setdefault("quality_gate_decisions", []).append(
                {
                    "gate": "answer_moderation",
                    "decision": "BEST_EFFORT",
                    "reason": "non-critical answer rejection rescued from actionable plan",
                    "critical_issues": [],
                }
            )
            return FINALIZE, "answer moderation rejected non-critical answer; finalized rescue answer"

        state["errors"].append("answer_moderation_rejected")
        state.setdefault("quality_gate_decisions", []).append(
            {
                "gate": "answer_moderation",
                "decision": "BLOCK",
                "reason": "answer moderation rejected final answer without rescueable plan",
                "critical_issues": critical_issues,
            }
        )
        return FAILED, "answer moderation rejected final answer"

    final_answer = state.get("final_answer")
    if not isinstance(final_answer, str) or not final_answer.strip():
        if _apply_answer_rescue(state, "answer_moderation_empty_noncritical"):
            state.setdefault("quality_gate_decisions", []).append(
                {
                    "gate": "answer_moderation",
                    "decision": "BEST_EFFORT",
                    "reason": "empty answer rescued from actionable plan",
                    "critical_issues": [],
                }
            )
            return FINALIZE, "answer moderation produced empty answer; finalized rescue answer"

        state["errors"].append("moderated_loop_returned_empty_final_answer")
        state.setdefault("quality_gate_decisions", []).append(
            {
                "gate": "answer_moderation",
                "decision": "BLOCK",
                "reason": "empty final answer",
                "critical_issues": critical_issues,
            }
        )
        return FAILED, "answer moderation failed to produce final answer"

    if decision == "ACCEPT":
        state.setdefault("quality_gate_decisions", []).append(
            {
                "gate": "answer_moderation",
                "decision": "ALLOW",
                "reason": "answer accepted",
                "critical_issues": [],
            }
        )
        return FINALIZE, "answer moderation accepted final answer"

    if decision == "REVISE":
        if can_best_effort_finalize(moderated_result=moderated_result):
            state["warnings"].append("answer_moderation_revise_best_effort")
            state["answer_moderation_best_effort"] = True
            state.setdefault("quality_gate_decisions", []).append(
                {
                    "gate": "answer_moderation",
                    "decision": "BEST_EFFORT",
                    "reason": "non-critical answer revision exhausted",
                    "critical_issues": [],
                }
            )
            return FINALIZE, "answer moderation requested non-critical revision; finalized best effort"

        state["errors"].append("answer_moderation_revise_critical_issues")
        state.setdefault("quality_gate_decisions", []).append(
            {
                "gate": "answer_moderation",
                "decision": "BLOCK",
                "reason": "revision contains critical blockers",
                "critical_issues": critical_issues,
            }
        )
        return FAILED, "answer moderation requested revision with critical issues"

    state["warnings"].append("answer_moderation_missing_decision_best_effort")
    state["answer_moderation_best_effort"] = True
    state.setdefault("quality_gate_decisions", []).append(
        {
            "gate": "answer_moderation",
            "decision": "BEST_EFFORT",
            "reason": "missing moderation decision without critical blockers",
            "critical_issues": [],
        }
    )
    return FINALIZE, "answer moderation decision missing; finalized best effort"


def _build_trace_report(state: dict) -> dict:
    moderation_reports = _safe_list(state.get("moderation_reports"))
    meta_decisions = _safe_list(state.get("meta_decisions"))
    conflict_reports = _safe_list(state.get("conflict_reports"))
    plan_critiques = _safe_list(state.get("plan_critiques"))
    deliberation_rounds = _safe_list(state.get("deliberation_rounds"))
    dynamic_role_reports = _safe_list(state.get("dynamic_role_reports"))
    dynamic_roles_generated = _flatten_dynamic_roles_generated(dynamic_role_reports)
    dynamic_roles_executed = _flatten_dynamic_roles_executed(state.get("expert_rounds"), dynamic_role_reports)
    expert_bundle = _safe_dict(state.get("expert_bundle"))
    raw_roles = _safe_list(expert_bundle.get("roles"))
    warnings = _safe_list(state.get("warnings"))
    errors = _safe_list(state.get("errors"))
    trace = {
        "original_query": state.get("original_query", ""),
        "formalized_query": state.get("formalized_query", ""),
        "query_intake": state.get("query_intake", {}),
        "router_decision": state.get("router_decision", {}),
        "cmm_mode": state.get("cmm_mode") or "",
        "estimated_cost_class": _safe_dict(state.get("router_decision")).get("estimated_cost_class") or "",
        "routing_warnings": _safe_list(state.get("routing_warnings")),
        "parallel_mode": state.get("parallel_mode") or "SEQUENTIAL",
        "max_workers": state.get("max_workers"),
        "parallelized_stages": _safe_list(state.get("parallelized_stages")),
        "roles_used": raw_roles,
        "roles_used_unique": _roles_used_unique(state.get("expert_rounds"), raw_roles),
        "expert_rounds": _safe_list(state.get("expert_rounds")),
        "deliberation_brief": state.get("deliberation_brief", {}),
        "balance_reports": _safe_list(state.get("balance_reports")),
        "conflict_reports": conflict_reports,
        "deliberation_rounds": deliberation_rounds,
        "deliberation_revisions": _flatten_deliberation_revisions(deliberation_rounds),
        "deliberation_round_count": int(state.get("deliberation_round_count", 0)),
        "max_deliberation_rounds": int(state.get("max_deliberation_rounds", 1)),
        "consensus_checks": _safe_list(state.get("consensus_checks")),
        "deliberation_position_changes": _safe_list(state.get("deliberation_position_changes")),
        "dynamic_role_reports": [_sanitize_dynamic_role_report(report) for report in dynamic_role_reports],
        "dynamic_roles_generated": dynamic_roles_generated,
        "dynamic_roles_executed": dynamic_roles_executed,
        "dynamic_roles_rejected": _flatten_dynamic_roles_rejected(dynamic_role_reports),
        "dynamic_roles_used": dynamic_roles_executed,
        "unresolved_tradeoffs": _flatten_conflict_field(conflict_reports, "unresolved_tradeoffs"),
        "premature_consensus_risks": _flatten_conflict_field(conflict_reports, "premature_consensus_risks"),
        "blind_spots": _flatten_conflict_field(conflict_reports, "blind_spots"),
        "plan": state.get("plan", {}),
        "plan_critique": state.get("plan_critique", {}),
        "moderation_reports": moderation_reports,
        "answer_moderation_final_decision": state.get("answer_moderation_final_decision") or "",
        "answer_moderation_critical_issues": _safe_list(state.get("answer_moderation_critical_issues")),
        "answer_moderation_revision_count": int(state.get("answer_moderation_revision_count") or 0),
        "answer_moderation_best_effort": bool(state.get("answer_moderation_best_effort")),
        "best_effort_answer_from_plan": bool(state.get("best_effort_answer_from_plan")),
        "quality_gate_decisions": _safe_list(state.get("quality_gate_decisions")),
        "context_compression": build_context_compression_report(state),
        "revision_count": max(0, len(moderation_reports) - 1),
        "final_confidence": _extract_final_confidence(moderation_reports),
        "meta_moderation_decisions": meta_decisions,
        "meta_recheck_count": int(state.get("meta_recheck_count", 0)),
        "meta_recheck_decisions": _safe_list(state.get("meta_recheck_decisions")),
        "conflicts_to_resolve": _flatten_meta_field(meta_decisions, "conflicts_to_resolve"),
        "risks_to_address": _flatten_meta_field(meta_decisions, "risks_to_address"),
        "warnings": warnings,
        "state_history": _safe_list(state.get("history")),
        "final_state": state.get("current_state"),
        "transition_count": state.get("transition_count", 0),
        "iteration_count": state.get("iteration_count", 0),
        "plans": _safe_list(state.get("plans")),
        "plan_critiques": plan_critiques,
        "plan_critique_statuses": [
            item.get("status") for item in plan_critiques if isinstance(item, dict) and item.get("status")
        ],
        "plan_replan_reasons": [
            item.get("reason") for item in plan_critiques if isinstance(item, dict) and item.get("reason")
        ],
        "plan_critique_decisions": _flatten_plan_critique_decisions(plan_critiques),
        "plan_critique_blockers": _flatten_plan_critique_field(plan_critiques, "critical_blockers"),
        "ignored_must_address": _flatten_plan_critique_field(plan_critiques, "ignored_must_address"),
        "ignored_risks": _flatten_plan_critique_field(plan_critiques, "ignored_risks"),
        "ignored_tradeoffs": _flatten_plan_critique_field(plan_critiques, "ignored_tradeoffs"),
        "errors": errors,
    }
    trace["json_health"] = _collect_json_health(trace)
    trace["estimated_call_count"] = _estimate_call_count(trace)
    trace["estimated_stage_count"] = len(_safe_list(trace.get("state_history")))
    final_answer = state.get("final_answer")
    trace["answer_chars"] = len(final_answer) if isinstance(final_answer, str) else 0
    trace["warnings_count"] = len(warnings)
    trace["errors_count"] = len(errors)
    return trace


def _compact_raw_state(state: dict) -> dict:
    return {
        "current_state": state.get("current_state"),
        "cmm_mode": state.get("cmm_mode") or "",
        "router_decision": state.get("router_decision", {}),
        "parallel_mode": state.get("parallel_mode") or "SEQUENTIAL",
        "max_workers": state.get("max_workers"),
        "transition_count": state.get("transition_count", 0),
        "iteration_count": state.get("iteration_count", 0),
        "meta_recheck_count": int(state.get("meta_recheck_count", 0)),
        "deliberation_round_count": int(state.get("deliberation_round_count", 0)),
        "max_deliberation_rounds": int(state.get("max_deliberation_rounds", 1)),
        "warnings": _safe_list(state.get("warnings")),
        "errors": _safe_list(state.get("errors")),
        "history": _safe_list(state.get("history")),
    }


def _build_result(state: dict) -> dict:
    return build_result_payload(
        state=state,
        trace_report=_build_trace_report(state),
        raw_state=_compact_raw_state(state),
        failed_state=FAILED,
    )


_HANDLERS = {
    INTAKE: handle_intake,
    ROUTE: handle_route,
    DIRECT_ANSWER: handle_direct_answer,
    PANEL_ROUND_1: handle_panel_round_1,
    BALANCE: handle_balance,
    CONFLICT_ANALYSIS: handle_conflict_analysis,
    META_DECISION: handle_meta_decision,
    DELIBERATION_ROUND: handle_deliberation_round,
    CONSENSUS_CHECK: handle_consensus_check,
    PANEL_ROUND_EXTRA: handle_panel_round_extra,
    REBALANCE: handle_rebalance,
    META_RECHECK: handle_meta_recheck,
    PLAN: handle_plan,
    PLAN_CRITIQUE: handle_plan_critique,
    REPLAN: handle_replan,
    ANSWER: handle_answer,
    ANSWER_MODERATION: handle_answer_moderation,
}


def run_cmm_state_machine(
    query: str,
    *,
    max_iters: int = 2,
    model: str = "deepseek-chat",
    max_transitions: int = 40,
    route_mode: str = "AUTO",
    parallel_mode: str = "SEQUENTIAL",
    max_workers: int | None = None,
    max_deliberation_rounds: int = 1,
) -> dict:
    """Run CMM through a bounded explicit state machine."""
    state = init_cmm_state(
        query,
        max_iters=max_iters,
        model=model,
        max_transitions=max_transitions,
        route_mode=route_mode,
        parallel_mode=parallel_mode,
        max_workers=max_workers,
        max_deliberation_rounds=max_deliberation_rounds,
    )

    while state.get("current_state") not in {FINALIZE, FAILED}:
        if int(state.get("transition_count", 0)) >= int(state.get("max_transitions", 40)):
            state["errors"].append("max_transitions_exceeded")
            transition(state, FAILED, "max transition guard exceeded")
            break

        current = state.get("current_state")
        handler = _HANDLERS.get(current)
        if handler is None:
            state["errors"].append(f"unknown_state: {current}")
            transition(state, FAILED, "unknown state")
            break

        try:
            next_state, reason = handler(state)
        except Exception as exc:
            state["errors"].append(f"state_handler_failed: {current}: {exc}")
            next_state, reason = FAILED, f"handler failed: {current}"
        transition(state, next_state, reason)

    return _build_result(state)
