import json
import unittest
from unittest.mock import patch


def _brief(risks=None, must_address=None, questions=None):
    return {
        "expert_risks": risks or [],
        "expert_questions": questions or [],
        "must_address": must_address or [],
    }


def _balance(missing=None, dominant=False):
    return {
        "dominant_perspective_found": dominant,
        "dominant_perspective": "risk" if dominant else None,
        "missing_perspectives": missing or [],
        "notes": [],
    }


def _model_decision():
    return {
        "decision": "FINALIZE",
        "reason": "Ready",
        "missing_perspectives": [],
        "conflicts_to_resolve": ["Conflict"],
        "risks_to_address": ["Risk"],
        "questions_to_answer": ["Question"],
        "next_actions": ["Finalize"],
        "confidence": 0.9,
    }


def _conflict_report(tradeoffs=None, premature=None, blind_spots=None):
    return {
        "agreements": [],
        "disagreements": [],
        "unresolved_tradeoffs": tradeoffs or [],
        "premature_consensus_risks": premature or [],
        "blind_spots": blind_spots or [],
        "minority_positions": [],
        "questions_for_next_round": [],
        "confidence": 0.6,
        "parse_warnings": [],
        "source": "rules",
    }


class MetaModeratorTests(unittest.TestCase):
    def test_valid_json_decision_parses_and_normalizes(self):
        from Lib.meta_moderator import run_meta_moderator

        with patch("Lib.json_retry.send_to_AI", return_value=json.dumps(_model_decision())):
            decision = run_meta_moderator("query", {}, _balance(), _brief())

        self.assertEqual(decision["decision"], "FINALIZE")
        self.assertEqual(decision["conflicts_to_resolve"], ["Conflict"])
        self.assertEqual(decision["confidence"], 0.9)
        self.assertEqual(decision["source"], "model")
        self.assertEqual(decision["json_attempts"], 1)

    def test_markdown_wrapped_json_decision_parses(self):
        from Lib.meta_moderator import run_meta_moderator

        raw = "```json\n" + json.dumps(_model_decision()) + "\n```"
        with patch("Lib.json_retry.send_to_AI", return_value=raw):
            decision = run_meta_moderator("query", {}, _balance(), _brief())

        self.assertEqual(decision["decision"], "FINALIZE")
        self.assertEqual(decision["next_actions"], ["Finalize"])

    def test_invalid_json_uses_rule_fallback(self):
        from Lib.meta_moderator import run_meta_moderator

        with patch("Lib.json_retry.send_to_AI", return_value="not json"):
            decision = run_meta_moderator("query", {}, _balance(missing=["user"]), _brief(risks=["Risk"]))

        self.assertEqual(decision["decision"], "DEEPEN")
        self.assertEqual(decision["missing_perspectives"], ["user"])
        self.assertEqual(decision["source"], "rules")
        self.assertEqual(decision["json_attempts"], 2)
        self.assertIn("meta_moderator_model_invalid_json", decision["parse_warnings"])

    def test_meta_moderator_retries_invalid_then_valid_json(self):
        from Lib.meta_moderator import run_meta_moderator

        with patch("Lib.json_retry.send_to_AI", side_effect=["not json", json.dumps(_model_decision())]):
            decision = run_meta_moderator("query", {}, _balance(), _brief())

        self.assertEqual(decision["decision"], "FINALIZE")
        self.assertEqual(decision["source"], "model")
        self.assertEqual(decision["json_attempts"], 2)
        self.assertIn("json_retry_after_invalid_json", decision["parse_warnings"])

    def test_meta_moderator_rule_guard_overrides_optimistic_model(self):
        from Lib.meta_moderator import run_meta_moderator

        balance = _balance()
        balance["recommended_action"] = "ADD_EXPERT"
        balance["missing_perspectives"] = ["legal"]
        with patch("Lib.json_retry.send_to_AI", return_value=json.dumps(_model_decision())):
            decision = run_meta_moderator("query", {}, balance, _brief())

        self.assertEqual(decision["decision"], "ADD_EXPERT")
        self.assertEqual(decision["source"], "rules")
        self.assertIn("model_decision_overridden_by_rule_guard", decision["parse_warnings"])

    def test_rule_fallback_deepen_for_missing_perspectives(self):
        from Lib.meta_moderator import _rule_based_decision

        decision = _rule_based_decision(
            balance_report=_balance(missing=["engineering"]),
            deliberation_brief=_brief(risks=["Risk"]),
        )

        self.assertEqual(decision["decision"], "DEEPEN")
        self.assertEqual(decision["missing_perspectives"], ["engineering"])

    def test_rule_fallback_deepen_for_dominant_perspective(self):
        from Lib.meta_moderator import _rule_based_decision

        decision = _rule_based_decision(
            balance_report=_balance(dominant=True),
            deliberation_brief=_brief(risks=["Risk"]),
        )

        self.assertEqual(decision["decision"], "DEEPEN")
        self.assertIn("Mitigate dominant perspective: risk", decision["conflicts_to_resolve"])

    def test_rule_fallback_synthesize_when_balance_is_adequate(self):
        from Lib.meta_moderator import _rule_based_decision

        decision = _rule_based_decision(
            balance_report=_balance(),
            deliberation_brief=_brief(risks=["Risk"], must_address=["Risk"]),
        )

        self.assertEqual(decision["decision"], "SYNTHESIZE")

    def test_meta_moderator_deepens_on_unresolved_tradeoff(self):
        from Lib.meta_moderator import run_meta_moderator

        conflict = _conflict_report(
            tradeoffs=[
                {
                    "tradeoff": "speed vs safety",
                    "why_it_matters": "Fast delivery needs risk control.",
                    "roles_involved": ["engineer", "risk_manager"],
                }
            ]
        )
        with patch("Lib.json_retry.send_to_AI", return_value="not json"):
            decision = run_meta_moderator("query", {}, _balance(), _brief(), conflict_report=conflict)

        self.assertEqual(decision["decision"], "DEEPEN")
        self.assertIn("speed vs safety", decision["conflicts_to_resolve"])


if __name__ == "__main__":
    unittest.main()
