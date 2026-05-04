import json
import unittest
from unittest.mock import patch


class QueryIntakeTests(unittest.TestCase):
    def test_build_query_intake_preserves_original_query_for_long_input(self):
        from Lib.query_intake import build_query_intake

        original = (
            "Нужно разработать программу развития университета.\n\n"
            "Контекст: региональный вуз, гибридное обучение, преподаватели перегружены.\n"
            "Ограничения: нельзя нанимать много новых сотрудников; бюджет ограничен; "
            "изменения должны стартовать в течение одного семестра.\n"
            "Критерии успеха: рост вовлечённости, понятные метрики, не увеличить нагрузку."
        ) * 4

        with patch("Lib.query_intake.send_to_AI", side_effect=RuntimeError("no real API")):
            intake = build_query_intake(original)

        self.assertEqual(intake["original_query"], original)
        self.assertLessEqual(len(intake["task_goal"]), 700)
        self.assertIn("model_intake_failed", " ".join(intake["parse_warnings"]))
        self.assertIn(intake["source"], {"fallback", "rules"})

    def test_build_query_intake_parses_valid_json(self):
        from Lib.query_intake import build_query_intake

        payload = {
            "task_goal": "Improve student engagement",
            "context": ["Regional university"],
            "constraints": ["Limited budget"],
            "success_criteria": ["Engagement metrics improve"],
            "unknowns": ["Baseline activity"],
            "user_preferences": ["Practical steps"],
            "risk_level": "high",
            "complexity": "complex",
            "should_use_cmm": True,
        }

        with patch("Lib.query_intake.send_to_AI", return_value=json.dumps(payload)):
            intake = build_query_intake("raw query")

        self.assertEqual(intake["original_query"], "raw query")
        self.assertEqual(intake["task_goal"], "Improve student engagement")
        self.assertEqual(intake["constraints"], ["Limited budget"])
        self.assertEqual(intake["risk_level"], "high")
        self.assertEqual(intake["complexity"], "complex")
        self.assertTrue(intake["should_use_cmm"])
        self.assertEqual(intake["source"], "model")

    def test_build_query_intake_markdown_json(self):
        from Lib.query_intake import build_query_intake

        payload = {
            "task_goal": "Choose a car",
            "context": ["Family use"],
            "constraints": ["Budget cap"],
            "success_criteria": ["Safe and reliable"],
            "unknowns": [],
            "user_preferences": ["Low maintenance"],
            "risk_level": "medium",
            "complexity": "moderate",
            "should_use_cmm": True,
        }
        raw = "```json\n" + json.dumps(payload) + "\n```"

        with patch("Lib.query_intake.send_to_AI", return_value=raw):
            intake = build_query_intake("raw query")

        self.assertEqual(intake["source"], "model")
        self.assertEqual(intake["context"], ["Family use"])
        self.assertEqual(intake["user_preferences"], ["Low maintenance"])

    def test_build_query_intake_invalid_json_fallback(self):
        from Lib.query_intake import build_query_intake

        original = "Нужно решить задачу. Ограничение: бюджет маленький."
        with patch("Lib.query_intake.send_to_AI", return_value="not json"):
            intake = build_query_intake(original)

        self.assertEqual(intake["original_query"], original)
        self.assertEqual(intake["source"], "fallback")
        self.assertIn("model_intake_invalid_json", intake["parse_warnings"])
        self.assertTrue(intake["should_use_cmm"])

    def test_no_real_api_calls_in_intake_tests(self):
        from Lib.query_intake import build_query_intake

        with patch("Lib.query_intake.send_to_AI", side_effect=AssertionError("no real API")):
            intake = build_query_intake("Short request")

        self.assertEqual(intake["original_query"], "Short request")
        self.assertEqual(intake["source"], "fallback")
        self.assertFalse(intake["should_use_cmm"])


if __name__ == "__main__":
    unittest.main()
