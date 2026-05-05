import unittest


def _intake(**overrides):
    data = {
        "task_goal": "Answer a simple question",
        "context": [],
        "constraints": [],
        "success_criteria": [],
        "unknowns": [],
        "user_preferences": [],
        "risk_level": "low",
        "complexity": "simple",
        "should_use_cmm": False,
    }
    data.update(overrides)
    return data


class RouterTests(unittest.TestCase):
    def test_simple_low_risk_query_routes_direct(self):
        from Lib.router import route_query

        decision = route_query(_intake(), original_query="What is 2+2?")

        self.assertEqual(decision["mode"], "DIRECT")
        self.assertFalse(decision["needs_expert_panel"])
        self.assertEqual(decision["estimated_cost_class"], "S")

    def test_moderate_constrained_query_routes_light(self):
        from Lib.router import route_query

        decision = route_query(
            _intake(
                complexity="moderate",
                should_use_cmm=True,
                constraints=["limited budget"],
                success_criteria=["clear metric"],
            ),
            original_query="Need a practical plan with a limited budget.",
        )

        self.assertEqual(decision["mode"], "LIGHT_CMM")
        self.assertTrue(decision["needs_expert_panel"])
        self.assertFalse(decision["needs_second_round"])

    def test_complex_high_risk_query_routes_full(self):
        from Lib.router import route_query

        decision = route_query(
            _intake(complexity="complex", risk_level="high", should_use_cmm=True),
            original_query="Design a privacy and security compliance strategy.",
        )

        self.assertEqual(decision["mode"], "FULL_CMM")
        self.assertEqual(decision["estimated_cost_class"], "L")

    def test_high_risk_never_routes_direct(self):
        from Lib.router import route_query

        decision = route_query(
            _intake(risk_level="high", should_use_cmm=False),
            original_query="Simple legal compliance question",
        )

        self.assertNotEqual(decision["mode"], "DIRECT")

    def test_should_use_cmm_false_routes_direct_only_without_risk_markers(self):
        from Lib.router import route_query

        direct = route_query(_intake(should_use_cmm=False), original_query="Define this word")
        full = route_query(
            _intake(should_use_cmm=False),
            original_query="Define privacy compliance risk",
        )

        self.assertEqual(direct["mode"], "DIRECT")
        self.assertEqual(full["mode"], "FULL_CMM")

    def test_output_schema_is_stable_for_empty_intake(self):
        from Lib.router import route_query

        decision = route_query({}, original_query="")

        for key in ("mode", "reason", "complexity", "needs_expert_panel", "needs_second_round", "estimated_cost_class"):
            self.assertIn(key, decision)
        self.assertIn(decision["mode"], {"DIRECT", "LIGHT_CMM", "FULL_CMM"})
        self.assertTrue(decision["warnings"])

    def test_russian_strategy_risk_markers_route_full(self):
        from Lib.router import route_query

        decision = route_query(
            _intake(complexity="moderate", should_use_cmm=True),
            original_query="Разбери подробно стратегию, риски и ограничения проекта.",
        )

        self.assertEqual(decision["mode"], "FULL_CMM")

    def test_cost_classes_match_modes(self):
        from Lib.router import route_query

        direct = route_query(_intake(), original_query="Hi")
        light = route_query(_intake(complexity="moderate", should_use_cmm=True, constraints=["budget"]))
        full = route_query(_intake(complexity="complex", should_use_cmm=True))

        self.assertEqual(direct["estimated_cost_class"], "S")
        self.assertEqual(light["estimated_cost_class"], "M")
        self.assertEqual(full["estimated_cost_class"], "L")


if __name__ == "__main__":
    unittest.main()
