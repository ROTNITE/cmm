"""Quality-aware balance analyzer for expert perspectives.

Balance Analyzer 2.0 preserves the original tag/count contract while adding
deterministic quality heuristics. It never calls an LLM.
"""

from __future__ import annotations

import json
import re
from typing import Any


_BASE_TAGS = ["strategy", "engineering", "risk", "user"]
_RISK_BUCKETS = ("low", "medium", "high", "unknown")

_HIGH_RISK_MARKERS = (
    "legal",
    "safety",
    "security",
    "privacy",
    "harm",
    "compliance",
    "critical",
    "failure",
    "irreversible",
    "medical",
    "financial",
    "vulnerable",
    "секрет",
    "безопасность",
    "закон",
    "вред",
    "критическ",
)
_MEDIUM_RISK_MARKERS = (
    "cost",
    "delay",
    "adoption",
    "operations",
    "quality",
    "rollback",
    "budget",
    "ресурсы",
    "сроки",
    "внедрение",
)
_LOW_RISK_MARKERS = ("minor", "cosmetic", "preference", "wording", "polish", "small")

_EVIDENCE_MARKERS = (
    "metric",
    "kpi",
    "test",
    "data",
    "evidence",
    "example",
    "standard",
    "constraint",
    "rubric",
    "measure",
    "метрик",
    "данн",
    "пример",
    "стандарт",
)
_ACTION_MARKERS = (
    "define",
    "measure",
    "test",
    "pilot",
    "assign",
    "prioritize",
    "mitigate",
    "sequence",
    "roll out",
    "clarify",
    "создать",
    "измер",
    "провер",
    "назнач",
    "сниз",
    "запустить",
)
_TRADEOFF_MARKERS = (
    "tradeoff",
    "trade-off",
    "vs",
    "versus",
    "balance",
    "compromise",
    "cost of",
    "risk of",
    "компромисс",
    "баланс",
    "против",
)
_GENERIC_RECOMMENDATIONS = {
    "clarify goal",
    "consider risks",
    "improve process",
    "think carefully",
    "add more detail",
    "make a plan",
    "улучшить процесс",
    "учесть риски",
}
_STAKEHOLDER_MARKERS = {
    "students": ("student", "students", "студент", "учащ"),
    "teachers": ("teacher", "teachers", "faculty", "instructor", "преподав", "учител"),
    "users": ("user", "users", "customer", "клиент", "пользователь"),
    "parents": ("parent", "parents", "родител"),
    "patients": ("patient", "patients", "пациент"),
    "employees": ("employee", "employees", "staff", "сотрудник", "персонал"),
    "managers": ("manager", "managers", "leadership", "руковод", "менедж"),
    "regulators": ("regulator", "regulators", "compliance", "регулятор", "надзор"),
    "disabled users": ("accessibility", "disability", "disabled", "доступност", "инвалид"),
}


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _clamp(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return round(float(value), 4)


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"[^\w\sа-яё]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value or "")


def _string_items(value: Any, max_items: int = 100) -> list[str]:
    out: list[str] = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, (int, float, bool)):
            text = str(item)
        else:
            continue
        if text:
            out.append(text)
        if len(out) >= max_items:
            break
    return out


def _contributions(bundle: dict) -> list[dict]:
    items = bundle.get("contributions") if isinstance(bundle, dict) else []
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _role_views(bundle: dict) -> list[dict]:
    roles = bundle.get("roles") if isinstance(bundle, dict) else []
    return [item for item in roles if isinstance(item, dict)] if isinstance(roles, list) else []


def _all_tags(bundle: dict, contributions: list[dict], dynamic_roles_used: list | None) -> list[str]:
    tags = list(_BASE_TAGS)
    for item in list(contributions) + _role_views(bundle) + _safe_list(dynamic_roles_used):
        if not isinstance(item, dict):
            continue
        tag = item.get("perspective_tag")
        if isinstance(tag, str) and tag.strip() and tag.strip() not in tags:
            tags.append(tag.strip())
    return tags


def _content_fields(contribution: dict) -> list[str]:
    return ["insights", "risks", "questions", "recommendations"]


