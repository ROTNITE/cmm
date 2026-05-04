"""Structured expert deliberation round for CMM."""

from __future__ import annotations

import json
from typing import Any

from Lib.AI_request import send_to_AI
from Lib.expert_roles import BASE_EXPERT_ROLES, ExpertRole
from Lib.json_utils import safe_json_loads, to_number, to_string_list


_ROLE_BY_KEY = {role.key: role for role in BASE_EXPERT_ROLES}
_ROLES_BY_PERSPECTIVE = {role.perspective_tag: role for role in BASE_EXPERT_ROLES}
_IMPLEMENTATION_MARKERS = (
    "implementation",
    "technical",
    "engineering",
    "engineer",
    "system",
    "integration",
    "deploy",
    "code",
    "тех",
    "инжен",
    "реализ",
    "внедр",
)
_STRATEGY_MARKERS = (
    "strategy",
    "priority",
    "roadmap",
    "scope",
    "tradeoff",
    "trade-off",
    "цель",
    "стратег",
    "приоритет",
    "план",
)


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _unique_strings(items: list[str], max_items: int = 20) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
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


def _unique_roles(roles: list[ExpertRole], max_roles: int) -> list[ExpertRole]:
    out: list[ExpertRole] = []
    seen: set[str] = set()
    for role in roles:
        if not isinstance(role, ExpertRole) or role.key in seen:
            continue
        seen.add(role.key)
        out.append(role)
        if len(out) >= max_roles:
            break
    return out


def _role_from_value(value: Any) -> ExpertRole | None:
    if not isinstance(value, str):
        return None
    key = value.strip()
    if not key:
        return None
    return _ROLE_BY_KEY.get(key) or _ROLES_BY_PERSPECTIVE.get(key)


def _add_role(selected: list[ExpertRole], key: str) -> None:
    role = _ROLE_BY_KEY.get(key)
    if role:
        selected.append(role)


def _text_has_any(items: list[str], markers: tuple[str, ...]) -> bool:
    text = " ".join(items).lower()
    return any(marker in text for marker in markers)


def _contributions(expert_bundle: dict | None) -> list[dict]:
    return [item for item in _as_list(_as_dict(expert_bundle).get("contributions")) if isinstance(item, dict)]


def _role_view(role: ExpertRole) -> dict:
    return {
        "key": role.key,
        "name": role.name,
        "perspective_tag": role.perspective_tag,
    }


def _contribution_role_key(contribution: dict) -> str:
    role_key = contribution.get("role_key")
    if isinstance(role_key, str) and role_key.strip():
        return role_key.strip()
    perspective = contribution.get("perspective_tag")
    if isinstance(perspective, str) and perspective.strip():
        role = _role_from_value(perspective)
        if role:
            return role.key
    return ""


def select_deliberation_roles(
    expert_bundle: dict,
    conflict_report: dict,
    meta_decision: dict | None = None,
    max_roles: int = 4,
) -> list[ExpertRole]:
    """Select safe base roles for a structured deliberation round."""
    selected: list[ExpertRole] = []
    conflict = _as_dict(conflict_report)
    meta = _as_dict(meta_decision)

    for disagreement in _as_list(conflict.get("disagreements")):
        if not isinstance(disagreement, dict):
            continue
        for position in _as_list(disagreement.get("positions")):
            if not isinstance(position, dict):
                continue
            role = _role_from_value(position.get("role"))
            if role:
                selected.append(role)

    for tradeoff in _as_list(conflict.get("unresolved_tradeoffs")):
        if not isinstance(tradeoff, dict):
            continue
        for role_value in _as_list(tradeoff.get("roles_involved")):
            role = _role_from_value(role_value)
            if role:
                selected.append(role)

    if _as_list(conflict.get("premature_consensus_risks")):
        _add_role(selected, "risk_manager")
        _add_role(selected, "strategist")

    if _as_list(conflict.get("blind_spots")) or _as_list(conflict.get("questions_for_next_round")):
        _add_role(selected, "user_advocate")
        _add_role(selected, "risk_manager")

    risks = to_string_list(meta.get("risks_to_address"), max_items=10)
    questions = to_string_list(meta.get("questions_to_answer"), max_items=10)
    conflicts = to_string_list(meta.get("conflicts_to_resolve"), max_items=10)
    if risks:
        _add_role(selected, "risk_manager")
    if questions:
        _add_role(selected, "user_advocate")
    if _text_has_any(conflicts + risks + questions, _IMPLEMENTATION_MARKERS):
        _add_role(selected, "engineer")
    if _text_has_any(conflicts + risks + questions, _STRATEGY_MARKERS):
        _add_role(selected, "strategist")

    selected = _unique_roles(selected, max_roles=max_roles)
    if selected:
        return selected

    contribution_roles = []
    for contribution in _contributions(expert_bundle):
        role = _role_from_value(_contribution_role_key(contribution))
        if role:
            contribution_roles.append(role)
    selected = _unique_roles(contribution_roles, max_roles=min(max_roles, 3))
    if selected:
        return selected

    fallback = [_ROLE_BY_KEY["risk_manager"], _ROLE_BY_KEY["strategist"]]
    return _unique_roles(fallback, max_roles=max_roles)


