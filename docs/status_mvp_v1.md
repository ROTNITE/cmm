# CMM MVP v1 Status

Date: 2026-05-05
Baseline tag: `cmm-mvp-v1`

## Implemented

- Public entrypoint: `Lib.orchestrator.run_cmm(...)`.
- Bounded state-machine orchestration in `Lib.state_machine`.
- Router modes: `DIRECT`, `LIGHT_CMM`, and `FULL_CMM`.
- Structured query intake preserving the original query.
- Expert panel, targeted expert rounds, and optional safe dynamic roles.
- Balance Analyzer 2.0 with deterministic quality heuristics.
- Semantic conflict analysis and structured deliberation round.
- Context-aware plan development and plan critique.
- Answer moderation and direct-answer fallback path.
- Optional thread-based parallel execution for independent expert calls.
- Mock evaluation harness with router/mode trace fields.

## Current Limitations

- Router, balance analysis, and plan critique are heuristic and can misclassify.
- State-machine loops are intentionally bounded; this is not an unbounded autonomous facilitator.
- Parallelism is optional and limited to independent expert calls; state transitions remain sequential.
- Dynamic roles are whitelist/template-based only; arbitrary model-generated roles are not allowed.
- Balance analysis remains deterministic and approximate, not proof of real perspective quality.
- Mock evaluation checks pipeline compatibility, not answer quality.

## Not Proven Yet

- Real improvement in answer quality over simpler prompting.
- Real cost/performance benefit from routing or optional parallelism.
- Robustness on a larger, diverse evaluation dataset.
- Stability under real model failures, malformed model outputs, or provider latency.
- Long-horizon facilitation quality against the full CMM 6.4 concept.

## Baseline P1 Issues Fixed After Tag

The `cmm-mvp-v1` tag intentionally captured the feature-complete baseline before the stabilization sprint. The following baseline P1 issues have since been fixed:

- Legacy `Lib.agent_critic.criticize_plan(...)` no longer passes unsupported `depth` into the active critic.
- `Lib.plan_development.develop_plan(...)` receives and forwards the public `model` value.
- `ANSWER_MODERATION` no longer finalizes a rejected answer just because text is non-empty.
- Trace now separates `dynamic_roles_generated`, `dynamic_roles_executed`, and `dynamic_roles_rejected`; `dynamic_roles_used` is a compatibility alias for executed roles.
- `Lib.agent_improver` falls back instead of passing through raw model error strings such as `Error: ...`.

## JSON Reliability Hardening After Tag

Real DeepSeek-style runs showed that invalid JSON could still degrade expert, planning, moderation, conflict, and meta-moderation stages even when fallback kept the pipeline alive. Current post-baseline hardening connects those JSON-first agents to the shared `Lib.json_retry.call_json_model(...)` helper:

- `Lib.expert_agent` retries expert contribution JSON once and records `json_attempts`, `parse_warnings`, `source`, and truncated raw output.
- `Lib.plan_development` retries planner JSON once, preserves the selected model, and builds a context-aware fallback plan from constraints, success criteria, must-address items, risks, and blind spots.
- `Lib.agent_moderator` retries moderation JSON once and returns explicit `final_decision`, `rejected`, and `critical_issues` metadata.
- `Lib.conflict_analyzer` and `Lib.meta_moderator` record retry diagnostics; meta moderation also guards against overly optimistic model decisions when strong rule-based gaps remain.
- `Lib.expert_selector` is rules-first for obvious domains and only uses model domain selection as an optional complex-query fallback.
- `trace_report["json_health"]` and eval diagnostics summarize JSON fallbacks, attempts, invalid expert contributions, planner format, and moderation decisions.
- Trace cleanup adds `roles_used_unique`, approximate call/stage telemetry, answer length, warning/error counts, and a compact `Lib.trace_formatter.format_trace_report(...)` summary for defense/debugging.
- Real-eval readiness adds `cmm_dataset_v2.csv`, expected-vs-actual router mode fields, human-review CSV artifacts, routing-review CSV artifacts, and `tools/analyze_eval_routing.py`.

## Remaining Real-Eval Risks

- A single repair retry improves reliability but cannot guarantee valid JSON from every model response.
- Large prompts may still need prompt-size reduction or schema simplification if retry failures remain frequent.
- JSON health diagnostics make failures visible; they do not prove answer quality.
- Real judged evaluation on a larger dataset is still required before claiming productivity or quality gains.

## Baseline Validation Results

- `python -m compileall .`: passed.
- `python -m unittest discover -s tests`: passed, 158 tests.
- `python -m cmm.eval --dataset cmm_dataset_v1.csv --limit 3 --mode mock --output-dir eval_results`: passed, 3 cases, 3 CMM wins in mock mode.
- `git diff --check`: passed.

## Quality Caveat

The mock evaluation result is a regression and compatibility signal only. It does not prove that CMM produces better real answers, better facilitation, or better decisions. Real evaluation must use a larger dataset, real model outputs, and preferably independent judging criteria.
