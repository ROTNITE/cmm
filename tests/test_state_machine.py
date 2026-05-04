import unittest
from unittest.mock import DEFAULT, patch


def _query_intake():
    return {
        "original_query": "raw query",
        "cleaned_query": "cleaned query",
        "task_goal": "Goal",
        "context": [],
        "constraints": ["Constraint"],
        "success_criteria": ["Success"],
        "unknowns": [],
        "user_preferences": [],
        "risk_level": "medium",
        "complexity": "moderate",
        "should_use_cmm": True,
        "parse_warnings": [],
        "source": "test",
    }


def _expert_bundle():
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


def _second_bundle():
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


def _balance(missing=None):
    return {
        "dominant_perspective_found": False,
        "dominant_perspective": None,
        "missing_perspectives": missing or [],
        "notes": [],
    }


def _conflict(disagreements=None, tradeoffs=None, blind_spots=None):
    return {
        "agreements": [],
        "disagreements": disagreements or [],
        "unresolved_tradeoffs": tradeoffs or [],
        "premature_consensus_risks": [],
        "blind_spots": blind_spots or [],
        "minority_positions": [],
        "questions_for_next_round": [],
        "confidence": 0.8,
        "parse_warnings": [],
        "source": "test",
    }


def _meta(decision="SYNTHESIZE"):
    return {
        "decision": decision,
        "reason": "Meta reason",
        "missing_perspectives": ["user"] if decision == "ADD_EXPERT" else [],
        "conflicts_to_resolve": ["Conflict"] if decision == "DEEPEN" else [],
        "risks_to_address": ["Risk"] if decision in {"DEEPEN", "ADD_EXPERT"} else [],
        "questions_to_answer": ["Question"] if decision in {"DEEPEN", "ADD_EXPERT"} else [],
        "next_actions": [],
        "confidence": 0.8,
        "parse_warnings": [],
        "source": "test",
    }


def _plan(name="plan"):
    return {"main_idea": name, "steps": [{"number": "1", "title": "step", "substeps": []}]}


def _critique():
    return {"recommendations": ["Improve plan"], "final_score": 8.0}


def _moderated():
    return {
        "final_answer": "final answer",
        "reports": [{"decision": "ACCEPT", "avg_score": 8.5, "improvements": []}],
        "trace": {},
    }


def _dynamic_report():
    return {"roles": [], "role_views": [], "rejected_suggestions": [], "warnings": [], "source": "test"}


def _deliberation_bundle():
    return {
        "type": "deliberation_round",
        "roles": [{"key": "strategist", "name": "Strategist", "perspective_tag": "strategy"}],
        "responses": [
            {
                "role_key": "strategist",
                "perspective_tag": "strategy",
                "agreements": [],
                "disagreements": ["Disagreement A"],
                "missed_by_others": [],
                "revised_recommendations": ["Revised A"],
                "new_risks": ["New risk A"],
                "questions_for_group": ["Question A"],
                "confidence_change": 0.0,
                "parse_warnings": [],
                "source": "test",
            }
        ],
        "synthesis": {
            "agreements": [],
            "disagreements": ["Disagreement A"],
            "revised_recommendations": ["Revised A"],
            "new_risks": ["New risk A"],
            "questions_for_group": ["Question A"],
        },
    }


def _deliberated_bundle():
    bundle = _expert_bundle()
    bundle["contributions"] = list(bundle["contributions"]) + [
        {
            "role_key": "strategist",
            "perspective_tag": "strategy",
            "contribution_type": "deliberation_response",
            "recommendations": ["Revised A"],
            "risks": ["New risk A"],
            "questions": ["Question A"],
            "insights": ["Disagreement A"],
            "confidence": 0.5,
        }
    ]
    bundle["synthesis"] = {
        "recommendations": ["Recommendation A", "Revised A"],
        "risks": ["Risk A", "New risk A"],
        "questions": ["Question A"],
        "perspective_counts": {"strategy": 2},
    }
    return bundle


