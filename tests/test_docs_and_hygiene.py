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

    def test_docs_mark_legacy_modules_as_compatibility_not_current_pipeline(self):
        docs = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "docs" / "architecture.md",
            REPO_ROOT / "docs" / "PZ_draft.md",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in docs)

        self.assertIn("Legacy compatibility", combined)
        self.assertIn("Start_formalization.py", combined)
        self.assertIn("Finish_agent.py", combined)
        self.assertIn("agent_critic.py", combined)
        self.assertIn("plan_critic.py", combined)
        self.assertIn("state_machine.py", combined)
        self.assertNotIn("agent_critic.py`: builds", combined)
        self.assertNotIn("Finish_agent.py`: builds", combined)

    def test_legacy_agent_critic_is_silent_by_default(self):
        from Lib.agent_critic import criticize_plan

        with patch(
            "Lib.agent_critic.check_plan_and_act",
            return_value={
                "status": "ready",
                "critique": {
                    "scores": {"query_alignment": 9, "constraint_coverage": 8, "risk_coverage": 7, "clarity": 9},
                    "overall_score": 8.5,
                    "strengths": ["Clear"],
                    "critical_issues": [],
                },
                "feedback": ["Keep it concise"],
            },
        ):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                result = criticize_plan({"main_idea": "Idea"}, "query")

        self.assertEqual(buffer.getvalue(), "")
        self.assertEqual(result["source"], "plan_critic_compat")
        self.assertEqual(result["final_score"], 8.5)
        self.assertEqual(result["recommendations"], ["Keep it concise"])

    def test_finish_agent_accepts_none_critique(self):
        from Lib.Finish_agent import finish_answer

        with patch("Lib.Finish_agent.send_to_AI", return_value=" polished answer "):
            result = finish_answer("query", {"steps": []}, critique=None, previous_answer="draft")

        self.assertEqual(result, "polished answer")


if __name__ == "__main__":
    unittest.main()
