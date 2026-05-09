"""Public CMM orchestration entrypoint."""

from __future__ import annotations

from Lib.config import get_default_model, get_default_options
from Lib.state_machine_instrumented import run_cmm_state_machine


def run_cmm(
    query: str,
    *,
    max_iters: int | None = None,
    model: str | None = None,
    route_mode: str | None = None,
    parallel_mode: str | None = None,
    max_workers: int | None = None,
    max_deliberation_rounds: int | None = None,
) -> dict:
    """Run the Collective Meta-Moderation pipeline through the state machine."""
    defaults = get_default_options()
    return run_cmm_state_machine(
        query,
        max_iters=int(max_iters if max_iters is not None else defaults.get("max_iters", 2)),
        model=get_default_model(model),
        route_mode=str(route_mode or defaults.get("route_mode") or "AUTO"),
        parallel_mode=str(parallel_mode or defaults.get("parallel_mode") or "SEQUENTIAL"),
        max_workers=max_workers if max_workers is not None else defaults.get("max_workers"),
        max_deliberation_rounds=int(
            max_deliberation_rounds
            if max_deliberation_rounds is not None
            else defaults.get("max_deliberation_rounds", 1)
        ),
    )
