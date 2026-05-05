"""Safe template-based dynamic role generation for CMM.

The model may suggest allowed role keys, but it must never define prompts or
arbitrary role behavior. All executable role behavior comes from this module's
static template catalog.
"""

from __future__ import annotations

import json
import re
from typing import Any

from Lib.expert_roles import ExpertRole
from Lib.json_retry import call_json_model


ALLOWED_DYNAMIC_PERSPECTIVE_TAGS = {
    "legal",
    "ethics",
    "measurement",
    "implementation",
    "stakeholder",
    "adversarial",
    "domain",
    "cost",
    "accessibility",
}


_ROLE_TEMPLATES: dict[str, dict[str, str]] = {
    "legal_reviewer": {
        "name": "Legal Reviewer",
        "perspective_tag": "legal",
        "responsibility": "Legal, regulatory, compliance, and policy constraints.",
        "system_prompt": (
            "You are a legal and compliance reviewer. Focus on legal, regulatory, "
            "policy, consent, and compliance constraints. Do not provide legal advice "
            "as a substitute for a qualified professional."
        ),
    },
    "ethics_reviewer": {
        "name": "Ethics Reviewer",
        "perspective_tag": "ethics",
        "responsibility": "Ethical risks, fairness, vulnerable users, harm, and social impact.",
        "system_prompt": (
            "You are an ethics reviewer. Focus on fairness, vulnerable users, harm "
            "prevention, social impact, and responsible use."
        ),
    },
    "measurement_expert": {
        "name": "Measurement Expert",
        "perspective_tag": "measurement",
        "responsibility": "Metrics, evaluation, KPIs, experiments, and success criteria.",
        "system_prompt": (
            "You are a measurement expert. Focus on metrics, evaluation design, KPIs, "
            "experiments, evidence quality, and success criteria."
        ),
    },
    "implementation_owner": {
        "name": "Implementation Owner",
        "perspective_tag": "implementation",
        "responsibility": "Rollout, ownership, operations, delivery, and change management.",
        "system_prompt": (
            "You are an implementation owner. Focus on rollout, ownership, operations, "
            "delivery sequencing, change management, and maintainability."
        ),
    },
    "stakeholder_representative": {
        "name": "Stakeholder Representative",
        "perspective_tag": "stakeholder",
        "responsibility": "Stakeholder incentives, governance, institutional constraints, and conflicts.",
        "system_prompt": (
            "You represent stakeholder interests. Focus on governance, incentives, "
            "institutional constraints, affected groups, and conflicts of interest."
        ),
    },
    "adversarial_reviewer": {
        "name": "Adversarial Reviewer",
        "perspective_tag": "adversarial",
        "responsibility": "Failure modes, blind spots, assumptions, and premature consensus.",
        "system_prompt": (
            "You are an adversarial reviewer. Challenge assumptions, identify blind "
            "spots, stress-test consensus, and look for failure modes."
        ),
    },
    "domain_expert": {
        "name": "Domain Expert",
        "perspective_tag": "domain",
        "responsibility": "Domain-specific correctness and practical constraints when no narrower safe role fits.",
        "system_prompt": (
            "You are a domain expert. Focus on domain-specific correctness, practical "
            "constraints, terminology, and professional standards."
        ),
    },
    "cost_optimizer": {
        "name": "Cost Optimizer",
        "perspective_tag": "cost",
        "responsibility": "Budget, affordability, resource constraints, and cost trade-offs.",
        "system_prompt": (
            "You are a cost optimizer. Focus on budget, affordability, resource "
            "constraints, cost trade-offs, and low-cost implementation options."
        ),
    },
    "accessibility_reviewer": {
        "name": "Accessibility Reviewer",
        "perspective_tag": "accessibility",
        "responsibility": "Accessibility, inclusive UX, disability access, and language barriers.",
        "system_prompt": (
            "You are an accessibility reviewer. Focus on inclusive design, disability "
            "access, language barriers, assistive technology, and practical accessibility."
        ),
    },
}


ALLOWED_DYNAMIC_ROLE_KEYS = set(_ROLE_TEMPLATES)
_ROLE_KEY_BY_TAG = {template["perspective_tag"]: key for key, template in _ROLE_TEMPLATES.items()}

_UNSAFE_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"reveal\s+secrets?",
    r"bypass\s+safety",
    r"act\s+as\s+(the\s+)?system",
    r"developer\s+mode",
    r"jailbreak",
    r"credential\s+theft",
    r"steal\s+credentials?",
    r"malware",
    r"exploit\s+creation",
    r"evasion",
    r"doxx",
    r"secret\s+extraction",
    r"illegal\s+acts?",
    r"self[-\s]?harm",
]


