from __future__ import annotations

import argparse
import sys

from Lib.orchestrator import run_cmm
from Lib.trace_formatter import format_trace_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Collective Meta-Moderation.")
    parser.add_argument("query", nargs="*", help="User query. If omitted, stdin prompt is used.")
    parser.add_argument("--trace-summary", action="store_true", help="Print a human-readable trace summary.")
    parser.add_argument("--route-mode", default=None, help="AUTO, DIRECT, LIGHT_CMM, or FULL_CMM. Defaults to config.")
    parser.add_argument("--parallel-mode", default=None, help="SEQUENTIAL or THREADS. Defaults to config.")
    parser.add_argument("--max-workers", type=int, default=None, help="Max worker threads for optional parallel experts.")
    parser.add_argument("--max-iters", type=int, default=None, help="Max plan/answer revision iterations. Defaults to config.")
    parser.add_argument("--model", default=None, help="Model name for provider calls. Defaults to config.")
    parser.add_argument(
        "--max-deliberation-rounds",
        type=int,
        default=None,
        help="Bounded deliberation rounds, capped to max 2. Defaults to config.",
    )
    return parser


def main(argv: list[str] | None = None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args([] if argv is None else argv)
    user_query = " ".join(args.query).strip()
    if not user_query:
        user_query = input("Пожалуйста, введите ваш запрос: ")
    run_kwargs = {}
    for key in (
        "max_iters",
        "model",
        "route_mode",
        "parallel_mode",
        "max_workers",
        "max_deliberation_rounds",
    ):
        value = getattr(args, key)
        if value is not None:
            run_kwargs[key] = value
    result = run_cmm(user_query, **run_kwargs)

    print(f"\n✅ Финальный ответ: {result['final_answer']}")

    trace = result.get("trace_report", {})
    if args.trace_summary:
        print()
        print(format_trace_report(trace).rstrip())
        return result

    roles_count = len(trace.get("roles_used", []))
    revision_count = trace.get("revision_count", 0)
    warnings = trace.get("warnings", [])

    print(f"\n🧭 Trace summary: roles={roles_count}, revisions={revision_count}")
    if warnings:
        print("⚠️ Warnings:")
        for warning in warnings:
            print(f"- {warning}")
    return result


if __name__ == "__main__":
    main(sys.argv[1:])
