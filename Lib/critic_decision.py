"""Compatibility wrapper for context-aware plan critique decisions."""

from __future__ import annotations

from Lib.plan_critic import check_plan_and_act, decide_on_critique


def quick_decision(plan: dict, query: str) -> dict:
    """Legacy quick decision helper."""
    return decide_on_critique(plan, query, depth="quick")


def show_critique(critique: dict) -> None:
    """Legacy display helper kept for manual scripts."""
    if not isinstance(critique, dict):
        print({})
        return
    print(critique)


__all__ = ["check_plan_and_act", "decide_on_critique", "quick_decision", "show_critique"]
