import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import DEFAULT, patch


def _sample_expert_bundle():
    return {
        "roles": [{"key": "strategist", "name": "Strategist", "perspective_tag": "strategy"}],
        "contributions": [
            {
                "role_key": "strategist",
                "perspective_tag": "strategy",
                "recommendations": ["Recommendation A"],
                "risks": ["Risk A"],
                "questions": ["Question A"],
            }
        ],
        "synthesis": {
            "recommendations": ["Recommendation A"],
            "risks": ["Risk A"],
            "questions": ["Question A"],
            "perspective_counts": {"strategy": 1},
        },
    }


def _sample_second_expert_bundle():
    return {
        "roles": [{"key": "user_advocate", "name": "User Advocate", "perspective_tag": "user"}],
        "contributions": [
            {
                "role_key": "user_advocate",
                "perspective_tag": "user",
                "recommendations": ["Recommendation B"],
                "risks": ["Risk B"],
                "questions": ["Question B"],
            }
        ],
        "synthesis": {
            "recommendations": ["Recommendation B"],
            "risks": ["Risk B"],
            "questions": ["Question B"],
            "perspective_counts": {"user": 1},
        },
    }


def _sample_merged_expert_bundle():
    return {
        "roles": _sample_expert_bundle()["roles"] + _sample_second_expert_bundle()["roles"],
        "contributions": _sample_expert_bundle()["contributions"] + _sample_second_expert_bundle()["contributions"],
        "synthesis": {
            "recommendations": ["Recommendation A", "Recommendation B"],
            "risks": ["Risk A", "Risk B"],
            "questions": ["Question A", "Question B"],
            "perspective_counts": {"strategy": 1, "user": 1},
        },
    }


def _sample_balance_report():
    return {
        "dominant_perspective_found": False,
        "dominant_perspective": None,
        "missing_perspectives": ["user"],
        "notes": ["Missing user perspective."],
    }


def _sample_updated_balance_report():
    return {
        "dominant_perspective_found": False,
        "dominant_perspective": None,
        "missing_perspectives": [],
        "notes": ["Second round covered user perspective."],
    }


def _sample_plan():
    return {"main_idea": "idea", "steps": [{"number": "1", "title": "step", "substeps": []}]}


def _sample_critique():
    return {"recommendations": ["Improve balance"], "final_score": 8.0}


def _sample_moderated_result():
    return {
        "final_answer": "final answer",
        "reports": [
            {"decision": "REVISE", "avg_score": 6.0, "improvements": ["fix"]},
            {"decision": "ACCEPT", "avg_score": 8.5, "improvements": []},
        ],
        "trace": {"expert_bundle_used": True},
    }


def _sample_dynamic_role_report():
    return {"roles": [], "role_views": [], "rejected_suggestions": [], "warnings": [], "source": "test"}


def _sample_meta_decision(decision="SYNTHESIZE"):
    return {
        "decision": decision,
        "reason": "Meta reason",
        "missing_perspectives": [],
        "conflicts_to_resolve": ["Conflict A"] if decision == "DEEPEN" else [],
        "risks_to_address": ["Risk A"] if decision == "DEEPEN" else [],
        "questions_to_answer": ["Question A"] if decision == "DEEPEN" else [],
        "next_actions": ["Next action"],
        "confidence": 0.8,
        "parse_warnings": [],
        "source": "test",
    }


def _sample_query_intake():
    return {
        "original_query": "raw query",
        "cleaned_query": "cleaned query",
        "task_goal": "Goal A",
        "context": ["Context A"],
        "constraints": ["Constraint A"],
        "success_criteria": ["Success A"],
        "unknowns": ["Unknown A"],
        "user_preferences": ["Preference A"],
        "risk_level": "medium",
        "complexity": "moderate",
        "should_use_cmm": True,
        "parse_warnings": [],
        "source": "test",
    }


def _sample_conflict_report():
    return {
        "agreements": [{"claim": "Agreement A", "supporting_roles": ["strategist"]}],
        "disagreements": [
            {
                "issue": "Disagreement A",
                "positions": [{"role": "strategist", "position": "Position A"}],
                "severity": "medium",
            }
        ],
        "unresolved_tradeoffs": [
            {
                "tradeoff": "Tradeoff A",
                "why_it_matters": "Matters A",
                "roles_involved": ["strategist", "risk_manager"],
            }
        ],
        "premature_consensus_risks": ["Consensus risk A"],
        "blind_spots": ["Blind spot A"],
        "minority_positions": ["Minority A"],
        "questions_for_next_round": ["Question next A"],
        "confidence": 0.7,
        "parse_warnings": [],
        "source": "test",
    }


