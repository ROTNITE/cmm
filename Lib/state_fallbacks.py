"""Fallback structures for the bounded CMM state machine."""

from __future__ import annotations

from typing import Any


def empty_expert_bundle() -> dict:
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


def _get_field(value: Any, field: str, default: str = "") -> str:
    if isinstance(value, dict):
        raw = value.get(field)
    else:
        raw = getattr(value, field, None)
    if raw is None:
        return default
    text = str(raw).strip()
    return text if text else default


def _string_list(value: Any, max_items: int = 8) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text[:220])
        if len(out) >= max_items:
            break
    return out


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _intake(context: dict | None) -> dict:
    if not isinstance(context, dict):
        return {}
    value = context.get("query_intake")
    return value if isinstance(value, dict) else {}


def _goal(query: str, context: dict | None) -> str:
    intake = _intake(context)
    for key in ("task_goal", "cleaned_query", "original_query"):
        value = intake.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:180]
    return str(query or "").strip()[:180]


def _role_view(role: Any) -> dict:
    key = _get_field(role, "key", "generalist")
    perspective = _get_field(role, "perspective_tag", key)
    name = _get_field(role, "name", key.replace("_", " ").title())
    return {
        "key": key,
        "name": name,
        "perspective_tag": perspective,
        "dynamic": bool(role.get("dynamic")) if isinstance(role, dict) else False,
    }


def _role_family(role: Any) -> str:
    fields = " ".join(
        _get_field(role, key)
        for key in ("key", "name", "perspective_tag", "responsibility", "why_needed")
    ).lower()
    families = (
        ("legal", ("legal", "law", "compliance", "privacy", "policy", "regulation", "закон", "прав", "комплаенс")),
        ("ethics", ("ethic", "fairness", "harm", "vulnerable", "этик", "справедлив", "вред")),
        ("cost", ("cost", "budget", "resource", "finance", "бюджет", "стоимост", "ресурс")),
        ("measurement", ("metric", "measure", "kpi", "evaluation", "success", "метрик", "оцен")),
        ("accessibility", ("accessibility", "inclusive", "disability", "доступност", "инклюзив")),
        ("risk", ("risk", "safety", "security", "privacy", "риск", "безопас")),
        ("engineering", ("engineer", "implementation", "technical", "system", "архитект", "техничес", "внедрен")),
        ("user", ("user", "customer", "stakeholder", "ux", "пользователь", "клиент")),
        ("strategy", ("strategy", "strategist", "business", "goal", "стратег", "цель")),
    )
    for family, markers in families:
        if any(marker in fields for marker in markers):
            return family
    return "general"


