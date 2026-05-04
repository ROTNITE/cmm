import json
import unittest
from unittest.mock import patch


def _expert_bundle():
    return {
        "roles": [
            {"key": "engineer", "name": "Engineer", "perspective_tag": "engineering"},
            {"key": "risk_manager", "name": "Risk Manager", "perspective_tag": "risk"},
        ],
        "contributions": [
            {
                "role_key": "engineer",
                "perspective_tag": "engineering",
                "insights": ["Implementation is straightforward"],
                "recommendations": ["Ship quickly with a small MVP"],
                "risks": ["Minor implementation risk"],
                "questions": ["What is the deadline?"],
                "confidence": 0.7,
            },
            {
                "role_key": "risk_manager",
                "perspective_tag": "risk",
                "insights": ["Rollback matters"],
                "recommendations": ["Add rollback before launch"],
                "risks": ["Fast launch can create operational risk"],
                "questions": ["What rollback threshold is acceptable?"],
                "confidence": 0.8,
            },
        ],
        "synthesis": {
            "recommendations": ["Ship quickly with a small MVP", "Add rollback before launch"],
            "risks": ["Minor implementation risk", "Fast launch can create operational risk"],
            "questions": ["What is the deadline?", "What rollback threshold is acceptable?"],
            "perspective_counts": {"engineering": 1, "risk": 1},
        },
    }


def _conflict_report():
    return {
        "agreements": [],
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
        "unresolved_tradeoffs": [],
        "premature_consensus_risks": [],
        "blind_spots": [],
        "minority_positions": [],
        "questions_for_next_round": [],
        "confidence": 0.7,
        "parse_warnings": [],
        "source": "rules",
    }


def _model_payload():
    return {
        "agreements": ["Rollback is useful"],
        "disagreements": ["Shipping without guardrails is too risky"],
        "missed_by_others": ["Operational owner is unspecified"],
        "revised_recommendations": ["Ship MVP with rollback gates"],
        "new_risks": ["Rollback ownership may be unclear"],
        "questions_for_group": ["Who owns rollback?"],
        "confidence_change": -0.2,
    }


class DeliberationRoundTests(unittest.TestCase):
    def test_select_deliberation_roles_from_disagreement_positions(self):
        from Lib.deliberation_round import select_deliberation_roles

        roles = select_deliberation_roles(_expert_bundle(), _conflict_report())

        self.assertIn("engineer", [role.key for role in roles])
        self.assertIn("risk_manager", [role.key for role in roles])

    def test_select_deliberation_roles_for_premature_consensus(self):
        from Lib.deliberation_round import select_deliberation_roles

        conflict = dict(_conflict_report())
        conflict["disagreements"] = []
        conflict["premature_consensus_risks"] = ["Consensus is shallow"]

        roles = select_deliberation_roles(_expert_bundle(), conflict)

        self.assertIn("risk_manager", [role.key for role in roles])
        self.assertIn("strategist", [role.key for role in roles])

    def test_run_deliberation_round_passes_other_roles_synthesis(self):
        from Lib.deliberation_round import run_deliberation_round

        captured = {}

        def fake_send(user_prompt, system_prompt, temp, tokens, model):
            captured["user_prompt"] = user_prompt
            captured["system_prompt"] = system_prompt
            return json.dumps(_model_payload())

        with patch("Lib.deliberation_round.send_to_AI", side_effect=fake_send):
            bundle = run_deliberation_round(
                query="raw query",
                query_intake={"cleaned_query": "cleaned"},
                expert_bundle=_expert_bundle(),
                deliberation_brief={"must_address": ["Launch speed"]},
                conflict_report=_conflict_report(),
                max_roles=1,
            )

        self.assertEqual(bundle["type"], "deliberation_round")
        self.assertIn("Ship quickly with a small MVP", captured["user_prompt"])
        self.assertIn("Add rollback before launch", captured["user_prompt"])
        self.assertIn("You must respond to other experts' positions", captured["system_prompt"])

    def test_run_deliberation_round_parses_valid_json(self):
        from Lib.deliberation_round import run_deliberation_round

        with patch("Lib.deliberation_round.send_to_AI", return_value=json.dumps(_model_payload())):
            bundle = run_deliberation_round(
                query="raw query",
                query_intake={},
                expert_bundle=_expert_bundle(),
                deliberation_brief={},
                conflict_report=_conflict_report(),
                max_roles=1,
            )

        response = bundle["responses"][0]
        self.assertEqual(response["role_key"], "engineer")
        self.assertEqual(response["agreements"], ["Rollback is useful"])
        self.assertEqual(response["revised_recommendations"], ["Ship MVP with rollback gates"])
        self.assertEqual(response["new_risks"], ["Rollback ownership may be unclear"])
        self.assertEqual(response["confidence_change"], -0.2)
        self.assertEqual(response["source"], "model")

    def test_run_deliberation_round_parses_markdown_json(self):
        from Lib.deliberation_round import run_deliberation_round

        raw = "```json\n" + json.dumps(_model_payload()) + "\n```"
        with patch("Lib.deliberation_round.send_to_AI", return_value=raw):
            bundle = run_deliberation_round(
                query="raw query",
                query_intake={},
                expert_bundle=_expert_bundle(),
                deliberation_brief={},
                conflict_report=_conflict_report(),
                max_roles=1,
            )

        self.assertEqual(bundle["responses"][0]["questions_for_group"], ["Who owns rollback?"])

    def test_run_deliberation_round_invalid_json_fallback(self):
        from Lib.deliberation_round import run_deliberation_round

        with patch("Lib.deliberation_round.send_to_AI", return_value="not json"):
            bundle = run_deliberation_round(
                query="raw query",
                query_intake={},
                expert_bundle=_expert_bundle(),
                deliberation_brief={},
                conflict_report=_conflict_report(),
                max_roles=1,
            )

        response = bundle["responses"][0]
        self.assertEqual(response["source"], "fallback")
        self.assertEqual(response["new_risks"], ["deliberation_response_failed"])
        self.assertIn("deliberation_json_parse_failed", response["parse_warnings"])

    def test_merge_deliberation_into_bundle_adds_revised_recommendations(self):
        from Lib.deliberation_round import merge_deliberation_into_bundle

        deliberation_bundle = {
            "type": "deliberation_round",
            "roles": [{"key": "engineer", "name": "Engineer", "perspective_tag": "engineering"}],
            "responses": [
                {
                    "role_key": "engineer",
                    "perspective_tag": "engineering",
                    "agreements": ["Rollback is useful"],
                    "disagreements": ["Need stronger guardrails"],
                    "missed_by_others": ["Owner missing"],
                    "revised_recommendations": ["Ship MVP with rollback gates"],
                    "new_risks": ["Rollback ownership may be unclear"],
                    "questions_for_group": ["Who owns rollback?"],
                    "confidence_change": -0.1,
                    "parse_warnings": [],
                    "source": "model",
                }
            ],
            "synthesis": {},
        }

        merged = merge_deliberation_into_bundle(_expert_bundle(), deliberation_bundle)

        self.assertEqual(len(merged["contributions"]), 3)
        self.assertIn("Ship quickly with a small MVP", merged["synthesis"]["recommendations"])
        self.assertIn("Ship MVP with rollback gates", merged["synthesis"]["recommendations"])
        self.assertIn("Rollback ownership may be unclear", merged["synthesis"]["risks"])
        self.assertIn("Who owns rollback?", merged["synthesis"]["questions"])
        self.assertEqual(merged["contributions"][-1]["contribution_type"], "deliberation_response")


if __name__ == "__main__":
    unittest.main()
