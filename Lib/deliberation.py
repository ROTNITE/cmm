"""Utilities for compact expert-panel synthesis."""

from __future__ import annotations

from typing import Any


def _as_string_list(value: Any, max_items: int) -> list[str]:
    if not isinstance(value, list):
        return []

    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= max_items:
            break
    return out


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_dict_list(value: Any, max_items: int) -> list[dict]:
    out: list[dict] = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict):
            out.append(dict(item))
        if len(out) >= max_items:
            break
    return out


def build_deliberation_brief(
    query: str,
    expert_bundle: dict | None,
    balance_report: dict | None,
) -> dict:
    """Build a stable, compact dict passed through planning and moderation."""
    bundle = _as_dict(expert_bundle)
    balance = _as_dict(balance_report)
    synthesis = _as_dict(bundle.get("synthesis"))

    recommendations = _as_string_list(synthesis.get("recommendations"), max_items=10)
    risks = _as_string_list(synthesis.get("risks"), max_items=10)
    questions = _as_string_list(synthesis.get("questions"), max_items=8)
    balance_notes = _as_string_list(balance.get("notes"), max_items=6)
    balance_quality = _as_dict(balance.get("argument_quality"))
    balance_blind_spots = _as_string_list(balance.get("blind_spots"), max_items=8)
    constraint_coverage = _as_dict_list(balance.get("constraint_coverage"), max_items=8)
    stakeholder_coverage = _as_dict_list(balance.get("stakeholder_coverage"), max_items=8)
    recommended_balance_action = balance.get("recommended_action")
    if recommended_balance_action not in {"SYNTHESIZE", "DEEPEN", "ADD_EXPERT"}:
        recommended_balance_action = "SYNTHESIZE"

    perspective_counts = synthesis.get("perspective_counts")
    if not isinstance(perspective_counts, dict):
        perspective_counts = {}

    missing_perspectives = _as_string_list(balance.get("missing_perspectives"), max_items=8)
    dominant_perspective_found = bool(balance.get("dominant_perspective_found", False))

    must_address = []
    must_address.extend(risks[:4])
    must_address.extend(recommendations[:4])
    if missing_perspectives:
        must_address.append(
            "Address missing expert perspectives: " + ", ".join(missing_perspectives)
        )
    if dominant_perspective_found:
        dominant = balance.get("dominant_perspective") or "unknown"
        must_address.append(f"Mitigate dominant perspective: {dominant}")
    for item in balance_blind_spots[:4]:
        must_address.append("Address balance blind spot: " + item)

    brief = {
        "summary": (
            f"Expert deliberation for query: {str(query or '').strip()[:240]}"
        ),
        "expert_recommendations": recommendations,
        "expert_risks": risks,
        "expert_questions": questions,
        "perspective_counts": perspective_counts,
        "missing_perspectives": missing_perspectives,
        "dominant_perspective_found": dominant_perspective_found,
        "balance_notes": balance_notes,
        "balance_quality": balance_quality,
        "constraint_coverage": constraint_coverage,
        "stakeholder_coverage": stakeholder_coverage,
        "balance_blind_spots": balance_blind_spots,
        "recommended_balance_action": recommended_balance_action,
        "must_address": _as_string_list(must_address, max_items=12),
    }

    return brief


def apply_meta_decision_to_brief(deliberation_brief: dict, meta_decision: dict) -> dict:
    """Enrich deliberation brief with deferred meta-moderator actions."""
    brief = dict(deliberation_brief) if isinstance(deliberation_brief, dict) else {}
    decision = meta_decision.get("decision") if isinstance(meta_decision, dict) else None

    if decision not in {"DEEPEN", "ADD_EXPERT"}:
        return brief

    additions: list[str] = []
    additions.extend(_as_string_list(meta_decision.get("risks_to_address"), max_items=10))
    additions.extend(_as_string_list(meta_decision.get("questions_to_answer"), max_items=10))
    additions.extend(_as_string_list(meta_decision.get("conflicts_to_resolve"), max_items=10))

    must_address = _as_string_list(brief.get("must_address"), max_items=20)
    for item in additions:
        if item not in must_address:
            must_address.append(item)
    brief["must_address"] = must_address[:20]

    notes = _as_string_list(brief.get("meta_process_notes"), max_items=10)
    reason = meta_decision.get("reason")
    if isinstance(reason, str) and reason.strip():
        notes.append(f"{decision}: {reason.strip()}")
    for action in _as_string_list(meta_decision.get("next_actions"), max_items=5):
        notes.append(action)
    brief["meta_process_notes"] = notes[:12]

    return brief


def _compact_disagreements(value: Any, max_items: int) -> list[dict]:
    out: list[dict] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        issue = item.get("issue")
        if not isinstance(issue, str) or not issue.strip():
            continue
        out.append(
            {
                "issue": issue.strip(),
                "severity": item.get("severity") if item.get("severity") in {"low", "medium", "high"} else "medium",
                "positions": item.get("positions") if isinstance(item.get("positions"), list) else [],
            }
        )
        if len(out) >= max_items:
            break
    return out


