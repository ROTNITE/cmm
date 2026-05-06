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


def _dynamic_report_with_role():
    return {
        "roles": [],
        "role_views": [
            {
                "key": "legal_reviewer",
                "name": "Legal Reviewer",
                "perspective_tag": "legal",
                "why_needed": "Legal constraints appear in the task.",
            }
        ],
        "rejected_suggestions": [],
        "warnings": [],
        "source": "test",
    }


def _expert_bundle_with_dynamic_role():
    bundle = _expert_bundle()
    bundle["roles"] = list(bundle["roles"]) + [
        {
            "key": "legal_reviewer",
            "name": "Legal Reviewer",
            "perspective_tag": "legal",
            "dynamic": True,
            "why_needed": "Legal constraints appear in the task.",
        }
    ]
    return bundle


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
            route_query=DEFAULT,
            run_direct_answer=DEFAULT,
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
        mocks["route_query"].return_value = {
            "mode": "FULL_CMM",
            "reason": "test full path",
            "complexity": "high",
            "needs_expert_panel": True,
            "needs_second_round": True,
            "estimated_cost_class": "L",
            "signals": {},
            "warnings": [],
        }
        mocks["run_direct_answer"].return_value = {"final_answer": "direct answer", "source": "test", "parse_warnings": []}
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
        self.assertEqual(trace["cmm_mode"], "FULL_CMM")
        states = [item["from"] for item in trace["state_history"]]
        self.assertIn("INTAKE", states)
        self.assertIn("ROUTE", states)
        self.assertIn("PLAN", states)
        self.assertIn("ANSWER", states)

    def test_rebalance_runs_meta_recheck_then_plan_when_conflicts_clear(self):
        from Lib.state_machine import run_cmm_state_machine

        first_conflict = _conflict(
            tradeoffs=[
                {
                    "tradeoff": "speed vs safety",
                    "why_it_matters": "needs resolution",
                    "roles_involved": ["strategist", "risk_manager"],
                }
            ]
        )
        cleared_conflict = _conflict()

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_meta_moderator"].side_effect = [_meta("DEEPEN")]
            mocks["analyze_conflicts"].side_effect = [first_conflict, cleared_conflict]
            mocks["run_deliberation_round"].return_value = _deliberation_bundle()
            mocks["merge_deliberation_into_bundle"].return_value = _deliberated_bundle()

            result = run_cmm_state_machine("raw query")

        trace = result["trace_report"]
        transitions = [(item["from"], item["to"]) for item in trace["state_history"]]

        self.assertIn(("DELIBERATION_ROUND", "CONSENSUS_CHECK"), transitions)
        self.assertIn(("CONSENSUS_CHECK", "META_RECHECK"), transitions)
        self.assertIn(("META_RECHECK", "PLAN"), transitions)
        self.assertEqual(trace["meta_recheck_count"], 1)
        self.assertEqual(trace["deliberation_round_count"], 1)
        self.assertEqual(trace["max_deliberation_rounds"], 1)
        self.assertEqual(trace["consensus_checks"][0]["decision"], "META_RECHECK")
        self.assertEqual(trace["meta_recheck_decisions"][0]["decision"], "SYNTHESIZE")
        self.assertEqual(trace["final_state"], "FINALIZE")

    def test_meta_recheck_can_request_extra_panel_for_remaining_gap(self):
        from Lib.state_machine import run_cmm_state_machine

        first_conflict = _conflict(
            tradeoffs=[
                {
                    "tradeoff": "speed vs safety",
                    "why_it_matters": "needs resolution",
                    "roles_involved": ["strategist", "risk_manager"],
                }
            ]
        )
        recheck_conflict = _conflict(blind_spots=["Critical legal/privacy blind spot remains."])

        extra_bundle = {
            "roles": [
                {
                    "key": "legal_reviewer",
                    "name": "Legal Reviewer",
                    "perspective_tag": "legal",
                    "dynamic": True,
                }
            ],
            "contributions": [],
            "synthesis": {"recommendations": [], "risks": [], "questions": [], "perspective_counts": {}},
        }
        merged_bundle = _expert_bundle()
        merged_bundle["roles"] = list(merged_bundle["roles"]) + list(extra_bundle["roles"])

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_meta_moderator"].side_effect = [_meta("DEEPEN"), _meta("ADD_EXPERT")]
            mocks["analyze_conflicts"].side_effect = [first_conflict, recheck_conflict, _conflict()]
            mocks["run_deliberation_round"].return_value = _deliberation_bundle()
            mocks["merge_deliberation_into_bundle"].return_value = _deliberated_bundle()
            mocks["run_targeted_expert_round"].return_value = extra_bundle
            mocks["merge_expert_bundles"].return_value = merged_bundle

            result = run_cmm_state_machine("raw query")

        trace = result["trace_report"]
        transitions = [(item["from"], item["to"]) for item in trace["state_history"]]

        self.assertIn(("CONSENSUS_CHECK", "META_RECHECK"), transitions)
        self.assertIn(("META_RECHECK", "PANEL_ROUND_EXTRA"), transitions)
        self.assertEqual(trace["meta_recheck_count"], 1)
        self.assertEqual(trace["consensus_checks"][0]["decision"], "META_RECHECK")
        self.assertEqual(trace["meta_recheck_decisions"][0]["decision"], "ADD_EXPERT")
        mocks["run_targeted_expert_round"].assert_called()

    def test_meta_recheck_limit_prevents_infinite_loop(self):
        from Lib.state_machine import run_cmm_state_machine

        persistent_conflict = _conflict(
            tradeoffs=[
                {
                    "tradeoff": "critical safety vs speed",
                    "why_it_matters": "critical safety risk remains",
                    "roles_involved": ["strategist", "risk_manager"],
                    "severity": "high",
                }
            ]
        )

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_meta_moderator"].side_effect = [_meta("DEEPEN"), _meta("DEEPEN")]
            mocks["analyze_conflicts"].side_effect = [persistent_conflict, persistent_conflict]
            mocks["run_deliberation_round"].return_value = _deliberation_bundle()
            mocks["merge_deliberation_into_bundle"].return_value = _deliberated_bundle()

            result = run_cmm_state_machine("raw query", max_transitions=40)

        trace = result["trace_report"]
        transitions = [(item["from"], item["to"]) for item in trace["state_history"]]

        self.assertEqual(trace["meta_recheck_count"], 1)
        self.assertEqual(transitions.count(("CONSENSUS_CHECK", "META_RECHECK")), 1)
        self.assertEqual(trace["deliberation_round_count"], 1)
        self.assertEqual(len(trace["consensus_checks"]), 1)
        self.assertNotIn("max_transitions_exceeded", trace["errors"])

    def test_deliberation_round_two_runs_only_for_high_unresolved_conflict(self):
        from Lib.state_machine import run_cmm_state_machine

        persistent_conflict = _conflict(
            disagreements=[
                {
                    "issue": "Launch speed",
                    "positions": [
                        {"role": "strategist", "position": "ship"},
                        {"role": "risk_manager", "position": "guard"},
                    ],
                    "severity": "high",
                }
            ]
        )

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_meta_moderator"].return_value = _meta("DEEPEN")
            mocks["analyze_conflicts"].side_effect = [persistent_conflict, persistent_conflict, _conflict()]
            mocks["run_deliberation_round"].side_effect = [_deliberation_bundle(), _deliberation_bundle()]
            mocks["merge_deliberation_into_bundle"].return_value = _deliberated_bundle()

            result = run_cmm_state_machine("raw query", max_deliberation_rounds=2)

        trace = result["trace_report"]
        transitions = [(item["from"], item["to"]) for item in trace["state_history"]]

        self.assertEqual(mocks["run_deliberation_round"].call_count, 2)
        self.assertEqual(trace["deliberation_round_count"], 2)
        self.assertEqual(trace["max_deliberation_rounds"], 2)
        self.assertEqual(trace["consensus_checks"][0]["decision"], "DELIBERATION_ROUND_2")
        self.assertEqual(trace["consensus_checks"][1]["decision"], "META_RECHECK")
        self.assertIn(("CONSENSUS_CHECK", "DELIBERATION_ROUND"), transitions)

    def test_deliberation_round_two_skips_for_medium_conflict(self):
        from Lib.state_machine import run_cmm_state_machine

        first_conflict = _conflict(
            disagreements=[
                {
                    "issue": "Launch speed",
                    "positions": [{"role": "strategist", "position": "ship"}],
                    "severity": "high",
                }
            ]
        )
        medium_conflict = _conflict(
            disagreements=[
                {
                    "issue": "Launch speed",
                    "positions": [{"role": "strategist", "position": "ship"}],
                    "severity": "medium",
                }
            ]
        )

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_meta_moderator"].return_value = _meta("DEEPEN")
            mocks["analyze_conflicts"].side_effect = [first_conflict, medium_conflict]
            mocks["run_deliberation_round"].return_value = _deliberation_bundle()
            mocks["merge_deliberation_into_bundle"].return_value = _deliberated_bundle()

            result = run_cmm_state_machine("raw query", max_deliberation_rounds=2)

        trace = result["trace_report"]

        self.assertEqual(mocks["run_deliberation_round"].call_count, 1)
        self.assertEqual(trace["deliberation_round_count"], 1)
        self.assertEqual(trace["consensus_checks"][0]["decision"], "META_RECHECK")

    def test_direct_mode_skips_full_cmm_stages(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["route_query"].return_value = {
                "mode": "DIRECT",
                "reason": "simple",
                "complexity": "low",
                "needs_expert_panel": False,
                "needs_second_round": False,
                "estimated_cost_class": "S",
                "signals": {},
                "warnings": [],
            }
            mocks["run_direct_answer"].return_value = {
                "final_answer": "direct final answer",
                "source": "test",
                "parse_warnings": [],
            }
            result = run_cmm_state_machine("simple query")

        trace = result["trace_report"]
        self.assertEqual(result["final_answer"], "direct final answer")
        self.assertEqual(trace["cmm_mode"], "DIRECT")
        self.assertEqual(trace["estimated_cost_class"], "S")
        self.assertEqual(trace["expert_rounds"], [])
        self.assertEqual(trace["balance_reports"], [])
        self.assertEqual(trace["conflict_reports"], [])
        self.assertEqual(trace["meta_moderation_decisions"], [])
        self.assertEqual(trace["plans"], [])
        self.assertEqual(trace["plan_critiques"], [])
        mocks["run_expert_panel"].assert_not_called()
        mocks["analyze_balance"].assert_not_called()
        mocks["analyze_conflicts"].assert_not_called()
        mocks["run_meta_moderator"].assert_not_called()
        mocks["develop_plan"].assert_not_called()
        mocks["check_plan_and_act"].assert_not_called()

    def test_direct_mode_ignores_threaded_expert_settings(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["route_query"].return_value = {
                "mode": "DIRECT",
                "reason": "simple",
                "complexity": "low",
                "needs_expert_panel": False,
                "needs_second_round": False,
                "estimated_cost_class": "S",
                "signals": {},
                "warnings": [],
            }
            result = run_cmm_state_machine("simple query", parallel_mode="THREADS", max_workers=3)

        trace = result["trace_report"]
        self.assertEqual(trace["cmm_mode"], "DIRECT")
        self.assertEqual(trace["parallel_mode"], "THREADS")
        self.assertEqual(trace["parallelized_stages"], [])
        mocks["run_expert_panel"].assert_not_called()

    def test_direct_mode_fallback_answer_still_finalizes(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["route_query"].return_value = {
                "mode": "DIRECT",
                "reason": "simple",
                "complexity": "low",
                "needs_expert_panel": False,
                "needs_second_round": False,
                "estimated_cost_class": "S",
                "signals": {},
                "warnings": [],
            }
            mocks["run_direct_answer"].return_value = {
                "final_answer": "fallback direct answer",
                "source": "fallback",
                "parse_warnings": ["direct_answer_failed"],
            }
            result = run_cmm_state_machine("simple query")

        self.assertEqual(result["final_answer"], "fallback direct answer")
        self.assertEqual(result["trace_report"]["final_state"], "FINALIZE")
        self.assertIn("direct_answer: direct_answer_failed", result["trace_report"]["warnings"])
        self.assertEqual(result["trace_report"]["errors"], [])

    def test_light_cmm_runs_panel_balance_plan_but_skips_full_stages(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["route_query"].return_value = {
                "mode": "LIGHT_CMM",
                "reason": "moderate",
                "complexity": "medium",
                "needs_expert_panel": True,
                "needs_second_round": False,
                "estimated_cost_class": "M",
                "signals": {},
                "warnings": [],
            }
            result = run_cmm_state_machine("moderate query")

        trace = result["trace_report"]
        self.assertEqual(result["final_answer"], "final answer")
        self.assertEqual(trace["cmm_mode"], "LIGHT_CMM")
        self.assertEqual(trace["estimated_cost_class"], "M")
        mocks["run_expert_panel"].assert_called_once()
        mocks["analyze_balance"].assert_called_once()
        mocks["develop_plan"].assert_called_once()
        mocks["check_plan_and_act"].assert_called_once()
        mocks["analyze_conflicts"].assert_not_called()
        mocks["run_meta_moderator"].assert_not_called()
        mocks["run_deliberation_round"].assert_not_called()
        mocks["run_targeted_expert_round"].assert_not_called()

    def test_answer_moderation_accept_finalizes(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_moderated_loop"].return_value = {
                "final_answer": "accepted answer",
                "reports": [{"decision": "ACCEPT", "avg_score": 9.0, "critical_issues": []}],
            }
            result = run_cmm_state_machine("raw query")

        trace = result["trace_report"]
        self.assertEqual(result["final_answer"], "accepted answer")
        self.assertEqual(trace["final_state"], "FINALIZE")
        self.assertEqual(trace["answer_moderation_final_decision"], "ACCEPT")
        self.assertFalse(trace["answer_moderation_best_effort"])

    def test_answer_moderation_revise_noncritical_finalizes_with_warning(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_moderated_loop"].return_value = {
                "final_answer": "revised best effort",
                "reports": [{"decision": "REVISE", "avg_score": 6.0, "critical_issues": []}],
            }
            result = run_cmm_state_machine("raw query")

        trace = result["trace_report"]
        self.assertEqual(result["final_answer"], "revised best effort")
        self.assertEqual(trace["final_state"], "FINALIZE")
        self.assertEqual(trace["answer_moderation_final_decision"], "REVISE")
        self.assertTrue(trace["answer_moderation_best_effort"])
        self.assertIn("answer_moderation_revise_best_effort", trace["warnings"])

    def test_trace_contains_context_compression(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            result = run_cmm_state_machine("raw query")

        compression = result["trace_report"]["context_compression"]
        self.assertIn("planner_context_chars", compression)
        self.assertIn("critic_context_chars", compression)
        self.assertIn("answer_context_chars", compression)
        self.assertIn("meta_context_chars", compression)
        self.assertGreaterEqual(compression["planner_context_chars"], 0)
        self.assertGreaterEqual(compression["critic_context_chars"], 0)
        self.assertGreaterEqual(compression["answer_context_chars"], 0)
        self.assertGreaterEqual(compression["meta_context_chars"], 0)

    def test_answer_moderation_reject_with_answer_fails(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_moderated_loop"].return_value = {
                "final_answer": "rejected answer",
                "reports": [{"decision": "REJECT", "avg_score": 2.0, "critical_issues": ["unsafe"]}],
            }
            result = run_cmm_state_machine("raw query")

        trace = result["trace_report"]
        self.assertEqual(result["final_answer"], "")
        self.assertEqual(trace["final_state"], "FAILED")
        self.assertEqual(trace["answer_moderation_final_decision"], "REJECT")
        self.assertEqual(trace["answer_moderation_critical_issues"], ["unsafe"])
        self.assertIn("answer_moderation_rejected", trace["errors"])

    def test_answer_moderation_empty_answer_fails(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_moderated_loop"].return_value = {
                "final_answer": "",
                "reports": [{"decision": "ACCEPT", "avg_score": 9.0, "critical_issues": []}],
            }
            result = run_cmm_state_machine("raw query")

        self.assertEqual(result["trace_report"]["final_state"], "FAILED")
        self.assertIn("moderated_loop_returned_empty_final_answer", result["trace_report"]["errors"])

    def test_threaded_mode_passes_config_to_initial_expert_panel_and_trace(self):
        from Lib.state_machine import run_cmm_state_machine

        captured = {}

        def capture_panel(query, context=None, max_roles=5, dynamic_roles=None, **kwargs):
            captured["kwargs"] = kwargs
            return _expert_bundle()

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_expert_panel"].side_effect = capture_panel
            result = run_cmm_state_machine("raw query", parallel_mode="THREADS", max_workers=3)

        trace = result["trace_report"]
        self.assertEqual(captured["kwargs"]["execution_mode"], "THREADS")
        self.assertEqual(captured["kwargs"]["max_workers"], 3)
        self.assertEqual(captured["kwargs"]["model"], "deepseek-chat")
        self.assertEqual(trace["parallel_mode"], "THREADS")
        self.assertEqual(trace["max_workers"], 3)
        self.assertIn("PANEL_ROUND_1", trace["parallelized_stages"])

    def test_forced_full_cmm_preserves_full_path_without_router_call(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            result = run_cmm_state_machine("raw query", route_mode="FULL_CMM")

        trace = result["trace_report"]
        self.assertEqual(trace["cmm_mode"], "FULL_CMM")
        self.assertIn("CONFLICT_ANALYSIS", [item["from"] for item in trace["state_history"]])
        mocks["route_query"].assert_not_called()
        mocks["analyze_conflicts"].assert_called()
        mocks["run_meta_moderator"].assert_called()

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
        captured_critique_kwargs = []

        def capture_plan(query, context=None, depth="detailed", model="deepseek-chat"):
            captured_contexts.append(context)
            return _plan(f"plan-{len(captured_contexts)}")

        def capture_critique(plan, query, min_score=0.7, **kwargs):
            captured_critique_kwargs.append(kwargs)
            if len(captured_critique_kwargs) == 1:
                return {"status": "needs_revision", "critique": _critique(), "feedback": ["Fix A"]}
            return {"status": "ready", "critique": _critique()}

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["develop_plan"].side_effect = capture_plan
            mocks["check_plan_and_act"].side_effect = capture_critique
            result = run_cmm_state_machine("raw query", max_iters=2)

        history = result["trace_report"]["state_history"]
        transitions = [(item["from"], item["to"]) for item in history]
        self.assertIn(("PLAN_CRITIQUE", "REPLAN"), transitions)
        self.assertIn(("REPLAN", "PLAN"), transitions)
        self.assertGreaterEqual(len(result["trace_report"]["plans"]), 2)
        self.assertGreaterEqual(len(result["trace_report"]["plan_critiques"]), 2)
        self.assertIn("replan_context", captured_contexts[1])
        self.assertEqual(captured_contexts[1]["replan_context"]["feedback"], ["Fix A"])
        self.assertEqual(captured_critique_kwargs[1]["replan_context"]["feedback"], ["Fix A"])

    def test_state_machine_passes_model_to_develop_plan(self):
        from Lib.state_machine import run_cmm_state_machine

        captured = {}

        def capture_plan(query, context=None, depth="detailed", model="deepseek-chat"):
            captured["model"] = model
            return _plan()

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["develop_plan"].side_effect = capture_plan
            run_cmm_state_machine("raw query", model="test-model")

        self.assertEqual(captured["model"], "test-model")

    def test_state_machine_passes_context_to_plan_critic(self):
        from Lib.state_machine import run_cmm_state_machine

        captured = {}

        def capture_critique(plan, query, min_score=0.7, **kwargs):
            captured["kwargs"] = kwargs
            return {"status": "ready", "critique": _critique()}

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["generate_dynamic_roles"].return_value = _dynamic_report_with_role()
            mocks["run_expert_panel"].return_value = _expert_bundle_with_dynamic_role()
            mocks["check_plan_and_act"].side_effect = capture_critique
            run_cmm_state_machine("raw query")

        kwargs = captured["kwargs"]
        self.assertEqual(kwargs["query_intake"], _query_intake())
        self.assertIn("must_address", kwargs["deliberation_brief"])
        self.assertEqual(kwargs["conflict_report"], _conflict())
        self.assertEqual(kwargs["dynamic_roles_used"][0]["key"], "legal_reviewer")
        self.assertEqual(kwargs["deliberation_revisions"], [])
        self.assertEqual(kwargs["meta_decision"], _meta("SYNTHESIZE"))
        self.assertTrue(kwargs["state_history"])
        self.assertEqual(kwargs["replan_context"], {})
        self.assertEqual(kwargs["model"], "deepseek-chat")

    def test_plan_critic_receives_only_executed_dynamic_roles(self):
        from Lib.state_machine import run_cmm_state_machine

        captured = {}

        def capture_critique(plan, query, min_score=0.7, **kwargs):
            captured["dynamic_roles_used"] = kwargs.get("dynamic_roles_used")
            return {"status": "ready", "critique": _critique()}

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["generate_dynamic_roles"].return_value = _dynamic_report_with_role()
            mocks["run_expert_panel"].return_value = _expert_bundle()
            mocks["check_plan_and_act"].side_effect = capture_critique
            result = run_cmm_state_machine("raw query")

        trace = result["trace_report"]
        self.assertEqual(trace["dynamic_roles_generated"][0]["key"], "legal_reviewer")
        self.assertEqual(trace["dynamic_roles_executed"], [])
        self.assertEqual(trace["dynamic_roles_used"], [])
        self.assertEqual(captured["dynamic_roles_used"], [])

    def test_roles_used_unique_dedupes_rounds_and_marks_dynamic_roles(self):
        from Lib.state_machine import run_cmm_state_machine

        extra_bundle = {
            "roles": [
                {"key": "strategist", "name": "Strategist", "perspective_tag": "strategy"},
                {
                    "key": "legal_reviewer",
                    "name": "Legal Reviewer",
                    "perspective_tag": "legal",
                    "dynamic": True,
                },
            ],
            "contributions": [],
            "synthesis": {"recommendations": [], "risks": [], "questions": [], "perspective_counts": {}},
        }
        merged_bundle = _expert_bundle()
        merged_bundle["roles"] = list(merged_bundle["roles"]) + list(extra_bundle["roles"])

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_meta_moderator"].return_value = _meta("ADD_EXPERT")
            mocks["run_targeted_expert_round"].return_value = extra_bundle
            mocks["merge_expert_bundles"].return_value = merged_bundle
            result = run_cmm_state_machine("raw query")

        roles = {role["key"]: role for role in result["trace_report"]["roles_used_unique"]}
        self.assertEqual(roles["strategist"]["rounds"], ["initial", "extra"])
        self.assertFalse(roles["strategist"]["dynamic"])
        self.assertEqual(roles["legal_reviewer"]["rounds"], ["extra"])
        self.assertTrue(roles["legal_reviewer"]["dynamic"])

    def test_trace_includes_observability_telemetry(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["develop_plan"].return_value = {
                "main_idea": "plan",
                "steps": [{"number": "1", "title": "step", "substeps": []}],
                "json_attempts": 2,
                "source": "model",
            }
            result = run_cmm_state_machine("raw query")

        trace = result["trace_report"]
        self.assertIsInstance(trace["estimated_call_count"], int)
        self.assertGreaterEqual(trace["estimated_call_count"], 2)
        self.assertEqual(trace["estimated_stage_count"], len(trace["state_history"]))
        self.assertEqual(trace["answer_chars"], len(result["final_answer"]))
        self.assertEqual(trace["warnings_count"], len(trace["warnings"]))
        self.assertEqual(trace["errors_count"], len(trace["errors"]))

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

    def test_noncritical_needs_revision_after_max_iters_proceeds_best_effort(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["check_plan_and_act"].return_value = {
                "status": "needs_revision",
                "critique": {"feedback": ["Improve specificity"]},
                "feedback": ["Improve specificity"],
                "reason": "minor gaps",
            }
            result = run_cmm_state_machine("raw query", max_iters=0)

        self.assertEqual(result["final_answer"], "final answer")
        self.assertEqual(result["trace_report"]["final_state"], "FINALIZE")
        self.assertTrue(
            any("plan_needs_revision_after_max_iters; proceeding_with_best_effort_plan" in item for item in result["trace_report"]["warnings"])
        )
        self.assertEqual(result["trace_report"]["errors"], [])
        mocks["run_moderated_loop"].assert_called_once()

    def test_critical_needs_revision_after_max_iters_still_fails(self):
        from Lib.state_machine import run_cmm_state_machine

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["check_plan_and_act"].return_value = {
                "status": "needs_revision",
                "critique": {"critical_blockers": ["critical privacy risk"]},
                "feedback": ["Fix blocker"],
                "reason": "critical blocker",
            }
            result = run_cmm_state_machine("raw query", max_iters=0)

        self.assertEqual(result["final_answer"], "")
        self.assertEqual(result["trace_report"]["final_state"], "FAILED")
        self.assertIn("plan_needs_revision_after_max_iters", result["trace_report"]["errors"])
        mocks["run_moderated_loop"].assert_not_called()

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

    def test_threaded_mode_passes_config_to_targeted_round(self):
        from Lib.state_machine import run_cmm_state_machine

        captured = {}

        def capture_second_round(query, roles, context, model="deepseek-chat", **kwargs):
            captured["kwargs"] = kwargs
            return _second_bundle()

        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["run_meta_moderator"].return_value = _meta("ADD_EXPERT")
            mocks["analyze_balance"].side_effect = [_balance(missing=["user"]), _balance()]
            mocks["run_targeted_expert_round"].side_effect = capture_second_round
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
            result = run_cmm_state_machine("raw query", parallel_mode="THREADS", max_workers=2)

        trace = result["trace_report"]
        self.assertEqual(captured["kwargs"]["execution_mode"], "THREADS")
        self.assertEqual(captured["kwargs"]["max_workers"], 2)
        self.assertIn("PANEL_ROUND_EXTRA", trace["parallelized_stages"])

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
            "json_health",
            "roles_used_unique",
            "estimated_call_count",
            "estimated_stage_count",
            "answer_chars",
            "warnings_count",
            "errors_count",
        ):
            self.assertIn(key, trace)

    def test_trace_flattens_plan_critique_compatibility_fields(self):
        from Lib.state_machine import run_cmm_state_machine

        critique = {
            "ignored_must_address": ["critical privacy requirement"],
            "ignored_risks": ["security risk"],
            "ignored_tradeoffs": ["speed vs safety"],
            "critical_blockers": ["critical privacy requirement"],
        }
        with self._patch_core() as mocks:
            self._configure_success(mocks)
            mocks["check_plan_and_act"].return_value = {
                "status": "needs_revision",
                "decision": "REVISE",
                "critique": critique,
                "feedback": ["Fix blockers"],
                "reason": "Plan must address critical blockers",
            }
            result = run_cmm_state_machine("raw query", max_iters=0)

        trace = result["trace_report"]
        self.assertIn("REVISE", trace["plan_critique_decisions"])
        self.assertIn("critical privacy requirement", trace["plan_critique_blockers"])
        self.assertIn("critical privacy requirement", trace["ignored_must_address"])
        self.assertIn("security risk", trace["ignored_risks"])
        self.assertIn("speed vs safety", trace["ignored_tradeoffs"])
        self.assertIn("needs_revision", trace["plan_critique_statuses"])
        self.assertIn("Plan must address critical blockers", trace["plan_replan_reasons"])


if __name__ == "__main__":
    unittest.main()
