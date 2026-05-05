"""Bounded state-machine orchestration for Collective Meta-Moderation."""

from __future__ import annotations

from typing import Any

from Lib.agent_moderator import run_moderated_loop
from Lib.balance_analyzer import analyze_balance
from Lib.conflict_analyzer import analyze_conflicts
from Lib.critic_decision import check_plan_and_act
from Lib.deliberation import (
    apply_conflict_report_to_brief,
    apply_deliberation_round_to_brief,
    apply_meta_decision_to_brief,
    build_deliberation_brief,
)
from Lib.deliberation_round import merge_deliberation_into_bundle, run_deliberation_round
from Lib.expert_panel import run_expert_panel
from Lib.expert_rounds import merge_expert_bundles, run_targeted_expert_round, select_targeted_roles
from Lib.meta_moderator import run_meta_moderator
from Lib.plan_development import develop_plan
from Lib.query_intake import build_query_intake
from Lib.role_generator import generate_dynamic_roles


INTAKE = "INTAKE"
PANEL_ROUND_1 = "PANEL_ROUND_1"
BALANCE = "BALANCE"
CONFLICT_ANALYSIS = "CONFLICT_ANALYSIS"
META_DECISION = "META_DECISION"
DELIBERATION_ROUND = "DELIBERATION_ROUND"
REBALANCE = "REBALANCE"
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


def _empty_expert_bundle() -> dict:
    return {
        "roles": [],
        "contributions": [],
        "synthesis": {
            "recommendations": [],
            "risks": [],
            "questions": [],
            "perspective_counts": {},
        },
    }


def _conservative_balance_report() -> dict:
    return {
        "dominant_perspective_found": False,
        "dominant_perspective": None,
        "missing_perspectives": ["strategy", "engineering", "risk", "user"],
        "notes": ["Balance analysis failed; conservative fallback marks all base perspectives as missing."],
    }


def _empty_deliberation_brief(query: str) -> dict:
    return {
        "summary": f"Expert deliberation for query: {query[:240]}",
        "expert_recommendations": [],
        "expert_risks": [],
        "expert_questions": [],
        "perspective_counts": {},
        "missing_perspectives": [],
        "dominant_perspective_found": False,
        "balance_notes": [],
        "must_address": [],
    }


def _fallback_query_intake(original_query: str, warning: str) -> dict:
    cleaned_query = str(original_query or "").strip()
    complexity = "simple" if len(cleaned_query.split()) <= 12 else "moderate"
    return {
        "original_query": original_query,
        "cleaned_query": cleaned_query or original_query,
        "task_goal": (cleaned_query or original_query)[:700],
        "context": [],
        "constraints": [],
        "success_criteria": [],
        "unknowns": [],
        "user_preferences": [],
        "risk_level": "medium" if cleaned_query else "low",
        "complexity": complexity,
        "should_use_cmm": complexity != "simple",
        "parse_warnings": [warning],
        "source": "fallback",
    }


def _fallback_conflict_report() -> dict:
    return {
        "agreements": [],
        "disagreements": [],
        "unresolved_tradeoffs": [],
        "premature_consensus_risks": [],
        "blind_spots": ["Conflict analysis failed."],
        "minority_positions": [],
        "questions_for_next_round": [],
        "confidence": 0.0,
        "parse_warnings": ["conflict_analysis_failed"],
        "source": "fallback",
    }


def _fallback_meta_decision(reason: str, warning: str) -> dict:
    return {
        "decision": "SYNTHESIZE",
        "reason": reason,
        "missing_perspectives": [],
        "conflicts_to_resolve": [],
        "risks_to_address": [],
        "questions_to_answer": [],
        "next_actions": ["Proceed to planning."],
        "confidence": 0.0,
        "parse_warnings": [warning],
        "source": "state_machine_fallback",
    }


def _build_intake_context(original_query: str, query_intake: dict) -> dict:
    return {
        "query_intake": query_intake,
        "original_query": original_query,
        "cleaned_query": query_intake.get("cleaned_query") or original_query,
        "instruction": _AUTHORITATIVE_QUERY_INSTRUCTION,
    }


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
    context = {
        "query_intake": state.get("query_intake", {}),
        "deliberation_brief": state.get("deliberation_brief", {}),
        "conflict_report": state.get("conflict_report", {}),
        "original_query_is_authoritative": True,
        "instruction": _AUTHORITATIVE_QUERY_INSTRUCTION,
    }
    replan_context = _safe_dict(state.get("replan_context"))
    if replan_context:
        context["replan_context"] = replan_context
    return context


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
        }
    return {
        "role_views": _safe_list(report.get("role_views")),
        "rejected_suggestions": _safe_list(report.get("rejected_suggestions")),
        "warnings": _safe_list(report.get("warnings")),
        "source": report.get("source") or "fallback",
        "round": report.get("round") or "",
    }


