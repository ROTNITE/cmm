"""Central MVP pipeline orchestrator for Collective Meta-Moderation."""

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


_AUTHORITATIVE_QUERY_INSTRUCTION = (
    "Original query is authoritative. Cleaned/formalized query is helper text only. "
    "Do not ignore constraints from original_query."
)


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


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


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


def _build_planner_context(query_intake: dict, deliberation_brief: dict, conflict_report: dict | None = None) -> dict:
    return {
        "query_intake": query_intake,
        "deliberation_brief": deliberation_brief,
        "conflict_report": conflict_report or {},
        "original_query_is_authoritative": True,
        "instruction": _AUTHORITATIVE_QUERY_INSTRUCTION,
    }


def _flatten_meta_field(meta_moderation_decisions: list | None, key: str) -> list[str]:
    out: list[str] = []
    for decision in _safe_list(meta_moderation_decisions):
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


def _deliberation_needed(conflict_report: dict | None, meta_decision: dict | None) -> bool:
    conflict = _safe_dict(conflict_report)
    if conflict.get("source") == "fallback":
        return False
    meta = _safe_dict(meta_decision)
    if meta.get("decision") in {"DEEPEN", "ADD_EXPERT"}:
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


def _build_trace_report(
    *,
    original_query: str,
    formalized_query: str,
    query_intake: dict | None,
    expert_bundle: dict,
    balance_report: dict,
    deliberation_brief: dict,
    plan: dict,
    plan_critique: dict,
    moderated_result: dict,
    warnings: list[str],
    meta_moderation_decisions: list | None = None,
    expert_rounds: list | None = None,
    balance_reports: list | None = None,
    conflict_reports: list | None = None,
    deliberation_rounds: list | None = None,
) -> dict:
    moderation_reports = _safe_list(moderated_result.get("reports") if isinstance(moderated_result, dict) else [])
    meta_moderation_decisions = _safe_list(meta_moderation_decisions)
    expert_rounds = _safe_list(expert_rounds) or [expert_bundle]
    balance_reports = _safe_list(balance_reports) or [balance_report]
    conflict_reports = _safe_list(conflict_reports)
    deliberation_rounds = _safe_list(deliberation_rounds)

    return {
        "original_query": original_query,
        "formalized_query": formalized_query,
        "query_intake": query_intake or {},
        "roles_used": _safe_list(expert_bundle.get("roles") if isinstance(expert_bundle, dict) else []),
        "expert_rounds": expert_rounds,
        "deliberation_brief": deliberation_brief,
        "balance_reports": balance_reports,
        "conflict_reports": conflict_reports,
        "deliberation_rounds": deliberation_rounds,
        "deliberation_revisions": _flatten_deliberation_revisions(deliberation_rounds),
        "unresolved_tradeoffs": _flatten_conflict_field(conflict_reports, "unresolved_tradeoffs"),
        "premature_consensus_risks": _flatten_conflict_field(conflict_reports, "premature_consensus_risks"),
        "blind_spots": _flatten_conflict_field(conflict_reports, "blind_spots"),
        "plan": plan,
        "plan_critique": plan_critique,
        "moderation_reports": moderation_reports,
        "revision_count": max(0, len(moderation_reports) - 1),
        "final_confidence": _extract_final_confidence(moderation_reports),
        "meta_moderation_decisions": meta_moderation_decisions,
        "conflicts_to_resolve": _flatten_meta_field(meta_moderation_decisions, "conflicts_to_resolve"),
        "risks_to_address": _flatten_meta_field(meta_moderation_decisions, "risks_to_address"),
        "warnings": warnings,
    }


def _build_result(
    *,
    final_answer: str,
    original_query: str,
    formalized_query: str,
    query_intake: dict | None,
    expert_bundle: dict,
    balance_report: dict,
    deliberation_brief: dict,
    plan: dict,
    plan_critique: dict,
    moderated_result: dict,
    warnings: list[str],
    meta_moderation_decisions: list | None = None,
    expert_rounds: list | None = None,
    balance_reports: list | None = None,
    conflict_reports: list | None = None,
    deliberation_rounds: list | None = None,
) -> dict:
    return {
        "final_answer": final_answer,
        "trace_report": _build_trace_report(
            original_query=original_query,
            formalized_query=formalized_query,
            query_intake=query_intake,
            expert_bundle=expert_bundle,
            balance_report=balance_report,
            deliberation_brief=deliberation_brief,
            plan=plan,
            plan_critique=plan_critique,
            moderated_result=moderated_result,
            warnings=warnings,
            meta_moderation_decisions=meta_moderation_decisions,
            expert_rounds=expert_rounds,
            balance_reports=balance_reports,
            conflict_reports=conflict_reports,
            deliberation_rounds=deliberation_rounds,
        ),
        "raw": {
            "expert_bundle": expert_bundle,
            "moderated_result": moderated_result,
        },
    }