def _is_error_contribution(contribution: dict) -> bool:
    blob = _normalize_text(_text(contribution))
    return any(marker in blob for marker in ("invalid json", "execution failed", "expert_execution_failed", "failed"))


def _perspective_coverage(tags: list[str], contributions: list[dict]) -> dict[str, float]:
    coverage: dict[str, float] = {tag: 0.0 for tag in tags}
    by_tag: dict[str, list[dict]] = {tag: [] for tag in tags}
    for contribution in contributions:
        tag = contribution.get("perspective_tag")
        if isinstance(tag, str) and tag.strip():
            by_tag.setdefault(tag.strip(), []).append(contribution)
            coverage.setdefault(tag.strip(), 0.0)

    for tag, items in by_tag.items():
        if not items:
            coverage[tag] = 0.0
            continue
        scores: list[float] = []
        for item in items:
            useful_fields = 0
            useful_items = 0
            for field in _content_fields(item):
                values = _string_items(item.get(field))
                if values:
                    useful_fields += 1
                    useful_items += len(values)
            score = 0.2 + min(0.55, useful_fields * 0.14) + min(0.25, useful_items * 0.025)
            if _is_error_contribution(item):
                score = min(score, 0.25)
            scores.append(_clamp(score))
        coverage[tag] = _clamp(max(scores) if scores else 0.0)
    return coverage


def _meaningful_tokens(value: str) -> list[str]:
    return [token for token in _normalize_text(value).split() if len(token) >= 4]


def _item_covered(item: str, text: str) -> float:
    normalized = _normalize_text(item)
    if not normalized:
        return 0.0
    if normalized in text:
        return 1.0
    tokens = _meaningful_tokens(item)
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens[:6] if token in text)
    return _clamp(hits / min(len(tokens), 4))


def _role_text(contribution: dict) -> str:
    return _normalize_text(_text({field: contribution.get(field) for field in _content_fields(contribution)}))


def _constraint_coverage(query_intake: dict | None, contributions: list[dict]) -> list[dict]:
    constraints = _string_items(_safe_dict(query_intake).get("constraints"), max_items=8)
    out: list[dict] = []
    for constraint in constraints:
        supporting: list[str] = []
        best = 0.0
        for contribution in contributions:
            score = _item_covered(constraint, _role_text(contribution))
            if score >= 0.45:
                role = contribution.get("role_key")
                if isinstance(role, str) and role not in supporting:
                    supporting.append(role)
            best = max(best, score)
        out.append(
            {
                "constraint": constraint,
                "covered": best >= 0.45,
                "supporting_roles": supporting[:6],
                "coverage_score": _clamp(best),
            }
        )
    return out


def _stakeholder_candidates(query_intake: dict | None, dynamic_roles_used: list | None) -> list[str]:
    intake = _safe_dict(query_intake)
    text = _normalize_text(
        " ".join(
            [
                str(intake.get("task_goal") or ""),
                _text(intake.get("context")),
                _text(intake.get("user_preferences")),
                _text(dynamic_roles_used or []),
            ]
        )
    )
    stakeholders: list[str] = []
    for name, markers in _STAKEHOLDER_MARKERS.items():
        if any(marker in text for marker in markers):
            stakeholders.append(name)
    return stakeholders[:8]


def _stakeholder_coverage(
    query_intake: dict | None,
    contributions: list[dict],
    dynamic_roles_used: list | None,
) -> list[dict]:
    out: list[dict] = []
    for stakeholder in _stakeholder_candidates(query_intake, dynamic_roles_used):
        markers = _STAKEHOLDER_MARKERS.get(stakeholder, (stakeholder,))
        supporting: list[str] = []
        for contribution in contributions:
            text = _role_text(contribution)
            if any(marker in text for marker in markers):
                role = contribution.get("role_key")
                if isinstance(role, str) and role not in supporting:
                    supporting.append(role)
        out.append(
            {
                "stakeholder": stakeholder,
                "covered": bool(supporting),
                "supporting_roles": supporting[:6],
            }
        )
    return out


