import unittest


class QualityGatesTests(unittest.TestCase):
    def test_plan_critical_blockers_detected(self):
        from Lib.quality_gates import has_critical_plan_blockers, plan_blockers

        critique_result = {
            "status": "needs_revision",
            "critique": {
                "critical_blockers": ["critical privacy leak risk"],
                "critical_issues": [],
            },
        }

        self.assertTrue(has_critical_plan_blockers(critique_result))
        self.assertEqual(plan_blockers(critique_result), ["critical privacy leak risk"])

    def test_noncritical_plan_revision_can_best_effort(self):
        from Lib.quality_gates import can_best_effort_finalize

        critique_result = {
            "status": "needs_revision",
            "critique": {
                "feedback": ["Improve specificity"],
                "critical_blockers": [],
                "critical_issues": [],
            },
        }

        self.assertTrue(can_best_effort_finalize(critique_result=critique_result))

    def test_rejected_empty_plan_cannot_best_effort(self):
        from Lib.quality_gates import can_best_effort_finalize

        critique_result = {
            "status": "rejected",
            "decision": "REJECT",
            "critique": {},
            "reason": "too weak",
        }

        self.assertFalse(can_best_effort_finalize(critique_result=critique_result))

    def test_rejected_actionable_noncritical_plan_can_best_effort(self):
        from Lib.quality_gates import can_best_effort_finalize

        critique_result = {
            "status": "rejected",
            "decision": "REJECT",
            "critique": {"feedback": ["Improve specificity"]},
            "reason": "quality gap",
        }
        plan = {"main_idea": "Useful plan", "steps": [{"title": "Do the useful step"}]}

        self.assertTrue(can_best_effort_finalize(critique_result=critique_result, plan=plan))

    def test_provider_failure_text_is_not_plan_blocker(self):
        from Lib.quality_gates import has_critical_plan_blockers, plan_blockers

        critique_result = {
            "status": "rejected",
            "critique": {
                "critical_blockers": ["CRITICAL: all expert API calls failed due to No credentials for provider: aimlapi"],
                "critical_issues": ["Complete failure of expert contribution system - invalid JSON"],
                "ignored_must_address": ["Address blind spot: all expert contributions failed due to API credential errors"],
            },
        }

        self.assertFalse(has_critical_plan_blockers(critique_result))
        self.assertEqual(plan_blockers(critique_result), [])

    def test_key_risk_word_is_not_secret_blocker(self):
        from Lib.quality_gates import has_critical_plan_blockers, plan_blockers

        critique_result = {
            "status": "needs_revision",
            "critique": {
                "critical_blockers": ["Нет fallback-плана на случай провала adoption, хотя это ключевой риск"],
                "critical_issues": ["Resolve deliberation disagreement about key risk mitigation"],
            },
        }

        self.assertFalse(has_critical_plan_blockers(critique_result))
        self.assertEqual(plan_blockers(critique_result), [])

    def test_ordinary_compliance_question_is_not_no_answer_blocker(self):
        from Lib.quality_gates import has_critical_plan_blockers, plan_blockers

        critique_result = {
            "status": "needs_revision",
            "critique": {
                "unresolved_tradeoffs": ["Проверить GDPR policy для экспорта истории чатов"],
                "ignored_must_address": ["Что делать если клиенты не помнят промокод — как повысить compliance"],
                "critical_issues": ["Право вето жителей требует процедуры голосования"],
            },
        }

        self.assertFalse(has_critical_plan_blockers(critique_result))
        self.assertEqual(plan_blockers(critique_result), [])

    def test_secret_key_text_is_still_blocker(self):
        from Lib.quality_gates import has_critical_plan_blockers, plan_blockers

        critique_result = {
            "status": "needs_revision",
            "critique": {
                "critical_blockers": ["План просит вставить секретный ключ API в общий чат"],
            },
        }

        self.assertTrue(has_critical_plan_blockers(critique_result))
        self.assertEqual(plan_blockers(critique_result), ["План просит вставить секретный ключ API в общий чат"])

    def test_answer_reject_blocks(self):
        from Lib.quality_gates import has_critical_answer_blockers

        moderated_result = {
            "final_answer": "bad answer",
            "reports": [{"decision": "REJECT", "critical_issues": ["unsafe"]}],
        }

        self.assertTrue(has_critical_answer_blockers(moderated_result))

    def test_answer_reject_without_critical_issue_does_not_block(self):
        from Lib.quality_gates import can_best_effort_finalize, has_critical_answer_blockers

        moderated_result = {
            "final_answer": "needs polish",
            "reports": [{"decision": "REJECT", "critical_issues": ["too generic"]}],
        }

        self.assertFalse(has_critical_answer_blockers(moderated_result))
        self.assertTrue(can_best_effort_finalize(moderated_result=moderated_result))

    def test_answer_revise_noncritical_can_best_effort(self):
        from Lib.quality_gates import can_best_effort_finalize

        moderated_result = {
            "final_answer": "usable answer",
            "reports": [{"decision": "REVISE", "critical_issues": [], "improvements": ["Clarify one metric"]}],
        }

        self.assertTrue(can_best_effort_finalize(moderated_result=moderated_result))

    def test_answer_revise_critical_cannot_best_effort(self):
        from Lib.quality_gates import can_best_effort_finalize, has_critical_answer_blockers

        moderated_result = {
            "final_answer": "unsafe answer",
            "reports": [{"decision": "REVISE", "critical_issues": ["critical legal compliance issue"]}],
        }

        self.assertTrue(has_critical_answer_blockers(moderated_result))
        self.assertFalse(can_best_effort_finalize(moderated_result=moderated_result))

    def test_normalize_old_moderation_format(self):
        from Lib.quality_gates import normalize_moderated_result

        normalized = normalize_moderated_result(
            {
                "final_answer": "answer",
                "reports": [{"decision": "ACCEPT", "avg_score": 8.5, "critical_issues": []}],
            }
        )

        self.assertEqual(normalized["final_answer"], "answer")
        self.assertEqual(normalized["final_decision"], "ACCEPT")
        self.assertEqual(normalized["critical_issues"], [])
        self.assertEqual(normalized["revision_count"], 0)
        self.assertFalse(normalized["rejected"])

    def test_normalize_rejected_result_clears_final_answer(self):
        from Lib.quality_gates import normalize_moderated_result

        normalized = normalize_moderated_result(
            {
                "final_answer": "bad answer",
                "reports": [{"decision": "REJECT", "critical_issues": ["unsafe"]}],
            }
        )

        self.assertEqual(normalized["final_answer"], "")
        self.assertEqual(normalized["rejected_answer"], "bad answer")
        self.assertEqual(normalized["final_decision"], "REJECT")
        self.assertTrue(normalized["rejected"])


if __name__ == "__main__":
    unittest.main()
