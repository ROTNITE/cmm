# Context Compression Eval Report
**Date**: 2026-05-06 03:06 UTC  
**Commit**: Context compression implementation  
**Dataset**: cmm_dataset_v1.csv (1 case)  
**Mode**: real, judge-mode: none

## Executive Summary

✅ **Context compression SUCCESS**: Reduced planner context from 29,214 chars to 17,067 chars (-41%)  
✅ **Expert JSON reliability**: 9/9 experts valid (100%)  
❌ **Plan quality FAILURE**: All 3 plans rejected, 0 chars final answer  

**Root cause**: Planner generates generic plans that ignore rich deliberation context (20 must_address items, 3 dynamic roles, unresolved tradeoffs).

---

## Key Metrics

| Metric | Value | Status |
|--------|-------|--------|
| Expert valid contributions | 9/9 | ✅ |
| Expert fallback | 0 | ✅ |
| Planner context chars | 17,067 | ✅ (-41%) |
| Plan 1 format | json | ✅ |
| Plan 2 format | fallback | ❌ |
| Plan 3 format | fallback | ❌ |
| Plan critique 1 | needs_revision | ⚠️ |
| Plan critique 2 | rejected | ❌ |
| Plan critique 3 | rejected | ❌ |
| CMM final state | FAILED | ❌ |
| Answer chars | 0 | ❌ |

---

## Context Compression Results

### Before (JSON hardening fix)
- **Planner context**: 29,214 chars
- **Problem**: Context overload causing planner JSON failures

### After (Context compression)
- **Meta context**: 20,764 chars
- **Planner context**: 17,067 chars (-41%)
- **Critic context**: 23,856 chars
- **Answer context**: 0 chars (never reached)

**Compression strategy**:
- Reduced `deliberation_brief` from 26 fields to 15 fields
- Tightened limits: expert_recommendations 10→5, expert_risks 10→5, must_address 14→8
- Reduced conflict_report item limits: agreements 5→3, disagreements 6→3, tradeoffs 6→3
- Added `unresolved_tradeoffs` to brief (was missing, caused test failure)
- Added `parse_warnings` and `source` to conflict_report (backward compatibility)

**Result**: Context compression achieved target, but exposed deeper planner quality issue.

---

## Plan Generation Analysis

### Plan 1 (JSON, needs_revision)
**Source**: model  
**Format**: json  
**JSON attempts**: 2 (1 retry)  
**Steps**: 4  

**Content**:
```
Main idea: Повысить вовлеченность студентов в гибридном формате через микро-геймификацию, 
           шаблоны обратной связи и пилотирование

Steps:
1. Внедрение микро-геймификации в пилотном курсе (4 substeps)
2. Создание шаблонов для быстрой обратной связи (3 substeps)
3. Запуск пилотного проекта и сбор данных (3 substeps)
4. Масштабирование успешных практик (3 substeps)
```

**Critique 1 (fallback due to model JSON failure)**:
- Source: rules (fallback)
- Overall score: 6.25
- Critical issues: 0
- Parse warnings: `plan_critic_model_failed: plan_critic_model_invalid_json`
- Decision: REVISE
- Reason: "Plan needs revision to address CMM context gaps."

**Generic feedback** (not specific to this plan):
- Cover deliberation_brief.must_address items
- Add mitigation for ignored expert risks
- Resolve or frame unresolved trade-offs with a decision rule
- Address blind spots before answer generation
- Incorporate concerns from selected dynamic roles

**Problem**: Critic model failed JSON, fell back to rule-based critique with generic feedback.

---

### Plan 2 (fallback, rejected)
**Source**: fallback  
**Format**: fallback  
**JSON attempts**: 2  
**Steps**: 5 (generated from fallback logic)  

**Critique 2 (model)**:
- Source: model
- Overall score: 4.5 / 10
- Critical issues: 3

**Critical issues**:
1. "Plan fails to address multiple must_address items from deliberation brief, including key constraints and blind spots."
2. "Unresolved tradeoff between implementation speed and risk control is not handled."
3. "Dynamic role ethics_reviewer is ignored despite being selected."

