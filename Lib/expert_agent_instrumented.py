"""Instrumented expert agent with logging."""

from __future__ import annotations

import os
from typing import Any

from Lib.expert_agent import run_expert as _original_run_expert
from Lib.expert_roles import ExpertRole


def run_expert(
    role: ExpertRole,
    query: str,
    context: dict | None = None,
    model: str = "deepseek-chat",
) -> dict:
    """Instrumented version of run_expert with logging."""
    # Only log if eval logging is enabled
    if os.environ.get("CMM_EVAL_LOGGING") != "1":
        return _original_run_expert(role, query, context, model)

    from Lib.eval_logger import get_logger

    logger = get_logger()
    logger.agent_start("expert", f"{role.name} ({role.perspective_tag})")

    result = _original_run_expert(role, query, context, model)

    # Log result
    is_valid = result.get("source") == "model"
    status = "success" if is_valid else "fallback"
    logger.agent_end("expert", status)

    if not is_valid:
        logger.warning(f"Expert {role.key} returned fallback (JSON parse failed)")

    return result
