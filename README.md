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
```

`mock` mode is offline and deterministic; it checks evaluation mechanics, not answer quality. Use `--mode real` only when you intentionally want real model/CMM calls. Real judged evaluation can export blind packets for human review or call an LLM judge explicitly:

```bash
python -m cmm.eval --dataset cmm_dataset_v1.csv --limit 10 --mode real --judge-mode none --output-dir eval_real_10
python -m cmm.eval --dataset cmm_dataset_v1.csv --limit 10 --mode real --judge-mode llm --output-dir eval_real_10
```

## Environment

1. Create a local `.env` from `.env.example`.
2. Set `DEEPSEEK_API_KEY` locally.
3. Install dependencies from `requirements.txt`.

Do not commit real secrets. `.env` and `Api.env` are ignored. The API client reads secrets only at call time and does not print key values.

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

`run_cmm(query, *, max_iters=2, model="deepseek-chat", route_mode="AUTO", parallel_mode="SEQUENTIAL", max_workers=None)` is the central MVP entrypoint. Existing calls without the newer optional keywords still work. Internally it delegates to a bounded CMM state machine with deterministic routing.

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
-> DELIBERATION_ROUND or PANEL_ROUND_EXTRA when needed
-> REBALANCE
-> PLAN
-> PLAN_CRITIQUE
-> REPLAN when critique requires it
-> ANSWER / ANSWER_MODERATION
-> FINALIZE or FAILED
```

Key modules:

- `Lib/orchestrator.py`: public `run_cmm(...)` wrapper.
- `Lib/state_machine.py`: bounded CMM state machine, transition history, trace/result assembly.
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
- `Lib/deliberation_round.py`: runs a structured deliberation pass where experts respond to other roles and revise recommendations.
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

## JSON Contracts

The project uses JSON-first contracts where downstream code depends on structured model output:

- Query intake requests JSON extraction and falls back to rule-based/fallback structure while preserving the full original query.
- Query intake, dynamic role model suggestions, and plan critique use a shared JSON retry helper. If the first model response is invalid JSON, CMM asks once for JSON repair and records `json_attempts` / parse warnings.
- Router decisions are deterministic and offline-first; they fall back to `FULL_CMM` if routing fails.
- Planner requests a JSON plan and falls back to legacy text parsing or a safe fallback plan.
- Plan critic requests JSON critique and falls back to conservative rule checks against constraints, expert risks, trade-offs, dynamic roles, and deliberation revisions.
- Expert agents and selector parse markdown-wrapped JSON through shared helpers.
- Moderator requests JSON evaluation with expert coverage, balance handling, unresolved questions, issues, and improvements.
- Invalid model output is treated as untrusted input and produces explicit fallback data with parse warnings.

## Meta Moderation

`meta_moderator` reviews the process after expert balance and before planning. It checks whether perspectives are missing, one perspective dominates, or risks/questions need deeper treatment.

When conflict or meta-moderation state indicates meaningful disagreement, unresolved trade-offs, blind spots, or premature consensus, the MVP can run one structured deliberation round using existing base roles. Experts see their own first contribution, compact positions from other roles, and the conflict report, then return agreements, disagreements, missed points, revised recommendations, new risks, and group questions.

If the decision is still `DEEPEN` or `ADD_EXPERT`, the MVP may also run the existing targeted second expert round using existing base roles and safe dynamic templates. It is sequential by default and can use opt-in thread execution for independent expert calls. The system merges downstream expert context, re-runs balance/conflict analysis, rebuilds `deliberation_brief`, and records expert rounds, deliberation rounds, dynamic role reports, balance reports, and conflict reports in `trace_report`.

## Evaluation Harness

The dataset `cmm_dataset_v1.csv` contains 36 cases with queries, constraints, expected perspectives, rubrics, reference outlines, and expected single-model failure modes.

The mock evaluation harness compares:

- baseline single-model style output
- CMM output through the same scoring interface

Mock mode scores deterministic outputs without network/API calls. It is a mechanical regression aid, not proof that CMM is better.

Real judged mode is explicit and may call external APIs. It generates baseline and CMM answers, preserves the CMM trace, creates blind Answer A/B packets, and either exports human-review artifacts (`--judge-mode none`) or calls an LLM judge (`--judge-mode llm`). Rubrics and expected perspectives are used as judge criteria, not hidden answer content.

The eval harness remains sequential in this stage to preserve row ordering and scoring semantics; parallel eval execution is a future extension.

Results are exported to CSV and JSON with:

- `case_id`
- `baseline_score`
- `cmm_score`
- coverage deltas
- `winner`
- `notes`

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
- The structured deliberation round lets selected experts respond to other roles and revise recommendations, but it is bounded and schema-driven.
- The context-aware plan critic is still an MVP control node with heuristic/model-assisted checks, not formal verification of plan correctness.
- The second expert round is implemented, but it is limited to existing safe base roles plus whitelisted dynamic templates.
- There is no fully free-form expert debate state machine.
- There is optional thread-based execution for independent expert calls only; there is no async or parallel state-machine orchestration.
- There is no arbitrary dynamic role generation; dynamic roles are whitelist-based and capped.
- Evaluation scoring is deterministic and useful for regression, but not a substitute for human evaluation.
- Real model behavior depends on external API availability and model output quality.
- The current CLI is minimal and intended for local experimentation.
