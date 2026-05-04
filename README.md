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

`run_cmm(query, *, max_iters=2, model="deepseek-chat")` is the central MVP entrypoint. Internally it delegates to a bounded CMM state machine.

## Architecture Overview

Current state-machine path:

```text
original_query
-> INTAKE
-> PANEL_ROUND_1
-> BALANCE
-> CONFLICT_ANALYSIS
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
- `Lib/query_intake.py`: preserves the original query as authoritative and extracts helper structure such as constraints, context, success criteria, unknowns, and preferences.
- `Lib/expert_panel.py`: runs selected expert roles and collects contributions.
- `Lib/expert_rounds.py`: selects safe follow-up roles, runs targeted second rounds, and merges bundles.
- `Lib/balance_analyzer.py`: checks missing and dominant perspectives.
- `Lib/conflict_analyzer.py`: checks semantic agreements, disagreements, unresolved trade-offs, blind spots, and premature consensus risks.
- `Lib/deliberation.py`: builds compact expert synthesis for downstream stages.
- `Lib/deliberation_round.py`: runs a structured deliberation pass where experts respond to other roles and revise recommendations.
- `Lib/meta_moderator.py`: makes process-level decisions such as `SYNTHESIZE` or `DEEPEN`.
- `Lib/plan_development.py`: creates a JSON-first plan with legacy fallback.
- `Lib/agent_moderator.py`: evaluates answers and drives revision.
- `cmm/eval.py`: offline-first baseline vs CMM evaluation harness.

The `original_query` is authoritative. `cleaned_query` / `formalized_query` is helper text only, and query intake extracts structure instead of rewriting away meaning. The `expert_bundle` is not decorative: it feeds the deliberation brief, plan context, answer generation, moderation, and trace report.

Balance analysis remains mostly tag/count based. Semantic conflict analysis adds support for detecting meaning-level disagreements, trade-offs, blind spots, and premature consensus. The structured deliberation round then lets selected experts respond to other roles' positions and revise recommendations, but it is still not a fully free-form debate system.

`REPLAN` is intentionally bounded: it regenerates the plan from the latest query intake, deliberation brief, conflict report, previous plan, and critique feedback. It does not restart the full expert pipeline.

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
- `roles_used` and `expert_rounds`
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
- Planner requests a JSON plan and falls back to legacy text parsing or a safe fallback plan.
- Expert agents and selector parse markdown-wrapped JSON through shared helpers.
- Moderator requests JSON evaluation with expert coverage, balance handling, unresolved questions, issues, and improvements.
- Invalid model output is treated as untrusted input and produces explicit fallback data with parse warnings.

## Meta Moderation

`meta_moderator` reviews the process after expert balance and before planning. It checks whether perspectives are missing, one perspective dominates, or risks/questions need deeper treatment.

When conflict or meta-moderation state indicates meaningful disagreement, unresolved trade-offs, blind spots, or premature consensus, the MVP can run one structured deliberation round using existing base roles. Experts see their own first contribution, compact positions from other roles, and the conflict report, then return agreements, disagreements, missed points, revised recommendations, new risks, and group questions.

If the decision is still `DEEPEN` or `ADD_EXPERT`, the MVP may also run the existing sequential targeted second expert round using existing base roles only. The system merges downstream expert context, re-runs balance/conflict analysis, rebuilds `deliberation_brief`, and records expert rounds, deliberation rounds, balance reports, and conflict reports in `trace_report`.

## Evaluation Harness

The dataset `cmm_dataset_v1.csv` contains 36 cases with queries, constraints, expected perspectives, rubrics, reference outlines, and expected single-model failure modes.

The mock evaluation harness compares:

- baseline single-model style output
- CMM output through the same scoring interface

Mock mode scores deterministic outputs without network/API calls. It is a mechanical regression aid, not proof that CMM is better.

Real judged mode is explicit and may call external APIs. It generates baseline and CMM answers, preserves the CMM trace, creates blind Answer A/B packets, and either exports human-review artifacts (`--judge-mode none`) or calls an LLM judge (`--judge-mode llm`). Rubrics and expected perspectives are used as judge criteria, not hidden answer content.

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
- Semantic conflict analysis supports trade-off and consensus-risk detection, but it does not fully solve groupthink by itself.
- The state machine is bounded and MVP-level; it is not an unbounded autonomous process controller.
- The structured deliberation round lets selected experts respond to other roles and revise recommendations, but it is bounded and schema-driven.
- The second expert round is implemented, but it is sequential and limited to existing safe roles.
- There is no fully free-form expert debate state machine.
- There is no async/parallel execution.
- There is no arbitrary dynamic role generation yet.
- Evaluation scoring is deterministic and useful for regression, but not a substitute for human evaluation.
- Real model behavior depends on external API availability and model output quality.
- The current CLI is minimal and intended for local experimentation.