def _flatten_dynamic_roles_used(dynamic_role_reports: list | None) -> list[dict]:
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


def init_cmm_state(
    query: str,
    *,
    max_iters: int = 2,
    model: str = "deepseek-chat",
    max_transitions: int = 40,
) -> dict:
    original_query = "" if query is None else str(query)
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
        "meta_decisions": [],
        "meta_decision": {},
        "plans": [],
        "plan": {},
        "plan_critiques": [],
        "plan_critique": {},
        "answers": [],
        "moderated_result": {},
        "moderation_reports": [],
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
    return PANEL_ROUND_1, "query intake complete"


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
        expert_bundle = run_expert_panel(
            state["original_query"],
            context=panel_context,
            max_roles=max(5, 5 + len(initial_dynamic_roles)),
            dynamic_roles=initial_dynamic_roles,
        )
        if not isinstance(expert_bundle, dict):
            state["warnings"].append("expert_panel_invalid; using empty expert bundle")
            expert_bundle = _empty_expert_bundle()
    except Exception as exc:
        state["warnings"].append(f"expert_panel_failed; using empty expert bundle: {exc}")
        expert_bundle = _empty_expert_bundle()
    state["expert_bundle"] = expert_bundle
    state["expert_rounds"].append(expert_bundle)
    return BALANCE, "initial expert panel complete"


def _run_balance(state: dict, warning_prefix: str) -> None:
    try:
        balance_report = analyze_balance(state.get("expert_bundle", {}))
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
    try:
        meta_decision = run_meta_moderator(
            query=state["original_query"],
            expert_bundle=state.get("expert_bundle", {}),
            balance_report=state.get("balance_report", {}),
            deliberation_brief=state.get("deliberation_brief", {}),
            conflict_report=state.get("conflict_report", {}),
            model=state["model"],
        )
        if not isinstance(meta_decision, dict):
            state["warnings"].append("meta_moderator_invalid; continuing without process decision")
            meta_decision = _fallback_meta_decision(
                "Meta moderator returned invalid output.",
                "meta_moderator_invalid",
            )
    except Exception as exc:
        state["warnings"].append(f"meta_moderator_failed; continuing with synthesis: {exc}")
        meta_decision = _fallback_meta_decision(
            "Meta moderator failed; proceed with existing deliberation brief.",
            "meta_moderator_failed",
        )

    state["meta_decision"] = meta_decision
    state["meta_decisions"].append(meta_decision)
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
    if state.get("deliberation_round_done"):
        return REBALANCE, "deliberation already completed"
    try:
        deliberation_bundle = run_deliberation_round(
            query=state["original_query"],
            query_intake=state.get("query_intake", {}),
            expert_bundle=state.get("expert_bundle", {}),
            deliberation_brief=state.get("deliberation_brief", {}),
            conflict_report=state.get("conflict_report", {}),
            meta_decision=state.get("meta_decision", {}),
            model=state["model"],
        )
        if not isinstance(deliberation_bundle, dict):
            raise ValueError("invalid deliberation round bundle")
        state["deliberation_rounds"].append(deliberation_bundle)
        expert_bundle = merge_deliberation_into_bundle(state.get("expert_bundle", {}), deliberation_bundle)
        if not isinstance(expert_bundle, dict):
            raise ValueError("invalid deliberation merge result")
        state["expert_bundle"] = expert_bundle
    except Exception as exc:
        state["warnings"].append(f"deliberation_round_failed; continuing_without_deliberation: {exc}")
    state["deliberation_round_done"] = True
    return REBALANCE, "deliberation round handled"


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
        second_bundle = run_targeted_expert_round(
            query=state["original_query"],
            roles=targeted_roles,
            context=second_round_context,
            model=state["model"],
        )
        if not isinstance(second_bundle, dict):
            raise ValueError("invalid second expert round bundle")
        state["expert_rounds"].append(second_bundle)
        state["expert_bundle"] = merge_expert_bundles(state.get("expert_bundle", {}), second_bundle)
    except Exception as exc:
        state["warnings"].append(f"second_expert_round_failed; continuing_with_current_bundle: {exc}")
    state["extra_panel_done"] = True
    return REBALANCE, "extra panel handled"


