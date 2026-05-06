"""Public CMM orchestration entrypoint."""

from __future__ import annotations

from Lib.state_machine import run_cmm_state_machine


def run_cmm(
    query: str,
    *,
    max_iters: int = 2,
    model: str = "deepseek-chat",
    route_mode: str = "AUTO",
    parallel_mode: str = "SEQUENTIAL",
    max_workers: int | None = None,
    max_deliberation_rounds: int = 1,
) -> dict:
    """Run the Collective Meta-Moderation pipeline through the state machine."""
    return run_cmm_state_machine(
        query,
        max_iters=max_iters,
        model=model,
        route_mode=route_mode,
        parallel_mode=parallel_mode,
        max_workers=max_workers,
        max_deliberation_rounds=max_deliberation_rounds,
    )
