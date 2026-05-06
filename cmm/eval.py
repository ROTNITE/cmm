"""Offline-first evaluation harness for CMM vs baseline comparisons."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from Lib.json_utils import safe_json_loads, to_number, to_string_list


REQUIRED_COLUMNS = ["id", "query"]
OPTIONAL_COLUMNS = [
    "context",
    "constraints",
    "expected_domain_expert",
    "expected_perspectives",
    "rubric_must_cover",
    "rubric_desirable",
    "rubric_should_cover",
    "reference_outline",
    "expected_single_model_failure_modes",
    "expected_mode",
]
RESULT_FIELDS = [
    "case_id",
    "expected_mode",
    "actual_mode",
    "router_mode_match",
    "baseline_score",
    "cmm_score",
    "rubric_coverage_delta",
    "perspective_coverage_delta",
    "risk_coverage_delta",
    "cmm_mode",
    "router_complexity",
    "estimated_cost_class",
    "cmm_final_state",
    "cmm_warning_count",
    "cmm_error_count",
    "cmm_warnings",
    "cmm_errors",
    "cmm_json_warnings",
    "cmm_json_fallback_count",
    "expert_valid_contributions",
    "expert_invalid_json_contributions",
    "planner_raw_format",
    "planner_json_attempts",
    "plan_critique_statuses",
    "answer_moderation_final_decision",
    "answer_moderation_best_effort",
    "roles_used_unique",
    "estimated_call_count",
    "estimated_stage_count",
    "answer_chars",
    "warnings_count",
    "errors_count",
    "winner",
    "notes",
]
JUDGE_SCORE_KEYS = [
    "rubric_coverage",
    "perspective_coverage",
    "risk_handling",
    "actionability",
    "clarity",
    "overall",
]
JUDGED_RESULT_FIELDS = [
    "case_id",
    "expected_mode",
    "actual_mode",
    "router_mode_match",
    "winner",
    "baseline_overall",
    "cmm_overall",
    "overall_delta",
    "baseline_rubric_coverage",
    "cmm_rubric_coverage",
    "baseline_perspective_coverage",
    "cmm_perspective_coverage",
    "baseline_risk_handling",
    "cmm_risk_handling",
    "baseline_actionability",
    "cmm_actionability",
    "baseline_clarity",
    "cmm_clarity",
    "reason",
    "baseline_failure_modes",
    "cmm_failure_modes",
    "baseline_answer_chars",
    "cmm_answer_chars",
    "cmm_trace_available",
    "cmm_mode",
    "router_complexity",
    "estimated_cost_class",
    "cmm_final_state",
    "cmm_warning_count",
    "cmm_error_count",
    "cmm_warnings",
    "cmm_errors",
    "cmm_json_warnings",
    "cmm_json_fallback_count",
    "expert_valid_contributions",
    "expert_invalid_json_contributions",
    "planner_raw_format",
    "planner_json_attempts",
    "plan_critique_statuses",
    "answer_moderation_final_decision",
    "answer_moderation_best_effort",
    "roles_used_unique",
    "estimated_call_count",
    "estimated_stage_count",
    "answer_chars",
    "warnings_count",
    "errors_count",
]
HUMAN_REVIEW_FIELDS = [
    "case_id",
    "query",
    "context",
    "constraints",
    "expected_mode",
    "answer_a",
    "answer_b",
    "manual_winner",
    "review_notes",
    "price_justified",
    "lost_constraints",
    "too_many_agents",
    "too_long",
]
ROUTING_REVIEW_FIELDS = [
    "case_id",
    "expected_mode",
    "actual_mode",
    "router_mode_match",
    "estimated_cost_class",
    "answer_chars",
    "warnings",
    "errors",
    "cmm_final_state",
]
_TIE_DELTA = 0.5


def parse_pipe_list(value: Any) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def _expected_mode(case: dict) -> str:
    value = str(case.get("expected_mode") or "").strip().upper()
    return value if value in {"DIRECT", "LIGHT_CMM", "FULL_CMM"} else ""


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"[^\w\sа-яё]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _coverage_ratio(items: list[str], text: str) -> float:
    if not items:
        return 0.0

    normalized_text = _normalize_text(text)
    if not normalized_text:
        return 0.0

    hits = 0
    for item in items:
        normalized_item = _normalize_text(item)
        if not normalized_item:
            continue
        item_tokens = [token for token in normalized_item.split() if len(token) >= 3]
        if normalized_item in normalized_text:
            hits += 1
        elif item_tokens and all(token in normalized_text for token in item_tokens[:4]):
            hits += 1

    return hits / len(items)


def _trace_text(trace_report: dict) -> str:
    try:
        return json.dumps(trace_report or {}, ensure_ascii=False)
    except Exception:
        return str(trace_report or "")


def _perspective_text(run_output: dict) -> str:
    parts: list[str] = []
    trace = run_output.get("trace_report") if isinstance(run_output, dict) else {}
    if isinstance(trace, dict):
        for role in trace.get("roles_used", []) or []:
            if isinstance(role, dict):
                parts.append(str(role.get("perspective_tag", "")))
                parts.append(str(role.get("key", "")))
                parts.append(str(role.get("name", "")))
        parts.append(_trace_text(trace))
    parts.append(str(run_output.get("answer") or run_output.get("final_answer") or ""))
    return " ".join(parts)


def _score_output(case: dict, run_output: dict) -> dict:
    answer = str(run_output.get("answer") or run_output.get("final_answer") or "")
    trace = run_output.get("trace_report") if isinstance(run_output, dict) else {}
    trace_blob = _trace_text(trace if isinstance(trace, dict) else {})

    rubric_items = parse_pipe_list(case.get("rubric_must_cover"))
    perspectives = parse_pipe_list(case.get("expected_perspectives"))
    failure_modes = parse_pipe_list(case.get("expected_single_model_failure_modes"))

    rubric = _coverage_ratio(rubric_items, answer)
    perspective = _coverage_ratio(perspectives, _perspective_text(run_output))
    risk = _coverage_ratio(failure_modes, answer + " " + trace_blob)

    components = []
    if rubric_items:
        components.append(rubric)
    if perspectives:
        components.append(perspective)
    if failure_modes:
        components.append(risk)

    total = sum(components) / len(components) if components else 0.0
    return {
        "total": round(total, 4),
        "rubric": round(rubric, 4),
        "perspective": round(perspective, 4),
        "risk": round(risk, 4),
    }


def load_dataset(path: str) -> tuple[list[dict], dict]:
    dataset_path = Path(path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    with dataset_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []
        missing_required = [name for name in REQUIRED_COLUMNS if name not in fieldnames]
        if missing_required:
            raise ValueError("Missing required dataset columns: " + ", ".join(missing_required))

        missing_optional = [name for name in OPTIONAL_COLUMNS if name not in fieldnames]
        rows: list[dict] = []
        warnings: list[str] = []
        for index, row in enumerate(reader, start=1):
            case = dict(row)
            case["case_id"] = case.get("id") or f"row-{index}"
            case_warnings = []
            if not str(case.get("query", "")).strip():
                case_warnings.append("empty_query")
            for column in ("expected_perspectives", "rubric_must_cover", "expected_single_model_failure_modes"):
                value = case.get(column, "")
                if value and not parse_pipe_list(value):
                    case_warnings.append(f"malformed_{column}")
            case["schema_warnings"] = case_warnings
            warnings.extend([f"{case['case_id']}: {warning}" for warning in case_warnings])
            rows.append(case)

    schema_report = {
        "path": str(dataset_path),
        "columns": fieldnames,
        "row_count": len(rows),
        "missing_optional_columns": missing_optional,
        "warnings": warnings,
    }
    return rows, schema_report


def _mock_baseline(case: dict) -> dict:
    answer = " ".join(
        [
            str(case.get("query", "")),
            str(case.get("context", "")),
            "baseline general answer",
        ]
    )
    return {"answer": answer, "trace_report": {"mode": "mock_baseline"}}


def _mock_cmm(case: dict) -> dict:
    perspectives = parse_pipe_list(case.get("expected_perspectives"))
    rubric = parse_pipe_list(case.get("rubric_must_cover"))
    failure_modes = parse_pipe_list(case.get("expected_single_model_failure_modes"))
    mode = _expected_mode(case) or "LIGHT_CMM"
    cost = {"DIRECT": "S", "LIGHT_CMM": "M", "FULL_CMM": "L"}[mode]
    answer = " ".join(
        [
            str(case.get("query", "")),
            str(case.get("context", "")),
            str(case.get("constraints", "")),
            " ".join(rubric),
            " ".join(failure_modes),
        ]
    )
    roles = [
        {"key": f"mock_{perspective}", "name": perspective.title(), "perspective_tag": perspective}
        for perspective in perspectives
    ]
    return {
        "answer": answer,
        "final_answer": answer,
        "trace_report": {
            "roles_used": roles,
            "mode": "mock_cmm",
            "cmm_mode": mode,
            "router_decision": {
                "mode": mode,
                "complexity": {"DIRECT": "low", "LIGHT_CMM": "medium", "FULL_CMM": "high"}[mode],
                "estimated_cost_class": cost,
            },
            "estimated_cost_class": cost,
        },
    }


def _real_baseline(case: dict, model: str = "deepseek-chat") -> dict:
    from Lib.AI_request import send_to_AI
    from Lib.eval_logger import get_logger

    logger = get_logger()
    logger.stage_start("baseline")

    prompt = "\n".join(
        [
            f"Query: {case.get('query', '')}",
            f"Context: {case.get('context', '')}",
            f"Constraints: {case.get('constraints', '')}",
        ]
    )
    answer = send_to_AI(
        user_prompt=prompt,
        system_prompt="Answer the user query directly.",
        temp=0.4,
        tokens=850,
        model=model,
    )

    logger.stage_end("baseline")
    return {"answer": answer or "", "trace_report": {"mode": "real_baseline"}}


def _real_cmm(case: dict, model: str = "deepseek-chat") -> dict:
    from Lib.orchestrator import run_cmm
    from Lib.eval_logger import get_logger

    logger = get_logger()
    logger.stage_start("cmm")

    query_parts = [
        str(case.get("query", "")),
        f"Контекст: {case.get('context', '')}" if case.get("context") else "",
        f"Ограничения: {case.get('constraints', '')}" if case.get("constraints") else "",
    ]
    result = run_cmm("\n".join(part for part in query_parts if part), model=model)

    # Log trace information
    trace = result.get("trace_report", {})
    if isinstance(trace, dict):
        # Log router decision
        router = trace.get("router_decision", {})
        if isinstance(router, dict):
            logger.router_decision(
                mode=router.get("mode", ""),
                complexity=router.get("complexity", ""),
                reasoning=router.get("reasoning", ""),
            )

        # Log expert contributions
        for role in trace.get("roles_used", []) or []:
            if isinstance(role, dict):
                logger.expert_contribution(
                    role=role.get("key", ""),
                    perspective=role.get("perspective_tag", ""),
                    valid=True,
                )

        # Log plan critiques
        for status in trace.get("plan_critique_statuses", []) or []:
            logger.plan_critique(status=str(status))

        # Log moderation
        if trace.get("answer_moderation_final_decision"):
            logger.moderation_decision(
                decision=trace.get("answer_moderation_final_decision", ""),
                best_effort=bool(trace.get("answer_moderation_best_effort")),
            )

        # Log warnings and errors
        for warning in trace.get("warnings", []) or []:
            logger.warning(str(warning))
        for error in trace.get("errors", []) or []:
            logger.error(str(error))

    logger.stage_end("cmm")
    return {
        "answer": result.get("final_answer", ""),
        "final_answer": result.get("final_answer", ""),
        "trace_report": result.get("trace_report", {}),
    }


def _answer_text(run_output: dict) -> str:
    if not isinstance(run_output, dict):
        return ""
    return str(run_output.get("answer") or run_output.get("final_answer") or "")


def _routing_fields(run_output: dict) -> dict:
    trace = run_output.get("trace_report") if isinstance(run_output, dict) else {}
    trace = trace if isinstance(trace, dict) else {}
    router = trace.get("router_decision") if isinstance(trace.get("router_decision"), dict) else {}
    return {
        "cmm_mode": trace.get("cmm_mode") or router.get("mode") or "",
        "router_complexity": router.get("complexity") or "",
        "estimated_cost_class": trace.get("estimated_cost_class") or router.get("estimated_cost_class") or "",
    }


def _mode_fields(case: dict, run_output: dict) -> dict:
    expected = _expected_mode(case)
    actual = _routing_fields(run_output).get("cmm_mode") or ""
    if not expected:
        match: str | bool = ""
    else:
        match = actual == expected
    return {
        "expected_mode": expected,
        "actual_mode": actual,
        "router_mode_match": match,
    }


def _cmm_diagnostic_fields(run_output: dict) -> dict:
    trace = run_output.get("trace_report") if isinstance(run_output, dict) else {}
    trace = trace if isinstance(trace, dict) else {}
    warnings = [str(item) for item in trace.get("warnings", []) or []]
    errors = [str(item) for item in trace.get("errors", []) or []]
    json_warnings = [item for item in warnings if "json" in item.lower()]
    json_health = trace.get("json_health") if isinstance(trace.get("json_health"), dict) else {}
    expert_health = json_health.get("expert_agent") if isinstance(json_health.get("expert_agent"), dict) else {}
    planner_health = json_health.get("planner") if isinstance(json_health.get("planner"), dict) else {}
    moderator_health = json_health.get("moderator") if isinstance(json_health.get("moderator"), dict) else {}
    conflict_health = json_health.get("conflict_analyzer") if isinstance(json_health.get("conflict_analyzer"), dict) else {}
    meta_health = json_health.get("meta_moderator") if isinstance(json_health.get("meta_moderator"), dict) else {}
    fallback_count = int(expert_health.get("fallbacks") or 0)
    if planner_health.get("called") and not planner_health.get("success"):
        fallback_count += 1
    fallback_count += int(moderator_health.get("invalid_json_count") or 0)
    fallback_count += int(conflict_health.get("invalid_json_count") or 0)
    fallback_count += int(meta_health.get("invalid_json_count") or 0)
    return {
        "cmm_final_state": trace.get("final_state") or "",
        "cmm_warning_count": len(warnings),
        "cmm_error_count": len(errors),
        "cmm_warnings": " | ".join(warnings[:20]),
        "cmm_errors": " | ".join(errors[:20]),
        "cmm_json_warnings": " | ".join(json_warnings[:20]),
        "cmm_json_fallback_count": fallback_count,
        "expert_valid_contributions": int(expert_health.get("success") or 0),
        "expert_invalid_json_contributions": int(expert_health.get("invalid_json_count") or 0),
        "planner_raw_format": planner_health.get("raw_format") or "",
        "planner_json_attempts": int(planner_health.get("json_attempts") or 0),
        "plan_critique_statuses": " | ".join(str(item) for item in trace.get("plan_critique_statuses", []) or []),
        "answer_moderation_final_decision": trace.get("answer_moderation_final_decision") or "",
        "answer_moderation_best_effort": bool(trace.get("answer_moderation_best_effort")),
        "roles_used_unique": json.dumps(trace.get("roles_used_unique") or [], ensure_ascii=False),
        "estimated_call_count": int(trace.get("estimated_call_count") or 0),
        "estimated_stage_count": int(trace.get("estimated_stage_count") or 0),
        "answer_chars": int(trace.get("answer_chars") or len(_answer_text(run_output))),
        "warnings_count": int(trace.get("warnings_count") if isinstance(trace.get("warnings_count"), int) else len(warnings)),
        "errors_count": int(trace.get("errors_count") if isinstance(trace.get("errors_count"), int) else len(errors)),
    }


def assign_blind_answers(case_id: str, baseline: dict, cmm: dict) -> dict:
    """Assign Answer A/B deterministically without global randomness."""
    stable_id = str(case_id or "")
    baseline_first = (sum(ord(ch) for ch in stable_id) % 2) == 0
    if baseline_first:
        answer_a_source = "BASELINE"
        answer_b_source = "CMM"
        answer_a = _answer_text(baseline)
        answer_b = _answer_text(cmm)
    else:
        answer_a_source = "CMM"
        answer_b_source = "BASELINE"
        answer_a = _answer_text(cmm)
        answer_b = _answer_text(baseline)

    return {
        "case_id": stable_id,
        "answer_a": answer_a,
        "answer_b": answer_b,
        "answer_a_source": answer_a_source,
        "answer_b_source": answer_b_source,
        "source_to_answer": {
            answer_a_source: "A",
            answer_b_source: "B",
        },
    }


def build_judge_prompt(case: dict, answer_a: str, answer_b: str) -> str:
    """Build a blind judge prompt. It intentionally does not name answer sources."""
    prompt_payload = {
        "case_id": case.get("case_id") or case.get("id") or "",
        "query": case.get("query", ""),
        "context": case.get("context", ""),
        "constraints": case.get("constraints", ""),
        "rubric_must_cover": parse_pipe_list(case.get("rubric_must_cover")),
        "expected_perspectives": parse_pipe_list(case.get("expected_perspectives")),
        "possible_failure_modes": parse_pipe_list(case.get("expected_single_model_failure_modes")),
        "answer_a": answer_a,
        "answer_b": answer_b,
    }
    return (
        "You are a blind evaluator of two answers to the same user case.\n"
        "Evaluate both answers against the same criteria. Do not favor longer answers automatically.\n"
        "Reward accurate rubric coverage, perspective coverage, risk handling, actionability, and clarity.\n"
        "Penalize hallucinated specifics, ignored constraints, generic advice, and missing risks.\n"
        "The answer sources are intentionally hidden. Do not infer or mention the source of either answer.\n"
        "Return STRICT JSON only with this schema:\n"
        "{\n"
        '  "answer_a_scores": {\n'
        '    "rubric_coverage": 0-10,\n'
        '    "perspective_coverage": 0-10,\n'
        '    "risk_handling": 0-10,\n'
        '    "actionability": 0-10,\n'
        '    "clarity": 0-10,\n'
        '    "overall": 0-10\n'
        "  },\n"
        '  "answer_b_scores": {\n'
        '    "rubric_coverage": 0-10,\n'
        '    "perspective_coverage": 0-10,\n'
        '    "risk_handling": 0-10,\n'
        '    "actionability": 0-10,\n'
        '    "clarity": 0-10,\n'
        '    "overall": 0-10\n'
        "  },\n"
        '  "winner": "A|B|TIE",\n'
        '  "reason": "string",\n'
        '  "answer_a_failure_modes": ["string"],\n'
        '  "answer_b_failure_modes": ["string"]\n'
        "}\n\n"
        "Evaluation packet:\n"
        + json.dumps(prompt_payload, ensure_ascii=False)
    )


def _zero_scores() -> dict:
    return {key: 0.0 for key in JUDGE_SCORE_KEYS}


def _normalize_scores(value: Any) -> dict:
    raw = value if isinstance(value, dict) else {}
    return {
        key: round(to_number(raw.get(key), default=0.0, min_value=0.0, max_value=10.0), 4)
        for key in JUDGE_SCORE_KEYS
    }


def _scores_for_source(source: str, answer_a_scores: dict, answer_b_scores: dict, mapping: dict) -> dict:
    answer_label = mapping.get("source_to_answer", {}).get(source)
    return answer_a_scores if answer_label == "A" else answer_b_scores


def _failures_for_source(source: str, answer_a_failures: list[str], answer_b_failures: list[str], mapping: dict) -> list[str]:
    answer_label = mapping.get("source_to_answer", {}).get(source)
    return answer_a_failures if answer_label == "A" else answer_b_failures


def normalize_judge_payload(payload: dict | None, mapping: dict, raw: str = "", warning: str | None = None) -> dict:
    """Normalize blind judge output and map Answer A/B back to BASELINE/CMM."""
    parse_warnings: list[str] = []
    if warning:
        parse_warnings.append(warning)
    if not isinstance(payload, dict):
        parse_warnings.append("judge_json_parse_failed")

        # Distinguish between human_review_required (judge-mode none) and actual parse failure
        if warning == "human_review_required":
            winner = "UNJUDGED"
            reason = "judge_mode=none; exported for human review"
        else:
            winner = "TIE"
            reason = "Judge output could not be parsed; marked as tie for review."

        return {
            "case_id": mapping.get("case_id", ""),
            "baseline_scores": _zero_scores(),
            "cmm_scores": _zero_scores(),
            "winner": winner,
            "reason": reason,
            "cmm_failure_modes": [],
            "baseline_failure_modes": [],
            "parse_warnings": parse_warnings,
            "raw": raw or "",
        }

    answer_a_scores = _normalize_scores(payload.get("answer_a_scores"))
    answer_b_scores = _normalize_scores(payload.get("answer_b_scores"))
    baseline_scores = _scores_for_source("BASELINE", answer_a_scores, answer_b_scores, mapping)
    cmm_scores = _scores_for_source("CMM", answer_a_scores, answer_b_scores, mapping)

    answer_a_failures = to_string_list(payload.get("answer_a_failure_modes"), max_items=10)
    answer_b_failures = to_string_list(payload.get("answer_b_failure_modes"), max_items=10)
    baseline_failures = _failures_for_source("BASELINE", answer_a_failures, answer_b_failures, mapping)
    cmm_failures = _failures_for_source("CMM", answer_a_failures, answer_b_failures, mapping)

    baseline_overall = baseline_scores.get("overall", 0.0)
    cmm_overall = cmm_scores.get("overall", 0.0)
    delta = cmm_overall - baseline_overall
    if abs(delta) < _TIE_DELTA:
        winner = "TIE"
    elif delta > 0:
        winner = "CMM"
    else:
        winner = "BASELINE"

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = "No judge reason provided."

    return {
        "case_id": mapping.get("case_id", ""),
        "baseline_scores": baseline_scores,
        "cmm_scores": cmm_scores,
        "winner": winner,
        "reason": reason.strip(),
        "cmm_failure_modes": cmm_failures,
        "baseline_failure_modes": baseline_failures,
        "parse_warnings": parse_warnings,
        "raw": raw or "",
    }


def judge_case_with_llm(case: dict, baseline: dict, cmm: dict, model: str = "deepseek-chat") -> dict:
    from Lib.AI_request import send_to_AI
    from Lib.eval_logger import get_logger

    logger = get_logger()
    logger.stage_start("judge")

    mapping = assign_blind_answers(case.get("case_id") or case.get("id") or "", baseline, cmm)
    prompt = build_judge_prompt(case, mapping["answer_a"], mapping["answer_b"])
    raw = send_to_AI(
        user_prompt=prompt,
        system_prompt="You are a careful blind evaluation judge. Return strict JSON only.",
        temp=0.2,
        tokens=900,
        model=model,
    )
    raw_text = raw if isinstance(raw, str) else ""
    payload = safe_json_loads(raw_text)
    result = normalize_judge_payload(payload, mapping, raw=raw_text)
    result["judge_prompt"] = prompt
    result["blind_mapping"] = {
        "answer_a_source": mapping["answer_a_source"],
        "answer_b_source": mapping["answer_b_source"],
    }

    logger.stage_end("judge")
    return result


def build_human_review_packet(case: dict, baseline: dict, cmm: dict) -> dict:
    mapping = assign_blind_answers(case.get("case_id") or case.get("id") or "", baseline, cmm)
    prompt = build_judge_prompt(case, mapping["answer_a"], mapping["answer_b"])
    judge_result = normalize_judge_payload(
        None,
        mapping,
        raw="",
        warning="human_review_required",
    )
    return {
        "case_id": mapping["case_id"],
        "case": case,
        "answer_a": mapping["answer_a"],
        "answer_b": mapping["answer_b"],
        "answer_a_source": mapping["answer_a_source"],
        "answer_b_source": mapping["answer_b_source"],
        "judge_prompt": prompt,
        "normalized_judge_result": judge_result,
    }


def _judged_result_row(case: dict, baseline: dict, cmm: dict, judge_result: dict) -> dict:
    baseline_scores = judge_result.get("baseline_scores") if isinstance(judge_result.get("baseline_scores"), dict) else {}
    cmm_scores = judge_result.get("cmm_scores") if isinstance(judge_result.get("cmm_scores"), dict) else {}
    baseline_answer = _answer_text(baseline)
    cmm_answer = _answer_text(cmm)
    trace = cmm.get("trace_report") if isinstance(cmm, dict) else None
    routing = _routing_fields(cmm)
    diagnostics = _cmm_diagnostic_fields(cmm)
    mode_fields = _mode_fields(case, cmm)
    return {
        "case_id": case.get("case_id") or case.get("id") or "",
        **mode_fields,
        "winner": judge_result.get("winner", "TIE"),
        "baseline_overall": baseline_scores.get("overall", 0.0),
        "cmm_overall": cmm_scores.get("overall", 0.0),
        "overall_delta": round(cmm_scores.get("overall", 0.0) - baseline_scores.get("overall", 0.0), 4),
        "baseline_rubric_coverage": baseline_scores.get("rubric_coverage", 0.0),
        "cmm_rubric_coverage": cmm_scores.get("rubric_coverage", 0.0),
        "baseline_perspective_coverage": baseline_scores.get("perspective_coverage", 0.0),
        "cmm_perspective_coverage": cmm_scores.get("perspective_coverage", 0.0),
        "baseline_risk_handling": baseline_scores.get("risk_handling", 0.0),
        "cmm_risk_handling": cmm_scores.get("risk_handling", 0.0),
        "baseline_actionability": baseline_scores.get("actionability", 0.0),
        "cmm_actionability": cmm_scores.get("actionability", 0.0),
        "baseline_clarity": baseline_scores.get("clarity", 0.0),
        "cmm_clarity": cmm_scores.get("clarity", 0.0),
        "reason": judge_result.get("reason", ""),
        "baseline_failure_modes": " | ".join(to_string_list(judge_result.get("baseline_failure_modes"), max_items=20)),
        "cmm_failure_modes": " | ".join(to_string_list(judge_result.get("cmm_failure_modes"), max_items=20)),
        "baseline_answer_chars": len(baseline_answer),
        "cmm_answer_chars": len(cmm_answer),
        "cmm_trace_available": isinstance(trace, dict) and bool(trace),
        **routing,
        **diagnostics,
    }


def score_case_judged(
    case: dict,
    baseline: dict,
    cmm: dict,
    *,
    judge_mode: str = "none",
    judge_model: str = "deepseek-chat",
) -> dict:
    if judge_mode not in {"none", "llm"}:
        raise ValueError("judge_mode must be 'none' or 'llm'")

    mapping = assign_blind_answers(case.get("case_id") or case.get("id") or "", baseline, cmm)
    human_packet = None
    if judge_mode == "llm":
        judge_result = judge_case_with_llm(case, baseline, cmm, model=judge_model)
        judge_prompt = judge_result.get("judge_prompt", "")
        blind_mapping = judge_result.get("blind_mapping", {})
    else:
        human_packet = build_human_review_packet(case, baseline, cmm)
        judge_result = human_packet["normalized_judge_result"]
        judge_prompt = human_packet["judge_prompt"]
        blind_mapping = {
            "answer_a_source": human_packet["answer_a_source"],
            "answer_b_source": human_packet["answer_b_source"],
        }

    row = _judged_result_row(case, baseline, cmm, judge_result)
    artifact = {
        "case_id": case.get("case_id") or case.get("id") or "",
        "case": case,
        "baseline": baseline,
        "cmm": cmm,
        "cmm_trace_report": cmm.get("trace_report") if isinstance(cmm, dict) else {},
        "answer_a_source": blind_mapping.get("answer_a_source") or mapping["answer_a_source"],
        "answer_b_source": blind_mapping.get("answer_b_source") or mapping["answer_b_source"],
        "judge_prompt": judge_prompt,
        "raw_judge_output": judge_result.get("raw", ""),
        "normalized_judge_result": judge_result,
    }
    return {
        "row": row,
        "artifact": artifact,
        "human_packet": human_packet,
    }


def score_case(case: dict, baseline: dict, cmm: dict) -> dict:
    baseline_scores = _score_output(case, baseline)
    cmm_scores = _score_output(case, cmm)

    baseline_total = baseline_scores["total"]
    cmm_total = cmm_scores["total"]
    if cmm_total > baseline_total:
        winner = "CMM"
    elif baseline_total > cmm_total:
        winner = "BASELINE"
    else:
        winner = "TIE"

    notes = []
    notes.extend(case.get("schema_warnings", []) or [])
    if not notes:
        notes.append("ok")
    routing = _routing_fields(cmm)
    diagnostics = _cmm_diagnostic_fields(cmm)
    mode_fields = _mode_fields(case, cmm)

    return {
        "case_id": case.get("case_id") or case.get("id") or "",
        **mode_fields,
        "baseline_score": baseline_total,
        "cmm_score": cmm_total,
        "rubric_coverage_delta": round(cmm_scores["rubric"] - baseline_scores["rubric"], 4),
        "perspective_coverage_delta": round(cmm_scores["perspective"] - baseline_scores["perspective"], 4),
        "risk_coverage_delta": round(cmm_scores["risk"] - baseline_scores["risk"], 4),
        **routing,
        **diagnostics,
        "winner": winner,
        "notes": "; ".join(notes),
    }


def _print_case_diagnostics(case: dict, cmm_output: dict, judge_mode: str) -> None:
    diag = _cmm_diagnostic_fields(cmm_output)
    routing = _routing_fields(cmm_output)
    case_id = case.get("case_id") or case.get("id") or ""
    print(f"Case {case_id}")
    print(f"Mode: {routing.get('cmm_mode')}")
    if _expected_mode(case):
        print(f"Expected mode: {_expected_mode(case)}")
    print(f"Final state: {diag.get('cmm_final_state')}")
    print(
        "Expert contributions: "
        f"{diag.get('expert_valid_contributions')}/"
        f"{int(diag.get('expert_valid_contributions') or 0) + int(diag.get('expert_invalid_json_contributions') or 0)} valid"
    )
    print(f"Planner: {diag.get('planner_raw_format') or 'unknown'}")
    print(f"Plan critique: {diag.get('plan_critique_statuses') or 'none'}")
    print(
        "Moderation: "
        f"{diag.get('answer_moderation_final_decision') or 'unknown'}"
        + (" best-effort" if diag.get("answer_moderation_best_effort") else "")
    )
    print(f"Judge: {judge_mode}")


def _boolish(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _cost_score(value: Any) -> int:
    return {"S": 1, "M": 2, "L": 3}.get(str(value or "").strip().upper(), 0)


def _mode_distribution(results: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for item in results:
        mode = str(item.get(key) or "").strip() or "unknown"
        out[mode] = out.get(mode, 0) + 1
    return out


def _technical_failure(row: dict) -> bool:
    final_state = str(row.get("cmm_final_state") or "").strip().upper()
    errors = str(row.get("cmm_errors") or "").strip()
    error_count = int(row.get("cmm_error_count") or row.get("errors_count") or 0)
    return bool((final_state and final_state != "FINALIZE") or errors or error_count)


def _diagnostic_summary(results: list[dict]) -> dict:
    cases = len(results)
    router_rows = [item for item in results if item.get("expected_mode")]
    matches = [item for item in router_rows if _boolish(item.get("router_mode_match")) is True]
    technical_by_mode: dict[str, int] = {}
    cost_distribution: dict[str, int] = {}
    answer_lengths: list[int] = []
    cost_scores: list[int] = []
    for item in results:
        mode = str(item.get("actual_mode") or item.get("cmm_mode") or "").strip() or "unknown"
        cost = str(item.get("estimated_cost_class") or "").strip().upper() or "unknown"
        cost_distribution[cost] = cost_distribution.get(cost, 0) + 1
        if _technical_failure(item):
            technical_by_mode[mode] = technical_by_mode.get(mode, 0) + 1
        answer_lengths.append(int(item.get("answer_chars") or item.get("cmm_answer_chars") or 0))
        score = _cost_score(cost)
        if score:
            cost_scores.append(score)
    return {
        "expected_mode_distribution": _mode_distribution(results, "expected_mode"),
        "actual_mode_distribution": _mode_distribution(results, "actual_mode"),
        "router_expected_cases": len(router_rows),
        "router_mode_matches": len(matches),
        "router_mode_accuracy": round(len(matches) / len(router_rows), 4) if router_rows else None,
        "technical_failures_by_mode": technical_by_mode,
        "direct_failures": technical_by_mode.get("DIRECT", 0),
        "light_failures": technical_by_mode.get("LIGHT_CMM", 0),
        "full_failures": technical_by_mode.get("FULL_CMM", 0),
        "average_cmm_answer_length": round(sum(answer_lengths) / cases, 2) if cases else 0.0,
        "average_estimated_cost_score": round(sum(cost_scores) / len(cost_scores), 4) if cost_scores else 0.0,
        "estimated_cost_class_distribution": cost_distribution,
    }


def _routing_review_row(row: dict) -> dict:
    return {
        "case_id": row.get("case_id") or "",
        "expected_mode": row.get("expected_mode") or "",
        "actual_mode": row.get("actual_mode") or row.get("cmm_mode") or "",
        "router_mode_match": row.get("router_mode_match"),
        "estimated_cost_class": row.get("estimated_cost_class") or "",
        "answer_chars": row.get("answer_chars") or row.get("cmm_answer_chars") or "",
        "warnings": row.get("cmm_warnings") or "",
        "errors": row.get("cmm_errors") or "",
        "cmm_final_state": row.get("cmm_final_state") or "",
    }


def _write_routing_review(results: list[dict], out_dir: Path) -> str:
    path = out_dir / "routing_review.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=ROUTING_REVIEW_FIELDS)
        writer.writeheader()
        for row in results:
            writer.writerow(_routing_review_row(row))
    return str(path)


def _write_human_review_csv(human_packets: list[dict], out_dir: Path) -> str:
    path = out_dir / "human_review.csv"
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=HUMAN_REVIEW_FIELDS)
        writer.writeheader()
        for packet in human_packets:
            case = packet.get("case") if isinstance(packet.get("case"), dict) else {}
            writer.writerow(
                {
                    "case_id": packet.get("case_id") or "",
                    "query": case.get("query") or "",
                    "context": case.get("context") or "",
                    "constraints": case.get("constraints") or "",
                    "expected_mode": _expected_mode(case),
                    "answer_a": packet.get("answer_a") or "",
                    "answer_b": packet.get("answer_b") or "",
                    "manual_winner": "",
                    "review_notes": "",
                    "price_justified": "",
                    "lost_constraints": "",
                    "too_many_agents": "",
                    "too_long": "",
                }
            )
    return str(path)


def _write_results(results: list[dict], schema_report: dict, output_dir: str) -> dict:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "results.csv"
    json_path = out_dir / "results.json"
    routing_review_path = _write_routing_review(results, out_dir)

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(results)

    payload = {
        "schema_report": schema_report,
        "results": results,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"csv": str(csv_path), "json": str(json_path), "routing_review_csv": routing_review_path}


def _summary_from_judged_results(results: list[dict], judge_mode: str, output_paths: dict) -> dict:
    cmm_overalls = [float(item.get("cmm_overall", 0.0) or 0.0) for item in results]
    baseline_overalls = [float(item.get("baseline_overall", 0.0) or 0.0) for item in results]
    cases = len(results)
    summary = {
        "cases": cases,
        "cmm_wins": sum(1 for item in results if item.get("winner") == "CMM"),
        "baseline_wins": sum(1 for item in results if item.get("winner") == "BASELINE"),
        "ties": sum(1 for item in results if item.get("winner") == "TIE"),
        "unjudged": sum(1 for item in results if item.get("winner") == "UNJUDGED"),
        "mode": "real",
        "judge_mode": judge_mode,
        "mean_cmm_overall": round(sum(cmm_overalls) / cases, 4) if cases else 0.0,
        "mean_baseline_overall": round(sum(baseline_overalls) / cases, 4) if cases else 0.0,
        "mean_overall_delta": round(
            (sum(cmm_overalls) - sum(baseline_overalls)) / cases,
            4,
        )
        if cases
        else 0.0,
        "interpretation": (
            "Limited first evaluation evidence only. This is not proof of universal CMM superiority."
        ),
        "output_paths": output_paths,
    }
    summary.update(_diagnostic_summary(results))
    return summary


def _write_judged_results(
    results: list[dict],
    artifacts: list[dict],
    schema_report: dict,
    output_dir: str,
    *,
    judge_mode: str,
    human_packets: list[dict] | None = None,
) -> tuple[dict, dict]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "results.csv"
    json_path = out_dir / "results.json"
    summary_path = out_dir / "summary.json"
    cases_path = out_dir / "cases.jsonl"
    routing_review_path = _write_routing_review(results, out_dir)

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=JUDGED_RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(results)

    payload = {
        "schema_report": schema_report,
        "judge_mode": judge_mode,
        "results": results,
        "artifacts": artifacts,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with cases_path.open("w", encoding="utf-8") as file:
        for artifact in artifacts:
            file.write(json.dumps(artifact, ensure_ascii=False) + "\n")

    output_paths = {
        "csv": str(csv_path),
        "json": str(json_path),
        "summary": str(summary_path),
        "cases_jsonl": str(cases_path),
        "routing_review_csv": routing_review_path,
    }

    if judge_mode == "none":
        human_path = out_dir / "human_review.jsonl"
        with human_path.open("w", encoding="utf-8") as file:
            for packet in human_packets or []:
                file.write(json.dumps(packet, ensure_ascii=False) + "\n")
        output_paths["human_review_jsonl"] = str(human_path)
        output_paths["human_review_csv"] = _write_human_review_csv(human_packets or [], out_dir)

    summary = _summary_from_judged_results(results, judge_mode=judge_mode, output_paths=output_paths)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_paths, summary


def _run_real_judged_eval(
    rows: list[dict],
    schema_report: dict,
    *,
    output_dir: str,
    judge_mode: str,
    judge_model: str,
    model: str = "deepseek-chat",
) -> dict:
    from Lib.eval_logger import get_logger, reset_logger

    # Reset and initialize logger for this eval run
    reset_logger()
    logger = get_logger()
    logger.enabled = True  # Enable logging for eval

    logger.info(f"Starting evaluation: {len(rows)} cases")
    logger.info(f"Judge mode: {judge_mode}")
    logger.info(f"Model: {model}")
    logger.info("")

    results: list[dict] = []
    artifacts: list[dict] = []
    human_packets: list[dict] = []

    for case in rows:
        # Start case logging
        case_id = case.get("case_id") or case.get("id") or ""
        query = case.get("query", "")

        # Encode query safely for Windows console
        try:
            query_display = query.encode('ascii', 'replace').decode('ascii')
        except:
            query_display = query

        logger.case_start(case_id=case_id, query=query_display)

        baseline_output = _real_baseline(case, model=model)
        cmm_output = _real_cmm(case, model=model)
        scored = score_case_judged(
            case,
            baseline_output,
            cmm_output,
            judge_mode=judge_mode,
            judge_model=judge_model,
        )
        _print_case_diagnostics(case, cmm_output, judge_mode)
        results.append(scored["row"])
        artifacts.append(scored["artifact"])
        if scored.get("human_packet"):
            human_packets.append(scored["human_packet"])

        # End case logging
        winner = scored["row"].get("winner", "TIE")
        logger.case_end(
            case_id=case_id,
            winner=winner,
        )

    output_paths, summary = _write_judged_results(
        results,
        artifacts,
        schema_report,
        output_dir,
        judge_mode=judge_mode,
        human_packets=human_packets,
    )
    summary["output_paths"] = output_paths

    # Print final summary
    logger.summary()
    logger.enabled = False

    return {
        "summary": summary,
        "schema_report": schema_report,
        "results": results,
        "artifacts": artifacts,
    }


def run_eval(
    dataset_path: str,
    *,
    limit: int | None = None,
    mode: str = "mock",
    output_dir: str = "eval_results",
    judge_mode: str = "none",
    judge_model: str = "deepseek-chat",
    model: str = "deepseek-chat",
) -> dict:
    if mode not in {"mock", "real"}:
        raise ValueError("mode must be 'mock' or 'real'")
    if judge_mode not in {"none", "llm"}:
        raise ValueError("judge_mode must be 'none' or 'llm'")

    rows, schema_report = load_dataset(dataset_path)
    if limit is not None:
        rows = rows[: max(0, limit)]

    if mode == "real":
        return _run_real_judged_eval(
            rows,
            schema_report,
            output_dir=output_dir,
            judge_mode=judge_mode,
            judge_model=judge_model,
            model=model,
        )

    baseline_runner = _mock_baseline
    cmm_runner = _mock_cmm

    results = []
    for case in rows:
        baseline_output = baseline_runner(case)
        cmm_output = cmm_runner(case)
        results.append(score_case(case, baseline_output, cmm_output))

    output_paths = _write_results(results, schema_report, output_dir)
    summary = {
        "cases": len(results),
        "cmm_wins": sum(1 for item in results if item["winner"] == "CMM"),
        "baseline_wins": sum(1 for item in results if item["winner"] == "BASELINE"),
        "ties": sum(1 for item in results if item["winner"] == "TIE"),
        "mode": mode,
        "judge_mode": "not_applicable",
        "output_paths": output_paths,
    }
    summary.update(_diagnostic_summary(results))
    return {
        "summary": summary,
        "schema_report": schema_report,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate CMM against a baseline.")
    parser.add_argument("--dataset", required=True, help="Path to cmm_dataset_v1.csv")
    parser.add_argument("--limit", type=int, default=None, help="Optional case limit")
    parser.add_argument("--mode", choices=["mock", "real"], default="mock", help="Evaluation mode")
    parser.add_argument("--judge-mode", choices=["none", "llm"], default="none", help="Judge mode for real eval")
    parser.add_argument("--judge-model", default="deepseek-chat", help="Model for --judge-mode llm")
    parser.add_argument("--model", default="deepseek-chat", help="Model for CMM and baseline")
    parser.add_argument("--output-dir", default="eval_results", help="Directory for CSV/JSON outputs")
    args = parser.parse_args(argv)

    result = run_eval(
        dataset_path=args.dataset,
        limit=args.limit,
        mode=args.mode,
        output_dir=args.output_dir,
        judge_mode=args.judge_mode,
        judge_model=args.judge_model,
        model=args.model,
    )
    summary = result["summary"]
    print(
        "Evaluation complete: "
        f"cases={summary['cases']}, "
        f"cmm_wins={summary['cmm_wins']}, "
        f"baseline_wins={summary['baseline_wins']}, "
        f"ties={summary['ties']}, "
        f"unjudged={summary.get('unjudged', 0)}"
    )
    if "judge_mode" in summary:
        print(f"Judge mode: {summary['judge_mode']}")
    print(f"CSV: {summary['output_paths']['csv']}")
    print(f"JSON: {summary['output_paths']['json']}")
    if "summary" in summary["output_paths"]:
        print(f"Summary: {summary['output_paths']['summary']}")
    if "cases_jsonl" in summary["output_paths"]:
        print(f"Cases: {summary['output_paths']['cases_jsonl']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