def build_other_roles_synthesis(expert_bundle: dict, current_role_key: str) -> dict:
    """Build compact synthesis of other expert positions for one role."""
    others: list[dict] = []
    recommendations: list[str] = []
    risks: list[str] = []
    questions: list[str] = []

    for contribution in _contributions(expert_bundle):
        role_key = _contribution_role_key(contribution)
        if role_key == current_role_key:
            continue
        recs = to_string_list(contribution.get("recommendations"), max_items=4)
        role_risks = to_string_list(contribution.get("risks"), max_items=4)
        role_questions = to_string_list(contribution.get("questions"), max_items=4)
        insights = to_string_list(contribution.get("insights"), max_items=4)
        others.append(
            {
                "role_key": role_key or "unknown",
                "perspective_tag": contribution.get("perspective_tag") or "",
                "insights": insights,
                "recommendations": recs,
                "risks": role_risks,
                "questions": role_questions,
            }
        )
        recommendations.extend(recs)
        risks.extend(role_risks)
        questions.extend(role_questions)

    return {
        "other_contributions": others[:6],
        "recommendations": _unique_strings(recommendations, max_items=10),
        "risks": _unique_strings(risks, max_items=10),
        "questions": _unique_strings(questions, max_items=10),
    }


def _own_contribution(expert_bundle: dict, role_key: str) -> dict:
    for contribution in _contributions(expert_bundle):
        if _contribution_role_key(contribution) == role_key:
            return contribution
    return {}


def normalize_deliberation_response(
    role: ExpertRole,
    payload: dict | None,
    raw: str = "",
    warning: str | None = None,
) -> dict:
    """Normalize one deliberation model response into the stable schema."""
    if not isinstance(payload, dict):
        warnings = [warning or "deliberation_json_parse_failed"]
        return {
            "role_key": role.key,
            "perspective_tag": role.perspective_tag,
            "agreements": [],
            "disagreements": [],
            "missed_by_others": [],
            "revised_recommendations": [],
            "new_risks": ["deliberation_response_failed"],
            "questions_for_group": [],
            "confidence_change": 0.0,
            "parse_warnings": warnings,
            "source": "fallback",
        }

    parse_warnings = [warning] if warning else []
    return {
        "role_key": role.key,
        "perspective_tag": role.perspective_tag,
        "agreements": to_string_list(payload.get("agreements"), max_items=8),
        "disagreements": to_string_list(payload.get("disagreements"), max_items=8),
        "missed_by_others": to_string_list(payload.get("missed_by_others"), max_items=8),
        "revised_recommendations": to_string_list(payload.get("revised_recommendations"), max_items=8),
        "new_risks": to_string_list(payload.get("new_risks"), max_items=8),
        "questions_for_group": to_string_list(payload.get("questions_for_group"), max_items=8),
        "confidence_change": to_number(payload.get("confidence_change"), default=0.0, min_value=-1.0, max_value=1.0),
        "parse_warnings": parse_warnings,
        "source": "model",
    }


def deliberation_bundle_to_synthesis(deliberation_responses: list[dict]) -> dict:
    """Aggregate deliberation responses into a compact synthesis."""
    agreements: list[str] = []
    disagreements: list[str] = []
    revised: list[str] = []
    risks: list[str] = []
    questions: list[str] = []

    for response in deliberation_responses:
        if not isinstance(response, dict):
            continue
        agreements.extend(to_string_list(response.get("agreements"), max_items=8))
        disagreements.extend(to_string_list(response.get("disagreements"), max_items=8))
        revised.extend(to_string_list(response.get("revised_recommendations"), max_items=8))
        risks.extend(to_string_list(response.get("new_risks"), max_items=8))
        questions.extend(to_string_list(response.get("questions_for_group"), max_items=8))

    return {
        "agreements": _unique_strings(agreements, max_items=20),
        "disagreements": _unique_strings(disagreements, max_items=20),
        "revised_recommendations": _unique_strings(revised, max_items=20),
        "new_risks": _unique_strings(risks, max_items=20),
        "questions_for_group": _unique_strings(questions, max_items=20),
    }


