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

    def test_call_json_model_no_retry_when_first_valid(self):
        from Lib.json_retry import call_json_model

        with patch("Lib.json_retry.send_to_AI", return_value='{"ok": true}') as mocked_send:
            result = call_json_model(
                user_prompt="return json",
                system_prompt="json only",
                model="test-model",
                temp=0.1,
                tokens=50,
            )

        self.assertEqual(result["payload"], {"ok": True})
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["warnings"], [])
        mocked_send.assert_called_once()

    def test_call_json_model_retries_invalid_then_valid(self):
        from Lib.json_retry import call_json_model

        with patch("Lib.json_retry.send_to_AI", side_effect=["not json", '{"ok": true}']):
            result = call_json_model(
                user_prompt="return json",
                system_prompt="json only",
                model="test-model",
                temp=0.1,
                tokens=50,
            )

        self.assertEqual(result["payload"], {"ok": True})
        self.assertEqual(result["attempts"], 2)
        self.assertIn("json_retry_after_invalid_json", result["warnings"])

    def test_call_json_model_returns_none_after_retry_exhausted(self):
        from Lib.json_retry import call_json_model

        with patch("Lib.json_retry.send_to_AI", return_value="not json"):
            result = call_json_model(
                user_prompt="return json",
                system_prompt="json only",
                model="test-model",
                temp=0.1,
                tokens=50,
            )

        self.assertIsNone(result["payload"])
        self.assertEqual(result["attempts"], 2)
        self.assertIn("json_retry_exhausted", result["warnings"])

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

        with patch("Lib.json_retry.send_to_AI", return_value=raw):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                plan = develop_plan("query", context={"expert_risks": ["Risk A"]})

        self.assertEqual(buffer.getvalue(), "")
        self.assertEqual(plan["raw_format"], "json")
        self.assertEqual(plan["main_idea"], "Idea")
        self.assertEqual(plan["steps"][0]["uses_expert_inputs"], ["Risk A"])
        self.assertEqual(plan["parse_warnings"], [])
        self.assertEqual(plan["json_attempts"], 1)
        self.assertEqual(plan["source"], "model")

    def test_develop_plan_passes_model_to_send_to_ai(self):
        from Lib.plan_development import develop_plan

        raw = json.dumps(
            {
                "main_idea": "Idea",
                "preparation": [],
                "steps": [{"number": "1", "title": "Step", "substeps": [], "uses_expert_inputs": []}],
                "nuances": [],
                "potential_problems": [],
                "result": "Result",
            },
            ensure_ascii=False,
        )

        with patch("Lib.json_retry.send_to_AI", return_value=raw) as mocked_send:
            develop_plan("query", model="custom-model")

        self.assertEqual(mocked_send.call_args.kwargs["model"], "custom-model")

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

        with patch("Lib.json_retry.send_to_AI", return_value=raw):
            with redirect_stdout(io.StringIO()):
                plan = develop_plan("query")

        self.assertEqual(plan["raw_format"], "json")
        self.assertEqual(plan["steps"][0]["title"], "Step")

    def test_planner_invalid_json_falls_back_clearly(self):
        from Lib.plan_development import develop_plan

        with patch("Lib.json_retry.send_to_AI", return_value="not a usable plan"):
            with redirect_stdout(io.StringIO()):
                plan = develop_plan(
                    "query",
                    context={
                        "query_intake": {"constraints": ["limited budget"], "success_criteria": ["clear metrics"]},
                        "deliberation_brief": {"must_address": ["student workload"], "expert_risks": ["overload"]},
                        "conflict_report": {"blind_spots": ["teacher adoption"]},
                    },
                )

        self.assertEqual(plan["raw_format"], "fallback")
        self.assertIn("json_and_legacy_plan_parse_failed", plan["parse_warnings"])
        self.assertEqual(plan["json_attempts"], 2)
        self.assertIn("limited budget", str(plan["steps"]))
        self.assertIn("clear metrics", str(plan["steps"]))
        self.assertTrue(plan["steps"])

    def test_planner_retries_invalid_then_valid_json(self):
        from Lib.plan_development import develop_plan

        valid = json.dumps(
            {
                "main_idea": "Retried idea",
                "preparation": [],
                "steps": [{"number": "1", "title": "Retried step", "substeps": [], "uses_expert_inputs": []}],
                "nuances": [],
                "potential_problems": [],
                "result": "Result",
            },
            ensure_ascii=False,
        )
        with patch("Lib.json_retry.send_to_AI", side_effect=["not json", valid]):
            plan = develop_plan("query")

        self.assertEqual(plan["raw_format"], "json")
        self.assertEqual(plan["json_attempts"], 2)
        self.assertIn("json_retry_after_invalid_json", plan["parse_warnings"])

    def test_moderator_parses_markdown_wrapped_json_contract(self):
        from Lib.agent_moderator import moderate_answer

        raw = "```json\n" + json.dumps(_moderation_payload(), ensure_ascii=False) + "\n```"

        with patch("Lib.json_retry.send_to_AI", return_value=raw):
            report = moderate_answer(
                original_query="query",
                plan={"main_idea": "Idea", "steps": []},
                answer="answer",
            )

        self.assertEqual(report["decision"], "ACCEPT")
        self.assertEqual(report["scores"]["expert_input_coverage"], 8.0)
        self.assertEqual(report["unresolved_questions"], [])
        self.assertEqual(report["parse_warnings"], [])
        self.assertEqual(report["json_attempts"], 1)
        self.assertEqual(report["source"], "model")

    def test_moderator_invalid_json_fallback_records_warning(self):
        from Lib.agent_moderator import moderate_answer

        with patch("Lib.json_retry.send_to_AI", return_value="not json"):
            report = moderate_answer(
                original_query="query",
                plan={"main_idea": "Idea", "steps": []},
                answer="answer",
            )

        self.assertEqual(report["decision"], "REVISE")
        self.assertIn("moderation_json_parse_failed", report["parse_warnings"])
        self.assertEqual(report["json_attempts"], 2)
        self.assertEqual(report["source"], "fallback")
        self.assertIn("Moderator JSON output could not be parsed after retry.", report["critical_issues"])
        self.assertEqual(report["unresolved_questions"], [])

    def test_moderator_retries_invalid_then_valid_json(self):
        from Lib.agent_moderator import moderate_answer

        with patch(
            "Lib.json_retry.send_to_AI",
            side_effect=["not json", json.dumps(_moderation_payload(), ensure_ascii=False)],
        ):
            report = moderate_answer(
                original_query="query",
                plan={"main_idea": "Idea", "steps": []},
                answer="answer",
            )

        self.assertEqual(report["decision"], "ACCEPT")
        self.assertEqual(report["json_attempts"], 2)
        self.assertIn("json_retry_after_invalid_json", report["parse_warnings"])

    def test_run_moderated_loop_returns_phase6_contract(self):
        from Lib.agent_moderator import run_moderated_loop

        with patch("Lib.agent_moderator.improve_plan_to_answer", return_value={"answer": "final answer"}), \
             patch("Lib.agent_moderator.moderate_answer", return_value=_moderation_payload("ACCEPT")):
            result = run_moderated_loop(
                original_query="query",
                plan={"main_idea": "Idea", "steps": []},
                critique={},
                max_iters=1,
                model="test-model",
            )

        self.assertEqual(result["final_answer"], "final answer")
        self.assertEqual(result["final_decision"], "ACCEPT")
        self.assertEqual(result["critical_issues"], [])
        self.assertEqual(result["revision_count"], 0)
        self.assertEqual(result["source"], "moderated_loop")
        self.assertIn("reports", result)

    def test_run_moderated_loop_reject_contract_clears_final_answer(self):
        from Lib.agent_moderator import run_moderated_loop

        rejected_payload = _moderation_payload("REJECT")
        rejected_payload["critical_issues"] = ["critical safety issue"]

        with patch("Lib.agent_moderator.improve_plan_to_answer", return_value={"answer": "unsafe answer"}), \
             patch("Lib.agent_moderator.moderate_answer", return_value=rejected_payload):
            result = run_moderated_loop(
                original_query="query",
                plan={"main_idea": "Idea", "steps": []},
                critique={},
                max_iters=1,
                model="test-model",
            )

        self.assertEqual(result["final_answer"], "")
        self.assertEqual(result["rejected_answer"], "unsafe answer")
        self.assertEqual(result["final_decision"], "REJECT")
        self.assertEqual(result["critical_issues"], ["critical safety issue"])
        self.assertTrue(result["rejected"])


if __name__ == "__main__":
    unittest.main()
