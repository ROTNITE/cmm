# Collective Meta-Moderation

Collective Meta-Moderation (CMM) is an experimental Python MVP for building an answer through a staged collective reasoning process: safe query intake, expert perspectives, balance analysis, semantic conflict analysis, structured expert deliberation, planning, moderation, revision, and traceable output.

Important limitation: a multi-agent pipeline does not automatically guarantee a better answer. The project makes expert context explicit and testable, then uses the evaluation harness to compare a CMM run with a baseline single-model answer.

## Quick Start

```bash
python -m unittest discover -s tests
python main.py
```

For the offline evaluation harness:

```bash
python -m cmm.eval --dataset cmm_dataset_v1.csv --limit 36 --mode mock --output-dir eval_results
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode mock --output-dir eval_results_v2_mock
```

`mock` mode is offline and deterministic; it checks evaluation mechanics, not answer quality. Use `--mode real` only when you intentionally want real model/CMM calls. Real judged evaluation can export blind packets for human review or call an LLM judge explicitly:

```bash
python -m cmm.eval --dataset cmm_dataset_v1.csv --limit 10 --mode real --judge-mode none --output-dir eval_real_10
python -m cmm.eval --dataset cmm_dataset_v1.csv --limit 10 --mode real --judge-mode llm --output-dir eval_real_10
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode none --output-dir eval_real_20
python tools/analyze_eval_routing.py --input eval_real_20/results.csv --output eval_real_20/routing_analysis.csv
```

## Environment

1. Edit `cmm_config.json` for non-secret defaults such as model, base URL, and API-key env var name.
2. Create a local `.env` file for secrets and optional overrides.
3. Install dependencies from `requirements.txt`.

### Option A: Claude via OmniRoute (recommended for agent testing)

```bash
# Start OmniRoute, open http://localhost:20128/dashboard
# Go to API Manager → Create API Key
# Copy the key and add to .env:

OMNIROUTE_API_KEY=sk-your-omniroute-key
```

Then set in `cmm_config.json`:

```json
{
  "model": "kr/claude-sonnet-4.5",
  "judge_model": "kr/claude-sonnet-4.5",
  "api": {
    "base_url": "http://localhost:20128/v1",
    "api_key_env": "OMNIROUTE_API_KEY"
  }
}
```

Verify setup:
```bash
curl http://localhost:20128/v1/models -H "Authorization: Bearer YOUR_KEY"
```

### Option B: DeepSeek (original setup)

```bash
DEEPSEEK_API_KEY=sk-your-deepseek-key
```

`cmm_config.json` is tracked and should contain only non-secret defaults. `cmm_config.local.json` is ignored and can be used for machine-local non-secret overrides. `.env` and `Api.env` are ignored and should contain real keys. Advanced process-level overrides such as `CMM_MODEL`, `CMM_BASE_URL`, and `CMM_API_KEY_ENV` are also supported, but the normal workflow is: change model/base URL in `cmm_config.json`, keep the real key in `.env`. The API client reads secrets only at call time and does not print key values.

## Running CMM

CLI:

```bash
python main.py
```

Programmatic API:

```python
from Lib.orchestrator import run_cmm

result = run_cmm("Как университету повысить вовлечённость студентов?")
print(result["final_answer"])
print(result["trace_report"])
```

`run_cmm(query, *, max_iters=None, model=None, route_mode=None, parallel_mode=None, max_workers=None, max_deliberation_rounds=None)` is the central MVP entrypoint. Existing calls still work. When optional values are omitted, they come from `cmm_config.json` / `.env`; explicit arguments still override config for that call. Internally it delegates to a bounded CMM state machine with deterministic routing. `max_deliberation_rounds` is capped to `1..2`; the default preserves the original one-round behavior.

For a compact demo/debug view:

```bash
python main.py --trace-summary "Кратко объясни коллективную метамодерацию"
```

## Architecture Overview

Current state-machine path:

```text
original_query
-> INTAKE
-> ROUTE
-> DIRECT_ANSWER for simple low-risk tasks
   or PANEL_ROUND_1 for LIGHT_CMM / FULL_CMM
-> BALANCE
-> PLAN for LIGHT_CMM
   or CONFLICT_ANALYSIS for FULL_CMM
-> META_DECISION
-> DELIBERATION_ROUND when needed
-> CONSENSUS_CHECK
-> optional second DELIBERATION_ROUND only for unresolved high-severity conflicts
-> META_RECHECK / PANEL_ROUND_EXTRA / REBALANCE when needed
-> PLAN
-> PLAN_CRITIQUE
-> REPLAN when critique requires it
-> ANSWER / ANSWER_MODERATION
-> FINALIZE or FAILED
```