def build_rules_expert_contribution(
    role: Any,
    query: str,
    context: dict | None = None,
    *,
    warnings: list[str] | None = None,
    raw: str = "",
) -> dict:
    """Build a small role-aware contribution when model calls are unavailable."""
    intake = _intake(context)
    constraints = _string_list(intake.get("constraints"), max_items=4)
    success = _string_list(intake.get("success_criteria"), max_items=3)
    goal = _goal(query, context)
    view = _role_view(role)
    family = _role_family(role)

    constraint_text = "; ".join(constraints) if constraints else "the stated user constraints"
    success_text = "; ".join(success) if success else "a useful answer for the user's goal"

    templates = {
        "strategy": {
            "insights": [
                f"Primary goal: {goal}",
                f"Success should be judged against: {success_text}.",
                "The final answer should prioritize the user's requested outcome before process detail.",
            ],
            "risks": [
                "A broad answer may miss the user's concrete decision point.",
                "Ignoring stated constraints can make the result less useful than a direct baseline answer.",
            ],
            "questions": [
                "Which outcome matters most if constraints conflict?",
                "What minimum useful answer can satisfy the request now?",
            ],
            "recommendations": [
                "Start with the direct recommendation or explanation.",
                "Use constraints as acceptance criteria for the final answer.",
                "Keep alternatives only when they improve the decision.",
            ],
        },
        "engineering": {
            "insights": [
                "The solution should be operationally concrete, not only conceptual.",
                f"Implementation must respect: {constraint_text}.",
                "Validation should be possible with simple checks or examples.",
            ],
            "risks": [
                "Overly abstract steps can fail during execution.",
                "Missing edge cases may create rework after delivery.",
            ],
            "questions": [
                "What is the smallest testable implementation step?",
                "Which assumptions need validation before rollout?",
            ],
            "recommendations": [
                "Break the answer into concrete ordered actions.",
                "Mention validation or rollback where relevant.",
                "Avoid unnecessary architecture if the request is simple.",
            ],
        },
        "risk": {
            "insights": [
                "Risk handling should be proportional to the user's risk level.",
                f"Constraints are risk controls when they limit scope: {constraint_text}.",
                "The answer should name practical mitigations, not just risks.",
            ],
            "risks": [
                "A confident answer can still be unsafe if it skips constraints.",
                "Unresolved trade-offs can lead to premature consensus.",
            ],
            "questions": [
                "Which risk would make the answer unusable?",
                "What mitigation is required before acting?",
            ],
            "recommendations": [
                "State key risks with practical mitigations.",
                "Separate true blockers from ordinary quality concerns.",
                "Do not let internal pipeline failures become user-facing risks.",
            ],
        },
        "user": {
            "insights": [
                "The answer should match the user's requested length and format.",
                "Clear language usually beats exhaustive process detail.",
                f"The user asked for value against: {goal}",
            ],
            "risks": [
                "Too much detail can lose to a concise baseline answer.",
                "Internal CMM process details can distract from the user's actual need.",
            ],
            "questions": [
                "What would make the answer immediately usable?",
                "Does the answer respect the user's brevity and clarity preference?",
            ],
            "recommendations": [
                "Put the answer first, then only necessary support.",
                "Use one example when brevity is requested.",
                "Avoid exposing internal expert-process mechanics.",
            ],
        },
        "legal": {
            "insights": [
                "Legal or policy constraints should be separated from ordinary preferences.",
                f"The answer should explicitly respect: {constraint_text}.",
                "If legal facts are uncertain, the answer should avoid definitive legal advice.",
            ],
            "risks": [
                "Overstating legal certainty can mislead the user.",
                "Privacy or compliance obligations may require escalation.",
            ],
            "questions": [
                "Is jurisdiction or policy scope specified?",
                "Does the answer need a legal-review caveat?",
            ],
            "recommendations": [
                "Use cautious wording for legal or compliance issues.",
                "Call out privacy/security blockers only when truly relevant.",
                "Keep non-legal quality gaps out of critical blockers.",
            ],
        },
        "ethics": {
            "insights": [
                "Ethical impact depends on who could be harmed or excluded.",
                "The answer should avoid hidden assumptions about affected groups.",
                "Fairness concerns should become concrete checks.",
            ],
            "risks": [
                "A solution can be efficient but unfair to a minority stakeholder.",
                "Premature consensus can hide harm or exclusion.",
            ],
            "questions": [
                "Who could be disadvantaged by this recommendation?",
                "What safeguard would make the answer more responsible?",
            ],
            "recommendations": [
                "Add a concrete ethical safeguard where relevant.",
                "Name affected stakeholders without over-expanding the answer.",
                "Prefer transparent trade-offs over false certainty.",
            ],
        },
        "cost": {
            "insights": [
                "Resource limits should shape the recommended path.",
                f"Budget or effort constraints should be treated as acceptance criteria: {constraint_text}.",
                "The answer should distinguish must-have from nice-to-have steps.",
            ],
            "risks": [
                "A high-effort answer can be impractical even if correct.",
                "Unbounded recommendations can lose against a simpler baseline.",
            ],
            "questions": [
                "What is the lowest-cost useful version?",
                "Which recommendations can be deferred?",
            ],
            "recommendations": [
                "Prioritize the smallest high-impact action.",
                "Mention cost or effort trade-offs where relevant.",
                "Avoid unnecessary expert process for simple requests.",
            ],
        },
        "measurement": {
            "insights": [
                "A strong answer should make success observable.",
                f"Success criteria should map to: {success_text}.",
                "Metrics should not replace the user's actual goal.",
            ],
            "risks": [
                "Weak evaluation criteria can make the answer hard to verify.",
                "Over-measuring can add noise for simple explanation requests.",
            ],
            "questions": [
                "How will the user know the answer worked?",
                "Which metric or example best validates the recommendation?",
            ],
            "recommendations": [
                "Include one clear success check when relevant.",
                "Keep measurement lightweight for concise answers.",
                "Tie metrics back to the user's goal.",
            ],
        },
        "accessibility": {
            "insights": [
                "The answer should be understandable to the intended audience.",
                "Accessibility includes language clarity and practical usability.",
                "Format constraints can improve accessibility when respected.",
            ],
            "risks": [
                "Dense formatting can reduce usability.",
                "Jargon can make a correct answer less useful.",
            ],
            "questions": [
                "Does the user need plain language?",
                "Could a simpler structure improve comprehension?",
            ],
            "recommendations": [
                "Use simple labels and short paragraphs.",
                "Avoid unnecessary jargon.",
                "Respect requested brevity and formatting.",
            ],
        },
        "general": {
            "insights": [
                f"Primary goal: {goal}",
                f"Important constraints: {constraint_text}.",
                "The answer should be concrete enough to act on.",
            ],
            "risks": [
                "Ambiguous requirements can produce a generic answer.",
                "Missing constraints can reduce practical value.",
            ],
            "questions": [
                "Which constraint is most important?",
                "What would make the answer actionable now?",
            ],
            "recommendations": [
                "Answer the user's direct request first.",
                "Reflect the main constraints explicitly.",
                "Keep the result concise unless complexity requires detail.",
            ],
        },
    }
    data = templates.get(family, templates["general"])
    parse_warnings = _string_list(warnings or [], max_items=6)
    if parse_warnings and "expert_model_unavailable_rules_fallback" not in parse_warnings:
        parse_warnings.append("expert_model_unavailable_rules_fallback")

    return {
        "role_key": view["key"],
        "perspective_tag": view["perspective_tag"],
        "insights": data["insights"][:3],
        "risks": data["risks"][:2],
        "questions": data["questions"][:2],
        "recommendations": data["recommendations"][:3],
        "confidence": 0.45,
        "parse_warnings": parse_warnings,
        "json_attempts": 0,
        "raw": str(raw or "")[:2000],
        "source": "rules_fallback",
    }