class StateMachineTests(unittest.TestCase):
    def _patch_core(self):
        return patch.multiple(
            "Lib.state_machine",
            build_query_intake=DEFAULT,
            generate_dynamic_roles=DEFAULT,
            run_expert_panel=DEFAULT,
            analyze_balance=DEFAULT,
            analyze_conflicts=DEFAULT,
            run_meta_moderator=DEFAULT,
            run_deliberation_round=DEFAULT,
            merge_deliberation_into_bundle=DEFAULT,
            run_targeted_expert_round=DEFAULT,
            merge_expert_bundles=DEFAULT,
            develop_plan=DEFAULT,
            check_plan_and_act=DEFAULT,
            run_moderated_loop=DEFAULT,
        )

    def _configure_success(self, mocks):
        mocks["build_query_intake"].return_value = _query_intake()
        mocks["generate_dynamic_roles"].return_value = _dynamic_report()
        mocks["run_expert_panel"].return_value = _expert_bundle()
        mocks["analyze_balance"].return_value = _balance()
        mocks["analyze_conflicts"].return_value = _conflict()
        mocks["run_meta_moderator"].return_value = _meta("SYNTHESIZE")
        mocks["develop_plan"].return_value = _plan()
        mocks["check_plan_and_act"].return_value = {"status": "ready", "critique": _critique()}
        mocks["run_moderated_loop"].return_value = _moderated()

    def test_state_machine_success_path_reaches_finalize(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            result = run_cmm_state_machine("raw query")

        trace = result["trace_report"]
        self.assertEqual(result["final_answer"], "final answer")
        self.assertEqual(trace["final_state"], "FINALIZE")
        states = [item["from"] for item in trace["state_history"]]
        self.assertIn("INTAKE", states)
        self.assertIn("PLAN", states)
        self.assertIn("ANSWER", states)

    def test_run_cmm_delegates_to_state_machine_or_returns_state_trace(self):
        from Lib.orchestrator import run_cmm

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            result = run_cmm("raw query")

        self.assertEqual(set(result.keys()), {"final_answer", "trace_report", "raw"})
        self.assertEqual(result["trace_report"]["final_state"], "FINALIZE")
        self.assertIn("state_history", result["trace_report"])

    def test_replan_runs_when_plan_needs_revision(self):
        from Lib.state_machine import run_cmm_state_machine

        captured_contexts = []

        def capture_plan(query, context=None, depth="detailed"):
            captured_contexts.append(context)
            return _plan(f"plan-{len(captured_contexts)}")

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["develop_plan"].side_effect = capture_plan
            mocks["check_plan_and_act"].side_effect = [
                {"status": "needs_revision", "critique": _critique(), "feedback": ["Fix A"]},
                {"status": "ready", "critique": _critique()},
            ]
            result = run_cmm_state_machine("raw query", max_iters=2)

        history = result["trace_report"]["state_history"]
        transitions = [(item["from"], item["to"]) for item in history]
        self.assertIn(("PLAN_CRITIQUE", "REPLAN"), transitions)
        self.assertIn(("REPLAN", "PLAN"), transitions)
        self.assertGreaterEqual(len(result["trace_report"]["plans"]), 2)
        self.assertGreaterEqual(len(result["trace_report"]["plan_critiques"]), 2)
        self.assertIn("replan_context", captured_contexts[1])
        self.assertEqual(captured_contexts[1]["replan_context"]["feedback"], ["Fix A"])

    def test_plan_rejected_fails_after_max_iters(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["check_plan_and_act"].return_value = {
                "status": "rejected",
                "critique": _critique(),
                "reason": "too weak",
            }
            result = run_cmm_state_machine("raw query", max_iters=1)

        self.assertEqual(result["final_answer"], "")
        self.assertEqual(result["trace_report"]["final_state"], "FAILED")
        self.assertTrue(any("plan_rejected" in item for item in result["trace_report"]["warnings"]))

    def test_meta_finalize_short_circuits_to_finalize(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_meta_moderator"].return_value = _meta("FINALIZE")
            result = run_cmm_state_machine("raw query")

        self.assertEqual(result["final_answer"], "")
        self.assertEqual(result["trace_report"]["final_state"], "FINALIZE")
        self.assertIn("meta_finalize_before_answer", result["trace_report"]["warnings"])
        mocks["develop_plan"].assert_not_called()
        mocks["run_moderated_loop"].assert_not_called()

    def test_meta_deepen_triggers_deliberation_or_extra_panel_state(self):
        from Lib.state_machine import run_cmm_state_machine

        disagreement = [{"issue": "Issue", "positions": [{"role": "strategist", "position": "A"}], "severity": "high"}]

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["analyze_conflicts"].side_effect = [_conflict(disagreements=disagreement), _conflict()]
            mocks["run_meta_moderator"].return_value = _meta("DEEPEN")
            mocks["analyze_balance"].side_effect = [_balance(), _balance()]
            mocks["run_deliberation_round"].return_value = _deliberation_bundle()
            mocks["merge_deliberation_into_bundle"].return_value = _deliberated_bundle()
            result = run_cmm_state_machine("raw query")

        history_states = [item["from"] for item in result["trace_report"]["state_history"]]
        self.assertIn("DELIBERATION_ROUND", history_states)
        self.assertGreaterEqual(len(result["trace_report"]["conflict_reports"]), 2)

    def test_add_expert_triggers_panel_round_extra(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_meta_moderator"].return_value = _meta("ADD_EXPERT")
            mocks["analyze_balance"].side_effect = [_balance(missing=["user"]), _balance()]
            mocks["run_targeted_expert_round"].return_value = _second_bundle()
            mocks["merge_expert_bundles"].return_value = {
                "roles": _expert_bundle()["roles"] + _second_bundle()["roles"],
                "contributions": _expert_bundle()["contributions"] + _second_bundle()["contributions"],
                "synthesis": {
                    "recommendations": ["Recommendation A", "Recommendation B"],
                    "risks": ["Risk A", "Risk B"],
                    "questions": ["Question A", "Question B"],
                    "perspective_counts": {"strategy": 1, "user": 1},
                },
            }
            result = run_cmm_state_machine("raw query")

        history_states = [item["from"] for item in result["trace_report"]["state_history"]]
        self.assertIn("PANEL_ROUND_EXTRA", history_states)

    def test_max_transitions_guard(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            result = run_cmm_state_machine("raw query", max_transitions=2)

        self.assertEqual(result["trace_report"]["final_state"], "FAILED")
        self.assertIn("max_transitions_exceeded", result["trace_report"]["errors"])

    def test_trace_preserves_old_fields(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            result = run_cmm_state_machine("raw query")

        trace = result["trace_report"]
        for key in (
            "query_intake",
            "expert_rounds",
            "balance_reports",
            "conflict_reports",
            "deliberation_rounds",
            "plan",
            "plan_critique",
            "moderation_reports",
        ):
            self.assertIn(key, trace)


if __name__ == "__main__":
    unittest.main()
