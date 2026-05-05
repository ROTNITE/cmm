import json
import unittest
from unittest.mock import DEFAULT, patch


def _contribution(role, tag, recommendations=None, risks=None, insights=None, questions=None):
    return {
        "role_key": role,
        "perspective_tag": tag,
        "recommendations": recommendations or [],
        "risks": risks or [],
        "insights": insights or [],
        "questions": questions or [],
        "confidence": 0.8,
    }


def _full_bundle():
    return {
        "roles": [
            {"key": "strategist", "perspective_tag": "strategy"},
            {"key": "engineer", "perspective_tag": "engineering"},
            {"key": "risk_manager", "perspective_tag": "risk"},
            {"key": "user_advocate", "perspective_tag": "user"},
        ],
        "contributions": [
            _contribution(
                "strategist",
                "strategy",
                recommendations=["Define KPI targets for a 4-week limited budget pilot"],
                insights=["Use evidence from student attendance data"],
                questions=["Which student segment is priority?"],
            ),
            _contribution(
                "engineer",
                "engineering",
                recommendations=["Build a measurable rollout checklist with owner and rollback step"],
                risks=["Operations delay if ownership is unclear"],
                insights=["Test the pilot before scaling"],
            ),
            _contribution(
                "risk_manager",
                "risk",
                recommendations=["Mitigate privacy risk with compliance review and data minimization"],
                risks=["Privacy compliance failure could harm students"],
            ),
            _contribution(
                "user_advocate",
                "user",
                recommendations=["Interview students and measure accessibility barriers weekly"],
                insights=["Students need clear communication and inclusive access"],
            ),
        ],
    }