def _template_to_role(key: str) -> ExpertRole:
    template = _ROLE_TEMPLATES[key]
    return ExpertRole(
        key=key,
        name=template["name"],
        responsibility=template["responsibility"],
        system_prompt=template["system_prompt"],
        perspective_tag=template["perspective_tag"],
    )


def get_dynamic_role_template(key: str) -> dict | None:
    template = _ROLE_TEMPLATES.get(str(key or "").strip())
    return dict(template) if template else None


def build_dynamic_role(key: str) -> ExpertRole | None:
    normalized = str(key or "").strip()
    if normalized not in _ROLE_TEMPLATES:
        return None
    return _template_to_role(normalized)


def _role_key(role: Any) -> str:
    if isinstance(role, ExpertRole):
        return role.key
    if isinstance(role, dict):
        value = role.get("key") or role.get("role_key")
        return str(value).strip() if value is not None else ""
    return ""


def _existing_role_keys(existing_roles: list | None) -> set[str]:
    return {key for key in (_role_key(role) for role in existing_roles or []) if key}


def _is_unsafe_text(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    if len(text) > 700:
        return True
    lowered = text.lower()
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in _UNSAFE_PATTERNS)


def _safe_why(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()[:300]
    return ""


def _role_view(role: ExpertRole, why_needed: str = "") -> dict:
    return {
        "key": role.key,
        "name": role.name,
        "perspective_tag": role.perspective_tag,
        "responsibility": role.responsibility,
        "why_needed": why_needed,
    }


def _reject(raw_key: Any, reason: str) -> dict:
    return {"raw_key": str(raw_key or "").strip(), "reason": reason}


def _normalize_suggestions(
    suggestions: list,
    *,
    existing_roles: list | None,
    max_roles: int,
) -> tuple[list[ExpertRole], list[dict], list[dict], list[str]]:
    roles: list[ExpertRole] = []
    role_views: list[dict] = []
    rejected: list[dict] = []
    warnings: list[str] = []
    seen = set(_existing_role_keys(existing_roles))

    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            rejected.append(_reject("", "invalid"))
            continue

        raw_key = suggestion.get("key") or suggestion.get("role_key") or suggestion.get("perspective_tag")
        key = str(raw_key or "").strip().lower()
        if not key or len(key) > 80:
            rejected.append(_reject(raw_key, "invalid"))
            continue

        if "system_prompt" in suggestion:
            rejected.append(_reject(raw_key, "unsafe"))
            warnings.append("model_suggested_system_prompt_rejected")
            continue

        if any(_is_unsafe_text(suggestion.get(field)) for field in ("key", "role_key", "perspective_tag", "why_needed")):
            rejected.append(_reject(raw_key, "unsafe"))
            continue

        suggested_tag = suggestion.get("perspective_tag")
        normalized_tag = str(suggested_tag).strip().lower() if suggested_tag else ""
        if normalized_tag and normalized_tag not in ALLOWED_DYNAMIC_PERSPECTIVE_TAGS:
            rejected.append(_reject(raw_key, "invalid_tag"))
            continue

        if key not in _ROLE_TEMPLATES and key in _ROLE_KEY_BY_TAG:
            key = _ROLE_KEY_BY_TAG[key]

        if key not in _ROLE_TEMPLATES:
            rejected.append(_reject(raw_key, "not_allowed"))
            continue

        if normalized_tag and normalized_tag != _ROLE_TEMPLATES[key]["perspective_tag"]:
            rejected.append(_reject(raw_key, "invalid_tag"))
            continue

        if key in seen:
            rejected.append(_reject(raw_key, "duplicate"))
            continue

        if len(roles) >= max(0, int(max_roles)):
            rejected.append(_reject(raw_key, "max_roles_exceeded"))
            continue

        role = _template_to_role(key)
        why_needed = _safe_why(suggestion.get("why_needed"))
        roles.append(role)
        role_views.append(_role_view(role, why_needed))
        seen.add(key)

    return roles, role_views, rejected, warnings


def _text_from_intake(query_intake: dict) -> str:
    parts: list[str] = []
    if isinstance(query_intake, dict):
        for key in (
            "original_query",
            "cleaned_query",
            "task_goal",
            "context",
            "constraints",
            "success_criteria",
            "unknowns",
            "user_preferences",
            "risk_level",
            "complexity",
        ):
            value = query_intake.get(key)
            if isinstance(value, list):
                parts.extend(str(item) for item in value)
            elif value is not None:
                parts.append(str(value))
    return " ".join(parts).lower()


def _text_from_context(*contexts: dict | None) -> str:
    chunks: list[str] = []
    for context in contexts:
        if isinstance(context, dict):
            try:
                chunks.append(json.dumps(context, ensure_ascii=False))
            except Exception:
                chunks.append(str(context))
    return " ".join(chunks).lower()


def _rule_suggestions(
    *,
    query_intake: dict,
    meta_decision: dict | None,
    conflict_report: dict | None,
    balance_report: dict | None,
) -> list[dict]:
    text = " ".join(
        [
            _text_from_intake(query_intake),
            _text_from_context(meta_decision, conflict_report, balance_report),
        ]
    )
    suggestions: list[dict] = []

    def add(key: str, why: str) -> None:
        if key not in [item.get("key") for item in suggestions]:
            suggestions.append({"key": key, "why_needed": why})

    if re.search(r"\b(legal|law|compliance|regulation|regulatory|policy|privacy)\b|закон|право|комплаенс|регулирован", text):
        add("legal_reviewer", "Legal or regulatory constraints appear in the task context.")
    if re.search(r"\b(ethics|ethical|fairness|vulnerable|students|children|education|ai ethics|harm)\b|этик|дети|студент|образован", text):
        add("ethics_reviewer", "The task may involve fairness, vulnerable users, education, or harm concerns.")
    if re.search(r"\b(metric|metrics|evaluation|evaluate|score|kpi|measure|success criteria|experiment)\b|метрик|оценк|эксперимент", text):
        add("measurement_expert", "The task needs metrics, evaluation, or success criteria.")
    if re.search(r"\b(budget|cost|affordability|limited budget|resource constraints|resources?)\b|бюджет|стоимост|ресурс", text):
        add("cost_optimizer", "Budget, cost, or resource constraints appear in the task.")
    if re.search(r"\b(accessibility|inclusive design|disability|assistive|language barriers?)\b|доступност|инклюзив|инвалид", text):
        add("accessibility_reviewer", "Accessibility or inclusive-use constraints appear in the task.")
    if re.search(r"\b(stakeholder|stakeholders|governance|university|organization|institution|team|conflict of interests?)\b|стейкхолдер|университет|организац|управлен", text):
        add("stakeholder_representative", "Multiple stakeholders or governance constraints appear in the task.")

    conflict = conflict_report if isinstance(conflict_report, dict) else {}
    if conflict.get("premature_consensus_risks") or conflict.get("blind_spots"):
        add("adversarial_reviewer", "Conflict analysis found blind spots or premature consensus risks.")
    if re.search(r"\b(rollout|operation|operations|delivery|change management|implementation|owner)\b|внедрен|операц|доставк", text):
        add("implementation_owner", "Rollout, operations, or implementation ownership needs attention.")
    if re.search(r"\b(domain expert|domain-specific|specialist)\b|доменн|отрасл", text):
        add("domain_expert", "The task appears to need domain-specific review.")

    return suggestions


def _build_model_prompts(
    *,
    query_intake: dict,
    meta_decision: dict | None,
    conflict_report: dict | None,
    balance_report: dict | None,
    existing_roles: list | None,
    max_roles: int,
) -> tuple[str, str]:
    allowed = sorted(ALLOWED_DYNAMIC_ROLE_KEYS)
    system_prompt = (
        "You suggest safe dynamic expert roles for a Collective Meta-Moderation process. "
        "Choose only from the allowed role keys. Do not invent prompts, role behavior, or tags. "
        "Do not include system_prompt. Return strict JSON only."
    )
    packet = {
        "query_intake": query_intake or {},
        "meta_decision": meta_decision or {},
        "conflict_report": conflict_report or {},
        "balance_report": balance_report or {},
        "existing_role_keys": sorted(_existing_role_keys(existing_roles)),
        "allowed_role_keys": allowed,
        "max_roles": max_roles,
        "schema": {"roles": [{"key": "ethics_reviewer", "why_needed": "string"}]},
    }
    user_prompt = (
        "Suggest at most {max_roles} dynamic roles. If none are needed, return {{\"roles\": []}}.\n"
        "Allowed keys only: {allowed}\n"
        "Do not include system_prompt or arbitrary role text.\n\n"
        "Context:\n{packet}"
    ).format(
        max_roles=max_roles,
        allowed=", ".join(allowed),
        packet=json.dumps(packet, ensure_ascii=False),
    )
    return system_prompt, user_prompt


def _report(
    *,
    roles: list[ExpertRole],
    role_views: list[dict],
    rejected_suggestions: list[dict],
    warnings: list[str],
    source: str,
    model_called: bool = False,
    json_attempts: int = 0,
) -> dict:
    return {
        "roles": roles,
        "role_views": role_views,
        "rejected_suggestions": rejected_suggestions,
        "warnings": warnings,
        "source": source,
        "model_called": model_called,
        "json_attempts": json_attempts,
    }


def _should_call_model_for_roles(
    *,
    query_intake: dict,
    meta_decision: dict | None,
    conflict_report: dict | None,
    balance_report: dict | None,
    remaining_slots: int,
) -> bool:
    if remaining_slots <= 0:
        return False
    if isinstance(query_intake, dict) and query_intake.get("complexity") == "complex":
        return True
    for context in (meta_decision, conflict_report, balance_report):
        if isinstance(context, dict) and any(context.get(key) for key in (
            "missing_perspectives",
            "blind_spots",
            "unresolved_tradeoffs",
            "premature_consensus_risks",
            "recommended_action",
        )):
            return True
    return False


def _model_role_suggestions(
    *,
    query_intake: dict,
    meta_decision: dict | None,
    conflict_report: dict | None,
    balance_report: dict | None,
    existing_roles: list | None,
    max_roles: int,
    model: str,
) -> tuple[list, list[str], int]:
    system_prompt, user_prompt = _build_model_prompts(
        query_intake=query_intake,
        meta_decision=meta_decision,
        conflict_report=conflict_report,
        balance_report=balance_report,
        existing_roles=existing_roles,
        max_roles=max_roles,
    )
    result = call_json_model(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        temp=0.15,
        tokens=350,
        model=model,
        max_retries=1,
    )
    warnings = list(result.get("warnings") or [])
    attempts = int(result.get("attempts") or 0)
    parsed = result.get("payload")
    if not isinstance(parsed, dict):
        warnings.append("dynamic_role_json_parse_failed")
        return [], warnings, attempts
    suggestions = parsed.get("roles")
    if not isinstance(suggestions, list):
        return [], warnings, attempts
    return suggestions, warnings, attempts


def generate_dynamic_roles(
    *,
    query_intake: dict,
    meta_decision: dict | None = None,
    conflict_report: dict | None = None,
    balance_report: dict | None = None,
    existing_roles: list | None = None,
    max_roles: int = 2,
    model: str = "deepseek-chat",
    strategy: str = "rules_first",
) -> dict:
    """Generate safe dynamic roles from static templates only."""
    max_roles = max(0, int(max_roles))
    warnings: list[str] = []
    strategy = str(strategy or "rules_first").lower()

    rule_suggestions = _rule_suggestions(
        query_intake=query_intake or {},
        meta_decision=meta_decision,
        conflict_report=conflict_report,
        balance_report=balance_report,
    )

    if strategy != "model_first":
        roles, role_views, rejected, normalize_warnings = _normalize_suggestions(
            rule_suggestions,
            existing_roles=existing_roles,
            max_roles=max_roles,
        )
        warnings.extend(normalize_warnings)
        remaining = max_roles - len(roles)
        if remaining <= 0 or not _should_call_model_for_roles(
            query_intake=query_intake or {},
            meta_decision=meta_decision,
            conflict_report=conflict_report,
            balance_report=balance_report,
            remaining_slots=remaining,
        ):
            return _report(
                roles=roles,
                role_views=role_views,
                rejected_suggestions=rejected,
                warnings=warnings,
                source="rules" if role_views else "fallback",
                model_called=False,
                json_attempts=0,
            )

        model_existing = list(existing_roles or []) + roles
        suggestions, model_warnings, attempts = _model_role_suggestions(
            query_intake=query_intake or {},
            meta_decision=meta_decision,
            conflict_report=conflict_report,
            balance_report=balance_report,
            existing_roles=model_existing,
            max_roles=remaining,
            model=model,
        )
        model_roles, model_views, model_rejected, normalize_warnings = _normalize_suggestions(
            suggestions,
            existing_roles=model_existing,
            max_roles=remaining,
        )
        warnings.extend(model_warnings)
        warnings.extend(normalize_warnings)
        return _report(
            roles=roles + model_roles,
            role_views=role_views + model_views,
            rejected_suggestions=rejected + model_rejected,
            warnings=warnings,
            source="rules+model" if model_roles else "rules" if roles else "fallback",
            model_called=True,
            json_attempts=attempts,
        )

    suggestions, model_warnings, attempts = _model_role_suggestions(
        query_intake=query_intake or {},
        meta_decision=meta_decision,
        conflict_report=conflict_report,
        balance_report=balance_report,
        existing_roles=existing_roles,
        max_roles=max_roles,
        model=model,
    )
    roles, role_views, rejected, normalize_warnings = _normalize_suggestions(
        suggestions,
        existing_roles=existing_roles,
        max_roles=max_roles,
    )
    warnings.extend(model_warnings)
    warnings.extend(normalize_warnings)
    return _report(
        roles=roles,
        role_views=role_views,
        rejected_suggestions=rejected,
        warnings=warnings,
        source="model" if role_views else "fallback",
        model_called=True,
        json_attempts=attempts,
    )


def dynamic_role_catalog() -> dict[str, dict[str, str]]:
    """Return a copy of the safe dynamic role template catalog."""
    return {key: dict(value) for key, value in _ROLE_TEMPLATES.items()}