def _empty_conflict_report():
    return {
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


def _sample_deliberation_bundle():
    return {
        "type": "deliberation_round",
        "roles": [{"key": "strategist", "name": "Strategist", "perspective_tag": "strategy"}],
        "responses": [
            {
                "role_key": "strategist",
                "perspective_tag": "strategy",
                "agreements": ["Agreement A"],
                "disagreements": ["Deliberation disagreement A"],
                "missed_by_others": ["Missed A"],
                "revised_recommendations": ["Revised recommendation A"],
                "new_risks": ["New risk A"],
                "questions_for_group": ["Group question A"],
                "confidence_change": -0.1,
                "parse_warnings": [],
                "source": "test",
            }
        ],
        "synthesis": {
            "agreements": ["Agreement A"],
            "disagreements": ["Deliberation disagreement A"],
            "revised_recommendations": ["Revised recommendation A"],
            "new_risks": ["New risk A"],
            "questions_for_group": ["Group question A"],
        },
    }


def _sample_deliberated_expert_bundle():
    bundle = _sample_expert_bundle()
    bundle["contributions"] = list(bundle["contributions"]) + [
        {
            "role_key": "strategist",
            "perspective_tag": "strategy",
            "contribution_type": "deliberation_response",
            "insights": ["Agreement A", "Deliberation disagreement A", "Missed A"],
            "recommendations": ["Revised recommendation A"],
            "risks": ["New risk A"],
            "questions": ["Group question A"],
            "confidence": 0.4,
        }
    ]
    bundle["synthesis"] = {
        "recommendations": ["Recommendation A", "Revised recommendation A"],
        "risks": ["Risk A", "New risk A"],
        "questions": ["Question A", "Group question A"],
        "perspective_counts": {"strategy": 2},
    }
    return bundle


class OrchestratorTests(unittest.TestCase):
    def _patch_happy_path(self):
        return patch.multiple(
            "Lib.state_machine",
            build_query_intake=DEFAULT,
            route_query=DEFAULT,
            run_direct_answer=DEFAULT,
            generate_dynamic_roles=DEFAULT,
            analyze_conflicts=DEFAULT,
            run_expert_panel=DEFAULT,
            analyze_balance=DEFAULT,
            run_meta_moderator=DEFAULT,
            run_deliberation_round=DEFAULT,
            merge_deliberation_into_bundle=DEFAULT,
            run_targeted_expert_round=DEFAULT,
            merge_expert_bundles=DEFAULT,
            develop_plan=DEFAULT,
            check_plan_and_act=DEFAULT,
            run_moderated_loop=DEFAULT,
        )

    def test_run_cmm_returns_final_answer_and_trace(self):
        from Lib.orchestrator import run_cmm

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["generate_dynamic_roles"].return_value = _sample_dynamic_role_report()
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].return_value = _sample_balance_report()
            mocks["run_meta_moderator"].return_value = _sample_meta_decision()
            mocks["develop_plan"].return_value = _sample_plan()
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            result = run_cmm("raw query")

        self.assertEqual(result["final_answer"], "final answer")
        self.assertEqual(set(result.keys()), {"final_answer", "trace_report", "raw"})
        self.assertIn("trace_report", result)
        self.assertIn("expert_bundle", result["raw"])
        self.assertIn("moderated_result", result["raw"])

    def test_original_query_preserved(self):
        from Lib.orchestrator import run_cmm

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].return_value = _sample_balance_report()
            mocks["run_meta_moderator"].return_value = _sample_meta_decision()
            mocks["develop_plan"].return_value = _sample_plan()
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            result = run_cmm("raw query")

        self.assertEqual(result["trace_report"]["original_query"], "raw query")
        self.assertEqual(result["trace_report"]["formalized_query"], "cleaned query")

    def test_meta_moderator_runs_before_planning(self):
        from Lib.orchestrator import run_cmm

        call_order = []

        def intake(query, model="deepseek-chat"):
            call_order.append("query_intake")
            return _sample_query_intake()

        def experts(query, context=None, max_roles=5, dynamic_roles=None):
            call_order.append("expert_panel")
            return _sample_expert_bundle()

        def balance(bundle, **kwargs):
            call_order.append("balance")
            return _sample_balance_report()

        def conflict(query_intake, expert_bundle, deliberation_brief, model="deepseek-chat"):
            call_order.append("conflict")
            return _sample_conflict_report()

        def meta(**kwargs):
            call_order.append("meta")
            return _sample_meta_decision()

        def plan(query, context=None, depth="detailed"):
            call_order.append("plan")
            return _sample_plan()

        with patch("Lib.state_machine.build_query_intake", side_effect=intake), patch(
            "Lib.state_machine.route_query",
            return_value={
                "mode": "FULL_CMM",
                "reason": "test full path",
                "complexity": "high",
                "needs_expert_panel": True,
                "needs_second_round": True,
                "estimated_cost_class": "L",
                "signals": {},
                "warnings": [],
            },
        ), patch(
            "Lib.state_machine.generate_dynamic_roles", return_value=_sample_dynamic_role_report()
        ), patch(
            "Lib.state_machine.run_expert_panel", side_effect=experts
        ), patch("Lib.state_machine.analyze_balance", side_effect=balance), patch(
            "Lib.state_machine.analyze_conflicts", side_effect=conflict
        ), patch(
            "Lib.state_machine.run_meta_moderator", side_effect=meta
        ), patch(
            "Lib.state_machine.develop_plan", side_effect=plan
        ), patch(
            "Lib.state_machine.check_plan_and_act",
            return_value={"status": "ready", "critique": _sample_critique()},
        ), patch(
            "Lib.state_machine.run_moderated_loop", return_value=_sample_moderated_result()
        ):
            run_cmm("raw query")

        self.assertLess(call_order.index("expert_panel"), call_order.index("plan"))
        self.assertLess(call_order.index("balance"), call_order.index("plan"))
        self.assertLess(call_order.index("conflict"), call_order.index("meta"))
        self.assertLess(call_order.index("meta"), call_order.index("plan"))

    def test_trace_contains_roles_balance_plan_moderation(self):
        from Lib.orchestrator import run_cmm

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].side_effect = [_sample_balance_report(), _sample_updated_balance_report()]
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("DEEPEN")
            mocks["run_targeted_expert_round"].return_value = _sample_second_expert_bundle()
            mocks["merge_expert_bundles"].return_value = _sample_merged_expert_bundle()
            mocks["develop_plan"].return_value = _sample_plan()
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            trace = run_cmm("raw query")["trace_report"]

        self.assertEqual(len(trace["expert_rounds"]), 2)
        self.assertEqual(trace["expert_rounds"][0], _sample_expert_bundle())
        self.assertEqual(trace["expert_rounds"][1], _sample_second_expert_bundle())
        self.assertEqual(trace["roles_used"][0], _sample_expert_bundle()["roles"][0])
        self.assertEqual(trace["roles_used"][1], _sample_second_expert_bundle()["roles"][0])
        self.assertEqual(trace["balance_reports"], [_sample_balance_report(), _sample_updated_balance_report()])
        self.assertEqual(trace["plan"], _sample_plan())
        self.assertEqual(trace["plan_critique"], _sample_critique())
        self.assertEqual(trace["moderation_reports"], _sample_moderated_result()["reports"])
        self.assertEqual(trace["revision_count"], 1)
        self.assertEqual(trace["final_confidence"], 0.85)
        self.assertEqual(trace["meta_moderation_decisions"], [_sample_meta_decision("DEEPEN")])
        self.assertEqual(trace["conflicts_to_resolve"], ["Conflict A"])
        self.assertEqual(trace["risks_to_address"], ["Risk A"])

    def test_plan_rejected_returns_structured_failure(self):
        from Lib.orchestrator import run_cmm

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].return_value = _sample_balance_report()
            mocks["run_meta_moderator"].return_value = _sample_meta_decision()
            mocks["develop_plan"].return_value = _sample_plan()
            mocks["check_plan_and_act"].return_value = {
                "status": "rejected",
                "critique": _sample_critique(),
                "reason": "too weak",
            }

            result = run_cmm("raw query")

        self.assertEqual(result["final_answer"], "")
        self.assertEqual(result["trace_report"]["moderation_reports"], [])
        self.assertIn("plan_rejected", result["trace_report"]["warnings"][-1])
        mocks["run_moderated_loop"].assert_not_called()

    def test_deepen_decision_runs_second_round_and_enriches_planner_context(self):
        from Lib.orchestrator import run_cmm

        captured = {}

        def capture_plan(query, context=None, depth="detailed"):
            captured["context"] = context
            return _sample_plan()

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].side_effect = [_sample_balance_report(), _sample_updated_balance_report()]
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("DEEPEN")
            mocks["run_targeted_expert_round"].return_value = _sample_second_expert_bundle()
            mocks["merge_expert_bundles"].return_value = _sample_merged_expert_bundle()
            mocks["develop_plan"].side_effect = capture_plan
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            result = run_cmm("raw query")

        brief = captured["context"]["deliberation_brief"]
        self.assertIn("Risk A", brief["must_address"])
        self.assertIn("Risk B", brief["must_address"])
        self.assertIn("Question A", brief["must_address"])
        self.assertIn("Recommendation B", brief["expert_recommendations"])
        self.assertEqual(captured["context"]["query_intake"]["constraints"], ["Constraint A"])
        self.assertEqual(len(result["trace_report"]["expert_rounds"]), 2)
        self.assertEqual(len(result["trace_report"]["balance_reports"]), 2)
        self.assertNotIn("second_pass_deferred", " ".join(result["trace_report"]["warnings"]))
        mocks["run_targeted_expert_round"].assert_called_once()

    def test_synthesize_decision_does_not_run_second_round(self):
        from Lib.orchestrator import run_cmm

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].return_value = _sample_balance_report()
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("SYNTHESIZE")
            mocks["develop_plan"].return_value = _sample_plan()
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            trace = run_cmm("raw query")["trace_report"]

        self.assertEqual(len(trace["expert_rounds"]), 1)
        self.assertEqual(len(trace["balance_reports"]), 1)
        mocks["run_targeted_expert_round"].assert_not_called()

    def test_run_cmm_trace_contains_query_intake(self):
        from Lib.orchestrator import run_cmm

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].return_value = _sample_balance_report()
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("SYNTHESIZE")
            mocks["develop_plan"].return_value = _sample_plan()
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            trace = run_cmm("raw query")["trace_report"]

        self.assertEqual(trace["query_intake"], _sample_query_intake())
        self.assertEqual(trace["original_query"], "raw query")
        self.assertEqual(trace["formalized_query"], "cleaned query")

    def test_run_cmm_passes_intake_to_expert_panel_context(self):
        from Lib.orchestrator import run_cmm

        captured = {}

        def capture_experts(query, context=None, max_roles=5, dynamic_roles=None):
            captured["query"] = query
            captured["context"] = context
            return _sample_expert_bundle()

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["run_expert_panel"].side_effect = capture_experts
            mocks["analyze_balance"].return_value = _sample_balance_report()
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("SYNTHESIZE")
            mocks["develop_plan"].return_value = _sample_plan()
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            run_cmm("raw query")

        self.assertEqual(captured["query"], "raw query")
        self.assertEqual(captured["context"]["original_query"], "raw query")
        self.assertEqual(captured["context"]["cleaned_query"], "cleaned query")
        self.assertEqual(captured["context"]["query_intake"]["constraints"], ["Constraint A"])
        self.assertIn("Original query is authoritative", captured["context"]["instruction"])

    def test_run_cmm_passes_intake_to_planner_context(self):
        from Lib.orchestrator import run_cmm

        captured = {}

        def capture_plan(query, context=None, depth="detailed"):
            captured["query"] = query
            captured["context"] = context
            return _sample_plan()

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].return_value = _sample_balance_report()
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("SYNTHESIZE")
            mocks["develop_plan"].side_effect = capture_plan
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            run_cmm("raw query")

        self.assertEqual(captured["query"], "raw query")
        self.assertTrue(captured["context"]["original_query_is_authoritative"])
        self.assertEqual(captured["context"]["query_intake"]["success_criteria"], ["Success A"])
        self.assertEqual(captured["context"]["deliberation_brief"]["constraints"], ["Constraint A"])

    def test_run_cmm_trace_contains_conflict_reports(self):
        from Lib.orchestrator import run_cmm

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["analyze_conflicts"].return_value = _sample_conflict_report()
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].return_value = _sample_balance_report()
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("SYNTHESIZE")
            mocks["develop_plan"].return_value = _sample_plan()
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            trace = run_cmm("raw query")["trace_report"]

        self.assertEqual(trace["conflict_reports"], [_sample_conflict_report()])
        self.assertEqual(trace["unresolved_tradeoffs"], _sample_conflict_report()["unresolved_tradeoffs"])
        self.assertEqual(trace["premature_consensus_risks"], ["Consensus risk A"])
        self.assertEqual(trace["blind_spots"], ["Blind spot A"])

    def test_run_cmm_conflict_exception_uses_stable_fallback_source(self):
        from Lib.orchestrator import run_cmm

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["analyze_conflicts"].side_effect = RuntimeError("conflict analyzer unavailable")
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].return_value = _sample_balance_report()
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("SYNTHESIZE")
            mocks["develop_plan"].return_value = _sample_plan()
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            trace = run_cmm("raw query")["trace_report"]

        self.assertEqual(trace["conflict_reports"][0]["source"], "fallback")
        self.assertEqual(trace["conflict_reports"][0]["parse_warnings"], ["conflict_analysis_failed"])
        self.assertEqual(trace["blind_spots"], ["Conflict analysis failed."])

    def test_planner_context_contains_conflict_report(self):
        from Lib.orchestrator import run_cmm

        captured = {}

        def capture_plan(query, context=None, depth="detailed"):
            captured["context"] = context
            return _sample_plan()

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["analyze_conflicts"].return_value = _sample_conflict_report()
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].return_value = _sample_balance_report()
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("SYNTHESIZE")
            mocks["develop_plan"].side_effect = capture_plan
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            run_cmm("raw query")

        self.assertEqual(captured["context"]["conflict_report"], _sample_conflict_report())
        brief = captured["context"]["deliberation_brief"]
        self.assertEqual(brief["unresolved_tradeoffs"], _sample_conflict_report()["unresolved_tradeoffs"])
        self.assertIn("Address trade-off: Tradeoff A", brief["must_address"])

    def test_second_round_context_contains_conflict_report(self):
        from Lib.orchestrator import run_cmm

        captured = {}

        def capture_second_round(query, roles, context, model="deepseek-chat"):
            captured["context"] = context
            return _sample_second_expert_bundle()

        first_report = _sample_conflict_report()
        second_report = dict(_sample_conflict_report())
        second_report["unresolved_tradeoffs"] = []
        second_report["blind_spots"] = ["Second blind spot"]

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["analyze_conflicts"].side_effect = [first_report, second_report]
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].side_effect = [_sample_balance_report(), _sample_updated_balance_report()]
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("DEEPEN")
            mocks["run_targeted_expert_round"].side_effect = capture_second_round
            mocks["develop_plan"].return_value = _sample_plan()
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            trace = run_cmm("raw query")["trace_report"]

        self.assertEqual(captured["context"]["conflict_report"], second_report)
        self.assertGreaterEqual(len(trace["conflict_reports"]), 2)
        self.assertEqual(trace["conflict_reports"][1], second_report)

    def test_run_cmm_trace_contains_deliberation_round_when_conflict_requires_it(self):
        from Lib.orchestrator import run_cmm

        after_deliberation = dict(_sample_conflict_report())
        after_deliberation["disagreements"] = []
        after_deliberation["unresolved_tradeoffs"] = []
        after_deliberation["premature_consensus_risks"] = []
        after_deliberation["blind_spots"] = []

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["analyze_conflicts"].side_effect = [_sample_conflict_report(), after_deliberation, _empty_conflict_report()]
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].side_effect = [
                _sample_balance_report(),
                _sample_updated_balance_report(),
                _sample_updated_balance_report(),
            ]
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("DEEPEN")
            mocks["run_deliberation_round"].return_value = _sample_deliberation_bundle()
            mocks["merge_deliberation_into_bundle"].return_value = _sample_deliberated_expert_bundle()
            mocks["run_targeted_expert_round"].return_value = _sample_second_expert_bundle()
            mocks["merge_expert_bundles"].return_value = _sample_deliberated_expert_bundle()
            mocks["develop_plan"].return_value = _sample_plan()
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            trace = run_cmm("raw query")["trace_report"]

        self.assertEqual(trace["deliberation_rounds"], [_sample_deliberation_bundle()])
        self.assertEqual(trace["deliberation_revisions"][0]["role_key"], "strategist")
        self.assertEqual(trace["deliberation_revisions"][0]["new_risks"], ["New risk A"])

    def test_conflict_report_recomputed_after_deliberation(self):
        from Lib.orchestrator import run_cmm

        first_report = _sample_conflict_report()
        second_report = _empty_conflict_report()

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["analyze_conflicts"].side_effect = [first_report, second_report, _empty_conflict_report()]
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].side_effect = [
                _sample_balance_report(),
                _sample_updated_balance_report(),
                _sample_updated_balance_report(),
            ]
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("DEEPEN")
            mocks["run_deliberation_round"].return_value = _sample_deliberation_bundle()
            mocks["merge_deliberation_into_bundle"].return_value = _sample_deliberated_expert_bundle()
            mocks["run_targeted_expert_round"].return_value = _sample_second_expert_bundle()
            mocks["merge_expert_bundles"].return_value = _sample_deliberated_expert_bundle()
            mocks["develop_plan"].return_value = _sample_plan()
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            trace = run_cmm("raw query")["trace_report"]

        self.assertEqual(trace["conflict_reports"][:2], [first_report, second_report])

    def test_planner_context_contains_deliberation_revisions(self):
        from Lib.orchestrator import run_cmm

        captured = {}

        def capture_plan(query, context=None, depth="detailed"):
            captured["context"] = context
            return _sample_plan()

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["analyze_conflicts"].side_effect = [_sample_conflict_report(), _empty_conflict_report(), _empty_conflict_report()]
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].side_effect = [
                _sample_balance_report(),
                _sample_updated_balance_report(),
                _sample_updated_balance_report(),
            ]
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("DEEPEN")
            mocks["run_deliberation_round"].return_value = _sample_deliberation_bundle()
            mocks["merge_deliberation_into_bundle"].return_value = _sample_deliberated_expert_bundle()
            mocks["run_targeted_expert_round"].return_value = _sample_second_expert_bundle()
            mocks["merge_expert_bundles"].return_value = _sample_deliberated_expert_bundle()
            mocks["develop_plan"].side_effect = capture_plan
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            run_cmm("raw query")

        brief = captured["context"]["deliberation_brief"]
        self.assertIn("Revised recommendation A", brief["revised_recommendations"])
        self.assertIn("New risk A", brief["new_risks"])
        self.assertIn("Address deliberation risk: New risk A", brief["must_address"])

    def test_no_deliberation_round_when_no_conflict_and_meta_synthesizes(self):
        from Lib.orchestrator import run_cmm

        with self._patch_happy_path() as mocks:
            mocks["build_query_intake"].return_value = _sample_query_intake()
            mocks["analyze_conflicts"].return_value = _empty_conflict_report()
            mocks["run_expert_panel"].return_value = _sample_expert_bundle()
            mocks["analyze_balance"].return_value = _sample_balance_report()
            mocks["run_meta_moderator"].return_value = _sample_meta_decision("SYNTHESIZE")
            mocks["develop_plan"].return_value = _sample_plan()
            mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _sample_critique()}
            mocks["run_moderated_loop"].return_value = _sample_moderated_result()

            trace = run_cmm("raw query")["trace_report"]

        self.assertEqual(trace["deliberation_rounds"], [])
        mocks["run_deliberation_round"].assert_not_called()

    def test_main_imports_without_side_effect_api_call(self):
        import main

        fake_result = {
            "final_answer": "cli answer",
            "trace_report": {
                "roles_used": [],
                "revision_count": 0,
                "warnings": [],
            },
        }

        with patch("builtins.input", return_value="query"), patch.object(
            main, "run_cmm", return_value=fake_result
        ) as run_cmm_mock, redirect_stdout(io.StringIO()) as output:
            main.main()

        self.assertIn("cli answer", output.getvalue())
        run_cmm_mock.assert_called_once_with("query")

    def test_run_cmm_accepts_route_mode_keyword(self):
        from Lib.orchestrator import run_cmm

        with patch("Lib.orchestrator.run_cmm_state_machine", return_value={"final_answer": "", "trace_report": {}, "raw": {}}) as mock:
            run_cmm("raw query", route_mode="FULL_CMM")

        mock.assert_called_once_with(
            "raw query",
            max_iters=2,
            model="deepseek-chat",
            route_mode="FULL_CMM",
            parallel_mode="SEQUENTIAL",
            max_workers=None,
        )

    def test_run_cmm_accepts_parallel_options(self):
        from Lib.orchestrator import run_cmm

        with patch("Lib.orchestrator.run_cmm_state_machine", return_value={"final_answer": "", "trace_report": {}, "raw": {}}) as mock:
            run_cmm("raw query", route_mode="FULL_CMM", parallel_mode="THREADS", max_workers=3)

        mock.assert_called_once_with(
            "raw query",
            max_iters=2,
            model="deepseek-chat",
            route_mode="FULL_CMM",
            parallel_mode="THREADS",
            max_workers=3,
        )


if __name__ == "__main__":
    unittest.main()
