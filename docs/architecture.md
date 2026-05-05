# Architecture

This document reflects the current implementation of the Collective Meta-Moderation MVP.

## Pipeline

```text
INTAKE
-> ROUTE
-> DIRECT_ANSWER for DIRECT
   or PANEL_ROUND_1 for LIGHT_CMM / FULL_CMM
-> BALANCE
-> PLAN for LIGHT_CMM
   or CONFLICT_ANALYSIS for FULL_CMM
-> META_DECISION
-> DELIBERATION_ROUND when deeper structured discussion is needed
-> PANEL_ROUND_EXTRA when targeted follow-up is still useful
-> REBALANCE
-> PLAN
-> PLAN_CRITIQUE
-> REPLAN when critique feedback requires a new plan
-> ANSWER
-> ANSWER_MODERATION
-> FINALIZE or FAILED
```

## Main Components

- `main.py` is a thin CLI wrapper around `Lib.orchestrator.run_cmm`.
- `Lib/orchestrator.py` exposes the stable public `run_cmm(...)` entrypoint.
- `Lib/state_machine.py` owns the bounded CMM state machine, transition history, and trace/result assembly.
- `Lib/router.py` deterministically selects `DIRECT`, `LIGHT_CMM`, or `FULL_CMM`.
- `Lib/direct_answer.py` handles simple low-risk direct answers.
- `Lib/query_intake.py` preserves `original_query` as the authoritative source and extracts helper fields such as `cleaned_query`, context, constraints, success criteria, unknowns, and user preferences.
- `Lib/role_generator.py` maps model/rule suggestions to whitelist-limited dynamic role templates.
- `Lib/expert_selector.py`, `Lib/expert_roles.py`, `Lib/expert_agent.py`, and `Lib/expert_panel.py` implement expert selection and contribution collection. Expert calls are sequential by default, with optional ordered thread execution for independent first-round calls.
- `Lib/expert_rounds.py` selects safe follow-up roles, runs targeted second expert rounds, and merges expert bundles. Targeted expert calls can use the same opt-in thread execution when several roles are selected.
- `Lib/parallel_utils.py` provides bounded standard-library helpers for ordered `ThreadPoolExecutor` execution.
- `Lib/balance_analyzer.py` identifies missing/dominant perspectives and adds deterministic quality heuristics for coverage, risk severity, argument quality, blind spots, and recommended balance action.
- `Lib/conflict_analyzer.py` identifies semantic agreements, disagreements, unresolved trade-offs, blind spots, minority positions, and premature consensus risks.
- `Lib/deliberation.py` converts expert output and balance data into a compact downstream context.
- `Lib/deliberation_round.py` runs one structured deliberation pass where selected experts answer other roles' positions and revise recommendations.
- `Lib/meta_moderator.py` evaluates process quality and can request deeper treatment.
- `Lib/plan_development.py`, `Lib/plan_critic.py`, `Lib/agent_improver.py`, and `Lib/agent_moderator.py` build, critique, answer, moderate, and revise.
- `cmm/eval.py` provides the offline-first evaluation CLI plus opt-in real judged evaluation with blind Answer A/B packets.

Legacy compatibility modules remain importable but are not first-class pipeline components: `Lib/Start_formalization.py` is superseded by `Lib/query_intake.py`, `Lib/agent_critic.py` and `Lib/critic_decision.py` preserve old critique imports around `Lib/plan_critic.py`, and `Lib/Finish_agent.py` is outside the main state-machine answer/moderation path.

## Data Flow Notes

`original_query` is authoritative and preserved in the trace. `formalized_query` is populated from query intake `cleaned_query` and is helper text only.

`query_intake` extracts structure instead of replacing the user's request:

- `task_goal`
- `context`
- `constraints`
- `success_criteria`
- `unknowns`
- `user_preferences`
- `complexity` and `risk_level`

After intake, `ROUTE` decides whether to run a direct answer, light CMM, or full CMM. `DIRECT` skips expert, balance, conflict, meta, deliberation, targeted second round, planning, and plan critique. `LIGHT_CMM` runs expert panel, balance, brief, planning, plan critique, and answer moderation, but skips conflict analysis, meta moderation, deliberation, and targeted second expert rounds. `FULL_CMM` preserves the complete pipeline for complex, high-risk, multi-stakeholder, strategic, legal, medical, financial, safety, privacy, or conflict-heavy requests.

`expert_bundle` flows into:

- balance analysis
- semantic conflict analysis
- deliberation brief
- planning context
- answer generation context
- moderation context
- trace report

This is intentional: expert work must influence downstream stages to matter.

