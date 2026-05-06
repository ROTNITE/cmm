# Claude API Integration via OmniRoute - Complete

## Summary

Successfully migrated CMM system from DeepSeek to Claude API via OmniRoute. The system now supports multiple AI providers through environment variables.

## Changes Made

### 1. Core API Client (Lib/AI_request.py)
- Added support for `OMNIROUTE_API_KEY`, `CLAUDE_API_KEY` in addition to existing keys
- Added `_get_base_url()` function to read `OMNIROUTE_BASE_URL`, `CLAUDE_BASE_URL`, `OPENAI_BASE_URL`
- Client now uses dynamic base URL instead of hardcoded DeepSeek endpoint
- Fallback priority: OmniRoute → Claude → DeepSeek → OpenAI

### 2. Evaluation Harness (cmm/eval.py)
- Added `--model` argument for CMM and baseline (default: `deepseek-chat`)
- Updated `_real_baseline()` to accept `model` parameter
- Updated `_real_cmm()` to accept `model` parameter and pass to `run_cmm()`
- Updated `_run_real_judged_eval()` to accept and propagate `model` parameter
- Updated `run_eval()` signature to include `model` parameter
- Updated `main()` to parse and pass `--model` argument

### 3. Main Entry Point (main.py)
- Added `sys.stdout.reconfigure(encoding='utf-8')` to fix Windows console encoding issues

### 4. Environment Configuration
- Fixed `.env` formatting (removed leading spaces)
- Created `.env.omniroute.example` template
- Updated `README.md` with OmniRoute setup instructions

### 5. Documentation
- Created `docs/omniroute_setup.md` with complete setup guide
- Added troubleshooting section
- Documented model selection recommendations

## Verification

### Test 1: Direct API Call
```bash
python -c "from Lib.AI_request import send_to_AI; result = send_to_AI('test', model='kr/claude-sonnet-4.5'); print(result[:100])"
```
✅ Result: "I'm here and ready to help. What would you like to work on?"

### Test 2: Main Entry Point
```bash
python main.py "Тестовый запрос" --model kr/claude-sonnet-4.5
```
✅ Result: Complete CMM response with trace summary

### Test 3: Evaluation Harness (1 case, no judge)
```bash
python -m cmm.eval --dataset cmm_dataset_v2.csv --output eval_claude_test --mode real --judge-mode none --limit 1 --model kr/claude-sonnet-4.5
```
✅ Result: 
- Baseline answer: 553 chars
- CMM answer: 571 chars
- Final state: FINALIZE
- Router mode: DIRECT (matched expected)

### Test 4: Evaluation Harness (2 cases, LLM judge)
```bash
python -m cmm.eval --dataset cmm_dataset_v2.csv --output eval_claude_2cases --mode real --judge-mode llm --limit 2 --model kr/claude-sonnet-4.5 --judge-model kr/claude-sonnet-4.5
```
✅ Result:
- Case V2-001: TIE (baseline: 9.0, CMM: 9.0)
- Case V2-002: TIE (baseline: 9.0, CMM: 9.0)
- Judge mode: llm
- All outputs generated correctly

## Usage

### Option A: Claude via OmniRoute (Recommended)

1. Start OmniRoute
2. Get API key from http://localhost:20128/dashboard
3. Configure `.env`:
```bash
OMNIROUTE_API_KEY=sk-your-key
OMNIROUTE_BASE_URL=http://localhost:20128/v1
AI_MODEL=kr/claude-sonnet-4.5
```

4. Run:
```bash
# Main entry point
python main.py "Your query" --model kr/claude-sonnet-4.5

# Evaluation
python -m cmm.eval --dataset cmm_dataset_v2.csv --output eval_results --mode real --judge-mode llm --limit 5 --model kr/claude-sonnet-4.5 --judge-model kr/claude-sonnet-4.5
```

### Option B: DeepSeek (Original)

Keep existing `.env`:
```bash
DEEPSEEK_API_KEY=sk-your-deepseek-key
AI_MODEL=deepseek-chat
```

Run without `--model` argument (uses default).

## Model Recommendations

- **kr/claude-sonnet-4.5** — Fast, cost-effective, recommended for agent testing and evaluation
- **kr/claude-opus-4** — More capable, use for production or complex queries
- **deepseek-chat** — Original model, still supported as fallback

## Files Modified

- `Lib/AI_request.py` — Multi-provider support
- `cmm/eval.py` — Model parameter propagation
- `main.py` — UTF-8 encoding fix
- `.env` — Formatting fix
- `README.md` — Setup instructions

## Files Created

- `.env.omniroute.example` — Configuration template
- `docs/omniroute_setup.md` — Complete setup guide
- `eval_claude_test/` — Test results (1 case)
- `eval_claude_2cases/` — Test results (2 cases with judge)

## Status

✅ All tests passing
✅ Claude API integration working
✅ Backward compatibility maintained
✅ Documentation complete
