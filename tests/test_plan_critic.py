import json
import unittest
from unittest.mock import patch


def _plan(text="Address privacy constraint, risk mitigation, tradeoff decision, legal compliance, measurement metrics"):
    return {
        "main_idea": text,
        "steps": [
            {
                "number": "1",
                "title": text,
                "substeps": ["Cover privacy constraint", "Mitigate risk", "Define measurement metrics"],
            }
        ],
        "nuances": ["Balance speed with safety tradeoff"],
        "potential_problems": ["Legal compliance risk"],
        "result": "Actionable plan",
    }


def _generic_plan(text="Do a generic pilot"):
    return {
        "main_idea": text,
        "steps": [{"number": "1", "title": text, "substeps": ["Prepare", "Execute", "Report"]}],
        "nuances": [],
        "potential_problems": [],
        "result": "Done",
    }


def _context():
    return {
        "query_intake": {
            "original_query": "Build a privacy-safe pilot",
            "cleaned_query": "Build a privacy-safe pilot",
            "task_goal": "Build a privacy-safe pilot",
            "constraints": ["privacy constraint"],
            "success_criteria": ["measurement metrics"],
            "unknowns": [],
            "user_preferences": [],
            "risk_level": "high",
            "complexity": "complex",
        },
        "deliberation_brief": {
            "must_address": ["risk mitigation"],
            "expert_recommendations": ["measurement metrics"],
            "expert_risks": ["legal compliance risk"],
        },
        "conflict_report": {
            "unresolved_tradeoffs": [
                {"tradeoff": "speed vs safety", "why_it_matters": "Pilot rollout risk", "roles_involved": ["risk_manager"]}
            ],
            "blind_spots": ["privacy blind spot"],
            "premature_consensus_risks": [],
        },
        "dynamic_roles_used": [{"key": "legal_reviewer", "perspective_tag": "legal"}],
        "deliberation_revisions": [
            {"role_key": "risk_manager", "revised_recommendations": ["risk mitigation"], "new_risks": []}
        ],
    }


def _valid_payload():
    return {
        "scores": {
            "query_alignment": 0.9,
            "constraint_coverage": 0.8,
            "success_criteria_coverage": 8,
            "expert_input_coverage": 8,
            "risk_coverage": 8,
            "conflict_resolution": 8,
            "dynamic_role_coverage": 8,
            "deliberation_revision_coverage": 8,
            "actionability": 8,
            "clarity": 8,
        },
        "missing_constraints": [],
        "ignored_success_criteria": [],
        "ignored_expert_risks": [],
        "ignored_expert_recommendations": [],
        "unresolved_tradeoffs": [],
        "ignored_blind_spots": [],
        "ignored_dynamic_roles": [],
        "ignored_deliberation_revisions": [],
        "premature_consensus_risks": [],
        "critical_issues": [],
        "strengths": ["Context covered"],
        "feedback": ["Proceed"],
        "overall_score": 0.85,
    }