def _run_role_deliberation(
    *,
    role: ExpertRole,
    query: str,
    query_intake: dict | None,
    expert_bundle: dict,
    deliberation_brief: dict,
    conflict_report: dict,
    meta_decision: dict | None,
    model: str,
) -> dict:
    system_prompt = (
        f"{role.system_prompt}\n\n"
        "You are participating in a Collective Meta-Moderation deliberation round.\n"
        "You are not writing the final answer.\n"
        "You must respond to other experts' positions.\n"
        "Original query is authoritative. Cleaned/formalized query is helper text only.\n"
        "Do not ignore constraints from original_query.\n"
        "Return strict JSON only."
    )
    state = {
        "role": _role_view(role),
        "original_query": query,
        "query_intake": query_intake or {},
        "own_first_contribution": _own_contribution(expert_bundle, role.key),
        "other_roles_synthesis": build_other_roles_synthesis(expert_bundle, role.key),
        "conflict_report": conflict_report or {},
        "deliberation_brief": deliberation_brief or {},
        "meta_decision": meta_decision or {},
        "schema": {
            "agreements": ["string"],
            "disagreements": ["string"],
            "missed_by_others": ["string"],
            "revised_recommendations": ["string"],
            "new_risks": ["string"],
            "questions_for_group": ["string"],
            "confidence_change": -1.0,
        },
    }
    user_prompt = (
        "Review this CMM deliberation state and answer as your expert role.\n"
        "1. Where do you agree with other experts?\n"
        "2. Where do you disagree?\n"
        "3. What did other experts miss?\n"
        "4. What would you revise in your own recommendations after seeing the group synthesis?\n"
        "5. What new risks or group questions should be carried forward?\n\n"
        + json.dumps(state, ensure_ascii=False)
    )
    try:
        raw = send_to_AI(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temp=0.25,
            tokens=550,
            model=model,
        )
        raw_text = raw if isinstance(raw, str) else ""
        parsed = safe_json_loads(raw_text)
        if not parsed:
            return normalize_deliberation_response(role, None, raw=raw_text)
        return normalize_deliberation_response(role, parsed, raw=raw_text)
    except Exception as exc:
        return normalize_deliberation_response(role, None, warning=f"deliberation_model_failed: {exc}")


def run_deliberation_round(
    *,
    query: str,
    query_intake: dict | None,
    expert_bundle: dict,
    deliberation_brief: dict,
    conflict_report: dict,
    meta_decision: dict | None = None,
    max_roles: int = 4,
    model: str = "deepseek-chat",
) -> dict:
    """Run selected experts through one structured deliberation round."""
    roles = select_deliberation_roles(
        expert_bundle=expert_bundle,
        conflict_report=conflict_report,
        meta_decision=meta_decision,
        max_roles=max_roles,
    )
    responses: list[dict] = []
    for role in roles:
        responses.append(
            _run_role_deliberation(
                role=role,
                query=query,
                query_intake=query_intake,
                expert_bundle=expert_bundle,
                deliberation_brief=deliberation_brief,
                conflict_report=conflict_report,
                meta_decision=meta_decision,
                model=model,
            )
        )

    return {
        "type": "deliberation_round",
        "roles": [_role_view(role) for role in roles],
        "responses": responses,
        "synthesis": deliberation_bundle_to_synthesis(responses),
    }


def _bundle_from_parts(roles: list[dict], contributions: list[dict]) -> dict:
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
        recommendations.extend(to_string_list(contribution.get("recommendations"), max_items=10))
        risks.extend(to_string_list(contribution.get("risks"), max_items=10))
        questions.extend(to_string_list(contribution.get("questions"), max_items=10))

    return {
        "roles": list(roles),
        "contributions": list(contributions),
        "synthesis": {
            "recommendations": _unique_strings(recommendations, max_items=40),
            "risks": _unique_strings(risks, max_items=40),
            "questions": _unique_strings(questions, max_items=40),
            "perspective_counts": perspective_counts,
        },
    }


def merge_deliberation_into_bundle(
    expert_bundle: dict,
    deliberation_bundle: dict,
) -> dict:
    """Append deliberation-derived contributions to the expert bundle."""
    bundle = _as_dict(expert_bundle)
    deliberation = _as_dict(deliberation_bundle)
    roles = list(_as_list(bundle.get("roles")))
    known_role_keys = {
        role.get("key")
        for role in roles
        if isinstance(role, dict) and isinstance(role.get("key"), str)
    }
    for role in _as_list(deliberation.get("roles")):
        if not isinstance(role, dict):
            continue
        key = role.get("key")
        if isinstance(key, str) and key not in known_role_keys:
            roles.append(role)
            known_role_keys.add(key)

    contributions = list(_as_list(bundle.get("contributions")))
    for response in _as_list(deliberation.get("responses")):
        if not isinstance(response, dict):
            continue
        insights = []
        insights.extend(to_string_list(response.get("agreements"), max_items=8))
        insights.extend(to_string_list(response.get("disagreements"), max_items=8))
        insights.extend(to_string_list(response.get("missed_by_others"), max_items=8))
        confidence = 0.5 + to_number(
            response.get("confidence_change"),
            default=0.0,
            min_value=-1.0,
            max_value=1.0,
        )
        if confidence < 0.0:
            confidence = 0.0
        if confidence > 1.0:
            confidence = 1.0
        contributions.append(
            {
                "role_key": response.get("role_key") or "unknown",
                "perspective_tag": response.get("perspective_tag") or "unknown",
                "contribution_type": "deliberation_response",
                "insights": _unique_strings(insights, max_items=20),
                "risks": to_string_list(response.get("new_risks"), max_items=8),
                "questions": to_string_list(response.get("questions_for_group"), max_items=8),
                "recommendations": to_string_list(response.get("revised_recommendations"), max_items=8),
                "confidence": confidence,
            }
        )

    return _bundle_from_parts(roles, contributions)
