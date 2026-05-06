#!/bin/bash
# Quick test script for eval logging

echo "Testing eval logging system..."
echo ""
echo "This will run 2 test cases with full logging enabled."
echo "You will see:"
echo "  - Each case start/end"
echo "  - All AI calls with token counts"
echo "  - Agent activities"
echo "  - Final summary with total tokens and cost"
echo ""
echo "Press Ctrl+C to cancel, or wait 3 seconds to continue..."
sleep 3

python test_eval_logging.py
