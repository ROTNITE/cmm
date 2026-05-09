Fix CMM quality gates: separate blocker classes and improve routing

## Problem
CMM system was generating empty answers (0 chars) on cases V2-006, V2-007, V2-010 
despite having valid expert contributions. Root cause: quality_gates.py was treating 
product trade-offs and design constraints as fatal NO_ANSWER_BLOCKER issues.

Regression: eval_cmm_quality_fix_10 (8 wins, +1.8 delta) → eval_cmm_quality_fix_10_final 
(6 wins, -1.5 delta, 3 technical failures).

## Solution: 6 systematic fixes

### 1. quality_gates.py: Separate blocker classes
- Split critical issues into three categories:
  - NO_ANSWER_BLOCKER: safety/legal/privacy (must refuse)
  - MUST_ADDRESS_IN_ANSWER: trade-offs/risks (must discuss)
  - QUALITY_IMPROVEMENT: style/detail suggestions (optional)
- Added classify_blocker() for deterministic classification
- Added create_quality_gate_debug() for explainable trace
- Added get_must_address_items() to pass items to final answer

### 2. plan_critic.py: Fix FINALIZE recognition
- Fixed _status_from_critique(): FINALIZE + no blockers → status = "ready"
- Added explicit check for markers: "ready for final answer", "готов к финализации"
- Previously: critic would say "ready" but status stayed "needs_revision"

### 3. router.py: Operational plan detection
- Added _OPERATIONAL_PLAN_MARKERS and _SMALL_SCOPE_MARKERS
- Logic: operational plan + small scope + no high-risk → LIGHT_CMM
- Fixed: "team" in operational context doesn't mean multi-stakeholder governance
- Example: "план запуска базы знаний для команды" → LIGHT_CMM (was FULL_CMM)

### 4. answer_budget.py: Mode-specific budgets
- DIRECT: 650-1000 chars (compact answers)
- LIGHT_CMM: 1200-2500 chars (structured plans)
- FULL_CMM: 2500-4500 chars (comprehensive analysis)
- Added mode parameter for explicit CMM mode specification
- Detect detailed_request to increase limit when appropriate

### 5. state_machine.py: Rename warnings
- Renamed: meta_recheck_limit_reached → meta_recheck_budget_exhausted
- Updated messages: "synthesizing unresolved tradeoffs with decision rules"
- Clearer distinction: budget exhaustion is normal bounded-loop termination, not error

### 6. tests/test_policy_gates.py: Policy validation
- 6 tests covering all fixes:
  1. Product trade-offs → MUST_ADDRESS (not NO_ANSWER_BLOCKER)
  2. Safety blockers → NO_ANSWER_BLOCKER
  3. Critic FINALIZE + no blockers → status = ready
  4. Actionable plan + no NO_ANSWER_BLOCKER → can finalize
  5. Operational plan → LIGHT_CMM (not FULL_CMM)
  6. DIRECT prompt without hardcoded KPI example
- All tests passing: python -m unittest tests.test_policy_gates -v

## Expected results
Before fixes (from old logs):
- V2-006: FULL_CMM, 0 chars, critical_plan_blockers ❌
- V2-007: 8519 chars generated → 0 chars output ❌
- V2-010: 0 chars, critical_plan_blockers ❌

After fixes (expected):
- V2-006: LIGHT_CMM, >0 chars, must_address items in answer ✓
- V2-007: >0 chars, best_effort finalize ✓
- V2-010: >0 chars, must_address items in answer ✓

## Files changed
- Lib/quality_gates.py
- Lib/plan_critic.py
- Lib/router.py
- Lib/answer_budget.py
- Lib/state_machine.py
- tests/test_policy_gates.py

## Documentation
- DIAGNOSTIC_IMPROVEMENTS.md: Full description of all 6 fixes
- ACTION_PLAN.md: Testing plan and eval protocol
- SUMMARY.md: Brief summary for users
- RESPONSE_TO_STAGES_5_6.md: Response to ID-based coverage and version stamping proposals
- SESSION_SUMMARY_2026-05-06.md: Complete session summary

## Next steps
1. Version stamping in cmm.eval (3-4 hours, КРИТИЧНО)
2. ID-based coverage in deliberation/planner/critic (2-3 hours, ВЫСОКИЙ)
3. Frozen answers protocol (2 hours)
4. Full eval on 20 cases with version stamping

Co-Authored-By: Claude Sonnet 4 <noreply@anthropic.com>
