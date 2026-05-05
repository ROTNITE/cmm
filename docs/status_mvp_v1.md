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

## Known P1 Issues To Fix Next

- Legacy `Lib.agent_critic.criticize_plan(...)` passes unsupported `depth` into the active critic.
- `Lib.plan_development.develop_plan(...)` does not yet receive the public `model` value.
- `ANSWER_MODERATION` can finalize a non-empty answer even when moderation rejected it.
- `dynamic_roles_used` currently conflates generated roles with actually executed roles.
- `Lib.agent_improver` can pass through raw model error strings such as `Error: ...`.

## Baseline Validation Results

- `python -m compileall .`: passed.
- `python -m unittest discover -s tests`: passed, 158 tests.
- `python -m cmm.eval --dataset cmm_dataset_v1.csv --limit 3 --mode mock --output-dir eval_results`: passed, 3 cases, 3 CMM wins in mock mode.
- `git diff --check`: passed.

## Quality Caveat

The mock evaluation result is a regression and compatibility signal only. It does not prove that CMM produces better real answers, better facilitation, or better decisions. Real evaluation must use a larger dataset, real model outputs, and preferably independent judging criteria.
