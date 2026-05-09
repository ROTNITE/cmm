"""Centralized quality gates for CMM finalization decisions.

This module owns the critical-blocker policy used by the CMM state machine:

Three blocker classes:
1. NO_ANSWER_BLOCKER: safety/legal/privacy/security/medical/financial advice/secrets/PII
   -> Must stop answer generation entirely
2. MUST_ADDRESS_IN_ANSWER: trade-offs, risks, constraints, missing perspectives
   -> Must be addressed in final answer (e.g., "choose X if..., Y if...")
3. QUALITY_IMPROVEMENT: style, completeness, depth, structure
   -> Suggestions for better answer, not blockers

The functions are intentionally deterministic and dependency-light so they can
be used by state_machine without pulling in model/API code.
"""

from __future__ import annotations

import re
from typing import Any


# ============================================================================
# BLOCKER CLASS 1: NO_ANSWER_BLOCKER
# These must stop answer generation entirely
# ============================================================================

# Specific phrases that always indicate true safety/legal/privacy issues
NO_ANSWER_BLOCKER_PHRASES = (
    "safety issue",
    "legal compliance issue",
    "privacy leak",
    "data leak",
    "gdpr violation",
    "hipaa violation",
    "security exploit",
    "bypass security",
    "medical advice",
    "financial advice",
    "investment advice",
    "irreversible harm",
    "api key",
    "secret key",
    "student privacy",
    "student data",
    "student information",
    "protect students",
    "student safety",
    "child safety",
    "minor privacy",
    "privacy laws",
    "data privacy breach",
    "data privacy breaches",
    "biased outputs",
    "harm to students",
    "medical secrecy",
    "medical confidentiality",
    "patient privacy",
    "patient data",
    "health data breach",
    "health information",
    "medical records",
    "clinical data",
    "diagnosis data",
    "treatment data",
    "accessibility violation",
    "accessibility requirement",
    "wcag violation",
    "data breach response",
    "breach notification",
    "security incident",
    "ключ доступа",
    "api ключ",
    "ключ api",
    "секретный ключ",
    "нарушает закон",
    "нарушение закона",
    "юридический запрет",
    "персональные данные",
    "персональных данных",
    "приватность учеников",
    "данные учеников",
    "утечка данных учеников",
    "защитить учеников",
    "безопасность учеников",
    "медицинскую тайну",
    "медицинская тайна",
    "конфиденциальность пациентов",
    "данные пациентов",
    "медицинские записи",
    "медицинский совет",
    "финансовый совет",
    "инвестиционный совет",
    "обойти безопасность",
    "необратимый вред",
    "утечка данных",
    "нарушение приватности",
)

# Generic words that indicate no-answer blockers (need context checking)
NO_ANSWER_BLOCKER_WORDS = (
    "unsafe",
    "harmful",
    "danger",
    "illegal",
    "unlawful",
    "violates law",
    "privacy",
    "breach",
    "breaches",
    "bias",
    "biased",
    "secret",
    "credential",
    "password",
    "token",
    "pii",
    "medical secrecy",
    "confidentiality",
    "незакон",
    "утеч",
    "вред",
    "приватност",
    "конфиденциальност",
    "секрет",
    "пароль",
    "токен",
)

# ============================================================================
# BLOCKER CLASS 2: MUST_ADDRESS_IN_ANSWER
# These must be addressed in final answer but don't block generation
# ============================================================================

MUST_ADDRESS_PHRASES = (
    "trade-off",
    "tradeoff",
    "risk",
    "constraint",
    "limitation",
    "missing perspective",
    "unresolved",
    "ignored",
    "not addressed",
    "компромисс",
    "риск",
    "ограничение",
    "не учтено",
    "не рассмотрено",
    "упущено",
)

MUST_ADDRESS_WORDS = (
    "vs",
    "versus",
    "or",
    "alternative",
    "option",
    "choice",
    "decision",
    "либо",
    "или",
    "выбор",
    "вариант",
    "альтернатива",
)

