import unittest
from unittest.mock import patch


class _Message:
    content = "Object message answer"


class _Choice:
    message = _Message()


class _Response:
    choices = [_Choice()]


class DirectAnswerTests(unittest.TestCase):
    def test_direct_answer_accepts_string_response(self):
        from Lib.direct_answer import run_direct_answer

        with patch("Lib.direct_answer.send_to_AI", return_value=" Direct answer "):
            result = run_direct_answer("query")

        self.assertEqual(result["final_answer"], "Direct answer")
        self.assertEqual(result["source"], "model")
        self.assertEqual(result["parse_warnings"], [])

    def test_direct_answer_extracts_dict_openai_like_response(self):
        from Lib.direct_answer import run_direct_answer

        raw = {"choices": [{"message": {"content": "Dict message answer"}}]}
        with patch("Lib.direct_answer.send_to_AI", return_value=raw):
            result = run_direct_answer("query")

        self.assertEqual(result["final_answer"], "Dict message answer")
        self.assertEqual(result["source"], "model")

    def test_direct_answer_extracts_object_openai_like_response(self):
        from Lib.direct_answer import run_direct_answer

        with patch("Lib.direct_answer.send_to_AI", return_value=_Response()):
            result = run_direct_answer("query")

        self.assertEqual(result["final_answer"], "Object message answer")
        self.assertEqual(result["source"], "model")

    def test_direct_answer_model_error_returns_non_empty_fallback(self):
        from Lib.direct_answer import run_direct_answer

        with patch("Lib.direct_answer.send_to_AI", return_value="Error: invalid json"):
            result = run_direct_answer(
                "Кратко объясни, что такое коллективная метамодерация.",
                query_intake={"task_goal": "Объяснить коллективную метамодерацию"},
            )

        self.assertTrue(result["final_answer"].strip())
        self.assertEqual(result["source"], "fallback")
        self.assertIn("direct_answer_failed", result["parse_warnings"])

    def test_direct_answer_empty_response_returns_non_empty_fallback(self):
        from Lib.direct_answer import run_direct_answer

        with patch("Lib.direct_answer.send_to_AI", return_value="   "):
            result = run_direct_answer("simple query")

        self.assertTrue(result["final_answer"].strip())
        self.assertEqual(result["source"], "fallback")

    def test_direct_answer_enforces_brevity_budget(self):
        from Lib.direct_answer import run_direct_answer

        long_answer = (
            "Метрика - это любой измеримый показатель. KPI - это ключевая метрика, привязанная к важной цели. "
            "Все KPI являются метриками, но не все метрики являются KPI. "
            "Пример: число посещений сайта - метрика, а конверсия в оплату для цели роста выручки - KPI. "
            "Дополнительный пример про продажи. Дополнительный пример про поддержку. "
            "Подробный абзац с лишними деталями, который должен быть обрезан для краткого ответа."
        )
        with patch("Lib.direct_answer.send_to_AI", return_value=long_answer):
            result = run_direct_answer(
                "Кратко объясни разницу между метрикой и KPI.",
                query_intake={"constraints": ["Ответ кратко."], "task_goal": "Объяснить разницу между метрикой и KPI."},
            )

        self.assertLessEqual(len(result["final_answer"]), 650)
        self.assertIn("Все KPI являются метриками", result["final_answer"])
        self.assertIn("не все метрики являются KPI", result["final_answer"])

    def test_direct_answer_adds_missing_metric_kpi_example(self):
        from Lib.direct_answer import run_direct_answer

        answer = (
            "Метрика — это любой измеримый показатель. KPI — ключевой показатель, связанный с целью. "
            "Все KPI являются метриками, но не все метрики являются KPI."
        )
        with patch("Lib.direct_answer.send_to_AI", return_value=answer):
            result = run_direct_answer(
                "Кратко объясни разницу между метрикой и KPI.",
                query_intake={"constraints": ["Ответ кратко."], "task_goal": "Разница между метрикой и KPI."},
            )

        self.assertIn("Пример:", result["final_answer"])
        self.assertIn("конверсии", result["final_answer"])

    def test_direct_answer_repairs_incomplete_tradeoff_answer(self):
        from Lib.direct_answer import run_direct_answer

        answer = "A trade-off in product design is a choice. Key examples: - Speed vs accuracy - Cost vs."
        with patch("Lib.direct_answer.send_to_AI", return_value=answer):
            result = run_direct_answer(
                "What is a trade-off in product design?",
                query_intake={"constraints": ["Keep it concise."], "task_goal": "Explain trade-offs."},
            )

        self.assertIn("Speed vs accuracy", result["final_answer"])
        self.assertIn("Cost vs quality", result["final_answer"])
        self.assertFalse(result["final_answer"].strip().endswith("vs."))

    def test_direct_answer_keeps_compact_tradeoff_examples(self):
        from Lib.direct_answer import run_direct_answer

        answer = (
            "A trade-off in product design is when you sacrifice one quality to gain another.\n\n"
            "Common examples:\n"
            "- Speed vs accuracy\n"
            "- Features vs simplicity\n"
            "- Cost vs quality\n"
            "- Performance vs battery life\n\n"
            "The point is to choose what matters most."
        )
        with patch("Lib.direct_answer.send_to_AI", return_value=answer):
            result = run_direct_answer(
                "What is a trade-off in product design?",
                query_intake={"task_goal": "Explain trade-offs."},
            )

        bullets = [line for line in result["final_answer"].splitlines() if line.strip().startswith("-")]
        self.assertGreaterEqual(len(bullets), 5)
        self.assertIn("Flexibility vs ease of use", result["final_answer"])


if __name__ == "__main__":
    unittest.main()
