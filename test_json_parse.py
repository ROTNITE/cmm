import json
import re

# Test the parsing logic
raw = '''```json
{
  "answer_a_scores": {
    "rubric_coverage": 10,
    "perspective_coverage": 8,
    "overall": 9
  },
  "answer_b_scores": {
    "rubric_coverage": 10,
    "perspective_coverage": 9,
    "overall": 9
  }
}
```'''

text = raw.strip()
fence_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, flags=re.DOTALL | re.IGNORECASE)
if fence_match:
    extracted = fence_match.group(1).strip()
    print('Extracted JSON:')
    print(extracted)
    print()
    try:
        data = json.loads(extracted)
        print('Parsed successfully!')
        print(f'answer_a overall: {data["answer_a_scores"]["overall"]}')
        print(f'answer_b overall: {data["answer_b_scores"]["overall"]}')
    except Exception as e:
        print(f'Parse failed: {e}')
else:
    print('No fence match found')

# Now test with actual raw output from case
print('\n' + '='*50)
print('Testing with actual case output:')
print('='*50 + '\n')

with open(r'C:\cmm-main\eval_results\cases_incremental.jsonl', 'r', encoding='utf-8') as f:
    case = json.loads(f.readline())
    raw_output = case.get('raw_judge_output', '')

    print(f'Raw output length: {len(raw_output)}')
    print(f'First 500 chars:\n{raw_output[:500]}\n')

    # Try to parse
    from Lib.json_utils import safe_json_loads
    parsed = safe_json_loads(raw_output)

    if parsed:
        print('✓ Parsed successfully!')
        print(f'Keys: {list(parsed.keys())}')
        if 'answer_a_scores' in parsed:
            print(f'answer_a overall: {parsed["answer_a_scores"].get("overall")}')
        if 'answer_b_scores' in parsed:
            print(f'answer_b overall: {parsed["answer_b_scores"].get("overall")}')
    else:
        print('✗ Parse failed - returned None')
