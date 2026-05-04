# Architecture

This document reflects the current implementation of the Collective Meta-Moderation MVP.

## Pipeline

```text
INTAKE
-> PANEL_ROUND_1
-> BALANCE
-> CONFLICT_ANALYSIS
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
- `Lib/query_intake.py` preserves `original_query` as the authoritative source and extracts helper fields such as `cleaned_query`, context, constraints, success criteria, unknowns, and user preferences.
- `Lib/expert_selector.py`, `Lib/expert_roles.py`, `Lib/expert_agent.py`, and `Lib/expert_panel.py` implement expert selection and contribution collection.
- `Lib/expert_rounds.py` selects safe follow-up roles, runs targeted second expert rounds, and merges expert bundles.
- `Lib/balance_analyzer.py` identifies missing base perspectives and dominant perspectives.
- `Lib/conflict_analyzer.py` identifies semantic agreements, disagreements, unresolved trade-offs, blind spots, minority positions, and premature consensus risks.
- `Lib/deliberation.py` converts expert output and balance data into a compact downstream context.
- `Lib/deliberation_round.py` runs one structured deliberation pass where selected experts answer other roles' positions and revise recommendations.
- `Lib/meta_moderator.py` evaluates process quality and can request deeper treatment.
- `Lib/plan_development.py`, `Lib/agent_critic.py`, `Lib/agent_improver.py`, and `Lib/agent_moderator.py` build, critique, answer, moderate, and revise.
- `cmm/eval.py` provides the offline-first evaluation CLI plus opt-in real judged evaluation with blind Answer A/B packets.

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

`expert_bundle` flows into:

- balance analysis
- semantic conflict analysis
- deliberation brief
- planning context
- answer generation context
- moderation context
- trace report

This is intentional: expert work must influence downstream stages to matter.

When `meta_moderator` returns `DEEPEN` or `ADD_EXPERT`, the state machine can select targeted base roles, run one sequential second expert round, merge both bundles, re-run balance analysis, and rebuild the final deliberation brief before planning.

Before planning, the state machine can also run one structured deliberation round when conflict or meta-moderation state shows disagreements, unresolved trade-offs, blind spots, or premature consensus. This pass is not another gap-filling expert round: each selected expert sees its own first contribution, compact positions from other roles, and the conflict report, then returns agreements, disagreements, missed points, revised recommendations, new risks, and group questions. The revisions are merged into expert context and conflict analysis is recomputed.

`REPLAN` is a bounded planner-only transition. It uses the latest query intake, deliberation brief, conflict report, previous plan, and critique feedback. It does not restart query intake or expert rounds in this MVP.

## Trace Report

The trace report is a structured audit object, not just debug logs. It includes:

- query fields
- query intake
- roles and expert rounds
- deliberation brief
- balance reports
- conflict reports
- deliberation rounds and revisions
- meta moderation decisions
- plan and critique
- moderation reports
- warnings and revision count
- state history, final state, transition count, iteration count, plans, plan critiques, and errors

## Failure Handling

The MVP favors explicit fallback structures over crashes:

- missing/invalid query intake falls back to the full original query plus mechanically cleaned helper text
- expert panel failure falls back to an empty expert bundle
- balance failure falls back to conservative missing-perspective data
- invalid model JSON records parse warnings where applicable
- rejected plans return structured failure instead of continuing blindly

## Known Gaps

- The second expert round is implemented as a sequential targeted pass over existing safe base roles.
- Experts can now respond to other roles in one structured deliberation round, but there is no fully free-form debate state machine.
- The state machine is bounded and MVP-level; it does not implement async, dynamic roles, or unbounded autonomous control.
- Balance analysis is still mostly tag/count based.
- Semantic conflict analysis is support for detecting trade-offs and consensus risks; deliberation is bounded and schema-driven.
- Query intake preserves source truth but does not guarantee downstream semantic completeness.
- Mock evaluation is heuristic and deterministic by default. Real judged evaluation provides limited first evidence, not proof of universal superiority.
- No async/parallel orchestration is implemented.
- No arbitrary dynamic role generation is implemented.
- No UI is included.