def _default_roles() -> list[dict]:
    return [
        {"key": "strategist", "name": "Strategist", "perspective_tag": "strategy", "dynamic": False},
        {"key": "engineer", "name": "Engineer", "perspective_tag": "engineering", "dynamic": False},
        {"key": "risk_manager", "name": "Risk Manager", "perspective_tag": "risk", "dynamic": False},
        {"key": "user_advocate", "name": "User Advocate", "perspective_tag": "user", "dynamic": False},
    ]


def rules_based_expert_bundle(query: str, context: dict | None = None, roles: list | None = None) -> dict:
    """Generate deterministic role-aware expert contributions when model calls fail."""
    source_roles = roles
    if not source_roles and isinstance(context, dict) and isinstance(context.get("roles"), list):
        source_roles = context.get("roles")
    if not source_roles:
        source_roles = _default_roles()

    warnings = []
    if isinstance(context, dict):
        warnings = _string_list(context.get("warnings"), max_items=6)

    role_views = [_role_view(role) for role in source_roles]
    contributions = [
        build_rules_expert_contribution(role, query, context=context, warnings=warnings)
        for role in source_roles
    ]

    all_recommendations: list[str] = []
    all_risks: list[str] = []
    all_questions: list[str] = []
    perspective_counts: dict[str, int] = {}
    for contribution in contributions:
        perspective = contribution.get("perspective_tag") or "general"
        perspective_counts[perspective] = perspective_counts.get(perspective, 0) + 1
        all_recommendations.extend(_string_list(contribution.get("recommendations"), max_items=3))
        all_risks.extend(_string_list(contribution.get("risks"), max_items=2))
        all_questions.extend(_string_list(contribution.get("questions"), max_items=2))

    return {
        "roles": role_views,
        "contributions": contributions,
        "synthesis": {
            "recommendations": _dedupe(all_recommendations),
            "risks": _dedupe(all_risks),
            "questions": _dedupe(all_questions),
            "perspective_counts": perspective_counts,
        },
        "source": "rules_fallback",
    }


def conservative_balance_report() -> dict:
    return {
        "dominant_perspective_found": False,
        "dominant_perspective": None,
        "missing_perspectives": ["strategy", "engineering", "risk", "user"],
        "notes": ["Balance analysis failed; conservative fallback marks all base perspectives as missing."],
        "perspective_coverage": {
            "strategy": 0.0,
            "engineering": 0.0,
            "risk": 0.0,
            "user": 0.0,
        },
        "stakeholder_coverage": [],
        "constraint_coverage": [],
        "risk_severity_distribution": {"low": 0, "medium": 0, "high": 0, "unknown": 0},
        "argument_quality": {
            "evidence_level": 0.0,
            "specificity": 0.0,
            "actionability": 0.0,
            "novelty": 0.0,
            "tradeoff_awareness": 0.0,
        },
        "dominance": {
            "dominant_perspective": None,
            "dominant_ratio": 0.0,
            "counts": {},
            "total_contributions": 0,
        },
        "blind_spots": [
            "Missing base perspective: strategy.",
            "Missing base perspective: engineering.",
            "Missing base perspective: risk.",
            "Missing base perspective: user.",
        ],
        "recommended_action": "ADD_EXPERT",
    }


def empty_deliberation_brief(query: str) -> dict:
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


def fallback_query_intake(original_query: str, warning: str) -> dict:
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


def fallback_conflict_report() -> dict:
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


def fallback_meta_decision(reason: str, warning: str) -> dict:
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


__all__ = [
    "empty_expert_bundle",
    "build_rules_expert_contribution",
    "rules_based_expert_bundle",
    "conservative_balance_report",
    "empty_deliberation_brief",
    "fallback_query_intake",
    "fallback_conflict_report",
    "fallback_meta_decision",
]
