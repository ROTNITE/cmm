# Real Eval 20 Report

Status: prepared template. Human blind judging is pending until `eval_real_20/human_review.csv` is filled or an LLM judge run is completed.

## Dataset Description

- Dataset: `cmm_dataset_v2.csv`.
- Size: 20 cases.
- Expected modes: 3 `DIRECT`, 5 `LIGHT_CMM`, 12 `FULL_CMM`.
- Coverage: simple factual/explanation, medium planning/comparison/product choices, complex education/product/governance/high-risk policy, multi-stakeholder and conflict-heavy cases.

## Method

Planned first run:

```powershell
python -m cmm.eval --dataset cmm_dataset_v2.csv --limit 20 --mode real --judge-mode none --output-dir eval_real_20
python tools/analyze_eval_routing.py --input eval_real_20/results.csv --output eval_real_20/routing_analysis.csv
```

This produces baseline and CMM answers, blind Answer A/B packets, routing diagnostics, and technical trace diagnostics. It does not declare a quality winner until human review or `--judge-mode llm` is run.

## Blind Judging

- Human review file: `eval_real_20/human_review.csv`.
- Review fields: `manual_winner`, `review_notes`, `price_justified`, `lost_constraints`, `too_many_agents`, `too_long`.
- CMM wins/losses are pending.

## Results By Mode

Pending real run. Fill from `summary.json`:

- DIRECT cases:
- LIGHT_CMM cases:
- FULL_CMM cases:
- Technical failures by mode:
- Average CMM answer length:
- Average estimated cost score:

## CMM Wins

Pending human or LLM judging. Record only cases where the CMM answer is materially better on rubric coverage, perspective coverage, risk handling, actionability, or clarity.

## CMM Losses

Pending human or LLM judging. Record baseline wins separately from technical failures and router errors.

## Router Errors

Use `eval_real_20/routing_analysis.csv`:

- Expected vs actual mode mismatches:
- Over-routing to FULL_CMM:
- Under-routing to DIRECT/LIGHT_CMM:

## Dynamic Roles Impact

Inspect traces for whether dynamic roles were generated, executed, and actually useful. Do not count generated-but-not-executed roles as impact.

## Plan Critic Issues

Record cases where plan critique caused excessive replan, best-effort finalization, or missed obvious blockers.

## Next Fixes

- Calibrate router thresholds from observed mismatches.
- Review JSON health diagnostics for recurring fallback-heavy stages.
- Compare 5-10 human judgements against the optional LLM judge before trusting judge-mode results.
