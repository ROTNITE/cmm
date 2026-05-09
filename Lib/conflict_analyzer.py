"""Semantic conflict and consensus analysis for CMM expert bundles."""

from __future__ import annotations

import json
import re
from typing import Any

from Lib.config import get_stage_settings
from Lib.json_retry import call_json_model
from Lib.json_utils import to_number, to_string_list


_SEVERITIES = {"low", "medium", "high"}


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"[^\w\sа-яё]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _role_name(contribution: dict) -> str:
    role = contribution.get("role_key")
    if isinstance(role, str) and role.strip():
        return role.strip()
    tag = contribution.get("perspective_tag")
    if isinstance(tag, str) and tag.strip():
        return tag.strip()
    return "unknown"


def _contributions(expert_bundle: dict | None) -> list[dict]:
    bundle = _as_dict(expert_bundle)
    return [item for item in _as_list(bundle.get("contributions")) if isinstance(item, dict)]


def _strings_from_contribution(contribution: dict, key: str) -> list[str]:
    return to_string_list(contribution.get(key), max_items=8)


def _normalize_positions(value: Any) -> list[dict]:
    out: list[dict] = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        position = item.get("position")
        if not isinstance(role, str) or not role.strip():
            continue
        if not isinstance(position, str) or not position.strip():
            continue
        out.append({"role": role.strip(), "position": position.strip()})
        if len(out) >= 6:
            break
    return out


def _normalize_agreements(value: Any) -> list[dict]:
    out: list[dict] = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        claim = item.get("claim")
        if not isinstance(claim, str) or not claim.strip():
            continue
        roles = to_string_list(item.get("supporting_roles"), max_items=8)
        out.append({"claim": claim.strip(), "supporting_roles": roles})
        if len(out) >= 8:
            break
    return out


def _normalize_disagreements(value: Any) -> list[dict]:
    out: list[dict] = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        issue = item.get("issue")
        if not isinstance(issue, str) or not issue.strip():
            continue
        severity = item.get("severity")
        if not isinstance(severity, str) or severity.strip().lower() not in _SEVERITIES:
            severity = "medium"
        out.append(
            {
                "issue": issue.strip(),
                "positions": _normalize_positions(item.get("positions")),
                "severity": str(severity).strip().lower(),
            }
        )
        if len(out) >= 8:
            break
    return out


def _normalize_tradeoffs(value: Any) -> list[dict]:
    out: list[dict] = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        tradeoff = item.get("tradeoff")
        why = item.get("why_it_matters")
        if not isinstance(tradeoff, str) or not tradeoff.strip():
            continue
        out.append(
            {
                "tradeoff": tradeoff.strip(),
                "why_it_matters": why.strip() if isinstance(why, str) and why.strip() else "",
                "roles_involved": to_string_list(item.get("roles_involved"), max_items=8),
            }
        )
        if len(out) >= 8:
            break
    return out


def _empty_report(
    source: str,
    warnings: list[str] | None = None,
    confidence: float = 0.0,
    *,
    json_attempts: int = 0,
    raw: str = "",
) -> dict:
    return {
        "agreements": [],
        "disagreements": [],
        "unresolved_tradeoffs": [],
        "premature_consensus_risks": [],
        "blind_spots": [],
        "minority_positions": [],
        "questions_for_next_round": [],
        "confidence": confidence,
        "parse_warnings": warnings or [],
        "json_attempts": int(json_attempts or 0),
        "raw": str(raw or "")[:2000],
        "source": source,
    }


def _normalize_report(
    payload: dict | None,
    source: str,
    warnings: list[str] | None = None,
    *,
    json_attempts: int = 1,
    raw: str = "",
) -> dict | None:
    if not isinstance(payload, dict):
        return None
    return {
        "agreements": _normalize_agreements(payload.get("agreements")),
        "disagreements": _normalize_disagreements(payload.get("disagreements")),
        "unresolved_tradeoffs": _normalize_tradeoffs(payload.get("unresolved_tradeoffs")),
        "premature_consensus_risks": to_string_list(payload.get("premature_consensus_risks"), max_items=10),
        "blind_spots": to_string_list(payload.get("blind_spots"), max_items=10),
        "minority_positions": to_string_list(payload.get("minority_positions"), max_items=10),
        "questions_for_next_round": to_string_list(payload.get("questions_for_next_round"), max_items=10),
        "confidence": to_number(payload.get("confidence"), default=0.0, max_value=1.0),
        "parse_warnings": warnings or [],
        "json_attempts": int(json_attempts or 0),
        "raw": str(raw or "")[:2000],
        "source": source,
    }


