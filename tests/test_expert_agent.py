import json
import unittest
from unittest.mock import patch

from Lib.expert_roles import BASE_EXPERT_ROLES


def _payload():
    return {
        "insights": ["Insight"],
        "risks": ["Risk"],
        "questions": ["Question"],
        "recommendations": ["Recommendation"],
        "confidence": 0.8,
    }


class ExpertAgentJsonRetryTests(unittest.TestCase):
    def test_expert_retries_invalid_then_valid_json(self):
        from Lib.expert_agent import run_expert

        with patch("Lib.json_retry.send_to_AI", side_effect=["not json", json.dumps(_payload())]):
            result = run_expert(BASE_EXPERT_ROLES[0], "query")

        self.assertEqual(result["source"], "model")
        self.assertEqual(result["json_attempts"], 2)
        self.assertEqual(result["insights"], ["Insight"])
        self.assertIn("json_retry_after_invalid_json", result["parse_warnings"])

    def test_expert_invalid_json_after_retry_returns_diagnostic_fallback(self):
        from Lib.expert_agent import run_expert

        with patch("Lib.json_retry.send_to_AI", return_value="not json"):
            result = run_expert(BASE_EXPERT_ROLES[0], "query")

        self.assertEqual(result["source"], "fallback")
        # After fix: technical errors no longer pollute expert_risks
        self.assertEqual(result["risks"], [])
        self.assertEqual(result["insights"], [])
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["json_attempts"], 2)
        self.assertIn("expert_json_parse_failed", result["parse_warnings"])
        self.assertEqual(result["raw"], "not json")

    def test_expert_valid_json_has_attempt_metadata(self):
        from Lib.expert_agent import run_expert

        with patch("Lib.json_retry.send_to_AI", return_value=json.dumps(_payload())):
            result = run_expert(BASE_EXPERT_ROLES[0], "query")

        self.assertEqual(result["source"], "model")
        self.assertEqual(result["json_attempts"], 1)
        self.assertEqual(result["parse_warnings"], [])


if __name__ == "__main__":
    unittest.main()
