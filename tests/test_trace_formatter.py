import unittest


class TraceFormatterTests(unittest.TestCase):
    def test_empty_trace_does_not_raise(self):
        from Lib.trace_formatter import format_trace_report

        summary = format_trace_report({})

        self.assertIn("CMM TRACE SUMMARY", summary)
        self.assertIn("1. Routing", summary)
        self.assertIn("9. Warnings / errors", summary)

    def test_full_trace_contains_key_human_sections(self):
        from Lib.trace_formatter import format_trace_report

        trace = {
            "cmm_mode": "FULL_CMM",
            "estimated_cost_class": "L",
            "router_decision": {"reason": "Complex request"},
            "state_history": [
                {"from": "INTAKE", "to": "ROUTE", "reason": "intake complete"},
                {"from": "ROUTE", "to": "PANEL_ROUND_1", "reason": "full"},
            ],
            "final_state": "FINALIZE",
            "roles_used_unique": [
                {"key": "strategist", "perspective_tag": "strategy", "rounds": ["initial"], "dynamic": False},
                {"key": "legal_reviewer", "perspective_tag": "legal", "rounds": ["extra"], "dynamic": True},
            ],
            "dynamic_roles_generated": [{"key": "legal_reviewer"}],
            "dynamic_roles_executed": [{"key": "legal_reviewer", "round": "extra"}],
            "dynamic_roles_rejected": [{"raw_key": "hacker_role", "reason": "not_allowed"}],
            "balance_reports": [
                {
                    "missing_perspectives": ["risk"],
                    "dominant_perspective": "strategy",
                    "argument_quality": {"actionability": 0.7},
                    "recommended_action": "DEEPEN",
                }
            ],
            "conflict_reports": [
                {
                    "disagreements": ["scope disagreement"],
                    "unresolved_tradeoffs": ["speed vs safety"],
                    "blind_spots": ["privacy"],
                }
            ],
            "deliberation_revisions": ["revise rollout"],
            "deliberation_round_count": 2,
            "consensus_checks": [{"after_round": 1, "decision": "DELIBERATION_ROUND_2"}],
            "deliberation_position_changes": [{"role_key": "risk_manager", "position_changed": True}],
            "plan_critique_decisions": ["ACCEPT"],
            "plan_critique_blockers": [],
            "plan_replan_reasons": [],
            "answer_moderation_final_decision": "ACCEPT",
            "revision_count": 1,
            "final_confidence": 0.85,
            "warnings": ["minor warning"],
            "errors": [],
            "raw": {"large": "object"},
            "expert_bundle": {"large": "object"},
        }

        summary = format_trace_report(trace)

        self.assertIn("Mode: FULL_CMM", summary)
        self.assertIn("Reason: Complex request", summary)
        self.assertIn("INTAKE -> ROUTE -> PANEL_ROUND_1", summary)
        self.assertIn("strategist (strategy) [initial]", summary)
        self.assertIn("legal_reviewer [extra]", summary)
        self.assertIn("Round count: 2", summary)
        self.assertIn("DELIBERATION_ROUND_2", summary)
        self.assertIn("minor warning", summary)
        self.assertNotIn("expert_bundle", summary)
        self.assertNotIn('"raw"', summary)

    def test_long_lists_are_limited(self):
        from Lib.trace_formatter import format_trace_report

        trace = {
            "warnings": ["w1", "w2", "w3"],
            "errors": ["e1", "e2", "e3"],
        }

        summary = format_trace_report(trace, max_items=2)

        self.assertIn("w1, w2, ... +1 more", summary)
        self.assertIn("e1, e2, ... +1 more", summary)


if __name__ == "__main__":
    unittest.main()
