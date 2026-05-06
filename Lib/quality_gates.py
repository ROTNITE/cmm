"""Centralized quality gates for CMM finalization decisions.

This module owns the critical-blocker policy used by the CMM state machine:

- critical plan blockers -> no answer generation
- critical answer moderation issues -> no finalize
- critical safety/legal/privacy risks ignored -> no best-effort finalize

The functions are intentionally deterministic and dependency-light so they can
be used by state_machine without pulling in model/API code.
"""

from __future__ import annotations

import re
from typing import Any


CRITICAL_MARKERS = (
    "critical",
    "safety",
    "security",
    "privacy",
    "legal",
    "compliance",
    "harm",
    "unsafe",
    "danger",
    "failure",
    "irreversible",
    "medical",
    "financial",
    "vulnerable",
    "secret",
    "credential",
    "leak",
    "pii",
    "gdpr",
    "hipaa",
    "критическ",
    "безопас",
    "опасн",
    "закон",
    "право",
    "комплаенс",
    "приват",
    "персональн",
    "утеч",
    "вред",
    "секрет",
    "ключ",
    "финанс",
    "медиц",
    "уязвим",
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


def _is_critical_text(value: Any) -> bool:
    text = _normalize_text(value)
    return bool(text) and any(marker in text for marker in CRITICAL_MARKERS)


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


def plan_blockers(critique_result: Any) -> list[str]:
    """Return critical plan blockers from a plan critique result."""
    result = _safe_dict(critique_result)
    critique = result.get("critique") if isinstance(result.get("critique"), dict) else result

    blockers: list[str] = []
    blockers.extend(_string_items(critique.get("critical_blockers")))
    blockers.extend(_string_items(critique.get("critical_issues")))

    for key in (
        "ignored_must_address",
        "ignored_risks",
        "ignored_expert_risks",
        "unresolved_tradeoffs",
        "ignored_tradeoffs",
    ):
        for item in _string_items(critique.get(key)):
            if _is_critical_text(item):
                blockers.append(item)

    if _decision_from_status(result.get("decision") or result.get("status")) == "REJECT":
        reason = str(result.get("reason") or "").strip()
        blockers.append(reason or "Plan critique rejected the plan.")

    return _dedupe(blockers)


def has_critical_plan_blockers(critique_result: Any) -> bool:
    """Return True when plan critique contains blockers that must stop answer generation."""
    return bool(plan_blockers(critique_result))


def _last_report(moderated_result: dict) -> dict:
    reports = _safe_list(moderated_result.get("reports"))
    if reports and isinstance(reports[-1], dict):
        return reports[-1]
    return {}


def _collect_answer_critical_issues(moderated_result: dict) -> list[str]:
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
    for item in issues:
        if _is_critical_text(item) or item in _string_items(moderated_result.get("critical_issues")):
            critical.append(item)

    return _dedupe(critical)


def normalize_moderated_result(value: Any) -> dict:
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

    critical_issues = _collect_answer_critical_issues(result)

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


def has_critical_answer_blockers(moderated_result: Any) -> bool:
    """Return True when answer moderation must block finalization."""
    normalized = normalize_moderated_result(moderated_result)
    if normalized.get("final_decision") == "REJECT":
        return True
    if normalized.get("rejected"):
        return True
    if _safe_list(normalized.get("critical_issues")):
        return True

    for report in _safe_list(normalized.get("reports")):
        if not isinstance(report, dict):
            continue
        if str(report.get("decision") or "").upper() == "REJECT":
            return True
        if _collect_answer_critical_issues({"reports": [report]}):
            return True

    return False


def can_best_effort_finalize(
    *,
    critique_result: Any | None = None,
    moderated_result: Any | None = None,
) -> bool:
    """Return True only when best-effort finalization is safe.

    Best-effort is allowed for non-critical needs_revision / REVISE cases.
    It is never allowed when plan or answer gates contain critical blockers.
    """
    if critique_result is not None:
        if has_critical_plan_blockers(critique_result):
            return False
        result = _safe_dict(critique_result)
        decision = _normalize_decision(result.get("decision") or result.get("status"))
        if decision == "REJECT":
            return False

    if moderated_result is not None:
        normalized = normalize_moderated_result(moderated_result)
        if has_critical_answer_blockers(normalized):
            return False
        if normalized.get("final_decision") == "REJECT":
            return False

    return True