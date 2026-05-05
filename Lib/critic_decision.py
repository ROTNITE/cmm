"""Compatibility wrapper for context-aware plan critique decisions.

The active implementation lives in ``Lib.plan_critic``. This module preserves
older imports and the manual ``show_critique`` helper.
"""

from __future__ import annotations

from Lib.plan_critic import check_plan_and_act, decide_on_critique


def quick_decision(plan: dict, query: str) -> dict:
    """Legacy quick decision helper backed by ``Lib.plan_critic``."""
    return decide_on_critique(plan, query, depth="quick")


def show_critique(critique: dict) -> None:
    """Legacy/manual display helper; not used by the CMM state machine."""
    if not isinstance(critique, dict):
        print({})
        return
    print(critique)


__all__ = ["check_plan_and_act", "decide_on_critique", "quick_decision", "show_critique"]