class BalanceAnalyzerV2Tests(unittest.TestCase):
    def test_backward_compatible_keys_and_dominance(self):
        from Lib.balance_analyzer import analyze_balance

        bundle = {
            "contributions": [
                _contribution("r1", "risk"),
                _contribution("r2", "risk"),
                _contribution("r3", "risk"),
                _contribution("s1", "strategy"),
            ]
        }

        report = analyze_balance(bundle)

        for key in ("dominant_perspective_found", "dominant_perspective", "missing_perspectives", "notes"):
            self.assertIn(key, report)
        self.assertTrue(report["dominant_perspective_found"])
        self.assertEqual(report["dominant_perspective"], "risk")
        self.assertEqual(report["dominance"]["dominant_perspective"], "risk")

    def test_perspective_coverage_scores_rich_contributions_higher_than_fallback(self):
        from Lib.balance_analyzer import analyze_balance

        report = analyze_balance(
            {
                "contributions": [
                    _contribution(
                        "strategist",
                        "strategy",
                        recommendations=["Define measurable rollout sequence"],
                        risks=["Budget risk"],
                        insights=["Evidence from pilot data"],
                        questions=["Who owns rollout?"],
                    ),
                    _contribution("engineer", "engineering", risks=["expert_execution_failed"]),
                ]
            }
        )

        self.assertGreater(report["perspective_coverage"]["strategy"], report["perspective_coverage"]["engineering"])
        self.assertLessEqual(report["perspective_coverage"]["engineering"], 0.25)

    def test_constraint_coverage_and_uncovered_constraint_blind_spot(self):
        from Lib.balance_analyzer import analyze_balance

        report = analyze_balance(
            _full_bundle(),
            query_intake={"constraints": ["limited budget", "must support rural learners"]},
        )

        covered = {item["constraint"]: item for item in report["constraint_coverage"]}
        self.assertTrue(covered["limited budget"]["covered"])
        self.assertFalse(covered["must support rural learners"]["covered"])
        self.assertTrue(any("must support rural learners" in item for item in report["blind_spots"]))
        self.assertEqual(report["recommended_action"], "DEEPEN")

    def test_stakeholder_coverage_detects_students(self):
        from Lib.balance_analyzer import analyze_balance

        report = analyze_balance(
            _full_bundle(),
            query_intake={"task_goal": "Improve engagement for students", "context": ["university"]},
        )

        students = [item for item in report["stakeholder_coverage"] if item["stakeholder"] == "students"][0]
        self.assertTrue(students["covered"])
        self.assertIn("user_advocate", students["supporting_roles"])

    def test_risk_severity_distribution(self):
        from Lib.balance_analyzer import analyze_balance

        report = analyze_balance(
            {
                "contributions": [
                    _contribution(
                        "risk_manager",
                        "risk",
                        risks=[
                            "Legal privacy compliance failure",
                            "Budget and operations delay",
                            "Minor wording issue",
                            "Unclear concern",
                        ],
                    )
                ]
            }
        )

        self.assertEqual(report["risk_severity_distribution"]["high"], 1)
        self.assertEqual(report["risk_severity_distribution"]["medium"], 1)
        self.assertEqual(report["risk_severity_distribution"]["low"], 1)
        self.assertEqual(report["risk_severity_distribution"]["unknown"], 1)

    def test_argument_quality_rewards_concrete_actionable_unique_items(self):
        from Lib.balance_analyzer import analyze_balance

        good = analyze_balance(_full_bundle())
        generic = analyze_balance(
            {
                "contributions": [
                    _contribution("strategist", "strategy", recommendations=["Consider risks"]),
                    _contribution("engineer", "engineering", recommendations=["Consider risks"]),
                    _contribution("risk_manager", "risk", recommendations=["Consider risks"]),
                    _contribution("user_advocate", "user", recommendations=["Consider risks"]),
                ]
            }
        )

        self.assertGreater(good["argument_quality"]["actionability"], generic["argument_quality"]["actionability"])
        self.assertGreater(good["argument_quality"]["novelty"], generic["argument_quality"]["novelty"])

    def test_recommended_action_synthesize_when_quality_is_adequate(self):
        from Lib.balance_analyzer import analyze_balance

        report = analyze_balance(
            _full_bundle(),
            query_intake={"constraints": ["limited budget"], "task_goal": "Improve engagement for students"},
        )

        self.assertEqual(report["missing_perspectives"], [])
        self.assertEqual(report["blind_spots"], [])
        self.assertEqual(report["recommended_action"], "SYNTHESIZE")

    def test_report_is_json_serializable(self):
        from Lib.balance_analyzer import analyze_balance

        report = analyze_balance(_full_bundle(), query_intake={"constraints": ["limited budget"]})

        json.dumps(report, ensure_ascii=False)

    def test_state_machine_passes_query_intake_to_balance_analyzer(self):
        from Lib.state_machine import run_cmm_state_machine

        captured = {}

        def capture_balance(bundle, **kwargs):
            captured["kwargs"] = kwargs
            return {
                "dominant_perspective_found": False,
                "dominant_perspective": None,
                "missing_perspectives": [],
                "notes": [],
                "perspective_coverage": {"strategy": 1.0},
                "stakeholder_coverage": [],
                "constraint_coverage": [],
                "risk_severity_distribution": {"low": 0, "medium": 0, "high": 0, "unknown": 0},
                "argument_quality": {
                    "evidence_level": 1.0,
                    "specificity": 1.0,
                    "actionability": 1.0,
                    "novelty": 1.0,
                    "tradeoff_awareness": 0.0,
                },
                "dominance": {"dominant_perspective": None, "dominant_ratio": 0.0, "counts": {}, "total_contributions": 0},
                "blind_spots": [],
                "recommended_action": "SYNTHESIZE",
            }

        with patch.multiple(
            "Lib.state_machine",
            build_query_intake=DEFAULT,
            generate_dynamic_roles=DEFAULT,
            run_expert_panel=DEFAULT,
            analyze_balance=DEFAULT,
            analyze_conflicts=DEFAULT,
            run_meta_moderator=DEFAULT,
            develop_plan=DEFAULT,
            check_plan_and_act=DEFAULT,
            run_moderated_loop=DEFAULT,
        ) as mocks:
            mocks["build_query_intake"].return_value = {"cleaned_query": "query", "constraints": ["limited budget"]}
            mocks["generate_dynamic_roles"].return_value = {"roles": [], "role_views": [], "warnings": [], "rejected_suggestions": []}
            mocks["run_expert_panel"].return_value = _full_bundle()
            mocks["analyze_balance"].side_effect = capture_balance
            mocks["analyze_conflicts"].return_value = {
                "agreements": [],
                "disagreements": [],
                "unresolved_tradeoffs": [],
                "premature_consensus_risks": [],
                "blind_spots": [],
                "minority_positions": [],
                "questions_for_next_round": [],
                "confidence": 0.8,
                "parse_warnings": [],
                "source": "test",
            }
            mocks["run_meta_moderator"].return_value = {"decision": "SYNTHESIZE"}
            mocks["develop_plan"].return_value = {"steps": []}
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": {}}
            mocks["run_moderated_loop"].return_value = {"final_answer": "ok", "reports": []}

            trace = run_cmm_state_machine("query")["trace_report"]

        self.assertEqual(captured["kwargs"]["query_intake"]["constraints"], ["limited budget"])
        self.assertIn("perspective_coverage", trace["balance_reports"][0])

    def test_meta_moderator_uses_balance_recommended_action(self):
        from Lib.meta_moderator import _rule_based_decision

        add = _rule_based_decision(
            balance_report={
                "recommended_action": "ADD_EXPERT",
                "missing_perspectives": ["legal"],
                "blind_spots": ["Legal perspective missing."],
            },
            deliberation_brief={"expert_risks": [], "expert_questions": []},
        )
        deepen = _rule_based_decision(
            balance_report={
                "recommended_action": "DEEPEN",
                "missing_perspectives": [],
                "blind_spots": ["Constraint not covered."],
                "argument_quality": {"specificity": 0.2},
            },
            deliberation_brief={"expert_risks": [], "expert_questions": []},
        )

        self.assertEqual(add["decision"], "ADD_EXPERT")
        self.assertEqual(deepen["decision"], "DEEPEN")


if __name__ == "__main__":
    unittest.main()