def handle_rebalance(state: dict) -> tuple[str, str]:
    _run_balance(state, "rebalance")
    _rebuild_brief(state, "rebalance_brief")
    if state.get("meta_decision"):
        state["deliberation_brief"] = apply_meta_decision_to_brief(
            state.get("deliberation_brief", {}),
            state.get("meta_decision", {}),
        )
    _run_conflict_analysis(state, "rebalance_conflict_analysis")

    if not state.get("extra_panel_done") and _targeted_followup_still_useful(
        meta_decision=state.get("meta_decision", {}),
        balance_report=state.get("balance_report", {}),
        deliberation_brief=state.get("deliberation_brief", {}),
        conflict_report=state.get("conflict_report", {}),
    ):
        return PANEL_ROUND_EXTRA, "targeted follow-up still useful after rebalance"
    return PLAN, "rebalance complete"


def handle_plan(state: dict) -> tuple[str, str]:
    try:
        planner_context = _build_planner_context(state)
        plan = develop_plan(state["original_query"], context=planner_context, depth="detailed")
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
        critique_result = check_plan_and_act(
            state.get("plan", {}),
            state["original_query"],
            min_score=0.7,
            query_intake=state.get("query_intake", {}),
            deliberation_brief=state.get("deliberation_brief", {}),
            conflict_report=state.get("conflict_report", {}),
            dynamic_roles_used=_flatten_dynamic_roles_used(state.get("dynamic_role_reports")),
            deliberation_revisions=_flatten_deliberation_revisions(state.get("deliberation_rounds")),
            meta_decision=state.get("meta_decision", {}),
            state_history=state.get("history", []),
            replan_context=state.get("replan_context", {}),
            model=state["model"],
        )
        if not isinstance(critique_result, dict):
            state["warnings"].append("plan_critique_invalid; continuing with empty critique")
            critique_result = {"status": "ready", "critique": {}}
    except Exception as exc:
        state["warnings"].append(f"plan_critique_failed; continuing with empty critique: {exc}")
        critique_result = {"status": "ready", "critique": {}}

    state["plan_critiques"].append(critique_result)
    state["plan_critique"] = (
        critique_result.get("critique") if isinstance(critique_result.get("critique"), dict) else {}
    )
    status = critique_result.get("status")
    if status == "ready":
        state["replan_context"] = {}
        return ANSWER, "plan critique accepted plan"

    if status in {"needs_revision", "rejected"}:
        if int(state.get("iteration_count", 0)) < int(state.get("max_iters", 0)):
            reason = critique_result.get("reason") or "plan needs revision"
            state["replan_context"] = {
                "previous_plan": state.get("plan", {}),
                "plan_critique": state.get("plan_critique", {}),
                "feedback": _safe_list(critique_result.get("feedback")),
                "reason": reason,
                "instruction": "Regenerate the plan and address the critique feedback.",
            }
            return REPLAN, f"plan critique requested {status}"
        message = f"plan_{status}_after_max_iters"
        state["warnings"].append(message)
        state["errors"].append(message)
        return FAILED, "plan critique exhausted replan iterations"

    return ANSWER, "plan critique status treated as ready"


def handle_replan(state: dict) -> tuple[str, str]:
    state["iteration_count"] = int(state.get("iteration_count", 0)) + 1
    return PLAN, "replanning with latest context and critique feedback"


def handle_answer(state: dict) -> tuple[str, str]:
    try:
        moderated_result = run_moderated_loop(
            state["original_query"],
            state.get("plan", {}),
            state.get("plan_critique", {}),
            expert_bundle=state.get("expert_bundle", {}),
            balance_report=state.get("balance_report", {}),
            deliberation_brief=state.get("deliberation_brief", {}),
            max_iters=state.get("max_iters", 2),
            model=state["model"],
        )
        if not isinstance(moderated_result, dict):
            state["warnings"].append("moderated_result_invalid; returning empty final_answer")
            moderated_result = {}
    except Exception as exc:
        state["warnings"].append(f"moderated_loop_failed; returning empty final_answer: {exc}")
        moderated_result = {}

    state["moderated_result"] = moderated_result
    state["moderation_reports"] = _safe_list(moderated_result.get("reports"))
    final_answer = moderated_result.get("final_answer") if isinstance(moderated_result, dict) else ""
    state["final_answer"] = final_answer if isinstance(final_answer, str) else ""
    if state["final_answer"]:
        state["answers"].append(state["final_answer"])
    return ANSWER_MODERATION, "answer moderation component completed"


