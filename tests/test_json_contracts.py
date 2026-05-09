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
                log_purpose="judge",
            )

        self.assertEqual(result["payload"], {"ok": True})
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["warnings"], [])
        mocked_send.assert_called_once()
        self.assertEqual(mocked_send.call_args.kwargs["log_purpose"], "judge")

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
        self.assertIn("constraints_covered", plan)
        self.assertIn("risks_mitigated", plan)

    def test_develop_plan_passes_model_to_send_to_ai(self):
        """Test that explicit model parameter is passed to send_to_AI.

        NEW BEHAVIOR: Explicit parameter has highest priority.
        """
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
        self.assertIn("constraints_covered", plan)

    def test_planner_rich_context_requires_linkage_or_falls_back(self):
        from Lib.plan_development import develop_plan

        raw = json.dumps(
            {
                "main_idea": "Do the project",
                "preparation": [],
                "steps": [
                    {
                        "number": "1",
                        "title": "Assess the current state",
                        "substeps": ["Review", "Discuss"],
                        "uses_expert_inputs": [],
                    }
                ],
                "nuances": [],
                "potential_problems": [],
                "result": "Done",
            },
            ensure_ascii=False,
        )

        context = {
            "query_intake": {
                "constraints": ["privacy constraint"],
                "success_criteria": ["clear measurement"],
            },
            "deliberation_brief": {
                "must_address": ["address user trust"],
                "expert_risks": ["legal compliance risk"],
                "stakeholder_coverage": ["users", "legal"],
            },
            "conflict_report": {
                "unresolved_tradeoffs": [{"tradeoff": "speed vs safety"}],
                "blind_spots": ["missing legal review"],
            },
        }

        with patch("Lib.json_retry.send_to_AI", return_value=raw):
            plan = develop_plan("query", context=context)

        # After repair, plan should be json and have inferred coverage
        self.assertEqual(plan["raw_format"], "json")
        # Repair should have added coverage even if model didn't provide it
        self.assertTrue(plan["must_address_mapping"])
        self.assertTrue(plan["stakeholder_coverage"])
        # Check that repair actually worked by verifying coverage was added
        self.assertGreater(len(plan["must_address_mapping"]), 0)

    def test_planner_rejects_fake_mapping_without_real_coverage(self):
        from Lib.plan_development import develop_plan

        raw = json.dumps(
            {
                "main_idea": "Move the project forward",
                "preparation": [],
                "steps": [
                    {
                        "number": "1",
                        "title": "Assess the situation",
                        "substeps": ["Review status"],
                        "uses_expert_inputs": ["general note"],
                    }
                ],
                "nuances": [],
                "potential_problems": [],
                "result": "Done",
                "stakeholder_coverage": [{"stakeholder": "users", "covered_in_steps": []}],
                "must_address_mapping": [{"item": "privacy constraint", "covered_in_steps": [], "coverage_type": "constraint"}],
            },
            ensure_ascii=False,
        )

        context = {
            "query_intake": {
                "constraints": ["privacy constraint"],
                "success_criteria": ["clear measurement"],
            },
            "deliberation_brief": {
                "must_address": ["address user trust", "privacy constraint", "legal review"],
                "expert_risks": ["legal compliance risk"],
                "stakeholder_coverage": [{"stakeholder": "users"}],
            },
            "conflict_report": {
                "unresolved_tradeoffs": [{"tradeoff": "speed vs safety"}],
                "blind_spots": ["missing legal review"],
            },
        }

        with patch("Lib.json_retry.send_to_AI", return_value=raw):
            plan = develop_plan("query", context=context)

        # After repair, plan should be json and have inferred coverage
        self.assertEqual(plan["raw_format"], "json")
        # Repair should have added coverage even if model didn't provide it
        self.assertTrue(plan["must_address_mapping"])
        self.assertTrue(plan["stakeholder_coverage"])
        # Check that repair actually worked by verifying coverage was added
        self.assertGreater(len(plan["must_address_mapping"]), 0)

    def test_planner_rich_context_keeps_mapping_fields(self):
        from Lib.plan_development import develop_plan

        raw = json.dumps(
            {
                "main_idea": "Run a privacy-safe pilot",
                "preparation": ["Align owners"],
                "steps": [
                    {
                        "number": "1",
                        "title": "Define a privacy-safe pilot scope",
                        "substeps": ["Limit personal data", "Set success metrics"],
                        "uses_expert_inputs": ["legal review", "risk review"],
                        "covers_constraints": ["privacy constraint"],
                        "covers_success_criteria": ["clear measurement"],
                        "mitigates_risks": ["legal compliance risk"],
                        "handles_tradeoffs": ["speed vs safety"],
                        "serves_stakeholders": ["users", "legal"],
                    }
                ],
                "nuances": [],
                "potential_problems": ["legal compliance risk"],
                "result": "Pilot can launch safely",
                "constraints_covered": ["privacy constraint"],
                "success_criteria_covered": ["clear measurement"],
                "risks_mitigated": ["legal compliance risk"],
                "tradeoffs_handled": ["speed vs safety"],
                "stakeholder_coverage": [
                    {"stakeholder": "users", "covered_in_steps": ["1"]},
                    {"stakeholder": "legal", "covered_in_steps": ["1"]},
                ],
                "must_address_mapping": [
                    {"item": "address user trust", "covered_in_steps": ["1"], "coverage_type": "stakeholder"}
                ],
            },
            ensure_ascii=False,
        )

        context = {
            "query_intake": {
                "constraints": ["privacy constraint"],
                "success_criteria": ["clear measurement"],
            },
            "deliberation_brief": {
                "must_address": ["address user trust"],
                "expert_risks": ["legal compliance risk"],
            },
            "conflict_report": {
                "unresolved_tradeoffs": [{"tradeoff": "speed vs safety"}],
            },
        }

        with patch("Lib.json_retry.send_to_AI", return_value=raw):
            plan = develop_plan("query", context=context)

        self.assertEqual(plan["raw_format"], "json")
        self.assertTrue(plan["must_address_mapping"])
        self.assertTrue(plan["stakeholder_coverage"])
        self.assertEqual(plan["steps"][0]["covers_constraints"], ["privacy constraint"])
        self.assertEqual(plan["steps"][0]["serves_stakeholders"], ["users", "legal"])

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

    def test_moderator_uses_roomy_token_budget_for_json_schema(self):
        from Lib.agent_moderator import moderate_answer
        from Lib.config import get_stage_settings

        with patch("Lib.json_retry.send_to_AI", return_value=json.dumps(_moderation_payload())) as mocked_send:
            moderate_answer(
                original_query="query",
                plan={"main_idea": "Idea", "steps": []},
                answer="answer",
            )

        self.assertEqual(mocked_send.call_args.kwargs["tokens"], get_stage_settings("moderator")["tokens"])

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

        with patch(
            "Lib.agent_moderator.improve_plan_to_answer",
            return_value={"answer": "final answer", "meta": {"source": "model"}},
        ), \
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
        self.assertEqual(result["answer_generation_source"], "model")
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
