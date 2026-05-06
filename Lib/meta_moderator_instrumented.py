"""Instrumented meta moderator with logging."""

from __future__ import annotations

import os
from typing import Any

from Lib.meta_moderator import run_meta_moderator as _original_run_meta_moderator


def run_meta_moderator(
    query: str,
    expert_bundle: dict,
    conflict_report: dict | None = None,
    context: dict | None = None,
    model: str = "deepseek-chat",
) -> dict:
    """Instrumented version of run_meta_moderator with logging."""
    # Only log if eval logging is enabled
    if os.environ.get("CMM_EVAL_LOGGING") != "1":
        return _original_run_meta_moderator(query, expert_bundle, conflict_report, context, model)

    from Lib.eval_logger import get_logger

    logger = get_logger()
    logger.agent_start("meta_moderator", "synthesizing expert inputs")

    result = _original_run_meta_moderator(query, expert_bundle, conflict_report, context, model)

    # Log result
    decision = result.get("decision", "unknown")
    status = "success" if decision in ["SUFFICIENT", "NEEDS_DELIBERATION"] else "fallback"
    logger.agent_end("meta_moderator", status)

    if decision == "NEEDS_DELIBERATION":
        logger.info("Meta moderator: needs deliberation")
    elif decision == "SUFFICIENT":
        logger.info("Meta moderator: sufficient consensus")

    return result
