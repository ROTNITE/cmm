"""Small result assembly helpers for CMM state-machine traces."""

from __future__ import annotations

from typing import Any


def build_result_payload(
    *,
    state: dict,
    trace_report: dict,
    raw_state: dict,
    failed_state: str = "FAILED",
) -> dict:
    """Assemble the public result payload without owning state transitions."""
    final_answer = state.get("final_answer") if state.get("current_state") != failed_state else ""
    if not isinstance(final_answer, str):
        final_answer = ""
    return {
        "final_answer": final_answer,
        "trace_report": trace_report,
        "raw": {
            "expert_bundle": state.get("expert_bundle", {}),
            "moderated_result": state.get("moderated_result", {}),
            "state": raw_state,
        },
    }


def safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


__all__ = ["build_result_payload", "safe_list"]
