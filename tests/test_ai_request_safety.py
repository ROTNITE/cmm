import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


class AIRequestSafetyTests(unittest.TestCase):
    def test_import_does_not_require_key_or_print_secret(self):
        with patch.dict(os.environ, {}, clear=True):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                import Lib.AI_request as ai_request

            self.assertEqual(buffer.getvalue(), "")
            self.assertTrue(hasattr(ai_request, "send_to_AI"))

    def test_missing_key_fails_at_call_time_without_network(self):
        import Lib.AI_request as ai_request

        with patch.dict(os.environ, {}, clear=True), patch.object(
            ai_request, "_load_local_env_files", return_value=None
        ):
            result = ai_request.send_to_AI("hello", tokens=10)

        self.assertIn("API key is not configured", result)

    def test_explicit_key_is_not_printed(self):
        import Lib.AI_request as ai_request

        class _Message:
            content = "ok"

        class _Choice:
            message = _Message()

        class _Response:
            choices = [_Choice()]

        class _Completions:
            @staticmethod
            def create(**kwargs):
                return _Response()

        class _Chat:
            completions = _Completions()

        class _Client:
            chat = _Chat()

            def __init__(self, **kwargs):
                pass

        buffer = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch.object(
            ai_request, "_load_local_env_files", return_value=None
        ), patch.dict("sys.modules", {"openai": type("OpenAIModule", (), {"OpenAI": _Client})}):
            with redirect_stdout(buffer):
                result = ai_request.send_to_AI("hello", tokens=10, api_key="test-secret")

        self.assertEqual(result, "ok")
        self.assertEqual(buffer.getvalue(), "")
        self.assertNotIn("test-secret", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
