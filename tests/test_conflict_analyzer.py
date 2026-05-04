import json
import unittest
from unittest.mock import patch


def _bundle(recommendations=None, risks=None, questions=None):
    recommendations = recommendations or {
        "engineer": ["Ship quickly with a small MVP"],
        "risk_manager": ["Add rollback and safety review before launch"],
    }
    risks = risks or {"risk_manager": ["Fast launch can create operational risk"]}
    questions = questions or {}
    contributions = []
    for role, recs in recommendations.items():
        contributions.append(
            {
                "role_key": role,
                "perspective_tag": role,
                "recommendations": recs,
                "risks": risks.get(role, []),
                "questions": questions.get(role, []),
            }
        )
    return {
        "roles": [{"key": role, "perspective_tag": role} for role in recommendations],
        "contributions": contributions,
        "synthesis": {},
    }


class ConflictAnalyzerTests(unittest.TestCase):
    def test_conflict_analyzer_parses_valid_json(self):
        from Lib.conflict_analyzer import analyze_conflicts

        payload = {
            "agreements": [{"claim": "Use phased rollout", "supporting_roles": ["engineer", "risk_manager"]}],
            "disagreements": [
                {
                    "issue": "Launch speed",
                    "positions": [
                        {"role": "engineer", "position": "Ship quickly"},
                        {"role": "risk_manager", "position": "Add controls"},
                    ],
                    "severity": "high",
                }
            ],
            "unresolved_tradeoffs": [
                {
                    "tradeoff": "speed vs safety",
                    "why_it_matters": "A fast launch can increase risk.",
                    "roles_involved": ["engineer", "risk_manager"],
                }
            ],
            "premature_consensus_risks": ["Consensus is shallow"],
            "blind_spots": ["No rollout metrics"],
            "minority_positions": ["Risk manager is more cautious"],
            "questions_for_next_round": ["What rollback threshold is acceptable?"],
            "confidence": 0.85,
        }

        with patch("Lib.conflict_analyzer.send_to_AI", return_value=json.dumps(payload)):
            report = analyze_conflicts({"complexity": "complex"}, _bundle(), {})

        self.assertEqual(report["source"], "model")
        self.assertEqual(report["confidence"], 0.85)
        self.assertEqual(report["disagreements"][0]["severity"], "high")
        self.assertEqual(report["unresolved_tradeoffs"][0]["tradeoff"], "speed vs safety")

    def test_conflict_analyzer_parses_markdown_json(self):
        from Lib.conflict_analyzer import analyze_conflicts

        payload = {
            "agreements": [],
            "disagreements": [],
            "unresolved_tradeoffs": [],
            "premature_consensus_risks": [],
            "blind_spots": ["Blind spot"],
            "minority_positions": [],
            "questions_for_next_round": [],
            "confidence": 0.5,
        }
        raw = "```json\n" + json.dumps(payload) + "\n```"

        with patch("Lib.conflict_analyzer.send_to_AI", return_value=raw):
            report = analyze_conflicts({"complexity": "moderate"}, _bundle(), {})

        self.assertEqual(report["source"], "model")
        self.assertEqual(report["blind_spots"], ["Blind spot"])

    def test_conflict_analyzer_invalid_json_fallback(self):
        from Lib.conflict_analyzer import analyze_conflicts

        with patch("Lib.conflict_analyzer.send_to_AI", return_value="not json"):
            report = analyze_conflicts({"complexity": "moderate"}, _bundle(), {})

        self.assertEqual(report["source"], "rules")
        self.assertIn("conflict_model_invalid_json", report["parse_warnings"])

    def test_different_recommendations_create_disagreement_or_tradeoff(self):
        from Lib.conflict_analyzer import analyze_conflicts

        with patch("Lib.conflict_analyzer.send_to_AI", return_value="not json"):
            report = analyze_conflicts({"complexity": "complex"}, _bundle(), {})

        self.assertTrue(report["disagreements"] or report["unresolved_tradeoffs"])

    def test_identical_recommendations_create_premature_consensus_for_complex_query(self):
        from Lib.conflict_analyzer import analyze_conflicts

        bundle = _bundle(
            recommendations={
                "strategist": ["Do a phased plan"],
                "engineer": ["Do a phased plan"],
                "risk_manager": ["Do a phased plan"],
            },
            risks={},
        )
        with patch("Lib.conflict_analyzer.send_to_AI", return_value="not json"):
            report = analyze_conflicts({"complexity": "complex"}, bundle, {})

        self.assertTrue(report["premature_consensus_risks"])


if __name__ == "__main__":
    unittest.main()