def run_cmm(query: str, *, max_iters: int = 2, model: str = "deepseek-chat") -> dict:
    """Run the Collective Meta-Moderation MVP pipeline."""
    original_query = "" if query is None else str(query)
    warnings: list[str] = []
    meta_moderation_decisions: list[dict] = []
    expert_rounds: list[dict] = []
    balance_reports: list[dict] = []
    conflict_reports: list[dict] = []
    deliberation_rounds: list[dict] = []

    try:
        query_intake = build_query_intake(original_query, model=model)
        if not isinstance(query_intake, dict):
            warnings.append("query_intake_invalid; using fallback query intake")
            query_intake = _fallback_query_intake(original_query, "query_intake_invalid")
    except Exception as exc:
        warnings.append(f"query_intake_failed; using fallback query intake: {exc}")
        query_intake = _fallback_query_intake(original_query, "query_intake_failed")

    intake_warnings = _safe_list(query_intake.get("parse_warnings"))
    warnings.extend([f"query_intake: {warning}" for warning in intake_warnings if isinstance(warning, str)])
    formalized_query = query_intake.get("cleaned_query") if isinstance(query_intake.get("cleaned_query"), str) else ""
    if not formalized_query.strip():
        formalized_query = original_query
    intake_context = _build_intake_context(original_query, query_intake)

    try:
        expert_bundle = run_expert_panel(original_query, context=intake_context)
        if not isinstance(expert_bundle, dict):
            warnings.append("expert_panel_invalid; using empty expert bundle")
            expert_bundle = _empty_expert_bundle()
    except Exception as exc:
        warnings.append(f"expert_panel_failed; using empty expert bundle: {exc}")
        expert_bundle = _empty_expert_bundle()
    expert_rounds.append(expert_bundle)

    try:
        balance_report = analyze_balance(expert_bundle)
        if not isinstance(balance_report, dict):
            warnings.append("balance_report_invalid; using conservative balance report")
            balance_report = _conservative_balance_report()
    except Exception as exc:
        warnings.append(f"balance_analysis_failed; using conservative balance report: {exc}")
        balance_report = _conservative_balance_report()
    balance_reports.append(balance_report)

    try:
        deliberation_brief = build_deliberation_brief(
            query=original_query,
            expert_bundle=expert_bundle,
            balance_report=balance_report,
        )
        if not isinstance(deliberation_brief, dict):
            warnings.append("deliberation_brief_invalid; using empty deliberation brief")
            deliberation_brief = _empty_deliberation_brief(original_query)
        deliberation_brief = _enrich_brief_with_intake(deliberation_brief, query_intake)
    except Exception as exc:
        warnings.append(f"deliberation_brief_failed; using empty deliberation brief: {exc}")
        deliberation_brief = _enrich_brief_with_intake(_empty_deliberation_brief(original_query), query_intake)

    try:
        conflict_report = analyze_conflicts(
            query_intake,
            expert_bundle,
            deliberation_brief,
            model=model,
        )
        if not isinstance(conflict_report, dict):
            raise ValueError("invalid conflict report")
    except Exception as exc:
        warnings.append(f"conflict_analysis_failed; continuing_with_empty_conflict_report: {exc}")
        conflict_report = {
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
    conflict_reports.append(conflict_report)
    deliberation_brief = apply_conflict_report_to_brief(deliberation_brief, conflict_report)

    try:
        meta_decision = run_meta_moderator(
            query=original_query,
            expert_bundle=expert_bundle,
            balance_report=balance_report,
            deliberation_brief=deliberation_brief,
            conflict_report=conflict_report,
            model=model,
        )
        if not isinstance(meta_decision, dict):
            warnings.append("meta_moderator_invalid; continuing without process decision")
            meta_decision = {
                "decision": "SYNTHESIZE",
                "reason": "Meta moderator returned invalid output.",
                "missing_perspectives": [],
                "conflicts_to_resolve": [],
                "risks_to_address": [],
                "questions_to_answer": [],
                "next_actions": ["Proceed to planning."],
                "confidence": 0.0,
                "parse_warnings": ["meta_moderator_invalid"],
                "source": "orchestrator_fallback",
            }
    except Exception as exc:
        warnings.append(f"meta_moderator_failed; continuing with synthesis: {exc}")
        meta_decision = {
            "decision": "SYNTHESIZE",
            "reason": "Meta moderator failed; proceed with existing deliberation brief.",
            "missing_perspectives": [],
            "conflicts_to_resolve": [],
            "risks_to_address": [],
            "questions_to_answer": [],
            "next_actions": ["Proceed to planning."],
            "confidence": 0.0,
            "parse_warnings": ["meta_moderator_failed"],
            "source": "orchestrator_fallback",
        }

    meta_moderation_decisions.append(meta_decision)
    if _deliberation_needed(conflict_report, meta_decision):
        try:
            deliberation_bundle = run_deliberation_round(
                query=original_query,
                query_intake=query_intake,
                expert_bundle=expert_bundle,
                deliberation_brief=deliberation_brief,
                conflict_report=conflict_report,
                meta_decision=meta_decision,
                model=model,
            )
            if not isinstance(deliberation_bundle, dict):
                raise ValueError("invalid deliberation round bundle")
            deliberation_rounds.append(deliberation_bundle)
            expert_bundle = merge_deliberation_into_bundle(expert_bundle, deliberation_bundle)
            if not isinstance(expert_bundle, dict):
                raise ValueError("invalid deliberation merge result")

            balance_report = analyze_balance(expert_bundle)
            if not isinstance(balance_report, dict):
                warnings.append("deliberation_balance_invalid; using conservative balance report")
                balance_report = _conservative_balance_report()
            balance_reports.append(balance_report)
            deliberation_brief = build_deliberation_brief(
                query=original_query,
                expert_bundle=expert_bundle,
                balance_report=balance_report,
            )
            deliberation_brief = _enrich_brief_with_intake(deliberation_brief, query_intake)
            deliberation_brief = apply_deliberation_round_to_brief(deliberation_brief, deliberation_bundle)
            conflict_report = analyze_conflicts(
                query_intake,
                expert_bundle,
                deliberation_brief,
                model=model,
            )
            if not isinstance(conflict_report, dict):
                raise ValueError("invalid post-deliberation conflict report")
            conflict_reports.append(conflict_report)
            deliberation_brief = apply_conflict_report_to_brief(deliberation_brief, conflict_report)
        except Exception as exc:
            warnings.append(f"deliberation_round_failed; continuing_without_deliberation: {exc}")

    targeted_followup_needed = _targeted_followup_still_useful(
        meta_decision=meta_decision,
        balance_report=balance_report,
        deliberation_brief=deliberation_brief,
        conflict_report=conflict_report,
    )
    if targeted_followup_needed:
        try:
            targeted_roles = select_targeted_roles(
                meta_decision=meta_decision,
                balance_report=balance_report,
                deliberation_brief=deliberation_brief,
            )
            second_round_context = {
                "round": 2,
                "original_query": original_query,
                "cleaned_query": formalized_query,
                "query_intake": query_intake,
                "conflict_report": conflict_report,
                "deliberation_round": deliberation_rounds[-1] if deliberation_rounds else {},
                "intake_context": intake_context,
                "first_deliberation_brief": deliberation_brief,
                "meta_decision": meta_decision,
                "instruction": _AUTHORITATIVE_QUERY_INSTRUCTION,
                "follow_up_instruction": (
                    "Address gaps, conflicts, risks, and unanswered questions identified by "
                    "meta_moderator. Do not repeat round 1 unless necessary."
                ),
            }
            second_bundle = run_targeted_expert_round(
                query=original_query,
                roles=targeted_roles,
                context=second_round_context,
                model=model,
            )
            if not isinstance(second_bundle, dict):
                raise ValueError("invalid second expert round bundle")

            expert_rounds.append(second_bundle)
            expert_bundle = merge_expert_bundles(expert_bundle, second_bundle)
            balance_report = analyze_balance(expert_bundle)
            if not isinstance(balance_report, dict):
                warnings.append("second_round_balance_invalid; using conservative balance report")
                balance_report = _conservative_balance_report()
            balance_reports.append(balance_report)
            deliberation_brief = build_deliberation_brief(
                query=original_query,
                expert_bundle=expert_bundle,
                balance_report=balance_report,
            )
            deliberation_brief = _enrich_brief_with_intake(deliberation_brief, query_intake)
            if deliberation_rounds:
                deliberation_brief = apply_deliberation_round_to_brief(deliberation_brief, deliberation_rounds[-1])
            conflict_report = analyze_conflicts(
                query_intake,
                expert_bundle,
                deliberation_brief,
                model=model,
            )
            if not isinstance(conflict_report, dict):
                raise ValueError("invalid second conflict report")
            conflict_reports.append(conflict_report)
            deliberation_brief = apply_conflict_report_to_brief(deliberation_brief, conflict_report)
            deliberation_brief = apply_meta_decision_to_brief(deliberation_brief, meta_decision)
        except Exception as exc:
            warnings.append(f"second_expert_round_failed; continuing_with_first_round: {exc}")
            deliberation_brief = apply_meta_decision_to_brief(deliberation_brief, meta_decision)
    else:
        deliberation_brief = apply_meta_decision_to_brief(deliberation_brief, meta_decision)

    try:
        planner_context = _build_planner_context(query_intake, deliberation_brief, conflict_report)
        plan = develop_plan(original_query, context=planner_context, depth="detailed")
        if not isinstance(plan, dict):
            warnings.append("plan_invalid; stopping before moderation")
            plan = {"error": "plan_invalid"}
            plan_critique = {"error": "plan_invalid"}
            return _build_result(
                final_answer="",
                original_query=original_query,
                formalized_query=formalized_query,
                query_intake=query_intake,
                expert_bundle=expert_bundle,
                balance_report=balance_report,
                deliberation_brief=deliberation_brief,
                plan=plan,
                plan_critique=plan_critique,
                moderated_result={},
                warnings=warnings,
                meta_moderation_decisions=meta_moderation_decisions,
                expert_rounds=expert_rounds,
                balance_reports=balance_reports,
                conflict_reports=conflict_reports,
                deliberation_rounds=deliberation_rounds,
            )
    except Exception as exc:
        warnings.append(f"plan_generation_failed; stopping before moderation: {exc}")
        plan = {"error": "plan_generation_failed"}
        plan_critique = {"error": "plan_generation_failed"}
        return _build_result(
            final_answer="",
            original_query=original_query,
            formalized_query=formalized_query,
            query_intake=query_intake,
            expert_bundle=expert_bundle,
            balance_report=balance_report,
            deliberation_brief=deliberation_brief,
            plan=plan,
            plan_critique=plan_critique,
            moderated_result={},
            warnings=warnings,
            meta_moderation_decisions=meta_moderation_decisions,
            expert_rounds=expert_rounds,
            balance_reports=balance_reports,
            conflict_reports=conflict_reports,
            deliberation_rounds=deliberation_rounds,
        )

    try:
        critique_result = check_plan_and_act(plan, original_query, min_score=0.7)
        if not isinstance(critique_result, dict):
            warnings.append("plan_critique_invalid; continuing with empty critique")
            critique_result = {"status": "ready", "critique": {}}
    except Exception as exc:
        warnings.append(f"plan_critique_failed; continuing with empty critique: {exc}")
        critique_result = {"status": "ready", "critique": {}}

    plan_critique = critique_result.get("critique") if isinstance(critique_result.get("critique"), dict) else {}

    if critique_result.get("status") == "rejected":
        reason = critique_result.get("reason") or "plan rejected"
        warnings.append(f"plan_rejected; stopping before moderation: {reason}")
        return _build_result(
            final_answer="",
            original_query=original_query,
            formalized_query=formalized_query,
            query_intake=query_intake,
            expert_bundle=expert_bundle,
            balance_report=balance_report,
            deliberation_brief=deliberation_brief,
            plan=plan,
            plan_critique=plan_critique,
            moderated_result={},
            warnings=warnings,
            meta_moderation_decisions=meta_moderation_decisions,
            expert_rounds=expert_rounds,
            balance_reports=balance_reports,
            conflict_reports=conflict_reports,
            deliberation_rounds=deliberation_rounds,
        )

    try:
        moderated_result = run_moderated_loop(
            original_query,
            plan,
            plan_critique,
            expert_bundle=expert_bundle,
            balance_report=balance_report,
            deliberation_brief=deliberation_brief,
            max_iters=max_iters,
            model=model,
        )
        if not isinstance(moderated_result, dict):
            warnings.append("moderated_result_invalid; returning empty final_answer")
            moderated_result = {}
    except Exception as exc:
        warnings.append(f"moderated_loop_failed; returning empty final_answer: {exc}")
        moderated_result = {}

    final_answer = moderated_result.get("final_answer") if isinstance(moderated_result, dict) else ""
    if not isinstance(final_answer, str):
        final_answer = ""

    return _build_result(
        final_answer=final_answer,
        original_query=original_query,
        formalized_query=formalized_query,
        query_intake=query_intake,
        expert_bundle=expert_bundle,
        balance_report=balance_report,
        deliberation_brief=deliberation_brief,
        plan=plan,
        plan_critique=plan_critique,
        moderated_result=moderated_result,
        warnings=warnings,
        meta_moderation_decisions=meta_moderation_decisions,
        expert_rounds=expert_rounds,
        balance_reports=balance_reports,
        conflict_reports=conflict_reports,
        deliberation_rounds=deliberation_rounds,
    )
