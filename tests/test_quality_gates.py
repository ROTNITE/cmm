import unittest


class QualityGatesTests(unittest.TestCase):
    def test_plan_critical_blockers_detected(self):
        from Lib.quality_gates import has_critical_plan_blockers, plan_blockers

        critique_result = {
            "status": "needs_revision",
            "critique": {
                "critical_blockers": ["critical privacy compliance risk"],
                "critical_issues": [],
            },
        }

        self.assertTrue(has_critical_plan_blockers(critique_result))
        self.assertEqual(plan_blockers(critique_result), ["critical privacy compliance risk"])

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

    def test_rejected_plan_cannot_best_effort(self):
        from Lib.quality_gates import can_best_effort_finalize

        critique_result = {
            "status": "rejected",
            "decision": "REJECT",
            "critique": {},
            "reason": "too weak",
        }

        self.assertFalse(can_best_effort_finalize(critique_result=critique_result))

    def test_answer_reject_blocks(self):
        from Lib.quality_gates import has_critical_answer_blockers

        moderated_result = {
            "final_answer": "bad answer",
            "reports": [{"decision": "REJECT", "critical_issues": ["unsafe"]}],
        }

        self.assertTrue(has_critical_answer_blockers(moderated_result))

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