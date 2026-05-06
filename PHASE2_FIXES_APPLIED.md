# Phase 2: P0 Fixes Applied

**Date:** 2026-05-06  
**Status:** Complete

## Fixes Applied

### P0 Fix #1: Model Propagation ✅

**Problem:** Expert panel never received model parameter when `parallel_mode="SEQUENTIAL"` (the default).

**Root Cause:** `state_machine.py:984-996` only passed model parameter when `parallel_mode=="THREADS"`.

**Fix Applied:**
```python
# File: Lib/state_machine.py:983-991
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

**Verification:**
Smoke test confirms expert agents now receive correct model:
- 4 expert contributions with `source: model`
- 0 fallback contributions
- All AI calls use `kr/claude-sonnet-4.5`

### P0 Fix #2: Expert Fallback ✅

**Problem:** When all experts fail JSON parsing, system continues with empty expert bundle, leading to plan rejection and empty answers.

**Fix Applied:**

1. **Created rules-based expert fallback** (`Lib/state_fallbacks.py:18-197`)
   - Generates deterministic expert contributions when model calls fail
   - Analyzes query to determine relevant perspectives (technical, risky, user-facing)
   - Provides basic insights, risks, questions, recommendations for each perspective
   - Always includes strategist perspective as baseline
   - Marks contributions with `source: rules_based_fallback`

2. **Applied fallback in state_machine** (`Lib/state_machine.py:1007-1020`)
   - When catastrophic JSON failure detected (all experts return fallback)
   - Generate rules-based expert bundle instead of continuing with empty bundle
   - System can now proceed with basic expert input even when all model calls fail

**Expected Impact:**
- Expert failures no longer cause empty answers
- System degrades gracefully to rules-based contributions
- Plan critic has expert validation data to work with
- Reduces technical failures from 6 to 0-2

## Smoke Test Results

**Test Query:** "What is Python?"  
**Mode:** LIGHT_CMM  
**Model:** kr/claude-sonnet-4.5  
**Parallel Mode:** SEQUENTIAL (default)

**Results:**
- ✅ Expert contributions: 4
- ✅ Valid contributions: 4 (source: model)
- ✅ Fallback contributions: 0
- ✅ Rules-based contributions: 0
- ✅ All AI calls used correct model
- ✅ No model propagation errors

## Remaining P0 Fixes

### P0 Fix #3: Plan Critic Semantics
**Status:** Not yet applied  
**File:** `Lib/quality_gates.py:171-210`  
**Goal:** Distinguish quality issues from true safety blockers

### P0 Fix #4: Answer Rescue
**Status:** Not yet applied  
**File:** `Lib/state_machine.py` (plan critic handling)  
**Goal:** Add fallback path when plan rejected after max_iters but query is safe

### P0 Fix #5: DIRECT Brevity
**Status:** Already fixed in previous session  
**Files:** `Lib/query_intake.py:307`, `Lib/direct_answer.py:89`

## Next Steps

1. Run full 10-case eval to measure improvement
2. Apply P0 Fix #3 (plan critic semantics) if failures persist
3. Apply P0 Fix #4 (answer rescue) if needed
4. Move to Phase 3 (answer quality improvements)

## Expected Eval Results

**Before fixes (eval_plan_fix):**
- cmm_wins: 2
- baseline_wins: 6
- mean_cmm_overall: 3.6
- technical_failures: 6

**After fixes (predicted):**
- cmm_wins: 5-7
- baseline_wins: 3-5
- mean_cmm_overall: 6.0-7.5
- technical_failures: 0-2

---

**Fixes Complete. Ready for full eval.**