Key modules:

- `Lib/orchestrator.py`: public `run_cmm(...)` wrapper.
- `Lib/state_machine.py`: bounded CMM state machine, transition history, trace/result assembly.
- `Lib/state_fallbacks.py`: fallback structures used by the state machine.
- `Lib/state_trace.py`: small result-payload assembly helpers for state-machine output.
- `Lib/router.py`: deterministic router that chooses `DIRECT`, `LIGHT_CMM`, or `FULL_CMM`.
- `Lib/direct_answer.py`: low-cost direct answer path for simple low-risk requests.
- `Lib/query_intake.py`: preserves the original query as authoritative and extracts helper structure such as constraints, context, success criteria, unknowns, and preferences.
- `Lib/json_retry.py`: retries strict JSON model calls once with a repair prompt before fallback.
- `Lib/role_generator.py`: suggests safe template-based dynamic roles from rules first, with optional whitelist-normalized model additions; models cannot create role prompts.
- `Lib/expert_panel.py`: runs selected expert roles and collects contributions; sequential execution is the default, with opt-in threaded execution for independent expert calls.
- `Lib/expert_rounds.py`: selects safe follow-up roles, runs targeted second rounds, and merges bundles; targeted expert calls can also use the same opt-in thread mode.
- `Lib/parallel_utils.py`: small standard-library helpers for bounded, deterministic, ordered thread execution.
- `Lib/balance_analyzer.py`: Balance Analyzer 2.0 checks missing/dominant perspectives plus deterministic quality heuristics.
- `Lib/conflict_analyzer.py`: checks semantic agreements, disagreements, unresolved trade-offs, blind spots, and premature consensus risks.
- `Lib/deliberation.py`: builds compact expert synthesis for downstream stages.
- `Lib/deliberation_round.py`: runs a structured deliberation pass where experts respond to other roles and revise recommendations; an opt-in second pass is limited to named roles in unresolved high-severity conflicts.
- `Lib/meta_moderator.py`: makes process-level decisions such as `SYNTHESIZE` or `DEEPEN`.
- `Lib/plan_development.py`: creates a JSON-first plan with legacy fallback.
- `Lib/plan_critic.py`: checks plans against the current CMM context and returns structured `ready` / `needs_revision` / `rejected` feedback.
- `Lib/agent_moderator.py`: evaluates answers and drives revision.
- `cmm/eval.py`: offline-first baseline vs CMM evaluation harness.

Legacy compatibility modules are still importable for older manual scripts, but they are not the current state-machine path: `Lib/Start_formalization.py` is superseded by `Lib/query_intake.py`, `Lib/agent_critic.py` and `Lib/critic_decision.py` wrap the current `Lib/plan_critic.py`, and `Lib/Finish_agent.py` is outside the main answer/moderation pipeline.

The `original_query` is authoritative. `cleaned_query` / `formalized_query` is helper text only, and query intake extracts structure instead of rewriting away meaning. The `expert_bundle` is not decorative: it feeds the deliberation brief, plan context, answer generation, moderation, and trace report.

The router prevents overusing the full pipeline. `DIRECT` is for simple low-risk requests and skips expert/pipeline stages. `LIGHT_CMM` runs a capped expert/balance/brief/plan/critique/moderation path while skipping conflict analysis, meta moderation, deliberation, and targeted second rounds. `FULL_CMM` preserves the complete state-machine process for complex, high-risk, strategic, multi-stakeholder, legal, medical, financial, safety, privacy, or conflict-heavy tasks. Routing is deterministic and heuristic in this stage; it may misclassify borderline requests.

Balance Analyzer 2.0 preserves tag/count checks for missing and dominant perspectives, then adds deterministic heuristics for perspective coverage, constraints, stakeholder coverage, risk severity, argument quality, dominance, blind spots, and a recommended balance action. Semantic conflict analysis adds support for detecting meaning-level disagreements, trade-offs, blind spots, and premature consensus. These signals are heuristic support, not proof of answer quality.

Dynamic roles are whitelist-limited templates. The rule layer suggests obvious roles first, so budget/metrics/legal/ethics signals do not depend on fragile JSON model output. If capacity remains and the task is complex, the model may suggest an allowed role key such as `legal_reviewer` or `measurement_expert`, but code normalizes it to a predefined `ExpertRole`; arbitrary tags and model-generated `system_prompt` values are rejected. Dynamic roles are capped and used to address missing expertise, blind spots, trade-offs, and `ADD_EXPERT` / `DEEPEN` decisions.

