# Phase 1: Baseline Diagnosis

**Date:** 2026-05-06  
**Status:** Complete

## Executive Summary

All 6 failures in eval_plan_fix show "Experts: 0 valid, 0 invalid" with empty expert_rounds. Root cause: **model parameter propagation failure** in `state_machine.py:984-996`.

## Critical Bug: Model Propagation Failure

### Location
`Lib/state_machine.py:984-996`

### The Bug
```python
execution_kwargs = {}
if state.get("parallel_mode") == "THREADS":
    execution_kwargs = {
        "execution_mode": "THREADS",
        "max_workers": state.get("max_workers"),
        "model": state["model"],  # ← Only set when parallel_mode == "THREADS"
    }
expert_bundle = run_expert_panel(
    state["original_query"],
    context=panel_context,
    max_roles=max(5, 5 + len(initial_dynamic_roles)),
    dynamic_roles=initial_dynamic_roles,
    **execution_kwargs,  # ← Empty dict when parallel_mode == "SEQUENTIAL"
)
```

### Why This Causes Failures

1. Default `parallel_mode` is `"SEQUENTIAL"` (state_machine.py:788, orchestrator.py:14)
2. When `parallel_mode != "THREADS"`, `execution_kwargs` is empty dict
3. `run_expert_panel()` never receives the `model` parameter
4. Falls back to hardcoded default `model="deepseek-chat"` (expert_panel.py:46)
5. Expert agents try to call `"deepseek-chat"` model
6. Local proxy at localhost:20128 only has `"kr/claude-sonnet-4.5"`
7. API call fails with "No credentials for provider: aimlapi"
8. Expert panel returns empty contributions with `source="fallback"`
9. All experts show 0 valid, 0 invalid
10. Plan critic rejects plans lacking expert validation
11. System hits max_iters and returns empty answer (CMM score: 0.0)

### Evidence

**eval_plan_fix/summary.json:**
- cmm_wins: 2
- baseline_wins: 6
- mean_cmm_overall: 3.6
- mean_baseline_overall: 8.9
- 6 technical failures

**eval_plan_fix/cases.jsonl:**
All 6 failed cases show identical pattern:
```
V2-004: LIGHT_CMM -> FAILED
  Experts: 0 valid, 0 invalid
  Plan source: model
  Errors: ['plan_rejected_after_max_iters']
```

### Affected Functions

All functions with `model="deepseek-chat"` default that are called from state_machine:

1. **expert_panel.py:46** - `run_expert_panel(model="deepseek-chat")`
2. **expert_agent.py:109** - `run_expert(model="deepseek-chat")`
3. **plan_development.py:324** - `develop_plan(model="deepseek-chat")`
4. **agent_moderator.py:144** - `moderate_answer(model="deepseek-chat")`
5. **meta_moderator.py:312** - `run_meta_moderator(model="deepseek-chat")`
6. **conflict_analyzer.py:426** - `analyze_conflicts(model="deepseek-chat")`
7. **plan_critic.py:719** - `check_plan_and_act(model="deepseek-chat")`

All of these are called from state_machine.py and need model parameter propagated.

## Secondary Issues Found

### Issue 2: Second Expert Panel Call (line 1275)
Same bug exists at state_machine.py:1275 for second expert panel round:
```python
execution_kwargs = {}
if state.get("parallel_mode") == "THREADS":
    execution_kwargs = {
        "execution_mode": "THREADS",
        "max_workers": state.get("max_workers"),
        "model": state["model"],
    }
```

### Issue 3: No Expert Fallback
When all experts fail JSON parsing, system continues with empty expert_bundle instead of using rules-based fallback contributions. This violates user requirement: "expert failures don't cause empty answers."

Location: state_machine.py:1010-1014
```python
if contributions and len(valid_contributions) == 0 and len(fallback_contributions) >= 5:
    state["warnings"].append(
        f"expert_panel_catastrophic_json_failure: {len(fallback_contributions)}/{len(contributions)} experts failed JSON parsing"
    )
    state["expert_panel_degraded"] = True
    # ← Missing: Generate rules-based expert contributions here
```

## Verification of Diagnosis

### Test 1: Check parallel_mode default
```bash
grep -n "parallel_mode.*=.*SEQUENTIAL" Lib/state_machine.py Lib/orchestrator.py
```
Result: Confirmed default is "SEQUENTIAL"

### Test 2: Check expert_panel signature
```bash
grep -n "def run_expert_panel" Lib/expert_panel.py
```
Result: Line 38, has `model: str = "deepseek-chat"` default

### Test 3: Check state_machine calls
```bash
grep -n "run_expert_panel(" Lib/state_machine.py
```
Result: Line 991, uses `**execution_kwargs` which is empty when parallel_mode != "THREADS"

## Impact Analysis

### Current State (eval_plan_fix)
- **6 failures** out of 10 cases (60% failure rate)
- **4 failures** due to expert panel returning 0 valid experts
- **2 failures** due to other issues
- All expert failures lead to empty CMM answers (score: 0.0)

### Expected After Fix
- Expert panel will receive correct model parameter
- Experts will successfully call "kr/claude-sonnet-4.5"
- Valid expert contributions will be generated
- Plan critic will have expert validation data
- Plans will pass critique more often
- **Estimated improvement:** 4-6 fewer failures, win rate 60-80%

## Next Steps (Phase 2)

### P0 Fix 1: Model Propagation
**File:** `Lib/state_machine.py:984-996`
**Change:** Always pass model parameter, not just when parallel_mode == "THREADS"

```python
# BEFORE:
execution_kwargs = {}
if state.get("parallel_mode") == "THREADS":
    execution_kwargs = {
        "execution_mode": "THREADS",
        "max_workers": state.get("max_workers"),
        "model": state["model"],
    }

# AFTER:
execution_kwargs = {"model": state["model"]}
if state.get("parallel_mode") == "THREADS":
    execution_kwargs["execution_mode"] = "THREADS"
    execution_kwargs["max_workers"] = state.get("max_workers")
```

Apply same fix at line 1275 for second expert panel round.

### P0 Fix 2: Expert Fallback
**File:** `Lib/state_machine.py:1010-1014`
**Change:** Generate rules-based expert contributions when all experts fail

```python
if contributions and len(valid_contributions) == 0 and len(fallback_contributions) >= 5:
    state["warnings"].append(
        f"expert_panel_catastrophic_json_failure: {len(fallback_contributions)}/{len(contributions)} experts failed JSON parsing"
    )
    state["expert_panel_degraded"] = True
    # Generate rules-based fallback contributions
    expert_bundle = _generate_fallback_expert_bundle(state["original_query"], panel_context)
```

### P0 Fix 3: Plan Critic Semantics
Review quality_gates.py:171-210 `plan_blockers()` to ensure quality issues don't become critical blockers.

### P0 Fix 4: Answer Rescue
Add fallback path in state_machine when plan is rejected after max_iters but query is safe.

### P0 Fix 5: DIRECT Brevity
Already fixed in previous session (query_intake.py:307, direct_answer.py:89).

## Acceptance Criteria Check

- [ ] No empty CMM answers for safe queries
- [ ] Technical failures → 0
- [ ] mean_cmm_overall improves from 3.6
- [ ] Expert failures don't cause empty answers
- [ ] Plan critic max-iteration on non-critical issues leads to best-effort answer not FAILED

---

**Diagnosis Complete. Ready for Phase 2 P0 Fixes.**
