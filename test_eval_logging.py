"""Test script for eval logging functionality."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from cmm.eval import run_eval


def main():
    """Run a small eval with logging enabled."""
    # Use a small dataset for testing
    dataset_path = "eval_intake_fix_final/dataset.csv"

    if not Path(dataset_path).exists():
        print(f"Dataset not found: {dataset_path}")
        print("Please provide a valid dataset path.")
        return 1

    print("Running eval with interactive logging...")
    print("=" * 80)
    print()

    result = run_eval(
        dataset_path=dataset_path,
        limit=2,  # Just 2 cases for testing
        mode="real",
        judge_mode="llm",
        judge_model="deepseek-chat",
        model="deepseek-chat",
        output_dir="eval_logging_test",
    )

    print()
    print("=" * 80)
    print("Eval complete!")
    print(f"Results saved to: {result['summary']['output_paths']['csv']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
