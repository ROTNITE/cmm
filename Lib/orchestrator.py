"""Public CMM orchestration entrypoint."""

from __future__ import annotations

from Lib.state_machine import run_cmm_state_machine


def run_cmm(query: str, *, max_iters: int = 2, model: str = "deepseek-chat") -> dict:
    """Run the Collective Meta-Moderation pipeline through the state machine."""
    return run_cmm_state_machine(query, max_iters=max_iters, model=model)