# ============================================================================
# BLOCKER CLASS 3: QUALITY_IMPROVEMENT
# These are suggestions, not blockers
# ============================================================================

QUALITY_IMPROVEMENT_PHRASES = (
    "could be more",
    "should include",
    "missing detail",
    "lacks depth",
    "too brief",
    "too verbose",
    "unclear",
    "можно улучшить",
    "стоит добавить",
    "недостаточно",
    "слишком кратко",
    "слишком подробно",
)

# Backward compatibility
CRITICAL_PHRASES = NO_ANSWER_BLOCKER_PHRASES

# Generic critical words that need context checking
CRITICAL_WORDS = NO_ANSWER_BLOCKER_WORDS

# Words that indicate non-critical context (recommendations, suggestions)
NON_CRITICAL_CONTEXT = (
    "recommend",
    "suggestion",
    "suggest",
    "should",
    "could",
    "improve",
    "better",
    "consider",
    "might",
    "optional",
    "рекоменд",
    "предлож",
    "стоит",
    "можно",
    "лучше",
    "улучш",
)

# Backward compatibility
CRITICAL_MARKERS = CRITICAL_PHRASES + CRITICAL_WORDS

PIPELINE_FAILURE_MARKERS = (
    "no credentials",
    "credential error",
    "api credential",
    "provider",
    "model error",
    "model unavailable",
    "json parse",
    "json model",
    "invalid json",
    "expert contributions failed",
    "expert contribution system",
    "expert execution failed",
    "expert panel catastrophic",
    "all expert",
    "call failed",
    "aimlapi",
)


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _string_items(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return out
    for item in value:
        if isinstance(item, str):
            text = item.strip()
        else:
            text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        marker = _normalize_text(item)
        if not marker or marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"[^\w\sа-яё]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def classify_blocker(value: Any, trace: list | None = None) -> dict:
    """Classify text into blocker classes.

    Returns:
        {
            "class": "NO_ANSWER_BLOCKER" | "MUST_ADDRESS_IN_ANSWER" | "QUALITY_IMPROVEMENT" | "NONE",
            "matched_phrases": list[str],
            "matched_words": list[str],
            "has_non_critical_context": bool,
            "text_sample": str
        }
    """
    text = _normalize_text(value)
    if not text:
        return {"class": "NONE", "matched_phrases": [], "matched_words": [], "has_non_critical_context": False, "text_sample": ""}

    result = {
        "matched_phrases": [],
        "matched_words": [],
        "has_non_critical_context": any(ctx in text for ctx in NON_CRITICAL_CONTEXT),
        "text_sample": text[:200],
    }

    if is_pipeline_failure_text(text):
        result["class"] = "NONE"
        if trace is not None:
            trace.append({"type": "classify_blocker_pipeline_failure_skip", **result})
        return result

    # Check NO_ANSWER_BLOCKER phrases first (highest priority)
    no_answer_phrases = [phrase for phrase in NO_ANSWER_BLOCKER_PHRASES if phrase in text]
    if no_answer_phrases:
        result["class"] = "NO_ANSWER_BLOCKER"
        result["matched_phrases"] = no_answer_phrases
        if trace is not None:
            trace.append({"type": "classify_blocker", **result})
        return result

    # Check NO_ANSWER_BLOCKER words with context
    no_answer_words = [word for word in NO_ANSWER_BLOCKER_WORDS if word in text]
    if no_answer_words and not result["has_non_critical_context"]:
        result["class"] = "NO_ANSWER_BLOCKER"
        result["matched_words"] = no_answer_words
        if trace is not None:
            trace.append({"type": "classify_blocker", **result})
        return result

    # Check MUST_ADDRESS phrases
    must_address_phrases = [phrase for phrase in MUST_ADDRESS_PHRASES if phrase in text]
    if must_address_phrases:
        result["class"] = "MUST_ADDRESS_IN_ANSWER"
        result["matched_phrases"] = must_address_phrases
        if trace is not None:
            trace.append({"type": "classify_blocker", **result})
        return result

    # Check MUST_ADDRESS words
    must_address_words = [word for word in MUST_ADDRESS_WORDS if word in text]
    if must_address_words:
        result["class"] = "MUST_ADDRESS_IN_ANSWER"
        result["matched_words"] = must_address_words
        if trace is not None:
            trace.append({"type": "classify_blocker", **result})
        return result

    # Check QUALITY_IMPROVEMENT phrases
    quality_phrases = [phrase for phrase in QUALITY_IMPROVEMENT_PHRASES if phrase in text]
    if quality_phrases:
        result["class"] = "QUALITY_IMPROVEMENT"
        result["matched_phrases"] = quality_phrases
        if trace is not None:
            trace.append({"type": "classify_blocker", **result})
        return result

    # No match
    result["class"] = "NONE"
    if trace is not None:
        trace.append({"type": "classify_blocker", **result})
    return result


def _is_critical_text(value: Any, trace: list | None = None) -> bool:
    """Check if text contains critical safety/legal/privacy issues.

    Uses hybrid approach:
    1. Specific phrases always trigger (e.g., "safety issue", "privacy leak")
    2. Generic words trigger only if not in recommendation context

    Args:
        value: Text to check
        trace: Optional list to append diagnostic info

    Returns:
        True if text contains critical issues
    """
    text = _normalize_text(value)
    if not text:
        return False

    # Check specific critical phrases first
    matched_phrases = [phrase for phrase in CRITICAL_PHRASES if phrase in text]
    if matched_phrases:
        if trace is not None:
            trace.append({
                "type": "critical_phrase_match",
                "matched": matched_phrases,
                "text_sample": text[:200],
            })
        return True

    # Check generic critical words with context
    matched_words = [word for word in CRITICAL_WORDS if word in text]
    if matched_words:
        # Check if this is a recommendation/suggestion context
        has_non_critical_context = any(ctx in text for ctx in NON_CRITICAL_CONTEXT)

        if trace is not None:
            trace.append({
                "type": "critical_word_check",
                "matched_words": matched_words,
                "has_non_critical_context": has_non_critical_context,
                "text_sample": text[:200],
            })

        if not has_non_critical_context:
            return True

    return False


def is_pipeline_failure_text(value: Any) -> bool:
    """Return True for internal provider/API/JSON failures, not user-domain risks."""
    text = _normalize_text(value)
    return bool(text) and any(marker in text for marker in PIPELINE_FAILURE_MARKERS)


def _is_plan_stop_text(value: Any, trace: list | None = None) -> bool:
    """True only for real no-answer blockers: safety/legal/privacy/medical/etc.

    Do not treat generic words like 'critical' or any REJECT as automatic
    no-answer blockers. Generic plan-quality rejection is handled separately
    by state_machine as plan_rejected_after_max_iters.

    Args:
        value: Text to check
        trace: Optional list to append diagnostic info

    Returns:
        True if text contains true no-answer blockers
    """
    text = _normalize_text(value)
    if not text:
        return False
    if is_pipeline_failure_text(text):
        if trace is not None:
            trace.append({
                "type": "pipeline_failure_skip",
                "text_sample": text[:200],
            })
        return False

    # Use the same hybrid logic as _is_critical_text
    return _is_critical_text(value, trace=trace)


def _normalize_decision(value: Any, default: str = "") -> str:
    decision = str(value or "").upper().strip()
    if decision in {"ACCEPT", "REVISE", "REJECT"}:
        return decision

    status = str(value or "").lower().strip()
    return {
        "ready": "ACCEPT",
        "needs_revision": "REVISE",
        "rejected": "REJECT",
    }.get(status, default)


def _decision_from_status(value: Any) -> str:
    return _normalize_decision(value, default="")


def plan_blockers(critique_result: Any, trace: list | None = None) -> dict:
    """Classify plan critique items into blocker classes.

    Returns:
        {
            "no_answer_blockers": list[str],  # Must stop answer generation
            "must_address": list[str],        # Must be addressed in answer
            "quality_improvements": list[str], # Suggestions only
            "debug": dict                     # Diagnostic info
        }

    Important:
    - Do not include every critical_issues item automatically.
    - Do not turn every REJECT into critical_plan_blockers.
    - Trade-offs, risks, constraints go to must_address, not no_answer_blockers.
    """
    result = _safe_dict(critique_result)
    critique = result.get("critique") if isinstance(result.get("critique"), dict) else result

    no_answer_blockers: list[str] = []
    must_address: list[str] = []
    quality_improvements: list[str] = []

    classify_trace: list[dict] = []
    raw_items: list[dict] = []

    # Process all critique fields
    all_fields = {
        "critical_blockers": _string_items(critique.get("critical_blockers")),
        "critical_issues": _string_items(critique.get("critical_issues")),
        "ignored_must_address": _string_items(critique.get("ignored_must_address")),
        "ignored_risks": _string_items(critique.get("ignored_risks")),
        "ignored_expert_risks": _string_items(critique.get("ignored_expert_risks")),
        "unresolved_tradeoffs": _string_items(critique.get("unresolved_tradeoffs")),
        "ignored_tradeoffs": _string_items(critique.get("ignored_tradeoffs")),
    }

    for field_name, items in all_fields.items():
        for item in items:
            classification = classify_blocker(item, trace=classify_trace)

            raw_items.append({
                "field": field_name,
                "text": item,
                "classification": classification["class"],
                "matched_phrases": classification.get("matched_phrases", []),
                "matched_words": classification.get("matched_words", []),
            })

            if classification["class"] == "NO_ANSWER_BLOCKER":
                no_answer_blockers.append(item)
            elif classification["class"] == "MUST_ADDRESS_IN_ANSWER":
                must_address.append(item)
            elif classification["class"] == "QUALITY_IMPROVEMENT":
                quality_improvements.append(item)

    debug_info = {
        "raw_items": raw_items,
        "no_answer_count": len(no_answer_blockers),
        "must_address_count": len(must_address),
        "quality_improvement_count": len(quality_improvements),
        "classify_trace": classify_trace,
    }

    if trace is not None:
        trace.append({
            "function": "plan_blockers",
            "debug": debug_info,
        })

    return {
        "no_answer_blockers": _dedupe(no_answer_blockers),
        "must_address": _dedupe(must_address),
        "quality_improvements": _dedupe(quality_improvements),
        "debug": debug_info,
    }


def has_critical_plan_blockers(critique_result: Any) -> bool:
    """Return True when plan critique contains NO_ANSWER_BLOCKER items that must stop answer generation.

    MUST_ADDRESS and QUALITY_IMPROVEMENT items do not block answer generation.
    """
    blockers = plan_blockers(critique_result)
    return bool(blockers.get("no_answer_blockers"))


def get_must_address_items(critique_result: Any) -> list[str]:
    """Get items that must be addressed in final answer but don't block generation.

    These are trade-offs, risks, constraints that should be converted to decision rules
    like "choose X if..., Y if...".
    """
    blockers = plan_blockers(critique_result)
    return blockers.get("must_address", [])


def _last_report(moderated_result: dict) -> dict:
    reports = _safe_list(moderated_result.get("reports"))
    if reports and isinstance(reports[-1], dict):
        return reports[-1]
    return {}


def _collect_answer_critical_issues(moderated_result: dict, trace: list | None = None) -> list[str]:
    """Collect only true NO_ANSWER_BLOCKER issues from answer moderation.

    Do not treat every item labeled 'critical_issues' as a hard blocker.
    Only block finalization for true safety/legal/privacy/medical/financial risks.
    """
    issues: list[str] = []
    last = _last_report(moderated_result)

    issues.extend(_string_items(moderated_result.get("critical_issues")))
    issues.extend(_string_items(last.get("critical_issues")))

    for key in (
        "ignored_expert_risks",
        "ignored_expert_recommendations",
        "unresolved_questions",
    ):
        issues.extend(_string_items(moderated_result.get(key)))
        issues.extend(_string_items(last.get(key)))

    critical: list[str] = []
    classify_trace: list[dict] = []

    for item in issues:
        classification = classify_blocker(item, trace=classify_trace)
        if classification["class"] == "NO_ANSWER_BLOCKER":
            critical.append(item)

    if trace is not None:
        trace.append({
            "function": "_collect_answer_critical_issues",
            "total_issues": len(issues),
            "no_answer_blockers": len(critical),
            "classify_trace": classify_trace,
        })

    return _dedupe(critical)


def normalize_moderated_result(value: Any, trace: list | None = None) -> dict:
    """Normalize old/new run_moderated_loop payloads into the Phase 6 contract.

    Expected contract:
    {
      "final_answer": str,
      "reports": list,
      "final_decision": "ACCEPT|REVISE|REJECT",
      "critical_issues": list[str],
      "revision_count": int,
      "source": str
    }
    """
    result = dict(value) if isinstance(value, dict) else {}

    reports = _safe_list(result.get("reports"))
    last = _last_report(result)

    final_answer = result.get("final_answer")
    if not isinstance(final_answer, str):
        final_answer = ""

    rejected_answer = result.get("rejected_answer")
    if not isinstance(rejected_answer, str):
        rejected_answer = ""

    final_decision = _normalize_decision(result.get("final_decision"))
    if not final_decision:
        final_decision = _normalize_decision(last.get("decision"))
    if not final_decision:
        final_decision = "ACCEPT" if final_answer.strip() else "REJECT"

    rejected = bool(result.get("rejected")) or final_decision == "REJECT"

    critical_issues = _collect_answer_critical_issues(result, trace=trace)

    if rejected:
        if final_answer and not rejected_answer:
            rejected_answer = final_answer
        final_answer = ""

    revision_count = result.get("revision_count")
    if not isinstance(revision_count, int):
        revision_count = sum(
            1 for report in reports
            if isinstance(report, dict) and str(report.get("decision") or "").upper() == "REVISE"
        )

    source = result.get("source") or last.get("source") or "moderated_loop"
    if not isinstance(source, str):
        source = "moderated_loop"

    normalized = dict(result)
    normalized.update(
        {
            "final_answer": final_answer,
            "rejected_answer": rejected_answer,
            "reports": reports,
            "final_decision": final_decision,
            "critical_issues": critical_issues,
            "revision_count": max(0, revision_count),
            "source": source,
            "rejected": rejected,
        }
    )
    return normalized


def has_critical_answer_blockers(moderated_result: Any, trace: list | None = None) -> bool:
    """Return True when answer moderation must block finalization.

    Only NO_ANSWER_BLOCKER items block finalization.
    """
    normalized = normalize_moderated_result(moderated_result, trace=trace)
    if _safe_list(normalized.get("critical_issues")):
        return True

    for report in _safe_list(normalized.get("reports")):
        if not isinstance(report, dict):
            continue
        if _collect_answer_critical_issues({"reports": [report]}, trace=trace):
            return True

    return False


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
        if _string_items(step.get("substeps")):
            return True
    return False


def can_best_effort_finalize(
    *,
    critique_result: Any | None = None,
    moderated_result: Any | None = None,
    plan: Any | None = None,
    trace: list | None = None,
) -> bool:
    """Return True only when best-effort finalization is safe.

    Best-effort is allowed for non-critical needs_revision / REVISE / REJECT cases.
    It is never allowed when plan or answer gates contain NO_ANSWER_BLOCKER items.

    IMPORTANT: REJECT decision alone is not a blocker. Only REJECT with critical
    safety/legal/privacy/security issues blocks answer generation.
    """
    if critique_result is not None:
        if has_critical_plan_blockers(critique_result):
            if trace is not None:
                trace.append({"best_effort_blocked_by": "critical_plan_blockers"})
            return False
        result = _safe_dict(critique_result)
        decision = _normalize_decision(result.get("decision") or result.get("status"))
        effective_plan = plan if plan is not None else result.get("plan")
        if decision == "REJECT" and not _has_actionable_plan(effective_plan):
            if trace is not None:
                trace.append({"best_effort_blocked_by": "reject_without_actionable_plan"})
            return False
        if effective_plan is not None and not _has_actionable_plan(effective_plan):
            if trace is not None:
                trace.append({"best_effort_blocked_by": "no_actionable_plan"})
            return False

    if moderated_result is not None:
        normalized = normalize_moderated_result(moderated_result, trace=trace)
        if has_critical_answer_blockers(normalized, trace=trace):
            if trace is not None:
                trace.append({"best_effort_blocked_by": "critical_answer_blockers"})
            return False

    if trace is not None:
        trace.append({"best_effort_allowed": True})
    return True


__all__ = [
    "classify_blocker",
    "plan_blockers",
    "has_critical_plan_blockers",
    "get_must_address_items",
    "has_critical_answer_blockers",
    "can_best_effort_finalize",
    "normalize_moderated_result",
    "is_pipeline_failure_text",
    "create_quality_gate_debug",
]


def create_quality_gate_debug(
    *,
    critique_result: Any | None = None,
    moderated_result: Any | None = None,
    plan: Any | None = None,
    stage: str = "UNKNOWN",
) -> dict:
    """Create comprehensive quality gate debug information.

    Returns:
        {
            "stage": str,
            "plan_analysis": {
                "raw_critical_blockers": list[str],
                "filtered_no_answer_blockers": list[str],
                "converted_to_must_address": list[str],
                "quality_improvements": list[str],
                "matched_policy_terms": dict,
                "trace": list[dict]
            },
            "answer_analysis": {
                "raw_critical_issues": list[str],
                "filtered_no_answer_blockers": list[str],
                "trace": list[dict]
            },
            "decision": "ALLOW" | "BEST_EFFORT" | "BLOCK",
            "why": str,
            "timestamp": str
        }
    """
    import datetime

    debug = {
        "stage": stage,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }

    # Plan analysis
    if critique_result is not None:
        plan_trace: list[dict] = []
        blockers = plan_blockers(critique_result, trace=plan_trace)

        debug["plan_analysis"] = {
            "raw_critical_blockers": blockers["debug"]["raw_items"],
            "filtered_no_answer_blockers": blockers["no_answer_blockers"],
            "converted_to_must_address": blockers["must_address"],
            "quality_improvements": blockers["quality_improvements"],
            "matched_policy_terms": {
                "no_answer_phrases": list(NO_ANSWER_BLOCKER_PHRASES),
                "no_answer_words": list(NO_ANSWER_BLOCKER_WORDS),
                "must_address_phrases": list(MUST_ADDRESS_PHRASES),
                "must_address_words": list(MUST_ADDRESS_WORDS),
            },
            "trace": plan_trace,
        }

    # Answer analysis
    if moderated_result is not None:
        answer_trace: list[dict] = []
        normalized = normalize_moderated_result(moderated_result, trace=answer_trace)
        critical_issues = normalized.get("critical_issues", [])

        debug["answer_analysis"] = {
            "raw_critical_issues": _string_items(moderated_result.get("critical_issues")),
            "filtered_no_answer_blockers": critical_issues,
            "trace": answer_trace,
        }

    # Decision
    decision_trace: list[dict] = []
    can_finalize = can_best_effort_finalize(
        critique_result=critique_result,
        moderated_result=moderated_result,
        plan=plan,
        trace=decision_trace,
    )

    has_plan_blockers = critique_result is not None and has_critical_plan_blockers(critique_result)
    has_answer_blockers = moderated_result is not None and has_critical_answer_blockers(moderated_result)

    if has_plan_blockers or has_answer_blockers:
        debug["decision"] = "BLOCK"
        reasons = []
        if has_plan_blockers:
            reasons.append("plan contains NO_ANSWER_BLOCKER items")
        if has_answer_blockers:
            reasons.append("answer contains NO_ANSWER_BLOCKER items")
        debug["why"] = "; ".join(reasons)
    elif can_finalize:
        debug["decision"] = "ALLOW"
        debug["why"] = "no critical blockers found"
    else:
        debug["decision"] = "BEST_EFFORT"
        debug["why"] = "non-critical issues present, best-effort allowed"

    debug["decision_trace"] = decision_trace

    return debug
