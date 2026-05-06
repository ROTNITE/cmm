import json
import unittest
from unittest.mock import patch


def _sample_expert_bundle():
    return {
        "roles": [{"key": "risk_manager", "name": "Risk Manager", "perspective_tag": "risk"}],
        "contributions": [
            {
                "role_key": "risk_manager",
                "perspective_tag": "risk",
                "insights": ["Insight"],
                "risks": ["Risk A"],
                "questions": ["Question A"],
                "recommendations": ["Recommendation A"],
                "confidence": 0.8,
            }
        ],
        "synthesis": {
            "recommendations": ["Recommendation A"],
            "risks": ["Risk A"],
            "questions": ["Question A"],
            "perspective_counts": {"risk": 1},
        },
    }


def _sample_balance_report():
    return {
        "dominant_perspective_found": True,
        "dominant_perspective": "risk",
        "missing_perspectives": ["user"],
        "notes": ["Missing user perspective."],
    }


class DeliberationFlowTests(unittest.TestCase):
    def test_build_deliberation_brief_extracts_expert_content(self):
        from Lib.deliberation import build_deliberation_brief

        brief = build_deliberation_brief(
            "query",
            _sample_expert_bundle(),
            _sample_balance_report(),
        )

        self.assertEqual(brief["expert_recommendations"], ["Recommendation A"])
        self.assertEqual(brief["expert_risks"], ["Risk A"])
        self.assertEqual(brief["expert_questions"], ["Question A"])
        self.assertEqual(brief["missing_perspectives"], ["user"])
        self.assertTrue(brief["dominant_perspective_found"])
        self.assertIn("Risk A", brief["must_address"])

    def test_improver_prompt_includes_expert_brief(self):
        from Lib.agent_improver import improve_plan_to_answer
        from Lib.deliberation import build_deliberation_brief

        captured = {}

        def fake_send_to_ai(**kwargs):
            captured["user_prompt"] = kwargs["user_prompt"]
            return "final answer"

        brief = build_deliberation_brief(
            "query",
            _sample_expert_bundle(),
            _sample_balance_report(),
        )

        with patch("Lib.agent_improver.send_to_AI", side_effect=fake_send_to_ai):
            result = improve_plan_to_answer(
                original_query="query",
                plan={"main_idea": "idea", "steps": []},
                deliberation_brief=brief,
            )

        self.assertEqual(result["answer"], "final answer")
        self.assertIn("Recommendation A", captured["user_prompt"])
        self.assertIn("Risk A", captured["user_prompt"])
        self.assertIn("ОБЯЗАТЕЛЬНО УЧЕСТЬ", captured["user_prompt"])
        self.assertTrue(result["meta"]["deliberation_brief_used"])

    def test_improver_model_error_uses_plan_fallback(self):
        from Lib.agent_improver import improve_plan_to_answer

        plan = {
            "main_idea": "Explain the concept",
            "steps": [{"number": "1", "title": "Give a short definition", "substeps": []}],
            "potential_problems": ["Avoid overclaiming"],
        }
        with patch("Lib.agent_improver.send_to_AI", return_value="Error: missing key"):
            result = improve_plan_to_answer("query", plan)

        self.assertNotIn("Error:", result["answer"])
        self.assertIn("fallback", result["answer"])
        self.assertIn("Explain the concept", result["answer"])
        self.assertEqual(result["meta"]["source"], "fallback")

    def test_improver_empty_response_uses_plan_fallback(self):
        from Lib.agent_improver import improve_plan_to_answer

        with patch("Lib.agent_improver.send_to_AI", return_value=""):
            result = improve_plan_to_answer(
                "query",
                {"main_idea": "Fallback idea", "steps": [{"title": "Step A"}]},
            )

        self.assertTrue(result["answer"].strip())
        self.assertIn("Fallback idea", result["answer"])
        self.assertEqual(result["meta"]["source"], "fallback")

    def test_improver_valid_response_passes_through(self):
        from Lib.agent_improver import improve_plan_to_answer

        with patch("Lib.agent_improver.send_to_AI", return_value=" valid answer "):
            result = improve_plan_to_answer("query", {"steps": []})

        self.assertEqual(result["answer"], "valid answer")
        self.assertEqual(result["meta"]["source"], "model")

    def test_moderator_prompt_includes_balance_and_expert_checks(self):
        from Lib.agent_moderator import moderate_answer
        from Lib.deliberation import build_deliberation_brief

        captured = {}

        def fake_send_to_ai(**kwargs):
            captured["user_prompt"] = kwargs["user_prompt"]
            return json.dumps(
                {
                    "decision": "ACCEPT",
                    "scores": {
                        "content_novelty": 8,
                        "content_groundedness": 8,
                        "content_applicability": 8,
                        "process_stimulates_thinking": 8,
                        "process_opens_directions": 8,
                        "process_supports_synthesis": 8,
                    },
                    "balance": {
                        "dominant_perspective_found": False,
                        "missing_perspectives": [],
                    },
                    "critical_issues": [],
                    "improvements": [],
                    "ignored_expert_risks": [],
                    "ignored_expert_recommendations": [],
                    "unresolved_balance_issues": [],
                },
                ensure_ascii=False,
            )

        brief = build_deliberation_brief(
            "query",
            _sample_expert_bundle(),
            _sample_balance_report(),
        )

        with patch("Lib.json_retry.send_to_AI", side_effect=fake_send_to_ai):
            report = moderate_answer(
                original_query="query",
                plan={"main_idea": "idea", "steps": []},
                answer="answer",
                balance_report=_sample_balance_report(),
                deliberation_brief=brief,
            )

        self.assertEqual(report["decision"], "ACCEPT")
        self.assertIn("Risk A", captured["user_prompt"])
        self.assertIn("Recommendation A", captured["user_prompt"])
        self.assertIn("НЕДОСТАЮЩИЕ ПЕРСПЕКТИВЫ: user", captured["user_prompt"])
        self.assertTrue(report["meta"]["balance_report_used"])

    def test_run_moderated_loop_returns_trace_without_api_calls(self):
        from Lib.agent_moderator import run_moderated_loop
        from Lib.deliberation import build_deliberation_brief

        brief = build_deliberation_brief(
            "query",
            _sample_expert_bundle(),
            _sample_balance_report(),
        )

        with patch(
            "Lib.agent_moderator.improve_plan_to_answer",
            return_value={"answer": "answer"},
        ), patch(
            "Lib.agent_moderator.moderate_answer",
            return_value={"decision": "ACCEPT", "improvements": []},
        ):
            result = run_moderated_loop(
                original_query="query",
                plan={"main_idea": "idea", "steps": []},
                critique={"recommendations": []},
                expert_bundle=_sample_expert_bundle(),
                balance_report=_sample_balance_report(),
                deliberation_brief=brief,
            )

        self.assertEqual(result["final_answer"], "answer")
        self.assertTrue(result["trace"]["expert_bundle_used"])
        self.assertTrue(result["trace"]["balance_report_used"])
        self.assertEqual(result["trace"]["deliberation_brief"], brief)

    def test_run_moderated_loop_marks_rejected_answer(self):
        from Lib.agent_moderator import run_moderated_loop

        with patch(
            "Lib.agent_moderator.improve_plan_to_answer",
            return_value={"answer": "unsafe answer"},
        ), patch(
            "Lib.agent_moderator.moderate_answer",
            return_value={"decision": "REJECT", "critical_issues": ["unsafe"], "improvements": []},
        ):
            result = run_moderated_loop(
                original_query="query",
                plan={"main_idea": "idea", "steps": []},
            )

        self.assertEqual(result["final_answer"], "")
        self.assertEqual(result["rejected_answer"], "unsafe answer")
        self.assertEqual(result["final_decision"], "REJECT")
        self.assertTrue(result["rejected"])
        self.assertEqual(result["critical_issues"], ["unsafe"])


if __name__ == "__main__":
    unittest.main()