Optional parallelism is deliberately narrow. The default `parallel_mode="SEQUENTIAL"` keeps deterministic sequential execution. `parallel_mode="THREADS"` may run independent first-round and targeted follow-up expert calls with a bounded `ThreadPoolExecutor`, but outputs are collected in selected-role order and all state-machine transitions, routing, balance/conflict/meta, planning, critique, answer generation, and moderation remain sequential. `DIRECT` ignores expert parallel settings because it does not run experts.

`PLAN_CRITIQUE` is context-aware: it checks whether the plan covers query-intake constraints, success criteria, expert risks and recommendations, `must_address`, unresolved trade-offs, blind spots, selected dynamic roles, deliberation revisions, and previous replan feedback. It also exposes Stage 9 compatibility aliases such as `decision`, `ignored_risks`, `ignored_tradeoffs`, and `ignored_must_address`; ignored critical risks or must-address items cannot be silently accepted. `REPLAN` is intentionally bounded: it regenerates the plan from the latest CMM context, previous plan, and actionable critique feedback. It does not restart the full expert pipeline.

## Trace Report

`run_cmm(...)` returns:

```python
{
    "final_answer": str,
    "trace_report": dict,
    "raw": {
        "expert_bundle": dict,
        "moderated_result": dict,
    },
}
```

`trace_report` summarizes:

- `original_query` and `formalized_query`
- `query_intake`
- `router_decision`, `cmm_mode`, `estimated_cost_class`, and `routing_warnings`
- `parallel_mode`, `max_workers`, and `parallelized_stages`
- `roles_used` and `expert_rounds`
- `roles_used_unique`, a deduplicated human/eval view with rounds and dynamic-role flags
- `dynamic_role_reports`, `dynamic_roles_generated`, `dynamic_roles_executed`, `dynamic_roles_rejected`
- `dynamic_roles_used` is retained as a compatibility alias for `dynamic_roles_executed`
- `deliberation_brief`
- `balance_reports`
- `conflict_reports`
- `deliberation_rounds` and `deliberation_revisions`
- `meta_moderation_decisions`
- `conflicts_to_resolve` and `risks_to_address`
- `plan` and `plan_critique`
- `moderation_reports`
- `revision_count`
- `final_confidence`
- `warnings`
- `state_history`, `final_state`, `transition_count`, `iteration_count`
- `plans`, `plan_critiques`, and `errors`
- `json_health`, a compact summary of JSON attempts, fallbacks, and invalid-output warnings across experts, planning, moderation, conflict analysis, and meta moderation
- observability telemetry: `estimated_call_count`, `estimated_stage_count`, `answer_chars`, `warnings_count`, and `errors_count`

For defense/debugging, `Lib.trace_formatter.format_trace_report(trace_report)` returns a compact text summary with routing, state path, roles, balance, conflicts, deliberation, plan critique, moderation, warnings, and errors. It is a human-readable view over the trace, not a replacement for the structured trace.

## JSON Contracts

The project uses JSON-first contracts where downstream code depends on structured model output:

- Query intake requests JSON extraction and falls back to rule-based/fallback structure while preserving the full original query.
- Query intake, expert agents, dynamic role model suggestions, the planner, conflict analyzer, meta moderator, plan critic, and answer moderator use the shared JSON retry helper. If the first model response is invalid JSON, CMM asks once for JSON repair and records `json_attempts` / parse warnings.
- Router decisions are deterministic and offline-first; they fall back to `FULL_CMM` if routing fails.
- Expert agents fall back to diagnostic empty contributions with `invalid_json_from_model`, `json_attempts`, `parse_warnings`, and truncated raw output when both JSON attempts fail.
- Planner requests a JSON plan and falls back to legacy text parsing or a context-aware safe fallback plan built from intake constraints, success criteria, must-address items, expert risks, and conflict blind spots.
- Plan critic requests JSON critique and falls back to conservative rule checks against constraints, expert risks, trade-offs, dynamic roles, and deliberation revisions.
- Expert selector is rules-first for obvious domains and uses model selection only as an optional fallback for complex queries.
- Moderator requests JSON evaluation with expert coverage, balance handling, unresolved questions, issues, and improvements; a final `REJECT` is surfaced explicitly rather than treated as a normal final answer.
- Meta moderation applies a deterministic guard so a strong rule-based `DEEPEN` / `ADD_EXPERT` signal cannot be silently overridden by an optimistic model `SYNTHESIZE` / `FINALIZE`.
- Invalid model output is treated as untrusted input and produces explicit fallback data with parse warnings.

## Meta Moderation