**Scores**:
- query_alignment: 7.0
- constraint_coverage: 5.0
- success_criteria_coverage: 6.0
- expert_input_coverage: 5.0
- risk_coverage: 6.0
- **conflict_resolution: 2.0** ⚠️
- **dynamic_role_coverage: 4.0** ⚠️
- **deliberation_revision_coverage: 3.0** ⚠️
- actionability: 6.0
- clarity: 7.0

**Decision**: REJECT (score 4.5 < 7.0 threshold, 3 critical issues)  
**Reason**: "Plan has critical unresolved issues."

---

### Plan 3 (fallback, rejected)
Same pattern as Plan 2: fallback plan, model critique found critical issues, REJECT.

---

## Root Cause Analysis

### Why plans failed

**Planner receives rich context**:
- 20 must_address items (risks, constraints, blind spots)
- 10 expert_risks
- 1 unresolved_tradeoff
- 1 blind_spot
- 3 dynamic roles executed (domain_expert_education, ethics_reviewer, cost_optimizer)

**But planner generates**:
- Generic 4-step plan
- No explicit reference to must_address items
- No mention of ethics_reviewer concerns
- No tradeoff resolution strategy
- No blind spot mitigation

**Why?**
1. **Planner prompt doesn't emphasize must_address**: System prompt says "create plan", but doesn't say "CRITICAL: address all must_address items"
2. **Planner token budget too low**: 1000 tokens for detailed plan with 20 must_address items = ~50 tokens per item = impossible
3. **Planner doesn't use substeps effectively**: Could map must_address → substeps, but doesn't
4. **Fallback plan logic is too simple**: Just concatenates first 5-8 items, no structure

### Why critic failed on Plan 1

**Critic model JSON failure**:
- Parse warning: `plan_critic_model_failed: plan_critic_model_invalid_json`
- Fell back to rule-based critique
- Rule-based critique gave score 6.25, generic feedback, REVISE decision
- But feedback was not actionable (no specific blockers)

**Why critic model failed**:
- Critic context: 23,856 chars (still large)
- Critic tokens: 850 (may be insufficient for 23KB context + detailed critique)
- Critic temp: 0.2 (good)
- DeepSeek JSON reliability issue (same as before hardening)

---

## Comparison with Previous Eval

### First eval (JSON hardening, before context compression)
- Expert valid: 11/11 ✅
- Planner context: 29,214 chars ❌
- Planner format: fallback ❌
- Plan critique: 3x needs_revision/rejected ❌
- Final state: FAILED ❌

### Second eval (context compression)
- Expert valid: 9/9 ✅
- Planner context: 17,067 chars ✅ (-41%)
- Planner format: json (plan 1), fallback (plans 2-3) ⚠️
- Plan critique: needs_revision, 2x rejected ❌
- Final state: FAILED ❌

**Progress**: Context compression worked, but revealed planner quality issue.

---

## Recommended Fixes

### Priority 1: Planner prompt and token budget

**Problem**: Planner doesn't emphasize must_address items, insufficient tokens.

**Fix in Lib/plan_development.py**:
```python
settings = {
    "quick": {"tokens": 800, "temp": 0.3},       # Was 500
    "detailed": {"tokens": 1500, "temp": 0.3},   # Was 1000
    "comprehensive": {"tokens": 2000, "temp": 0.4}  # Was 1400
}

system_prompt = """Ты планировщик. Создай план ответа.

CRITICAL REQUIREMENTS:
1. Address ALL items from deliberation_brief.must_address
2. Incorporate insights from ALL dynamic roles (if present)
3. Resolve or explicitly frame unresolved_tradeoffs
4. Mitigate blind_spots from conflict_report
5. Map must_address items to specific substeps

Original query is authoritative. Cleaned/formalized query is helper text only.

Return ONLY valid JSON. No markdown blocks. No comments. No extra text.
Close all brackets and braces properly.

Schema:
{
  "main_idea": "string",
  "preparation": ["string"],
  "steps": [
    {
      "number": "1",
      "title": "string",
      "substeps": ["string"],  // Map must_address items here
      "uses_expert_inputs": ["string"]  // Reference specific expert/dynamic role
    }
  ],
  "nuances": ["string"],
  "potential_problems": ["string"],
  "result": "string"
}
"""
```

**Rationale**:
- Explicit CRITICAL markers force model attention
- Increased tokens (1000→1500 for detailed) allow richer plans
- Guidance on mapping must_address → substeps

---

### Priority 2: Critic token budget

