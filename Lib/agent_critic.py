"""Legacy compatibility wrapper for plan critique.

The active CMM state machine uses :mod:`Lib.plan_critic` through
``Lib.critic_decision``. This module is kept only for older manual scripts that
still import ``criticize_plan`` or ``show_critique``. It is silent by default.
"""

from __future__ import annotations

from Lib.plan_critic import check_plan_and_act


def _legacy_scores(critique: dict) -> dict:
    scores = critique.get("scores") if isinstance(critique, dict) else {}
    if not isinstance(scores, dict):
        return {}
    return {
        "Соответствие": float(scores.get("query_alignment", 0.0) or 0.0),
        "Полнота": float(scores.get("constraint_coverage", 0.0) or 0.0),
        "Риски": float(scores.get("risk_coverage", 0.0) or 0.0),
        "Понятность": float(scores.get("clarity", 0.0) or 0.0),
    }


def criticize_plan(plan, original_query, depth="standard"):
    """Return a legacy-shaped critique dict using the current plan critic.

    This compatibility function does not decide the CMM process flow and does
    not print. New code should import from ``Lib.plan_critic`` or
    ``Lib.critic_decision`` directly.
    """
    result = check_plan_and_act(plan, original_query, depth=depth)
    critique = result.get("critique") if isinstance(result, dict) else {}
    critique = critique if isinstance(critique, dict) else {}
    feedback = result.get("feedback") if isinstance(result, dict) and isinstance(result.get("feedback"), list) else []
    strengths = critique.get("strengths") if isinstance(critique.get("strengths"), list) else []
    critical_issues = critique.get("critical_issues") if isinstance(critique.get("critical_issues"), list) else []
    final_score = critique.get("overall_score", critique.get("final_score", 0.0))
    try:
        final_score = float(final_score)
    except Exception:
        final_score = 0.0

    return {
        "scores": _legacy_scores(critique),
        "strengths": strengths,
        "weaknesses": critical_issues,
        "recommendations": feedback,
        "final_score": final_score,
        "status": result.get("status") if isinstance(result, dict) else "needs_revision",
        "source": "plan_critic_compat",
    }


def show_critique(critique):
    """Manual display helper for legacy scripts; intentionally prints."""
    if not isinstance(critique, dict):
        print({})
        return
    print(critique)

__all__ = ["criticize_plan", "show_critique"]
