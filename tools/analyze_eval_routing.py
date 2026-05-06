"""Build a compact routing analysis CSV from CMM eval results."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


FIELDS = [
    "case_id",
    "expected_mode",
    "actual_mode",
    "router_mode_match",
    "winner",
    "failure_mode",
    "answer_chars",
    "warnings",
    "errors",
]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def classify_failure(row: dict) -> str:
    final_state = str(row.get("cmm_final_state") or "").strip().upper()
    errors = str(row.get("cmm_errors") or row.get("errors") or "").strip()
    if (final_state and final_state != "FINALIZE") or errors:
        return "technical_failure"
    if row.get("expected_mode") and not _truthy(row.get("router_mode_match")):
        return "router_mismatch"
    if str(row.get("winner") or "").strip().upper() == "BASELINE":
        return "baseline_win"
    return "none"


def analyze_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        out.append(
            {
                "case_id": row.get("case_id") or row.get("id") or "",
                "expected_mode": row.get("expected_mode") or "",
                "actual_mode": row.get("actual_mode") or row.get("cmm_mode") or "",
                "router_mode_match": row.get("router_mode_match") or "",
                "winner": row.get("winner") or "",
                "failure_mode": classify_failure(row),
                "answer_chars": row.get("answer_chars") or row.get("cmm_answer_chars") or "",
                "warnings": row.get("cmm_warnings") or row.get("warnings") or "",
                "errors": row.get("cmm_errors") or row.get("errors") or "",
            }
        )
    return out


def analyze_file(input_path: str, output_path: str) -> dict:
    source = Path(input_path)
    if not source.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    with source.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    analysis = analyze_rows(rows)

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(analysis)

    return {"input": str(source), "output": str(target), "rows": len(analysis)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze routing results from CMM eval CSV.")
    parser.add_argument("--input", required=True, help="Path to eval results.csv")
    parser.add_argument("--output", required=True, help="Path to routing_analysis.csv")
    args = parser.parse_args(argv)

    result = analyze_file(args.input, args.output)
    print(f"Routing analysis complete: rows={result['rows']}, output={result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
