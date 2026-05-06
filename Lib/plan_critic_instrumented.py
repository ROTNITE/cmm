"""Instrumented plan critic with logging."""

from __future__ import annotations

import os
from typing import Any

from Lib.plan_critic import critique_plan as _original_critique_plan


def critique_plan(
    plan: Any,
    context: dict | None = None,
    model: str = "deepseek-chat",
) -> dict:
    """Instrumented version of critique_plan with logging."""
    # Only log if eval logging is enabled
    if os.environ.get("CMM_EVAL_LOGGING") != "1":
        return _original_critique_plan(plan, context, model)

    from Lib.eval_logger import get_logger

    logger = get_logger()
    logger.agent_start("plan_critic", "evaluating plan")

    result = _original_critique_plan(plan, context, model)

    # Log result
    decision = result.get("decision", "unknown")
    status = "success" if decision in ["APPROVED", "NEEDS_REVISION"] else "fallback"
    logger.agent_end("plan_critic", status)

    if decision == "NEEDS_REVISION":
        logger.info(f"Plan needs revision: {result.get('summary', '')[:100]}")
    elif decision == "APPROVED":
        logger.info("Plan approved")

    return result
