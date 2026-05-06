"""Stable evaluation protocol with frozen answers and repeated judge.

Usage:
    python stable_eval.py --dataset cmm_dataset_v2.csv --limit 10 --judge-repeats 5
"""

import argparse
import json
import hashlib
from pathlib import Path


def hash_answer(answer: str) -> str:
    """Generate hash for answer to detect changes."""
    return hashlib.sha256(answer.encode('utf-8')).hexdigest()[:16]


def main():
    parser = argparse.ArgumentParser(description='Stable evaluation with frozen answers')
    parser.add_argument('--dataset', required=True, help='Path to dataset CSV')
    parser.add_argument('--limit', type=int, default=10, help='Number of cases to evaluate')
    parser.add_argument('--judge-repeats', type=int, default=5, help='Number of judge runs per case')
    parser.add_argument('--frozen-dir', default='eval_frozen', help='Directory for frozen answers')
    parser.add_argument('--output-dir', default='eval_stable', help='Output directory')

    args = parser.parse_args()

    frozen_dir = Path(args.frozen_dir)
    frozen_dir.mkdir(exist_ok=True)

    print(f"Stable evaluation protocol:")
    print(f"  Dataset: {args.dataset}")
    print(f"  Limit: {args.limit}")
    print(f"  Judge repeats: {args.judge_repeats}")
    print(f"  Frozen answers: {frozen_dir}")
    print(f"  Output: {args.output_dir}")
    print()

    # Step 1: Generate or load frozen answers
    frozen_file = frozen_dir / f"answers_{args.limit}.json"

    if frozen_file.exists():
        print(f"[LOAD] Loading frozen answers from {frozen_file}")
        with open(frozen_file, 'r', encoding='utf-8') as f:
            frozen_answers = json.load(f)
    else:
        print(f"[GENERATE] Generating frozen answers...")
        print(f"  Run: python -m cmm.eval --dataset {args.dataset} --limit {args.limit} --mode real --output-dir {frozen_dir}/generation")
        print()
        print("After generation completes, run this script again to judge.")
        return

    # Step 2: Run judge multiple times on frozen answers
    print(f"[JUDGE] Running judge {args.judge_repeats} times on frozen answers...")

    # TODO: Implement judge-only mode in cmm.eval
    print("TODO: Implement --judge-only mode in cmm.eval")
    print()
    print("Recommended changes to cmm.eval:")
    print("  1. Add --judge-only flag")
    print("  2. Add --frozen-answers path")
    print("  3. Add --judge-run-id for tracking")
    print("  4. Add --temperature 0 for judge")
    print("  5. Save judge_run_id, judge_repeats in CSV")


if __name__ == '__main__':
    main()
