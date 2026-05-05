import json
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


def _moderation_payload(decision="ACCEPT"):
    return {
        "decision": decision,
        "scores": {
            "content_novelty": 8,
            "content_groundedness": 8,
            "content_applicability": 8,
            "process_stimulates_thinking": 8,
            "process_opens_directions": 8,
            "process_supports_synthesis": 8,
            "expert_input_coverage": 8,
            "balance_issue_handling": 8,
        },
        "balance": {
            "dominant_perspective_found": False,
            "missing_perspectives": [],
        },
        "ignored_expert_risks": [],
        "ignored_expert_recommendations": [],
        "unresolved_questions": [],
        "critical_issues": [],
        "improvements": [],
    }


class JsonContractTests(unittest.TestCase):
    def test_safe_json_loads_valid_markdown_and_invalid(self):
        from Lib.json_utils import safe_json_loads

        self.assertEqual(safe_json_loads('{"ok": true}'), {"ok": True})
        self.assertEqual(safe_json_loads('```json\n{"ok": true}\n```'), {"ok": True})
        self.assertEqual(safe_json_loads('prefix {"ok": true} suffix'), {"ok": True})
        self.assertIsNone(safe_json_loads("not json"))

    def test_planner_parses_json_contract(self):
        from Lib.plan_development import develop_plan

        raw = json.dumps(
            {
                "main_idea": "Idea",
                "preparation": ["Prep"],
                "steps": [
                    {
                        "number": "1",
                        "title": "Step",
                        "substeps": ["Sub"],
                        "uses_expert_inputs": ["Risk A"],
                    }
                ],
                "nuances": ["Nuance"],
                "potential_problems": ["Problem"],
                "result": "Result",
            },
            ensure_ascii=False,
        )

        with patch("Lib.plan_development.send_to_AI", return_value=raw):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                plan = develop_plan("query", context={"expert_risks": ["Risk A"]})

        self.assertEqual(buffer.getvalue(), "")
        self.assertEqual(plan["raw_format"], "json")
        self.assertEqual(plan["main_idea"], "Idea")
        self.assertEqual(plan["steps"][0]["uses_expert_inputs"], ["Risk A"])
        self.assertEqual(plan["parse_warnings"], [])

    def test_planner_parses_markdown_wrapped_json(self):
        from Lib.plan_development import develop_plan

        raw = """```json
{
  "main_idea": "Idea",
  "preparation": [],
  "steps": [{"number": "1", "title": "Step", "substeps": [], "uses_expert_inputs": []}],
  "nuances": [],
  "potential_problems": [],
  "result": "Result"
}
```"""

        with patch("Lib.plan_development.send_to_AI", return_value=raw):
            with redirect_stdout(io.StringIO()):
                plan = develop_plan("query")

        self.assertEqual(plan["raw_format"], "json")
        self.assertEqual(plan["steps"][0]["title"], "Step")

    def test_planner_invalid_json_falls_back_clearly(self):
        from Lib.plan_development import develop_plan

        with patch("Lib.plan_development.send_to_AI", return_value="not a usable plan"):
            with redirect_stdout(io.StringIO()):
                plan = develop_plan("query")

        self.assertEqual(plan["raw_format"], "fallback")
        self.assertIn("json_and_legacy_plan_parse_failed", plan["parse_warnings"])
        self.assertTrue(plan["steps"])

    def test_moderator_parses_markdown_wrapped_json_contract(self):
        from Lib.agent_moderator import moderate_answer

        raw = "```json\n" + json.dumps(_moderation_payload(), ensure_ascii=False) + "\n```"

        with patch("Lib.agent_moderator.send_to_AI", return_value=raw):
            report = moderate_answer(
                original_query="query",
                plan={"main_idea": "Idea", "steps": []},
                answer="answer",
            )

        self.assertEqual(report["decision"], "ACCEPT")
        self.assertEqual(report["scores"]["expert_input_coverage"], 8.0)
        self.assertEqual(report["unresolved_questions"], [])
        self.assertEqual(report["parse_warnings"], [])

    def test_moderator_invalid_json_fallback_records_warning(self):
        from Lib.agent_moderator import moderate_answer

        with patch("Lib.agent_moderator.send_to_AI", return_value="not json"):
            report = moderate_answer(
                original_query="query",
                plan={"main_idea": "Idea", "steps": []},
                answer="answer",
            )

        self.assertEqual(report["decision"], "REVISE")
        self.assertIn("moderation_json_parse_failed", report["parse_warnings"])
        self.assertEqual(report["unresolved_questions"], [])


if __name__ == "__main__":
    unittest.main()
