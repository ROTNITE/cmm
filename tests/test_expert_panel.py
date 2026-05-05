import time
import unittest
from unittest.mock import patch

from Lib.expert_panel import run_expert_panel
from Lib.expert_roles import BASE_EXPERT_ROLES


def _roles():
    return [BASE_EXPERT_ROLES[0], BASE_EXPERT_ROLES[1], BASE_EXPERT_ROLES[2]]


def _contribution(role):
    return {
        "role_key": role.key,
        "perspective_tag": role.perspective_tag,
        "insights": [f"{role.key} insight"],
        "risks": [],
        "questions": [],
        "recommendations": [f"{role.key} recommendation"],
        "confidence": 0.8,
    }


class ExpertPanelParallelTests(unittest.TestCase):
    def test_sequential_default_keeps_role_order(self):
        roles = _roles()

        with patch("Lib.expert_panel.determine_expert_roles", return_value=roles), patch(
            "Lib.expert_panel.run_expert", side_effect=lambda role, **kwargs: _contribution(role)
        ) as run_expert:
            bundle = run_expert_panel("query")

        self.assertEqual([item["role_key"] for item in bundle["contributions"]], [role.key for role in roles])
        self.assertEqual(run_expert.call_count, len(roles))

    def test_threaded_mode_calls_all_roles_and_preserves_selected_order(self):
        roles = _roles()

        def delayed_expert(role, **kwargs):
            if role.key == roles[0].key:
                time.sleep(0.02)
            return _contribution(role)

        with patch("Lib.expert_panel.determine_expert_roles", return_value=roles), patch(
            "Lib.expert_panel.run_expert", side_effect=delayed_expert
        ) as run_expert:
            bundle = run_expert_panel("query", execution_mode="THREADS", max_workers=3)

        self.assertEqual(run_expert.call_count, len(roles))
        self.assertEqual([item["role_key"] for item in bundle["contributions"]], [role.key for role in roles])
        self.assertEqual([item["key"] for item in bundle["roles"]], [role.key for role in roles])

    def test_threaded_mode_uses_fallback_for_one_failing_role(self):
        roles = _roles()

        def sometimes_fails(role, **kwargs):
            if role.key == roles[1].key:
                raise RuntimeError("offline")
            return _contribution(role)

        with patch("Lib.expert_panel.determine_expert_roles", return_value=roles), patch(
            "Lib.expert_panel.run_expert", side_effect=sometimes_fails
        ):
            bundle = run_expert_panel("query", execution_mode="THREADS", max_workers=3)

        self.assertEqual([item["role_key"] for item in bundle["contributions"]], [role.key for role in roles])
        self.assertEqual(bundle["contributions"][1]["risks"], ["expert_execution_failed"])
        self.assertIn("expert_execution_failed", bundle["synthesis"]["risks"])


if __name__ == "__main__":
    unittest.main()