def _compact_agreements(value: Any, max_items: int) -> list[dict]:
    out: list[dict] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        claim = item.get("claim")
        if not isinstance(claim, str) or not claim.strip():
            continue
        out.append(
            {
                "claim": claim.strip(),
                "supporting_roles": _as_string_list(item.get("supporting_roles"), max_items=6),
            }
        )
        if len(out) >= max_items:
            break
    return out


def _compact_tradeoffs(value: Any, max_items: int) -> list[dict]:
    out: list[dict] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        tradeoff = item.get("tradeoff")
        if not isinstance(tradeoff, str) or not tradeoff.strip():
            continue
        why = item.get("why_it_matters")
        out.append(
            {
                "tradeoff": tradeoff.strip(),
                "why_it_matters": why.strip() if isinstance(why, str) and why.strip() else "",
                "roles_involved": _as_string_list(item.get("roles_involved"), max_items=6),
            }
        )
        if len(out) >= max_items:
            break
    return out


def apply_conflict_report_to_brief(deliberation_brief: dict, conflict_report: dict) -> dict:
    """Compact semantic conflict report into deliberation brief for planning/moderation."""
    brief = dict(deliberation_brief) if isinstance(deliberation_brief, dict) else {}
    report = conflict_report if isinstance(conflict_report, dict) else {}

    agreements = _compact_agreements(report.get("agreements"), max_items=5)
    disagreements = _compact_disagreements(report.get("disagreements"), max_items=5)
    tradeoffs = _compact_tradeoffs(report.get("unresolved_tradeoffs"), max_items=5)
    premature = _as_string_list(report.get("premature_consensus_risks"), max_items=5)
    blind_spots = _as_string_list(report.get("blind_spots"), max_items=5)
    questions = _as_string_list(report.get("questions_for_next_round"), max_items=5)

    brief["agreements"] = agreements
    brief["disagreements"] = disagreements
    brief["unresolved_tradeoffs"] = tradeoffs
    brief["premature_consensus_risks"] = premature
    brief["blind_spots"] = blind_spots
    brief["questions_for_next_round"] = questions

    must_address = _as_string_list(brief.get("must_address"), max_items=30)
    for item in disagreements:
        if item.get("severity") in {"medium", "high"}:
            must_address.append("Resolve disagreement: " + item["issue"])
    for item in tradeoffs:
        must_address.append("Address trade-off: " + item["tradeoff"])
    for item in blind_spots:
        must_address.append("Address blind spot: " + item)
    for item in questions:
        must_address.append("Answer next-round question: " + item)
    for item in premature:
        must_address.append("Check premature consensus risk: " + item)

    brief["must_address"] = _as_string_list(must_address, max_items=20)
    return brief


def apply_deliberation_round_to_brief(deliberation_brief: dict, deliberation_bundle: dict) -> dict:
    """Compact structured deliberation output into downstream brief fields."""
    brief = dict(deliberation_brief) if isinstance(deliberation_brief, dict) else {}
    bundle = deliberation_bundle if isinstance(deliberation_bundle, dict) else {}
    synthesis = _as_dict(bundle.get("synthesis"))

    agreements = _as_string_list(synthesis.get("agreements"), max_items=5)
    disagreements = _as_string_list(synthesis.get("disagreements"), max_items=5)
    revised = _as_string_list(synthesis.get("revised_recommendations"), max_items=8)
    risks = _as_string_list(synthesis.get("new_risks"), max_items=8)
    questions = _as_string_list(synthesis.get("questions_for_group"), max_items=8)

    brief["deliberation_agreements"] = agreements
    brief["deliberation_disagreements"] = disagreements
    brief["revised_recommendations"] = revised
    brief["new_risks"] = risks
    brief["questions_for_group"] = questions

    expert_recommendations = _as_string_list(brief.get("expert_recommendations"), max_items=20)
    for item in revised:
        if item not in expert_recommendations:
            expert_recommendations.append(item)
    brief["expert_recommendations"] = expert_recommendations[:20]

    expert_risks = _as_string_list(brief.get("expert_risks"), max_items=20)
    for item in risks:
        if item not in expert_risks:
            expert_risks.append(item)
    brief["expert_risks"] = expert_risks[:20]

    expert_questions = _as_string_list(brief.get("expert_questions"), max_items=16)
    for item in questions:
        if item not in expert_questions:
            expert_questions.append(item)
    brief["expert_questions"] = expert_questions[:16]

    must_address = _as_string_list(brief.get("must_address"), max_items=30)
    for item in disagreements:
        must_address.append("Resolve deliberation disagreement: " + item)
    for item in risks:
        must_address.append("Address deliberation risk: " + item)
    for item in questions:
        must_address.append("Answer group question: " + item)
    brief["must_address"] = _as_string_list(must_address, max_items=24)
    return brief
