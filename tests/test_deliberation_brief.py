import unittest


class DeliberationBriefTests(unittest.TestCase):
    def test_provider_failure_text_does_not_enter_must_address(self):
        from Lib.deliberation import build_deliberation_brief, apply_conflict_report_to_brief

        expert_bundle = {
            "synthesis": {
                "recommendations": ["Answer the direct user goal first."],
                "risks": ["Complete failure of expert contribution system - invalid JSON"],
                "questions": ["No credentials for provider: aimlapi"],
                "perspective_counts": {"strategy": 1},
            }
        }
        balance_report = {
            "missing_perspectives": [],
            "blind_spots": ["All expert contributions failed due to API credential errors"],
            "recommended_action": "SYNTHESIZE",
        }
        brief = build_deliberation_brief("query", expert_bundle, balance_report)
        brief = apply_conflict_report_to_brief(
            brief,
            {
                "disagreements": [{"issue": "expert panel catastrophic JSON failure", "severity": "high"}],
                "unresolved_tradeoffs": [{"tradeoff": "No credentials for provider: aimlapi"}],
                "blind_spots": ["all expert contributions failed due to API credential errors"],
                "premature_consensus_risks": ["invalid JSON from all experts"],
                "questions_for_next_round": ["provider model error"],
            },
        )

        must_address = " ".join(brief.get("must_address", []))
        self.assertIn("Answer the direct user goal first.", must_address)
        self.assertNotIn("No credentials", must_address)
        self.assertNotIn("invalid JSON", must_address)
        self.assertNotIn("expert contributions failed", must_address)


if __name__ == "__main__":
    unittest.main()
