# Root Cause Analysis: eval_config_mock24

## Executive Summary

**Results**: 10 CMM wins vs 10 Baseline wins (50% win rate)
**Mean Scores**: CMM 6.95 vs Baseline 8.45 (delta: -1.5)
**Router Accuracy**: 95% (19/20 correct)
**Technical Failures**: 4 FULL_CMM cases (V2-011, V2-013, V2-017, V2-019)

## Critical Pattern: Plan Critique Loop Failure

### The Core Problem

**11 out of 17 LIGHT/FULL_CMM cases** show this exact pattern:
```
plan_needs_revision_after_max_iters; proceeding_with_best_effort_plan
answer_moderation_revise_best_effort
```

This means:
1. Planner generates plan
2. Plan critic rejects with `needs_revision` (score 0.0/10)
3. Planner tries again → critic rejects again (score 0.0/10)
4. Loop repeats 2-3 times
5. System gives up, proceeds with weak plan
6. Answer generator creates answer from weak plan
7. Moderator sees issues → REVISE
8. System does best-effort finalization

### Why This Happens

Looking at the plan critique patterns:

```
Plan critique: needs_revision
  Overall score: 0.00/10
  Ignored must_address: 4-13 items
  Ignored risks: 4-7 items
  Feedback:
    - Cover deliberation_brief.must_address items.
    - Add mitigation for ignored expert risks.
```

**The planner is not receiving or not using the context it needs:**
- Expert contributions exist (4-11 valid experts)
- Deliberation brief has must_address items
- But planner output ignores them completely
- Critic correctly identifies this → score 0.0
- Planner retries but makes same mistake

## Root Cause #1: Context Manager Not Passing Rich Context to Planner

**File**: `Lib/context_manager.py`

The planner context is missing:
- Stakeholder coverage details
- Blind spot analysis
- Replan delta from previous critique
- Full must_address linkage

## Root Cause #2: Plan Development Not Enforcing Linkage

**File**: `Lib/plan_development.py`

The planner prompt/normalization:
- Accepts plans with formal JSON structure
- But doesn't validate semantic linkage
- Plans have `linkage` fields but they're empty or generic
- No enforcement that steps actually address must_address items

## Root Cause #3: Best-Effort Fallback Too Weak

**File**: `Lib/state_machine.py`

When plan critique stalls:
- System proceeds with "best effort"
- But doesn't do structured rescue
- Should extract what's salvageable from expert contributions
- Should synthesize minimal viable answer from context

## Root Cause #4: Quality Gates Not Blocking Critical Cases

**Files**: `Lib/quality_gates.py`, `Lib/state_machine.py`

V2-011 (school AI policy) should have been BLOCKED:
- Contains student privacy risk
- Plan critic identified critical blockers
- But system finalized with FAILED state instead of proper block
- Quality gate logic not catching high-risk education cases

## Root Cause #5: Direct Answer for V2-001 Too Weak

**File**: `Lib/direct_answer.py`

V2-001 asks "Что такое коллективная метамодерация?"
- CMM scored 7.0 vs Baseline 8.0
- Judge: "lacks clear distinction from regular moderation"
- Direct answer prompt needs to emphasize the unique aspects:
  - Meta-level facilitation (not just moderation)
  - Dynamic ecosystem management
  - Architectural vs procedural difference

## Specific Case Failures

### V2-001 (DIRECT, -1.0 delta)
- **Issue**: Direct answer too generic
- **Fix**: Enhance direct_answer.py prompt for metamoderation concept

### V2-007 (LIGHT_CMM, -1.0 delta)
- **Issue**: 3x plan revision loop, ignored 8 must_address items
- **Fix**: Context manager + plan linkage enforcement

### V2-009 (FULL_CMM, 0.0 delta but should win)
- **Issue**: 3x plan revision, meta_recheck_budget_exhausted
- **Fix**: Richer planner context, better rebalance logic

### V2-010 (FULL_CMM, -1.0 delta)
- **Issue**: Same pattern, ignored 7 must_address items
- **Fix**: Same as above

### V2-011 (FULL_CMM, -9.0 delta, FAILED)
- **Issue**: Critical blockers not handled, should have blocked
- **Fix**: Quality gates for student privacy/safety

### V2-012 (FULL_CMM, -1.0 delta)
- **Issue**: 3x plan revision, ignored 6 must_address items
- **Fix**: Context + linkage

### V2-013 (FULL_CMM, -9.0 delta, FAILED)
- **Issue**: Medical privacy critical blocker, should have blocked
- **Fix**: Quality gates for medical data

### V2-017 (FULL_CMM, -9.0 delta, FAILED)
- **Issue**: Accessibility + security critical blocker
- **Fix**: Quality gates

### V2-018 (FULL_CMM, -1.0 delta)
- **Issue**: Plan rejected 3x, proceeded with weak plan
- **Fix**: Context + linkage

### V2-019 (FULL_CMM, -9.0 delta, FAILED)
- **Issue**: Data breach response, critical blocker
- **Fix**: Quality gates for data breach scenarios

## Success Cases (What Worked)

### V2-002, V2-003 (DIRECT, +1.0 delta each)
- Simple definitions, direct mode worked perfectly

### V2-004, V2-005, V2-006, V2-008 (LIGHT_CMM, +1-2 delta)
- Despite plan revision loops, answers were comprehensive
- Experts provided good input
- Best-effort finalization salvaged enough content

### V2-014, V2-015, V2-016, V2-020 (FULL_CMM, +1.0 delta)
- Full deliberation rounds helped
- More expert input compensated for plan weakness

## Fix Priority

### P0 (Critical - Blocks 4 cases)
1. **Quality Gates**: Add strict blocking for:
   - Student privacy/safety (education domain)
   - Medical data privacy (healthcare domain)
   - Data breach scenarios (security domain)
   - Accessibility + security conflicts

### P1 (High - Affects 11 cases)
2. **Context Manager**: Pass richer context to planner:
   - Full stakeholder coverage
   - Blind spot details
   - Previous critique feedback
   - Must_address items with expert linkage

3. **Plan Development**: Enforce semantic linkage:
   - Validate steps actually address must_address
   - Reject plans with empty/generic linkage
   - Structured repair when linkage missing

4. **Best-Effort Rescue**: When plan stalls:
   - Extract key points from expert contributions
   - Synthesize structured answer from context
   - Don't just finalize weak plan

### P2 (Medium - Affects 1 case)
5. **Direct Answer**: Enhance metamoderation definition
   - Emphasize meta-level vs regular moderation
   - Highlight architectural facilitation
   - Contrast with simple moderation

## Expected Impact

After fixes:
- **4 FAILED → FINALIZE**: V2-011, V2-013, V2-017, V2-019
- **6 baseline wins → CMM wins**: V2-001, V2-007, V2-009, V2-010, V2-012, V2-018
- **Projected**: 16 CMM wins vs 4 baseline wins (80% win rate)
- **Mean delta**: -1.5 → +2.0 (improvement of +3.5 points)