def handle_answer_moderation(state: dict) -> tuple[str, str]:
    if state.get("final_answer"):
        return FINALIZE, "final answer available"
    state["errors"].append("moderated_loop_returned_empty_final_answer")
    return FAILED, "answer moderation failed to produce final answer"


def _build_trace_report(state: dict) -> dict:
    moderation_reports = _safe_list(state.get("moderation_reports"))
    meta_decisions = _safe_list(state.get("meta_decisions"))
    conflict_reports = _safe_list(state.get("conflict_reports"))
    plan_critiques = _safe_list(state.get("plan_critiques"))
    deliberation_rounds = _safe_list(state.get("deliberation_rounds"))
    dynamic_role_reports = _safe_list(state.get("dynamic_role_reports"))
    expert_bundle = _safe_dict(state.get("expert_bundle"))
    return {
        "original_query": state.get("original_query", ""),
        "formalized_query": state.get("formalized_query", ""),
        "query_intake": state.get("query_intake", {}),
        "roles_used": _safe_list(expert_bundle.get("roles")),
        "expert_rounds": _safe_list(state.get("expert_rounds")),
        "deliberation_brief": state.get("deliberation_brief", {}),
        "balance_reports": _safe_list(state.get("balance_reports")),
        "conflict_reports": conflict_reports,
        "deliberation_rounds": deliberation_rounds,
        "deliberation_revisions": _flatten_deliberation_revisions(deliberation_rounds),
        "dynamic_role_reports": [_sanitize_dynamic_role_report(report) for report in dynamic_role_reports],
        "dynamic_roles_used": _flatten_dynamic_roles_used(dynamic_role_reports),
        "unresolved_tradeoffs": _flatten_conflict_field(conflict_reports, "unresolved_tradeoffs"),
        "premature_consensus_risks": _flatten_conflict_field(conflict_reports, "premature_consensus_risks"),
        "blind_spots": _flatten_conflict_field(conflict_reports, "blind_spots"),
        "plan": state.get("plan", {}),
        "plan_critique": state.get("plan_critique", {}),
        "moderation_reports": moderation_reports,
        "revision_count": max(0, len(moderation_reports) - 1),
        "final_confidence": _extract_final_confidence(moderation_reports),
        "meta_moderation_decisions": meta_decisions,
        "conflicts_to_resolve": _flatten_meta_field(meta_decisions, "conflicts_to_resolve"),
        "risks_to_address": _flatten_meta_field(meta_decisions, "risks_to_address"),
        "warnings": _safe_list(state.get("warnings")),
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
        "errors": _safe_list(state.get("errors")),
    }


def _compact_raw_state(state: dict) -> dict:
    return {
        "current_state": state.get("current_state"),
        "transition_count": state.get("transition_count", 0),
        "iteration_count": state.get("iteration_count", 0),
        "warnings": _safe_list(state.get("warnings")),
        "errors": _safe_list(state.get("errors")),
        "history": _safe_list(state.get("history")),
    }


def _build_result(state: dict) -> dict:
    final_answer = state.get("final_answer") if state.get("current_state") != FAILED else ""
    if not isinstance(final_answer, str):
        final_answer = ""
    return {
        "final_answer": final_answer,
        "trace_report": _build_trace_report(state),
        "raw": {
            "expert_bundle": state.get("expert_bundle", {}),
            "moderated_result": state.get("moderated_result", {}),
            "state": _compact_raw_state(state),
        },
    }


_HANDLERS = {
    INTAKE: handle_intake,
    PANEL_ROUND_1: handle_panel_round_1,
    BALANCE: handle_balance,
    CONFLICT_ANALYSIS: handle_conflict_analysis,
    META_DECISION: handle_meta_decision,
    DELIBERATION_ROUND: handle_deliberation_round,
    PANEL_ROUND_EXTRA: handle_panel_round_extra,
    REBALANCE: handle_rebalance,
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
) -> dict:
    """Run CMM through a bounded explicit state machine."""
    state = init_cmm_state(query, max_iters=max_iters, model=model, max_transitions=max_transitions)

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
