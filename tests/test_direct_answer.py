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


if __name__ == "__main__":
    unittest.main()
