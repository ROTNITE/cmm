import unittest
from unittest.mock import patch


class ImportAndHelperTests(unittest.TestCase):
    def test_main_modules_import_from_project_root(self):
        modules = [
            "main",
            "Lib.Start_formalization",
            "Lib.plan_development",
            "Lib.critic_decision",
            "Lib.expert_roles",
            "Lib.expert_selector",
            "Lib.expert_agent",
            "Lib.expert_panel",
            "Lib.balance_analyzer",
            "Lib.deliberation",
            "Lib.deliberation_round",
            "Lib.json_utils",
            "Lib.orchestrator",
            "Lib.meta_moderator",
            "Lib.agent_improver",
            "Lib.agent_moderator",
            "Lib.Finish_agent",
        ]

        for module_name in modules:
            with self.subTest(module=module_name):
                __import__(module_name)

    def test_balance_analyzer_handles_invalid_bundle(self):
        from Lib.balance_analyzer import analyze_balance

        result = analyze_balance(None)

        self.assertEqual(
            result["missing_perspectives"],
            ["strategy", "engineering", "risk", "user"],
        )
        self.assertFalse(result["dominant_perspective_found"])

    def test_expert_agent_json_fallback(self):
        from Lib.expert_agent import _safe_json_loads

        self.assertIsNone(_safe_json_loads("not json"))
        self.assertEqual(_safe_json_loads('prefix {"ok": true} suffix'), {"ok": True})

    def test_expert_panel_uses_fallback_when_expert_fails(self):
        from Lib.expert_roles import BASE_EXPERT_ROLES
        from Lib.expert_panel import run_expert_panel

        with patch("Lib.expert_panel.determine_expert_roles", return_value=[BASE_EXPERT_ROLES[0]]), patch(
            "Lib.expert_panel.run_expert", side_effect=RuntimeError("offline")
        ):
            bundle = run_expert_panel("query")

        self.assertEqual(bundle["roles"][0]["key"], "strategist")
        self.assertEqual(bundle["contributions"][0]["risks"], ["expert_execution_failed"])
        self.assertIn("synthesis", bundle)


if __name__ == "__main__":
    unittest.main()