When `meta_moderator` returns `DEEPEN` or `ADD_EXPERT`, the state machine can select targeted base roles and safe dynamic templates, run one second expert round, merge both bundles, re-run balance analysis, and rebuild the final deliberation brief before planning. This round is sequential by default and may use opt-in thread execution only for independent expert calls.

Before planning, the state machine can also run one structured deliberation round when conflict or meta-moderation state shows disagreements, unresolved trade-offs, blind spots, or premature consensus. This pass is not another gap-filling expert round: each selected expert sees its own first contribution, compact positions from other roles, and the conflict report, then returns agreements, disagreements, missed points, revised recommendations, new risks, and group questions. The revisions are merged into expert context and conflict analysis is recomputed.

Dynamic roles are generated only through a fixed template catalog. The model may suggest allowed role keys or perspective tags, but code rejects arbitrary keys, arbitrary tags, unsafe text, duplicates, over-limit suggestions, and any attempt to provide `system_prompt`.

Balance Analyzer 2.0 remains offline and deterministic. It preserves the original tag/count fields while adding perspective coverage, constraint coverage, stakeholder coverage, risk severity distribution, argument quality, dominance detail, blind spots, and a recommended action for meta moderation.

`PLAN_CRITIQUE` is a context-aware control node. It evaluates the generated plan against query-intake constraints, success criteria, `deliberation_brief.must_address`, expert recommendations and risks, semantic conflict reports, dynamic roles, deliberation revisions, latest meta decision, state history, and previous replan feedback. Stage 9 hardening keeps the richer critic while adding compatibility aliases (`decision`, `ignored_risks`, `ignored_tradeoffs`, `ignored_must_address`) and deterministic critical-blocker checks so ignored critical expert risks or must-address items cannot be accepted silently.

`REPLAN` is a bounded planner-only transition. It uses the latest query intake, deliberation brief, conflict report, previous plan, and context-aware critique feedback. It does not restart query intake or expert rounds in this MVP.

Optional parallelism is scoped to independent expert execution. `parallel_mode="SEQUENTIAL"` is the default. `parallel_mode="THREADS"` can run first-round or targeted follow-up expert calls with a bounded thread pool while preserving selected-role output order. Shared `CMMState` mutation, state transitions, routing, balance/conflict/meta, deliberation merge, planning, plan critique, answer generation, and answer moderation stay sequential.

## Trace Report

The trace report is a structured audit object, not just debug logs. It includes:

- query fields
- query intake
- roles and expert rounds
- dynamic role reports and dynamic roles used
- deliberation brief
- balance reports
- conflict reports
- deliberation rounds and revisions
- meta moderation decisions
- plan and critique
- moderation reports
- router decision, CMM mode, estimated cost class, and routing warnings
- parallel mode, max workers, and parallelized stages
- warnings and revision count
- state history, final state, transition count, iteration count, plans, plan critiques, and errors

## Failure Handling

The MVP favors explicit fallback structures over crashes:

- missing/invalid query intake falls back to the full original query plus mechanically cleaned helper text
- expert panel failure falls back to an empty expert bundle
- balance failure falls back to conservative missing-perspective data
- invalid model JSON records parse warnings where applicable
- weak or context-missing plans return `needs_revision` / `rejected` with structured feedback
- rejected plans return structured failure instead of continuing blindly

## Known Gaps

- The second expert round is implemented as a targeted pass over existing safe base roles plus whitelisted dynamic role templates.
- Experts can now respond to other roles in one structured deliberation round, but there is no fully free-form debate state machine.
- The state machine is bounded and MVP-level; it does not implement async, parallel state mutation, or unbounded autonomous control.
- Router decisions are deterministic heuristics and can misclassify borderline tasks; routing should be evaluated by mode and complexity.
- Balance Analyzer 2.0 is still heuristic and deterministic; it is not proof of quality.
- Semantic conflict analysis is support for detecting trade-offs and consensus risks; deliberation is bounded and schema-driven.
- Query intake preserves source truth but does not guarantee downstream semantic completeness.
- Context-aware plan critique improves REPLAN feedback, but it remains heuristic/model-assisted rather than formal verification and can still miss semantic failures.
- Mock evaluation is heuristic and deterministic by default. Real judged evaluation provides limited first evidence, not proof of universal superiority.
- Optional thread-based parallelism is limited to independent expert calls; no async/parallel orchestration is implemented.
- The eval harness remains sequential in this stage; parallel eval execution is a future extension to avoid changing scoring/order semantics.
- No arbitrary dynamic role generation is implemented; dynamic roles are capped and template-based.
- No UI is included.
