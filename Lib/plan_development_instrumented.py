"""Instrumented plan development with logging."""

from __future__ import annotations

import os
from typing import Any

from Lib.plan_development import develop_plan as _original_develop_plan


def develop_plan(query, context=None, depth="detailed", model="deepseek-chat"):
    """Instrumented version of develop_plan with logging."""
    # Only log if eval logging is enabled
    if os.environ.get("CMM_EVAL_LOGGING") != "1":
        return _original_develop_plan(query, context, depth, model)

    from Lib.eval_logger import get_logger

    logger = get_logger()
    logger.agent_start("planner", f"depth={depth}")

    result = _original_develop_plan(query, context, depth, model)

    # Log result
    is_valid = isinstance(result, dict) and result.get("steps")
    status = "success" if is_valid else "fallback"
    logger.agent_end("planner", status)

    if not is_valid:
        logger.warning("Planner returned fallback (JSON parse failed)")

    return result
