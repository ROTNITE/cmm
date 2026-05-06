"""Human-readable summaries for CMM trace reports."""

from __future__ import annotations

from typing import Any


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _text(value: Any, default: str = "none") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _item_text(item: Any) -> str:
    if isinstance(item, dict):
        for key in (
            "key",
            "name",
            "title",
            "summary",
            "description",
            "reason",
            "issue",
            "constraint",
            "tradeoff",
            "raw_key",
        ):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        parts = []
        for key in ("from", "to", "severity", "role", "perspective_tag"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        return " / ".join(parts) if parts else "item"
    return _text(item)


def _limited(items: Any, *, max_items: int) -> list[str]:
    values = [_item_text(item) for item in _safe_list(items)]
    if max_items < 1:
        max_items = 1
    if len(values) <= max_items:
        return values
    remaining = len(values) - max_items
    return values[:max_items] + [f"... +{remaining} more"]


def _line(label: str, value: Any) -> str:
    return f"- {label}: {_text(value)}"


def _list_line(label: str, items: Any, *, max_items: int) -> str:
    values = _limited(items, max_items=max_items)
    return f"- {label}: {', '.join(values) if values else 'none'}"


def _state_path(trace: dict) -> str:
    history = _safe_list(trace.get("state_history"))
    if not history:
        final_state = trace.get("final_state")
        return _text(final_state)
    states: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        from_state = str(item.get("from") or "").strip()
        to_state = str(item.get("to") or "").strip()
        if from_state and not states:
            states.append(from_state)
        if to_state:
            states.append(to_state)
    return " -> ".join(states) if states else _text(trace.get("final_state"))


def _role_label(role: dict) -> str:
    key = _text(role.get("key"))
    tag = _text(role.get("perspective_tag"), "")
    rounds = _safe_list(role.get("rounds"))
    suffix = f" [{'/'.join(str(item) for item in rounds)}]" if rounds else ""
    return f"{key}{f' ({tag})' if tag else ''}{suffix}"


def _roles_by_dynamic(trace: dict, dynamic: bool) -> list[str]:
    out = []
    for role in _safe_list(trace.get("roles_used_unique")):
        if isinstance(role, dict) and bool(role.get("dynamic")) is dynamic:
            out.append(_role_label(role))
    return out


def _latest_report(trace: dict, key: str) -> dict:
    reports = [item for item in _safe_list(trace.get(key)) if isinstance(item, dict)]
    return reports[-1] if reports else {}


def _argument_quality(balance: dict) -> str:
    quality = _safe_dict(balance.get("argument_quality"))
    if not quality:
        return "none"
    parts = []
    for key in ("evidence_level", "specificity", "actionability", "novelty", "tradeoff_awareness"):
        if key in quality:
            parts.append(f"{key}={quality.get(key)}")
    return ", ".join(parts) if parts else "none"


def _dynamic_executed_label(role: dict) -> str:
    key = _text(role.get("key"))
    round_name = _text(role.get("round"), "")
    return f"{key}{f' [{round_name}]' if round_name else ''}"


def format_trace_report(trace_report: dict, *, max_items: int = 8) -> str:
    """Format a compact, human-readable CMM trace summary."""
    trace = _safe_dict(trace_report)
    router = _safe_dict(trace.get("router_decision"))
    balance = _latest_report(trace, "balance_reports")
    conflict = _latest_report(trace, "conflict_reports")

    lines = ["CMM TRACE SUMMARY", ""]

    lines.extend(
        [
            "1. Routing",
            _line("Mode", trace.get("cmm_mode") or router.get("mode")),
            _line("Reason", router.get("reason")),
            _line("Cost class", trace.get("estimated_cost_class") or router.get("estimated_cost_class")),
            "",
            "2. State path",
            _line("Path", _state_path(trace)),
            _line("Final state", trace.get("final_state")),
            "",
            "3. Roles",
            _list_line("Base", _roles_by_dynamic(trace, False), max_items=max_items),
            _list_line("Dynamic generated", trace.get("dynamic_roles_generated"), max_items=max_items),
            _list_line(
                "Dynamic executed",
                [_dynamic_executed_label(role) for role in _safe_list(trace.get("dynamic_roles_executed")) if isinstance(role, dict)],
                max_items=max_items,
            ),
            _list_line("Rejected suggestions", trace.get("dynamic_roles_rejected"), max_items=max_items),
            "",
            "4. Balance",
            _list_line("Missing", balance.get("missing_perspectives"), max_items=max_items),
            _line("Dominance", balance.get("dominant_perspective") or _safe_dict(balance.get("dominance")).get("dominant_perspective")),
            _line("Argument quality", _argument_quality(balance)),
            _line("Recommended action", balance.get("recommended_action")),
            "",
            "5. Conflicts",
            _list_line("Disagreements", conflict.get("disagreements"), max_items=max_items),
            _list_line("Trade-offs", conflict.get("unresolved_tradeoffs"), max_items=max_items),
            _list_line("Blind spots", conflict.get("blind_spots"), max_items=max_items),
            "",
            "6. Deliberation",
            _list_line("Revised recommendations", trace.get("deliberation_revisions"), max_items=max_items),
            _list_line("New risks", _safe_dict(_latest_report(trace, "deliberation_rounds")).get("new_risks"), max_items=max_items),
            "",
            "7. Plan critique",
            _list_line("Decision", trace.get("plan_critique_decisions") or trace.get("plan_critique_statuses"), max_items=max_items),
            _list_line("Blockers", trace.get("plan_critique_blockers"), max_items=max_items),
            _list_line("Replan reasons", trace.get("plan_replan_reasons"), max_items=max_items),
            "",
            "8. Answer moderation",
            _line("Final decision", trace.get("answer_moderation_final_decision")),
            _line("Revision count", trace.get("revision_count")),
            _line("Confidence", trace.get("final_confidence")),
            "",
            "9. Warnings / errors",
            _list_line("Warnings", trace.get("warnings"), max_items=max_items),
            _list_line("Errors", trace.get("errors"), max_items=max_items),
        ]
    )

    return "\n".join(lines).rstrip() + "\n"


__all__ = ["format_trace_report"]
