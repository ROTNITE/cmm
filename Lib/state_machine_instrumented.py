"""Instrumented state machine wrapper with logging for eval."""

from __future__ import annotations

from Lib.config import get_default_model
from Lib.state_machine import run_cmm_state_machine as _original_run_cmm_state_machine
from Lib.eval_logger import get_logger


def run_cmm_state_machine(
    query: str,
    *,
    max_iters: int = 2,
    model: str | None = None,
    max_transitions: int = 40,
    route_mode: str = "AUTO",
    parallel_mode: str = "SEQUENTIAL",
    max_workers: int | None = None,
    max_deliberation_rounds: int = 1,
) -> dict:
    """Instrumented version of run_cmm_state_machine with logging."""
    logger = get_logger()

    # Log start
    logger.info(f"Starting CMM state machine (route_mode={route_mode})")

    # Run original
    result = _original_run_cmm_state_machine(
        query,
        max_iters=max_iters,
        model=get_default_model(model),
        max_transitions=max_transitions,
        route_mode=route_mode,
        parallel_mode=parallel_mode,
        max_workers=max_workers,
        max_deliberation_rounds=max_deliberation_rounds,
    )

    # Log completion
    trace = result.get("trace_report", {})
    if isinstance(trace, dict):
        final_state = trace.get("final_state", "unknown")
        logger.info(f"CMM completed with state: {final_state}")

    return result