`meta_moderator` reviews the process after expert balance and before planning. It checks whether perspectives are missing, one perspective dominates, or risks/questions need deeper treatment.

When conflict or meta-moderation state indicates meaningful disagreement, unresolved trade-offs, blind spots, or premature consensus, the MVP runs one structured deliberation round using existing roles. Experts see their own first contribution, compact positions from other roles, and the conflict report, then return agreements, disagreements, missed points, revised recommendations, new risks, and group questions.

By default deliberation remains one round. If `max_deliberation_rounds=2`, the state machine performs a `CONSENSUS_CHECK` after round 1, refreshes balance/brief/conflict context once, and runs a second round only when a high-severity unresolved conflict remains and the conflicting roles are identifiable. This keeps deliberation bounded and prevents open-ended debate.

If the decision is still `DEEPEN` or `ADD_EXPERT`, the MVP may also run the existing targeted second expert round using existing base roles and safe dynamic templates. It is sequential by default and can use opt-in thread execution for independent expert calls. The system merges downstream expert context, re-runs balance/conflict analysis, rebuilds `deliberation_brief`, and records expert rounds, deliberation rounds, dynamic role reports, balance reports, and conflict reports in `trace_report`.

## Evaluation Harness

The dataset `cmm_dataset_v1.csv` contains 36 broad benchmark cases. `cmm_dataset_v2.csv` is the first real-eval calibration set with 20 cases and explicit `expected_mode` labels for `DIRECT`, `LIGHT_CMM`, and `FULL_CMM`.

The mock evaluation harness compares:

- baseline single-model style output
- CMM output through the same scoring interface

Mock mode scores deterministic outputs without network/API calls. It is a mechanical regression aid, not proof that CMM is better.

Real judged mode is explicit and may call external APIs. It generates baseline and CMM answers, preserves the CMM trace, creates blind Answer A/B packets, and either exports human-review artifacts (`--judge-mode none`) or calls an LLM judge (`--judge-mode llm`). Rubrics and expected perspectives are used as judge criteria, not hidden answer content.

`--judge-mode none` writes `human_review.jsonl`, `human_review.csv`, and `routing_review.csv`. The CSV files are intended for manual blind review and router calibration before trusting any LLM judge. `tools/analyze_eval_routing.py` converts `results.csv` into a compact `routing_analysis.csv` with technical failures, router mismatches, and baseline wins.

The eval harness remains sequential in this stage to preserve row ordering and scoring semantics; parallel eval execution is a future extension.

Results are exported to CSV and JSON with:

- `case_id`
- `baseline_score`
- `cmm_score`
- coverage deltas
- `winner`
- `notes`
- CMM diagnostics such as `cmm_final_state`, warning/error counts, JSON fallback counts, expert valid/invalid contribution counts, planner raw format/attempts, plan critique statuses, and answer-moderation final decision
- Observability fields such as unique roles used, estimated call/stage counts, answer length, and warning/error counts
- Router calibration fields such as `expected_mode`, `actual_mode`, `router_mode_match`, mode distributions, technical failures by mode, and average estimated cost score

The scoring is a lightweight deterministic heuristic, not a paper-grade experimental result.

Real judged results are first evaluation evidence on a limited sample, not proof of universal superiority.

## Tests

```bash
python -m unittest discover -s tests
```

The test suite is designed to run without a real API key, network access, or external services.

## Limitations

- CMM is an MVP, not proof that multi-agent output is always better.
- Query intake protects the original query but does not prove that downstream answers are always better.
- Balance Analyzer 2.0 and semantic conflict analysis provide heuristic quality signals, but they do not prove quality or fully solve groupthink.
- The state machine is bounded and MVP-level; it is not an unbounded autonomous process controller.
- The router is deterministic and heuristic; real evaluation should compare quality and cost by `cmm_mode` and router complexity.
- The structured deliberation round lets selected experts respond to other roles and revise recommendations, but it is bounded and schema-driven. A second deliberation round is opt-in, capped, and only for unresolved high-severity conflicts with identifiable roles.
- The context-aware plan critic is still an MVP control node with heuristic/model-assisted checks, not formal verification of plan correctness.
- The second expert round is implemented, but it is limited to existing safe base roles plus whitelisted dynamic templates.
- There is no fully free-form expert debate state machine.
- There is optional thread-based execution for independent expert calls only; there is no async or parallel state-machine orchestration.
- There is no arbitrary dynamic role generation; dynamic roles are whitelist-based and capped.
- Evaluation scoring is deterministic and useful for regression, but not a substitute for human evaluation.
- Real model behavior depends on external API availability and model output quality.
- The current CLI is minimal and intended for local experimentation.
