import unittest


def _state():
    return {
        "original_query": "raw query",
        "formalized_query": "cleaned query",
        "query_intake": {
            "original_query": "raw query",
            "cleaned_query": "cleaned query",
            "task_goal": "Goal",
            "context": ["Context"],
            "constraints": ["Constraint A"],
            "success_criteria": ["Success A"],
            "unknowns": ["Unknown A"],
            "user_preferences": ["Preference A"],
            "risk_level": "medium",
            "complexity": "complex",
            "should_use_cmm": True,
        },
        "expert_bundle": {
            "roles": [
                {"key": "strategist", "name": "Strategist", "perspective_tag": "strategy"},
                {"key": "legal_reviewer", "name": "Legal Reviewer", "perspective_tag": "legal", "dynamic": True},
            ],
            "contributions": [
                {
                    "role_key": "strategist",
                    "perspective_tag": "strategy",
                    "recommendations": ["Recommendation A"],
                    "risks": ["Risk A"],
                    "questions": ["Question A"],
                    "insights": ["Insight A"],
                }
            ],
            "synthesis": {
                "recommendations": ["Recommendation A"],
                "risks": ["Risk A"],
                "questions": ["Question A"],
                "perspective_counts": {"strategy": 1},
            },
        },
        "expert_rounds": [
            {
                "roles": [
                    {"key": "strategist", "name": "Strategist", "perspective_tag": "strategy"},
                    {"key": "legal_reviewer", "name": "Legal Reviewer", "perspective_tag": "legal", "dynamic": True},
                ],
                "contributions": [],
                "synthesis": {},
            }
        ],
        "dynamic_role_reports": [
            {
                "round": "initial",
                "role_views": [
                    {
                        "key": "legal_reviewer",
                        "name": "Legal Reviewer",
                        "perspective_tag": "legal",
                        "why_needed": "Legal constraints appear.",
                    }
                ],
                "rejected_suggestions": [],
                "warnings": [],
                "source": "test",
            }
        ],
        "balance_report": {
            "dominant_perspective_found": False,
            "missing_perspectives": [],
            "notes": ["Balanced"],
            "argument_quality": {"specificity": 0.7},
            "blind_spots": ["Blind spot A"],
            "recommended_action": "SYNTHESIZE",
        },
        "deliberation_brief": {
            "revised_recommendations": ["Revised A"],
            "new_risks": ["New risk A"],
            "questions_for_group": ["Group question A"],
            "summary": "Brief",
            "expert_recommendations": ["Recommendation A"],
            "expert_risks": ["Risk A"],
            "expert_questions": ["Question A"],
            "must_address": ["Must A"],
            "constraints": ["Constraint A"],
            "success_criteria": ["Success A"],
            "unresolved_tradeoffs": [{"tradeoff": "speed vs safety"}],
            "blind_spots": ["Blind spot A"],
        },
        "conflict_report": {
            "agreements": [],
            "disagreements": [{"issue": "Disagreement A", "severity": "medium"}],
            "unresolved_tradeoffs": [{"tradeoff": "speed vs safety", "why_it_matters": "Risk"}],
            "premature_consensus_risks": [],
            "blind_spots": ["Blind spot A"],
            "minority_positions": [],
            "questions_for_next_round": ["Question next A"],
            "confidence": 0.7,
            "source": "test",
        },
        "deliberation_rounds": [
            {
                "responses": [
                    {
                        "role_key": "strategist",
                        "revised_recommendations": ["Revised A"],
                        "new_risks": ["New risk A"],
                        "disagreements": ["Disagreement A"],
                    }
                ]
            }
        ],
        "meta_decision": {"decision": "SYNTHESIZE", "reason": "Ok"},
        "plan_critiques": [
            {
                "status": "needs_revision",
                "decision": "REVISE",
                "reason": "Needs detail",
                "feedback": ["Fix A"],
                "critique": {"critical_blockers": [], "ignored_risks": ["Risk A"]},
            }
        ],
        "replan_context": {"reason": "Needs detail", "feedback": ["Fix A"]},
        "history": [{"from": "PLAN", "to": "PLAN_CRITIQUE", "reason": "plan generated"}],
        "warnings": ["warning A"],
        "context_compression": {},
    }


class ContextManagerTests(unittest.TestCase):
    def test_build_compact_planner_context_preserves_legacy_keys(self):
        from Lib.context_manager import build_compact_planner_context

        context = build_compact_planner_context(_state())

        self.assertEqual(context["deliberation_brief"]["revised_recommendations"], ["Revised A"])
        self.assertEqual(context["deliberation_brief"]["new_risks"], ["New risk A"])
        self.assertEqual(context["deliberation_brief"]["questions_for_group"], ["Group question A"])
        self.assertEqual(context["original_query"], "raw query")
        self.assertTrue(context["original_query_is_authoritative"])
        self.assertEqual(context["query_intake"]["constraints"], ["Constraint A"])
        self.assertEqual(context["deliberation_brief"]["must_address"], ["Must A"])
        self.assertEqual(context["conflict_report"]["blind_spots"], ["Blind spot A"])
        self.assertIn("Original query is authoritative", context["instruction"])

    def test_build_compact_critic_context_has_expected_kwargs(self):
        from Lib.context_manager import build_compact_critic_context

        context = build_compact_critic_context(_state())

        self.assertEqual(context["query_intake"]["success_criteria"], ["Success A"])
        self.assertEqual(context["dynamic_roles_used"][0]["key"], "legal_reviewer")
        self.assertEqual(context["deliberation_revisions"][0]["new_risks"], ["New risk A"])
        self.assertEqual(context["replan_context"]["feedback"], ["Fix A"])

    def test_build_compact_answer_context_contains_only_downstream_fields(self):
        from Lib.context_manager import build_compact_answer_context

        context = build_compact_answer_context(_state())

        self.assertIn("expert_bundle", context)
        self.assertIn("balance_report", context)
        self.assertIn("deliberation_brief", context)
        self.assertNotIn("history", context)
        self.assertEqual(context["deliberation_brief"]["expert_risks"], ["Risk A"])

    def test_build_compact_meta_context_has_process_inputs(self):
        from Lib.context_manager import build_compact_meta_context

        context = build_compact_meta_context(_state())

        self.assertEqual(context["query"], "raw query")
        self.assertIn("expert_bundle", context)
        self.assertIn("balance_report", context)
        self.assertIn("deliberation_brief", context)
        self.assertIn("conflict_report", context)

    def test_record_context_size_and_report(self):
        from Lib.context_manager import (
            build_compact_planner_context,
            build_context_compression_report,
            record_context_size,
        )

        state = _state()
        context = build_compact_planner_context(state)
        record_context_size(state, "planner", context)
        report = build_context_compression_report(state)

        self.assertGreater(report["planner_context_chars"], 0)
        self.assertIn("critic_context_chars", report)
        self.assertIn("answer_context_chars", report)
        self.assertIn("meta_context_chars", report)


if __name__ == "__main__":
    unittest.main()