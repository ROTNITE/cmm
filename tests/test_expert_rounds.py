import unittest
from unittest.mock import patch

from Lib.expert_rounds import merge_expert_bundles, run_targeted_expert_round, select_targeted_roles
from Lib.expert_roles import BASE_EXPERT_ROLES


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

    def test_threaded_targeted_round_preserves_selected_order(self):
        roles = [BASE_EXPERT_ROLES[2], BASE_EXPERT_ROLES[0], BASE_EXPERT_ROLES[3]]

        def expert(role, **kwargs):
            return {
                "role_key": role.key,
                "perspective_tag": role.perspective_tag,
                "recommendations": [f"{role.key} recommendation"],
                "risks": [],
                "questions": [],
            }

        with patch("Lib.expert_rounds.run_expert", side_effect=expert) as run_expert:
            bundle = run_targeted_expert_round(
                query="query",
                roles=roles,
                context={},
                execution_mode="THREADS",
                max_workers=3,
            )

        self.assertEqual(run_expert.call_count, len(roles))
        self.assertEqual([item["key"] for item in bundle["roles"]], [role.key for role in roles])
        self.assertEqual([item["role_key"] for item in bundle["contributions"]], [role.key for role in roles])

    def test_threaded_targeted_round_falls_back_for_failed_role(self):
        roles = [BASE_EXPERT_ROLES[0], BASE_EXPERT_ROLES[1]]

        def expert(role, **kwargs):
            if role.key == "engineer":
                raise RuntimeError("offline")
            return {
                "role_key": role.key,
                "perspective_tag": role.perspective_tag,
                "recommendations": ["ok"],
                "risks": [],
                "questions": [],
            }

        with patch("Lib.expert_rounds.run_expert", side_effect=expert):
            bundle = run_targeted_expert_round(
                query="query",
                roles=roles,
                context={},
                execution_mode="THREADS",
                max_workers=2,
            )

        self.assertEqual([item["role_key"] for item in bundle["contributions"]], ["strategist", "engineer"])
        self.assertEqual(bundle["contributions"][1]["risks"], ["expert_execution_failed"])
        self.assertIn("expert_execution_failed", bundle["synthesis"]["risks"])


if __name__ == "__main__":
    unittest.main()
