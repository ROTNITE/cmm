"""Instrumented answer moderator with logging."""

from __future__ import annotations

import os
from typing import Any

from Lib.agent_moderator import moderate_answer as _original_moderate_answer


def moderate_answer(
    answer: str,
    query: str,
    context: dict | None = None,
    model: str = "deepseek-chat",
) -> dict:
    """Instrumented version of moderate_answer with logging."""
    # Only log if eval logging is enabled
    if os.environ.get("CMM_EVAL_LOGGING") != "1":
        return _original_moderate_answer(answer, query, context, model)

    from Lib.eval_logger import get_logger

    logger = get_logger()
    logger.agent_start("answer_moderator", "checking answer quality")

    result = _original_moderate_answer(answer, query, context, model)

    # Log result
    decision = result.get("decision", "unknown")
    status = "success" if decision in ["APPROVED", "NEEDS_REVISION"] else "fallback"
    logger.agent_end("answer_moderator", status)

    if decision == "NEEDS_REVISION":
        issues = result.get("issues", [])
        logger.warning(f"Answer needs revision: {len(issues)} issues found")
    elif decision == "APPROVED":
        logger.info("Answer approved")

    return result
