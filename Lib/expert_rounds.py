"""Helpers for targeted follow-up expert rounds."""

from __future__ import annotations

from Lib.expert_agent import run_expert
from Lib.expert_roles import BASE_EXPERT_ROLES, ExpertRole


def _string_items(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _unique_roles(roles: list[ExpertRole]) -> list[ExpertRole]:
    seen: set[str] = set()
    out: list[ExpertRole] = []
    for role in roles:
        if role.key in seen:
            continue
        seen.add(role.key)
        out.append(role)
    return out


def _role_by_key(key: str) -> ExpertRole | None:
    for role in BASE_EXPERT_ROLES:
        if role.key == key:
            return role
    return None


def _roles_by_perspective(tag: str, dynamic_roles: list[ExpertRole] | None = None) -> list[ExpertRole]:
    roles = list(BASE_EXPERT_ROLES) + list(dynamic_roles or [])
    return [role for role in roles if role.perspective_tag == tag]


def _dynamic_roles_from_context_text(dynamic_roles: list[ExpertRole] | None, *contexts: dict | None) -> list[ExpertRole]:
    if not dynamic_roles:
        return []
    parts: list[str] = []
    for context in contexts:
        if isinstance(context, dict):
            parts.append(str(context).lower())
    text = " ".join(parts)
    selected: list[ExpertRole] = []
    for role in dynamic_roles:
        if role.key.lower() in text or role.perspective_tag.lower() in text or role.name.lower() in text:
            selected.append(role)
    return selected


def select_targeted_roles(
    meta_decision: dict,
    balance_report: dict,
    deliberation_brief: dict,
    dynamic_roles: list[ExpertRole] | None = None,
    conflict_report: dict | None = None,
) -> list[ExpertRole]:
    """Select safe existing base roles for a second expert round."""
    selected: list[ExpertRole] = []

    missing = []
    if isinstance(balance_report, dict):
        missing.extend(_string_items(balance_report.get("missing_perspectives")))
    if isinstance(meta_decision, dict):
        missing.extend(_string_items(meta_decision.get("missing_perspectives")))

    for perspective in missing:
        selected.extend(_roles_by_perspective(perspective, dynamic_roles=dynamic_roles))
        for role in dynamic_roles or []:
            if perspective == role.key:
                selected.append(role)

    selected.extend(_dynamic_roles_from_context_text(dynamic_roles, meta_decision, deliberation_brief, conflict_report))

    if isinstance(meta_decision, dict) and _string_items(meta_decision.get("risks_to_address")):
        risk_manager = _role_by_key("risk_manager")
        if risk_manager:
            selected.append(risk_manager)

    if isinstance(meta_decision, dict) and _string_items(meta_decision.get("questions_to_answer")):
        user_advocate = _role_by_key("user_advocate")
        if user_advocate:
            selected.append(user_advocate)

    if isinstance(deliberation_brief, dict) and _string_items(deliberation_brief.get("expert_questions")):
        user_advocate = _role_by_key("user_advocate")
        if user_advocate:
            selected.append(user_advocate)

    selected = _unique_roles(selected)
    if selected:
        return selected

    if dynamic_roles and any(
        _string_items(value)
        for value in (
            meta_decision.get("missing_perspectives") if isinstance(meta_decision, dict) else [],
            meta_decision.get("conflicts_to_resolve") if isinstance(meta_decision, dict) else [],
            meta_decision.get("risks_to_address") if isinstance(meta_decision, dict) else [],
            conflict_report.get("blind_spots") if isinstance(conflict_report, dict) else [],
            conflict_report.get("unresolved_tradeoffs") if isinstance(conflict_report, dict) else [],
        )
    ):
        return _unique_roles(list(dynamic_roles))

    fallback = [_role_by_key("risk_manager"), _role_by_key("strategist")]
    return [role for role in fallback if role is not None]


def _fallback_contribution(role: ExpertRole) -> dict:
    return {
        "role_key": role.key,
        "perspective_tag": role.perspective_tag,
        "insights": [],
        "risks": ["expert_execution_failed"],
        "questions": [],
        "recommendations": [],
        "confidence": 0.0,
    }


def _bundle_from_roles_and_contributions(roles: list[dict], contributions: list[dict]) -> dict:
    recommendations: list[str] = []
    risks: list[str] = []
    questions: list[str] = []
    perspective_counts: dict[str, int] = {}

    for contribution in contributions:
        if not isinstance(contribution, dict):
            continue
        tag = contribution.get("perspective_tag")
        if isinstance(tag, str) and tag.strip():
            perspective_counts[tag] = perspective_counts.get(tag, 0) + 1
        recommendations.extend(_string_items(contribution.get("recommendations")))
        risks.extend(_string_items(contribution.get("risks")))
        questions.extend(_string_items(contribution.get("questions")))

    return {
        "roles": roles,
        "contributions": contributions,
        "synthesis": {
            "recommendations": _unique_keep_order(recommendations),
            "risks": _unique_keep_order(risks),
            "questions": _unique_keep_order(questions),
            "perspective_counts": perspective_counts,
        },
    }


def run_targeted_expert_round(
    query: str,
    roles: list[ExpertRole],
    context: dict,
    model: str = "deepseek-chat",
) -> dict:
    """Run selected experts sequentially and return an expert bundle."""
    dynamic_role_views = {}
    if isinstance(context, dict) and isinstance(context.get("dynamic_role_views"), list):
        for view in context.get("dynamic_role_views", []):
            if isinstance(view, dict) and isinstance(view.get("key"), str):
                dynamic_role_views[view["key"]] = view

    role_views = []
    for role in roles:
        source_view = dynamic_role_views.get(role.key, {})
        view = {
            "key": role.key,
            "name": role.name,
            "perspective_tag": role.perspective_tag,
        }
        if role.key in dynamic_role_views:
            view["dynamic"] = True
            if isinstance(source_view.get("why_needed"), str):
                view["why_needed"] = source_view.get("why_needed", "")
        role_views.append(view)
    contributions: list[dict] = []

    for role in roles:
        try:
            contribution = run_expert(role=role, query=query, context=context, model=model)
            if not isinstance(contribution, dict):
                raise ValueError("invalid contribution format")
        except Exception:
            contribution = _fallback_contribution(role)
        contributions.append(contribution)

    return _bundle_from_roles_and_contributions(role_views, contributions)


def merge_expert_bundles(first: dict, second: dict) -> dict:
    """Append expert rounds and recompute synthesis from all contributions."""
    first_roles = first.get("roles") if isinstance(first, dict) and isinstance(first.get("roles"), list) else []
    second_roles = second.get("roles") if isinstance(second, dict) and isinstance(second.get("roles"), list) else []
    first_contribs = (
        first.get("contributions") if isinstance(first, dict) and isinstance(first.get("contributions"), list) else []
    )
    second_contribs = (
        second.get("contributions") if isinstance(second, dict) and isinstance(second.get("contributions"), list) else []
    )

    return _bundle_from_roles_and_contributions(
        roles=list(first_roles) + list(second_roles),
        contributions=list(first_contribs) + list(second_contribs),
    )
