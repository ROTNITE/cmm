import unittest

from Lib.expert_rounds import merge_expert_bundles, select_targeted_roles


class ExpertRoundsTests(unittest.TestCase):
    def test_missing_user_perspective_selects_user_advocate(self):
        roles = select_targeted_roles(
            meta_decision={"missing_perspectives": []},
            balance_report={"missing_perspectives": ["user"]},
            deliberation_brief={},
        )

        self.assertEqual([role.key for role in roles], ["user_advocate"])

    def test_risks_select_risk_manager(self):
        roles = select_targeted_roles(
            meta_decision={"risks_to_address": ["deployment risk"]},
            balance_report={"missing_perspectives": []},
            deliberation_brief={},
        )

        self.assertIn("risk_manager", [role.key for role in roles])

    def test_unmapped_gap_falls_back_to_risk_manager_and_strategist(self):
        roles = select_targeted_roles(
            meta_decision={"missing_perspectives": ["legal"]},
            balance_report={"missing_perspectives": ["legal"]},
            deliberation_brief={},
        )

        self.assertEqual([role.key for role in roles], ["risk_manager", "strategist"])

    def test_merge_expert_bundles_dedupes_synthesis_and_recomputes_counts(self):
        first = {
            "roles": [{"key": "strategist", "perspective_tag": "strategy"}],
            "contributions": [
                {
                    "role_key": "strategist",
                    "perspective_tag": "strategy",
                    "recommendations": ["Clarify goal", "Prioritize rollout"],
                    "risks": ["Scope creep"],
                    "questions": ["Who owns it?"],
                }
            ],
        }
        second = {
            "roles": [{"key": "risk_manager", "perspective_tag": "risk"}],
            "contributions": [
                {
                    "role_key": "risk_manager",
                    "perspective_tag": "risk",
                    "recommendations": ["Clarify goal", "Add rollback"],
                    "risks": ["Scope creep", "No rollback"],
                    "questions": ["Who owns it?", "What fails first?"],
                }
            ],
        }

        merged = merge_expert_bundles(first, second)

        self.assertEqual(len(merged["roles"]), 2)
        self.assertEqual(
            merged["synthesis"]["recommendations"],
            ["Clarify goal", "Prioritize rollout", "Add rollback"],
        )
        self.assertEqual(merged["synthesis"]["risks"], ["Scope creep", "No rollback"])
        self.assertEqual(merged["synthesis"]["questions"], ["Who owns it?", "What fails first?"])
        self.assertEqual(merged["synthesis"]["perspective_counts"], {"strategy": 1, "risk": 1})


if __name__ == "__main__":
    unittest.main()
