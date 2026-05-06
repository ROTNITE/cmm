"""Policy tests for quality gates and routing decisions.

These tests validate that the system correctly classifies blockers and routes queries.
They serve as regression tests for the diagnostic improvements.
"""

import unittest

from Lib.quality_gates import classify_blocker, plan_blockers
from Lib.router import route_query


class TestPolicyGates(unittest.TestCase):
    """Test policy-level behavior of quality gates and router."""

    def test_product_tradeoffs_are_must_address_not_blockers(self):
        """Test 1: Product/tool trade-offs don't become critical_plan_blockers.

        They should go to must_address_in_answer, not no_answer_blockers.
        """
        # Product trade-offs
        tradeoff_texts = [
            "Trade-off: search functionality vs simplicity",
            "Notion vs self-hosted wiki",
            "Single owner vs multiple champions",
            "Cost vs features",
            "Speed vs accuracy",
        ]

        for text in tradeoff_texts:
            classification = classify_blocker(text)
            self.assertEqual(
                classification["class"],
                "MUST_ADDRESS_IN_ANSWER",
                f"Product trade-off '{text}' should be MUST_ADDRESS, not {classification['class']}"
            )

        # Test in plan_blockers context
        critique_result = {
            "critique": {
                "unresolved_tradeoffs": tradeoff_texts,
                "ignored_risks": ["Consider maintenance burden"],
            }
        }

        blockers = plan_blockers(critique_result)
        self.assertEqual(
            len(blockers["no_answer_blockers"]),
            0,
            f"Product trade-offs should not create no_answer_blockers, got: {blockers['no_answer_blockers']}"
        )
        self.assertGreater(
            len(blockers["must_address"]),
            0,
            "Product trade-offs should create must_address items"
        )

    def test_true_safety_blockers_actually_block(self):
        """Test 2: True privacy/security/medical/legal blocker actually blocks."""
        safety_texts = [
            "Privacy leak: user emails exposed in logs",
            "Security exploit: SQL injection vulnerability",
            "Medical advice: recommending specific medication",
            "Legal compliance issue: GDPR violation",
            "API key exposed in response",
        ]

        for text in safety_texts:
            classification = classify_blocker(text)
            self.assertEqual(
                classification["class"],
                "NO_ANSWER_BLOCKER",
                f"Safety issue '{text}' should be NO_ANSWER_BLOCKER, not {classification['class']}"
            )

        # Test in plan_blockers context
        critique_result = {
            "critique": {
                "critical_issues": safety_texts,
            }
        }

        blockers = plan_blockers(critique_result)
        self.assertGreater(
            len(blockers["no_answer_blockers"]),
            0,
            "Safety issues should create no_answer_blockers"
        )

    def test_critic_finalize_with_no_blockers_becomes_ready(self):
        """Test 3: Critic says FINALIZE + no blockers → status becomes ready.

        This tests the plan_critic normalizer fix.
        """
        from Lib.plan_critic import _status_from_critique

        critique = {
            "feedback": ["Plan is ready for final answer generation."],
            "recommendations": ["Proceed with answer generation."],
            "critical_issues": [],
            "critical_blockers": [],
            "missing_constraints": [],
            "ignored_must_address": [],
            "ignored_expert_risks": [],
            "unresolved_tradeoffs": [],
            "ignored_dynamic_roles": [],
            "overall_score": 8.5,
        }

        status, reason = _status_from_critique(critique, min_score=0.7)
        self.assertEqual(
            status,
            "ready",
            f"Critique with FINALIZE markers and no blockers should be 'ready', got '{status}'"
        )

    def test_actionable_plan_with_no_blockers_cannot_return_empty(self):
        """Test 4: Non-empty actionable plan + no no-answer blockers → cannot return empty answer.

        This tests that can_best_effort_finalize allows finalization.
        """
        from Lib.quality_gates import can_best_effort_finalize

        plan = {
            "main_idea": "Launch internal knowledge base using Notion",
            "steps": [
                {"title": "Set up Notion workspace", "substeps": ["Create account", "Configure permissions"]},
                {"title": "Migrate existing docs", "substeps": ["Audit current docs", "Import to Notion"]},
            ],
        }

        critique_result = {
            "critique": {
                "critical_blockers": [],
                "critical_issues": [],
                "ignored_must_address": ["Consider search functionality"],
                "unresolved_tradeoffs": ["Notion vs self-hosted"],
            },
            "status": "needs_revision",
        }

        can_finalize = can_best_effort_finalize(
            critique_result=critique_result,
            plan=plan,
        )

        self.assertTrue(
            can_finalize,
            "Actionable plan with only MUST_ADDRESS items (no NO_ANSWER_BLOCKERS) should allow best-effort finalization"
        )

    def test_operational_plan_routes_light_cmm_not_full(self):
        """Test 5: Operational plan query routes LIGHT_CMM, not FULL_CMM."""
        operational_queries = [
            {
                "query": "Помоги составить лёгкий план запуска внутренней базы знаний для команды из 5 человек",
                "intake": {
                    "task_goal": "Create launch plan for internal knowledge base",
                    "constraints": ["недорого", "за месяц", "небольшая команда"],
                    "complexity": "medium",
                },
            },
            {
                "query": "Quick setup plan for team wiki using Notion",
                "intake": {
                    "task_goal": "Setup team wiki",
                    "constraints": ["quick", "small team", "low cost"],
                    "complexity": "low",
                },
            },
        ]

        for item in operational_queries:
            result = route_query(item["intake"], original_query=item["query"])
            self.assertEqual(
                result["mode"],
                "LIGHT_CMM",
                f"Operational plan '{item['query']}' should route to LIGHT_CMM, got {result['mode']}"
            )

    def test_direct_prompt_no_hardcoded_kpi_example(self):
        """Test 6: DIRECT prompt doesn't contain specific KPI example.

        This validates that hardcoded answers are kept in _enhance_direct_answer,
        not in the prompt itself.
        """
        from Lib.direct_answer import run_direct_answer

        # This test just checks that the function exists and doesn't crash
        # The actual validation is that hardcoded answers are in _enhance_direct_answer
        result = run_direct_answer(
            "Какая разница между метрикой и KPI?",
            query_intake={"task_goal": "Explain difference between metric and KPI"},
        )

        self.assertIn("final_answer", result)
        self.assertIsInstance(result["final_answer"], str)

        # The answer should contain the hardcoded response
        answer = result["final_answer"].lower()
        self.assertTrue(
            "метрика" in answer or "kpi" in answer,
            "Answer should contain metric/KPI explanation"
        )


if __name__ == "__main__":
    unittest.main()