**Problem**: Critic model JSON failure at 850 tokens with 23KB context.

**Fix in Lib/plan_critic.py, line 678**:
```python
result = call_json_model(
    user_prompt="Evaluate this CMM plan and return strict JSON only:\n" + json.dumps(packet, ensure_ascii=False),
    system_prompt=system_prompt,
    temp=0.2,
    tokens=1200,  # Was 850
    model=model,
    max_retries=1,
)
```

**Rationale**: 23KB context + detailed critique schema needs more output budget.

---

### Priority 3: Fallback plan quality

**Problem**: Fallback plan just concatenates items, no structure.

**Fix**: Enhance `_fallback_steps()` in `Lib/plan_development.py` to:
1. Group must_address by theme (risks, constraints, blind spots)
2. Create dedicated steps for each group
3. Map dynamic roles to uses_expert_inputs

---

## Next Steps

### Immediate (before next eval)

1. **Increase planner tokens**: 1000 → 1500 for detailed
2. **Add CRITICAL markers to planner prompt**: emphasize must_address
3. **Increase critic tokens**: 850 → 1200
4. **Run single-case eval**: 
   ```bash
   python -m cmm.eval --dataset cmm_dataset_v1.csv --limit 1 --mode real --judge-mode none --output-dir eval_real_planner_fix
   ```

**Success criteria**:
- Plan 1 format: json ✅
- Plan 1 critique: ready or needs_revision (not rejected)
- Plan 1 score: ≥7.0
- Critic source: model (not fallback)
- CMM final state: FINALIZE
- Answer chars: >0

---

### If still failing

**Diagnostic**:
1. Check planner raw output for must_address coverage
2. Check critic raw output for JSON structure
3. Check if critic context still too large (>20KB)

**Additional fixes**:
- Lower planner temp to 0.2 (from 0.3)
- Add example valid plan to planner prompt
- Switch to structured output API (if available for DeepSeek)
- Consider alternative model for planner (e.g., GPT-4 for planning, DeepSeek for experts)

---

### After successful single-case

1. **Run 5-case eval**: 
   ```bash
   python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 5 --mode real --judge-mode none --output-dir eval_real_planner_5
   ```
2. **Analyze routing**: 
   ```bash
   python tools/analyze_eval_routing.py --input eval_real_planner_5/results.csv
   ```
3. **Calibrate router thresholds** if needed
4. **Create commit**: "Fix planner quality: increase tokens, add CRITICAL markers, enhance fallback"

---

## Lessons Learned

1. **Context compression is necessary but not sufficient**: Reducing context from 29KB to 17KB fixed one problem but exposed another.

2. **Generic feedback is useless**: Critic saying "cover must_address items" without listing which ones doesn't help planner improve.

3. **Token budget matters**: 1000 tokens for a plan with 20 must_address items is too tight.

4. **Fallback quality matters**: When model fails, fallback should be good enough to pass basic critique, not just "something".

5. **Observability is critical**: Without detailed trace (plan content, critique scores, critical_issues), would have blamed context compression instead of planner quality.

---

## Appendix: Test Results

All 218 tests pass after context compression changes:
- ✅ test_build_compact_planner_context_preserves_legacy_keys
- ✅ test_planner_context_contains_conflict_report
- ✅ test_expert_invalid_json_after_retry_returns_diagnostic_fallback

**Backward compatibility**: Maintained all required fields in planner context while reducing size.

---

## Appendix: Context Compression Implementation

**Files changed**:
- `Lib/context_manager.py`: Added `_brief_summary_for_planner()`, updated `build_compact_planner_context()`
- `tests/test_context_manager.py`: Updated to expect new field limits

**Key changes**:
```python
def _brief_summary_for_planner(state: dict) -> dict:
    """Ultra-compact brief for planner to avoid context overload."""
    return {
        "summary": _clip_string(brief.get("summary"), 400),  # Was 1000
        "expert_recommendations": _string_list(..., max_items=5),  # Was 10
        "expert_risks": _string_list(..., max_items=5),  # Was 10
        "must_address": _string_list(..., max_items=8),  # Was 14
        "unresolved_tradeoffs": _dict_list(..., max_items=3),  # Added
        # ... 15 fields total, down from 26
    }
```

**Result**: 17KB planner context, all tests pass, backward compatible.
