import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]


class DocsAndHygieneTests(unittest.TestCase):
    def test_formalization_empty_ai_fallback_is_silent(self):
        from Lib.Start_formalization import formalization

        buffer = io.StringIO()
        with patch("Lib.Start_formalization.send_to_AI", return_value=""):
            with redirect_stdout(buffer):
                result = formalization("Привет!!!     Что делать????")

        self.assertEqual(buffer.getvalue(), "")
        self.assertEqual(result, "Привет! Что делать?")

    def test_docs_do_not_claim_second_round_is_deferred(self):
        docs = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "docs" / "architecture.md",
            REPO_ROOT / "docs" / "PZ_draft.md",
        ]
        forbidden = [
            "second expert round is deferred",
            "second expert round is not implemented",
            "second-pass expert execution is deferred",
            "второй экспертный проход пока не запускается",
            "Нет полноценного второго экспертного раунда",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in docs)

        for phrase in forbidden:
            self.assertNotIn(phrase, combined)

        self.assertIn("targeted second expert round", combined)
        self.assertIn("Второй экспертный раунд есть", combined)
        self.assertIn("query_intake", combined)
        self.assertIn("original_query` is authoritative", combined)
        self.assertIn("helper text only", combined)


if __name__ == "__main__":
    unittest.main()