class PlanCriticTests(unittest.TestCase):
    def test_plan_critic_parses_valid_json(self):
        from Lib.plan_critic import check_plan_and_act

        with patch("Lib.plan_critic.send_to_AI", return_value=json.dumps(_valid_payload())):
            result = check_plan_and_act(_plan(), "Build a privacy-safe pilot", **_context())

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["critique"]["source"], "model")
        self.assertAlmostEqual(result["critique"]["scores"]["query_alignment"], 9.0)
        self.assertAlmostEqual(result["critique"]["overall_score"], 8.5)
        self.assertEqual(result["feedback"], ["Proceed"])

    def test_plan_critic_parses_markdown_json(self):
        from Lib.plan_critic import check_plan_and_act

        raw = "```json\n" + json.dumps(_valid_payload()) + "\n```"
        with patch("Lib.plan_critic.send_to_AI", return_value=raw):
            result = check_plan_and_act(_plan(), "Build a privacy-safe pilot", **_context())

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["critique"]["source"], "model")

    def test_plan_critic_invalid_json_fallback(self):
        from Lib.plan_critic import check_plan_and_act

        with patch("Lib.plan_critic.send_to_AI", return_value="not json"):
            result = check_plan_and_act(_generic_plan("generic step"), "Build a privacy-safe pilot", **_context())

        self.assertIn(result["status"], {"needs_revision", "rejected"})
        self.assertEqual(result["critique"]["source"], "rules")
        self.assertTrue(result["critique"]["parse_warnings"])

    def test_empty_plan_rejected(self):
        from Lib.plan_critic import check_plan_and_act

        with patch("Lib.plan_critic.send_to_AI", side_effect=AssertionError("model should not be called")):
            result = check_plan_and_act({}, "Build a privacy-safe pilot", **_context())

        self.assertEqual(result["status"], "rejected")
        self.assertIn("Plan is empty or invalid.", result["critique"]["critical_issues"])

    def test_missing_constraints_causes_needs_revision(self):
        from Lib.plan_critic import check_plan_and_act

        with patch("Lib.plan_critic.send_to_AI", return_value="invalid"):
            result = check_plan_and_act(_generic_plan("Do a generic pilot"), "Build a privacy-safe pilot", **_context())

        self.assertIn(result["status"], {"needs_revision", "rejected"})
        self.assertIn("privacy constraint", result["critique"]["missing_constraints"])
        self.assertIn("Explicitly address missing query constraints.", result["feedback"])

    def test_unresolved_tradeoff_causes_needs_revision(self):
        from Lib.plan_critic import check_plan_and_act

        ctx = _context()
        ctx["query_intake"]["constraints"] = []
        ctx["deliberation_brief"]["expert_risks"] = []
        ctx["dynamic_roles_used"] = []
        with patch("Lib.plan_critic.send_to_AI", return_value="invalid"):
            result = check_plan_and_act(_generic_plan("Implement quickly with ordered steps"), "Build pilot", **ctx)

        self.assertEqual(result["status"], "needs_revision")
        self.assertIn("speed vs safety", result["critique"]["unresolved_tradeoffs"])

    def test_ignored_dynamic_role_causes_needs_revision(self):
        from Lib.plan_critic import check_plan_and_act

        ctx = _context()
        ctx["query_intake"]["constraints"] = []
        ctx["deliberation_brief"]["expert_risks"] = []
        ctx["conflict_report"] = {"unresolved_tradeoffs": [], "blind_spots": [], "premature_consensus_risks": []}
        ctx["dynamic_roles_used"] = [{"key": "measurement_expert", "perspective_tag": "measurement"}]
        with patch("Lib.plan_critic.send_to_AI", return_value="invalid"):
            result = check_plan_and_act(_generic_plan("Execute a generic implementation plan"), "Build pilot", **ctx)

        self.assertEqual(result["status"], "needs_revision")
        self.assertIn("measurement_expert", result["critique"]["ignored_dynamic_roles"])

    def test_good_plan_ready_with_context(self):
        from Lib.plan_critic import check_plan_and_act

        with patch("Lib.plan_critic.send_to_AI", return_value="invalid"):
            result = check_plan_and_act(_plan(), "Build a privacy-safe pilot", **_context())

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["critique"]["source"], "rules")

    def test_check_plan_and_act_backward_compatible(self):
        from Lib.critic_decision import check_plan_and_act

        with patch("Lib.plan_critic.send_to_AI", return_value="invalid"):
            result = check_plan_and_act(_plan("Answer the query with clear steps"), "Answer the query", min_score=0.7)

        self.assertIn(result["status"], {"ready", "needs_revision", "rejected"})
        self.assertIn("critique", result)
        self.assertIn("feedback", result)

    def test_no_real_api_calls(self):
        from Lib.plan_critic import check_plan_and_act

        with patch("Lib.plan_critic.send_to_AI", side_effect=RuntimeError("no network")):
            result = check_plan_and_act(_plan("Generic plan"), "Build a privacy-safe pilot", **_context())

        self.assertIn(result["status"], {"needs_revision", "rejected"})
        self.assertEqual(result["critique"]["source"], "rules")


if __name__ == "__main__":
    unittest.main()