def _classify_risk(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return "unknown"
    if any(marker in normalized for marker in _HIGH_RISK_MARKERS):
        return "high"
    if any(marker in normalized for marker in _MEDIUM_RISK_MARKERS):
        return "medium"
    if any(marker in normalized for marker in _LOW_RISK_MARKERS):
        return "low"
    return "unknown"


def _risk_strings(contributions: list[dict], deliberation_revisions: list | None) -> list[str]:
    risks: list[str] = []
    for contribution in contributions:
        risks.extend(_string_items(contribution.get("risks")))
    for revision in _safe_list(deliberation_revisions):
        if isinstance(revision, dict):
            risks.extend(_string_items(revision.get("new_risks")))
    return risks


def _risk_distribution(contributions: list[dict], deliberation_revisions: list | None) -> dict[str, int]:
    distribution = {key: 0 for key in _RISK_BUCKETS}
    for risk in _risk_strings(contributions, deliberation_revisions):
        distribution[_classify_risk(risk)] += 1
    return distribution


def _recommendations(contributions: list[dict], deliberation_revisions: list | None) -> list[str]:
    recs: list[str] = []
    for contribution in contributions:
        recs.extend(_string_items(contribution.get("recommendations")))
    for revision in _safe_list(deliberation_revisions):
        if isinstance(revision, dict):
            recs.extend(_string_items(revision.get("revised_recommendations")))
    return recs


def _average_marker_score(items: list[str], markers: tuple[str, ...]) -> float:
    if not items:
        return 0.0
    hits = 0
    for item in items:
        text = _normalize_text(item)
        if any(marker in text for marker in markers):
            hits += 1
    return _clamp(hits / len(items))


def _specificity_score(items: list[str]) -> float:
    if not items:
        return 0.0
    scores = []
    for item in items:
        tokens = _meaningful_tokens(item)
        has_number = bool(re.search(r"\d", item))
        scores.append(_clamp(min(1.0, len(tokens) / 8) + (0.15 if has_number else 0.0)))
    return _clamp(sum(scores) / len(scores))


def _novelty_score(recommendations: list[str]) -> float:
    if not recommendations:
        return 0.0
    normalized = [_normalize_text(item) for item in recommendations if _normalize_text(item)]
    if not normalized:
        return 0.0
    unique = len(set(normalized))
    generic_count = sum(1 for item in normalized if item in _GENERIC_RECOMMENDATIONS or len(_meaningful_tokens(item)) < 3)
    return _clamp((unique / len(normalized)) - (generic_count / len(normalized)) * 0.35)


def _argument_quality(
    contributions: list[dict],
    conflict_report: dict | None,
    deliberation_revisions: list | None,
) -> dict[str, float]:
    recs = _recommendations(contributions, deliberation_revisions)
    risks = _risk_strings(contributions, deliberation_revisions)
    insights = []
    questions = []
    for contribution in contributions:
        insights.extend(_string_items(contribution.get("insights")))
        questions.extend(_string_items(contribution.get("questions")))
    all_items = recs + risks + insights + questions
    conflict = _safe_dict(conflict_report)
    tradeoff_items = _safe_list(conflict.get("unresolved_tradeoffs")) + _safe_list(conflict.get("disagreements"))
    tradeoff_texts = [_text(item) for item in tradeoff_items]
    return {
        "evidence_level": _average_marker_score(all_items, _EVIDENCE_MARKERS),
        "specificity": _specificity_score(all_items),
        "actionability": _average_marker_score(recs, _ACTION_MARKERS),
        "novelty": _novelty_score(recs),
        "tradeoff_awareness": _clamp(
            max(
                _average_marker_score(all_items, _TRADEOFF_MARKERS),
                0.7 if tradeoff_texts and any(_item_covered(item, _normalize_text(" ".join(all_items))) > 0.2 for item in tradeoff_texts) else 0.0,
            )
        ),
    }


def _counts(contributions: list[dict]) -> tuple[dict[str, int], int]:
    counts: dict[str, int] = {}
    total = 0
    for item in contributions:
        tag = item.get("perspective_tag")
        if not isinstance(tag, str) or not tag.strip():
            continue
        tag = tag.strip()
        counts[tag] = counts.get(tag, 0) + 1
        total += 1
    return counts, total


def _dominance(counts: dict[str, int], total: int) -> dict:
    dominant_tag = None
    dominant_ratio = 0.0
    for tag, count in counts.items():
        ratio = count / total if total else 0.0
        if ratio > dominant_ratio:
            dominant_ratio = ratio
            dominant_tag = tag
    return {
        "dominant_perspective": dominant_tag,
        "dominant_ratio": _clamp(dominant_ratio),
        "counts": dict(counts),
        "total_contributions": total,
    }


def _blind_spots(
    *,
    missing_base: list[str],
    constraint_coverage: list[dict],
    stakeholder_coverage: list[dict],
    risk_distribution: dict[str, int],
    perspective_coverage: dict[str, float],
    argument_quality: dict[str, float],
    conflict_report: dict | None,
    dynamic_roles_used: list | None,
) -> list[str]:
    spots: list[str] = []
    for tag in missing_base:
        spots.append(f"Missing base perspective: {tag}.")
    for item in constraint_coverage:
        if not item.get("covered"):
            spots.append(f"Constraint not covered by expert contributions: {item.get('constraint')}.")
    for item in stakeholder_coverage:
        if not item.get("covered"):
            spots.append(f"Stakeholder not explicitly covered: {item.get('stakeholder')}.")
    if risk_distribution.get("high", 0) > 0 and perspective_coverage.get("risk", 0.0) < 0.45:
        spots.append("High-severity risks exist but risk perspective coverage is weak.")
    conflict = _safe_dict(conflict_report)
    if _safe_list(conflict.get("unresolved_tradeoffs")) and argument_quality.get("tradeoff_awareness", 0.0) < 0.4:
        spots.append("Unresolved trade-offs exist but expert contributions show weak trade-off awareness.")
    if argument_quality.get("novelty", 0.0) < 0.35:
        spots.append("Expert recommendations appear generic or duplicative.")
    for role in _safe_list(dynamic_roles_used):
        if not isinstance(role, dict):
            continue
        tag = role.get("perspective_tag")
        key = role.get("key")
        if isinstance(tag, str) and tag and perspective_coverage.get(tag, 0.0) < 0.35:
            spots.append(f"Selected dynamic role perspective is not meaningfully covered: {key or tag}.")
    out: list[str] = []
    for spot in spots:
        if spot not in out:
            out.append(spot)
    return out[:12]


def _recommended_action(
    *,
    missing_base: list[str],
    blind_spots: list[str],
    constraint_coverage: list[dict],
    stakeholder_coverage: list[dict],
    risk_distribution: dict[str, int],
    argument_quality: dict[str, float],
    perspective_coverage: dict[str, float],
    dynamic_roles_used: list | None,
) -> str:
    if missing_base:
        return "ADD_EXPERT"
    for role in _safe_list(dynamic_roles_used):
        if isinstance(role, dict):
            tag = role.get("perspective_tag")
            if isinstance(tag, str) and perspective_coverage.get(tag, 0.0) < 0.35:
                return "ADD_EXPERT"
    if any(not item.get("covered") for item in constraint_coverage):
        return "DEEPEN"
    if any(not item.get("covered") for item in stakeholder_coverage):
        return "DEEPEN"
    if risk_distribution.get("high", 0) > 0 and argument_quality.get("actionability", 0.0) < 0.45:
        return "DEEPEN"
    if blind_spots:
        return "DEEPEN"
    if (
        argument_quality.get("specificity", 0.0) < 0.35
        or argument_quality.get("actionability", 0.0) < 0.35
        or argument_quality.get("novelty", 0.0) < 0.35
    ):
        return "DEEPEN"
    return "SYNTHESIZE"


def _empty_quality_result() -> dict:
    return {
        "perspective_coverage": {tag: 0.0 for tag in _BASE_TAGS},
        "stakeholder_coverage": [],
        "constraint_coverage": [],
        "risk_severity_distribution": {key: 0 for key in _RISK_BUCKETS},
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
        "blind_spots": [],
        "recommended_action": "ADD_EXPERT",
    }


def analyze_balance(
    expert_bundle: dict,
    query_intake: dict | None = None,
    conflict_report: dict | None = None,
    dynamic_roles_used: list | None = None,
    deliberation_revisions: list | None = None,
) -> dict:
    """Analyze perspective balance and quality signals.

    Old callers can still use ``analyze_balance(expert_bundle)`` and receive the
    original keys. New callers may pass CMM context for quality-aware heuristics.
    """
    result = {
        "dominant_perspective_found": False,
        "dominant_perspective": None,
        "missing_perspectives": [],
        "notes": [],
    }
    result.update(_empty_quality_result())

    if not isinstance(expert_bundle, dict):
        result["missing_perspectives"] = list(_BASE_TAGS)
        result["blind_spots"] = [f"Missing base perspective: {tag}." for tag in _BASE_TAGS]
        result["notes"].append("expert_bundle is not a dict; fallback to missing all base perspectives.")
        return result

    contributions = _contributions(expert_bundle)
    counts, total = _counts(contributions)
    tags = _all_tags(expert_bundle, contributions, dynamic_roles_used)
    perspective_coverage = _perspective_coverage(tags, contributions)
    present_base = [tag for tag in _BASE_TAGS if counts.get(tag, 0) > 0]
    missing_base = [tag for tag in _BASE_TAGS if counts.get(tag, 0) == 0]
    dominance = _dominance(counts, total)
    constraint_coverage = _constraint_coverage(query_intake, contributions)
    stakeholder_coverage = _stakeholder_coverage(query_intake, contributions, dynamic_roles_used)
    risk_distribution = _risk_distribution(contributions, deliberation_revisions)
    argument_quality = _argument_quality(contributions, conflict_report, deliberation_revisions)
    blind_spots = _blind_spots(
        missing_base=missing_base,
        constraint_coverage=constraint_coverage,
        stakeholder_coverage=stakeholder_coverage,
        risk_distribution=risk_distribution,
        perspective_coverage=perspective_coverage,
        argument_quality=argument_quality,
        conflict_report=conflict_report,
        dynamic_roles_used=dynamic_roles_used,
    )
    recommended_action = _recommended_action(
        missing_base=missing_base,
        blind_spots=blind_spots,
        constraint_coverage=constraint_coverage,
        stakeholder_coverage=stakeholder_coverage,
        risk_distribution=risk_distribution,
        argument_quality=argument_quality,
        perspective_coverage=perspective_coverage,
        dynamic_roles_used=dynamic_roles_used,
    )

    if len(present_base) < 3:
        result["notes"].append(
            f"Only {len(present_base)} base perspective(s) represented; less than 3 indicates weak diversity."
        )

    result["missing_perspectives"] = missing_base
    if missing_base:
        result["notes"].append("Missing base perspectives: " + ", ".join(missing_base) + ".")
    else:
        result["notes"].append("All base perspectives are represented.")

    if total == 0:
        result["notes"].append("No valid contributions found for perspective analysis.")
    elif dominance["dominant_perspective"] is not None and dominance["dominant_ratio"] >= 0.6:
        result["dominant_perspective_found"] = True
        result["dominant_perspective"] = dominance["dominant_perspective"]
        result["notes"].append(
            f"Perspective '{dominance['dominant_perspective']}' dominates with {dominance['dominant_ratio']:.0%} of contributions (>=60%)."
        )
    else:
        result["notes"].append("No dominant perspective detected (max share < 60%).")

    if blind_spots:
        result["notes"].append("Balance quality blind spots detected.")

    result.update(
        {
            "perspective_coverage": perspective_coverage,
            "stakeholder_coverage": stakeholder_coverage,
            "constraint_coverage": constraint_coverage,
            "risk_severity_distribution": risk_distribution,
            "argument_quality": argument_quality,
            "dominance": dominance,
            "blind_spots": blind_spots,
            "recommended_action": recommended_action,
        }
    )
    return result