def _query_is_complex(query_intake: dict | None) -> bool:
    intake = _as_dict(query_intake)
    complexity = str(intake.get("complexity") or "").lower()
    risk = str(intake.get("risk_level") or "").lower()
    return complexity in {"moderate", "complex"} or risk == "high"


def _role_items(contributions: list[dict], key: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for contribution in contributions:
        role = _role_name(contribution)
        items = _strings_from_contribution(contribution, key)
        if items:
            out[role] = items
    return out


def _find_agreements(recommendations_by_role: dict[str, list[str]]) -> list[dict]:
    claim_roles: dict[str, list[str]] = {}
    claim_text: dict[str, str] = {}
    for role, items in recommendations_by_role.items():
        for item in items:
            normalized = _normalize_text(item)
            if not normalized:
                continue
            claim_roles.setdefault(normalized, [])
            if role not in claim_roles[normalized]:
                claim_roles[normalized].append(role)
            claim_text.setdefault(normalized, item)

    agreements = []
    for normalized, roles in claim_roles.items():
        if len(roles) >= 2:
            agreements.append({"claim": claim_text[normalized], "supporting_roles": roles})
        if len(agreements) >= 5:
            break
    return agreements


def _find_distinct_priority_disagreement(recommendations_by_role: dict[str, list[str]]) -> list[dict]:
    roles = [role for role, recs in recommendations_by_role.items() if recs]
    if len(roles) < 2:
        return []

    normalized_sets = {
        role: {_normalize_text(item) for item in recommendations_by_role[role] if _normalize_text(item)}
        for role in roles
    }
    disjoint_pairs = []
    for index, left in enumerate(roles):
        for right in roles[index + 1 :]:
            if normalized_sets[left] and normalized_sets[right] and not normalized_sets[left].intersection(normalized_sets[right]):
                disjoint_pairs.append((left, right))

    if not disjoint_pairs:
        return []

    left, right = disjoint_pairs[0]
    return [
        {
            "issue": "Different expert priorities require synthesis.",
            "positions": [
                {"role": left, "position": recommendations_by_role[left][0]},
                {"role": right, "position": recommendations_by_role[right][0]},
            ],
            "severity": "medium",
        }
    ]


def _contains_any(items: list[str], markers: tuple[str, ...]) -> bool:
    text = " ".join(items).lower()
    return any(marker in text for marker in markers)


def _find_speed_risk_tradeoff(recommendations_by_role: dict[str, list[str]], risks_by_role: dict[str, list[str]]) -> list[dict]:
    speed_roles = []
    for role in ("engineer", "strategist"):
        if _contains_any(
            recommendations_by_role.get(role, []),
            ("quick", "fast", "ship", "launch", "mvp", "быстр", "запуск", "старт", "скор"),
        ):
            speed_roles.append(role)

    risk_items = risks_by_role.get("risk_manager", [])
    if speed_roles and risk_items:
        return [
            {
                "tradeoff": "implementation speed vs risk control",
                "why_it_matters": "Fast execution recommendations need to be reconciled with risk controls before synthesis.",
                "roles_involved": speed_roles + ["risk_manager"],
            }
        ]
    return []


def _find_user_question_blind_spots(recommendations_by_role: dict[str, list[str]], questions_by_role: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    user_questions = questions_by_role.get("user_advocate", [])
    if not user_questions:
        return [], []
    all_recommendations = _normalize_text(" ".join(item for recs in recommendations_by_role.values() for item in recs))
    unresolved = []
    for question in user_questions:
        tokens = [token for token in _normalize_text(question).split() if len(token) >= 5]
        if not tokens or not any(token in all_recommendations for token in tokens[:4]):
            unresolved.append(question)
        if len(unresolved) >= 5:
            break
    if unresolved:
        return ["User advocate questions are not clearly addressed by recommendations."], unresolved
    return [], []


def _find_premature_consensus(
    query_intake: dict | None,
    recommendations_by_role: dict[str, list[str]],
    disagreements: list[dict],
) -> list[str]:
    if not _query_is_complex(query_intake) or len(recommendations_by_role) < 2:
        return []

    normalized_all = [
        _normalize_text(item)
        for recs in recommendations_by_role.values()
        for item in recs
        if _normalize_text(item)
    ]
    unique = set(normalized_all)
    risks = []
    if normalized_all and len(unique) <= max(1, len(recommendations_by_role) // 2):
        risks.append("Expert recommendations are highly similar despite a complex/high-risk query.")
    if not disagreements:
        risks.append("No substantive disagreement detected despite complex/high-risk task.")
    return risks[:5]


def _rule_based_report(
    query_intake: dict | None,
    expert_bundle: dict | None,
    warning: str | None = None,
    *,
    warnings: list[str] | None = None,
    json_attempts: int = 0,
    raw: str = "",
) -> dict:
    contributions = _contributions(expert_bundle)
    all_warnings = ([warning] if warning else []) + list(warnings or [])
    report = _empty_report(
        "rules",
        warnings=all_warnings,
        confidence=0.45,
        json_attempts=json_attempts,
        raw=raw,
    )

    if len(contributions) < 2:
        report["blind_spots"].append("Not enough expert contributions to compare perspectives.")
        report["confidence"] = 0.25
        return report

    recommendations_by_role = _role_items(contributions, "recommendations")
    risks_by_role = _role_items(contributions, "risks")
    questions_by_role = _role_items(contributions, "questions")

    report["agreements"] = _find_agreements(recommendations_by_role)
    report["disagreements"] = _find_distinct_priority_disagreement(recommendations_by_role)
    report["unresolved_tradeoffs"] = _find_speed_risk_tradeoff(recommendations_by_role, risks_by_role)

    blind_spots, questions = _find_user_question_blind_spots(recommendations_by_role, questions_by_role)
    report["blind_spots"].extend(blind_spots)
    report["questions_for_next_round"].extend(questions)
    report["premature_consensus_risks"] = _find_premature_consensus(
        query_intake,
        recommendations_by_role,
        report["disagreements"],
    )

    if report["disagreements"] or report["unresolved_tradeoffs"] or report["premature_consensus_risks"]:
        report["confidence"] = 0.6
    return report


def _model_conflict_report(
    query_intake: dict | None,
    expert_bundle: dict,
    deliberation_brief: dict,
    *,
    model: str,
) -> tuple[dict | None, dict]:
    stage = get_stage_settings("conflict", {"tokens": 800, "temp": 0.2})
    system_prompt = (
        "You are a semantic conflict analyzer for a Collective Meta-Moderation process. "
        "Analyze expert contributions, not the final answer. Identify agreements, disagreements, "
        "unresolved trade-offs, premature consensus risks, blind spots, minority positions, and "
        "questions for the next round. Return strict JSON only."
    )
    state = {
        "query_intake": query_intake or {},
        "expert_roles": _as_dict(expert_bundle).get("roles", []),
        "expert_contributions": _as_dict(expert_bundle).get("contributions", []),
        "deliberation_brief": deliberation_brief or {},
        "schema": {
            "agreements": [{"claim": "string", "supporting_roles": ["role_key"]}],
            "disagreements": [
                {
                    "issue": "string",
                    "positions": [{"role": "role_key", "position": "string"}],
                    "severity": "low|medium|high",
                }
            ],
            "unresolved_tradeoffs": [
                {
                    "tradeoff": "string",
                    "why_it_matters": "string",
                    "roles_involved": ["role_key"],
                }
            ],
            "premature_consensus_risks": ["string"],
            "blind_spots": ["string"],
            "minority_positions": ["string"],
            "questions_for_next_round": ["string"],
            "confidence": 0.0,
        },
    }
    result = call_json_model(
        user_prompt="Analyze semantic conflicts in this CMM state:\n" + json.dumps(state, ensure_ascii=False),
        system_prompt=system_prompt,
        temp=float(stage.get("temp") or 0.2),
        tokens=int(stage.get("tokens") or 800),
        model=model,
        max_retries=1,
        log_purpose="conflict_analyzer",
    )
    warnings = result.get("warnings") if isinstance(result, dict) and isinstance(result.get("warnings"), list) else []
    attempts = result.get("attempts") if isinstance(result, dict) and isinstance(result.get("attempts"), int) else 0
    raw = result.get("raw") if isinstance(result, dict) and isinstance(result.get("raw"), str) else ""
    parsed = result.get("payload") if isinstance(result, dict) else None
    report = _normalize_report(
        parsed,
        source="model",
        warnings=warnings,
        json_attempts=attempts,
        raw=raw,
    )
    return report, {"warnings": warnings, "attempts": attempts, "raw": raw}


def analyze_conflicts(
    query_intake: dict | None,
    expert_bundle: dict,
    deliberation_brief: dict,
    *,
    model: str = "deepseek-chat",
) -> dict:
    """Analyze semantic agreements, disagreements, tradeoffs, and consensus risks."""
    try:
        model_report, diagnostics = _model_conflict_report(
            query_intake,
            expert_bundle,
            deliberation_brief,
            model=model,
        )
        if model_report is not None:
            return model_report
        return _rule_based_report(
            query_intake,
            expert_bundle,
            warning="conflict_model_invalid_json",
            warnings=diagnostics.get("warnings"),
            json_attempts=diagnostics.get("attempts", 0),
            raw=diagnostics.get("raw", ""),
        )
    except Exception as exc:
        return _rule_based_report(query_intake, expert_bundle, warning=f"conflict_model_failed: {exc}")
