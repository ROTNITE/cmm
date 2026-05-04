import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _write_fixture(path: Path) -> None:
    rows = [
        {
            "id": "CASE-1",
            "query": "How to improve engagement?",
            "context": "hybrid university",
            "constraints": "limited budget",
            "expected_perspectives": "strategy | user | risk",
            "rubric_must_cover": "limited budget | hybrid university",
            "expected_single_model_failure_modes": "generic advice | no metrics",
        }
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _baseline():
    return {"answer": "baseline answer", "trace_report": {"mode": "real_baseline"}}


def _cmm():
    return {"answer": "cmm answer", "trace_report": {"roles_used": [{"perspective_tag": "strategy"}]}}


class RealEvalJudgeTests(unittest.TestCase):
    def test_blind_assignment_is_deterministic_and_reversible(self):
        from cmm.eval import assign_blind_answers

        first = assign_blind_answers("CASE-1", _baseline(), _cmm())
        second = assign_blind_answers("CASE-1", _baseline(), _cmm())

        self.assertEqual(first, second)
        self.assertEqual({first["answer_a_source"], first["answer_b_source"]}, {"BASELINE", "CMM"})
        self.assertEqual(first["source_to_answer"][first["answer_a_source"]], "A")
        self.assertEqual(first["source_to_answer"][first["answer_b_source"]], "B")

    def test_judge_prompt_is_blind_but_contains_criteria(self):
        from cmm.eval import build_judge_prompt

        case = {
            "case_id": "CASE-1",
            "query": "Question?",
            "context": "Context",
            "constraints": "Budget",
            "rubric_must_cover": "Budget | Metrics",
            "expected_perspectives": "strategy | risk",
            "expected_single_model_failure_modes": "generic advice",
        }
        prompt = build_judge_prompt(case, "Answer one", "Answer two")

        self.assertIn("answer_a", prompt)
        self.assertIn("answer_b", prompt)
        self.assertIn("Budget", prompt)
        self.assertIn("strategy", prompt)
        self.assertNotIn("baseline", prompt.lower())
        self.assertNotIn("cmm", prompt.lower())

    def test_normalize_judge_payload_maps_answer_scores_back_to_sources(self):
        from cmm.eval import assign_blind_answers, normalize_judge_payload

        mapping = assign_blind_answers("CASE-1", _baseline(), _cmm())
        payload = {
            "answer_a_scores": {
                "rubric_coverage": 6,
                "perspective_coverage": 6,
                "risk_handling": 6,
                "actionability": 6,
                "clarity": 6,
                "overall": 6,
            },
            "answer_b_scores": {
                "rubric_coverage": 8,
                "perspective_coverage": 8,
                "risk_handling": 8,
                "actionability": 8,
                "clarity": 8,
                "overall": 8,
            },
            "winner": "B",
            "reason": "B is stronger.",
            "answer_a_failure_modes": ["A weak"],
            "answer_b_failure_modes": ["B weak"],
        }

        result = normalize_judge_payload(payload, mapping, raw="{}")

        if mapping["answer_b_source"] == "CMM":
            self.assertEqual(result["winner"], "CMM")
            self.assertEqual(result["cmm_scores"]["overall"], 8.0)
            self.assertEqual(result["baseline_scores"]["overall"], 6.0)
        else:
            self.assertEqual(result["winner"], "BASELINE")
            self.assertEqual(result["baseline_scores"]["overall"], 8.0)
            self.assertEqual(result["cmm_scores"]["overall"], 6.0)

    def test_invalid_judge_output_falls_back_to_tie(self):
        from cmm.eval import assign_blind_answers, normalize_judge_payload

        mapping = assign_blind_answers("CASE-1", _baseline(), _cmm())
        result = normalize_judge_payload(None, mapping, raw="not json")

        self.assertEqual(result["winner"], "TIE")
        self.assertEqual(result["baseline_scores"]["overall"], 0.0)
        self.assertEqual(result["cmm_scores"]["overall"], 0.0)
        self.assertIn("judge_json_parse_failed", result["parse_warnings"])
        self.assertEqual(result["raw"], "not json")

    def test_judge_mode_none_writes_human_review_without_judge_call(self):
        from cmm.eval import run_eval

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dataset = tmp_path / "dataset.csv"
            out = tmp_path / "out"
            _write_fixture(dataset)

            with patch("cmm.eval._real_baseline", return_value=_baseline()), patch(
                "cmm.eval._real_cmm", return_value=_cmm()
            ), patch("Lib.AI_request.send_to_AI", side_effect=AssertionError("judge should not run")):
                result = run_eval(
                    str(dataset),
                    limit=1,
                    mode="real",
                    judge_mode="none",
                    output_dir=str(out),
                )

            self.assertEqual(result["summary"]["judge_mode"], "none")
            self.assertTrue((out / "results.csv").exists())
            self.assertTrue((out / "results.json").exists())
            self.assertTrue((out / "summary.json").exists())
            self.assertTrue((out / "cases.jsonl").exists())
            self.assertTrue((out / "human_review.jsonl").exists())
            packet = json.loads((out / "human_review.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertIn("answer_a", packet)
            self.assertIn("answer_b", packet)

    def test_real_judged_run_writes_artifacts_with_mocked_llm_judge(self):
        from cmm.eval import run_eval

        judge_payload = {
            "answer_a_scores": {
                "rubric_coverage": 7,
                "perspective_coverage": 7,
                "risk_handling": 7,
                "actionability": 7,
                "clarity": 7,
                "overall": 7,
            },
            "answer_b_scores": {
                "rubric_coverage": 7.2,
                "perspective_coverage": 7.2,
                "risk_handling": 7.2,
                "actionability": 7.2,
                "clarity": 7.2,
                "overall": 7.2,
            },
            "winner": "B",
            "reason": "Close results.",
            "answer_a_failure_modes": [],
            "answer_b_failure_modes": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dataset = tmp_path / "dataset.csv"
            out = tmp_path / "out"
            _write_fixture(dataset)

            with patch("cmm.eval._real_baseline", return_value=_baseline()), patch(
                "cmm.eval._real_cmm", return_value=_cmm()
            ), patch("Lib.AI_request.send_to_AI", return_value=json.dumps(judge_payload)):
                result = run_eval(
                    str(dataset),
                    limit=1,
                    mode="real",
                    judge_mode="llm",
                    output_dir=str(out),
                )

            self.assertEqual(result["summary"]["judge_mode"], "llm")
            self.assertTrue((out / "results.csv").exists())
            self.assertTrue((out / "results.json").exists())
            self.assertTrue((out / "summary.json").exists())
            self.assertTrue((out / "cases.jsonl").exists())
            self.assertFalse((out / "human_review.jsonl").exists())
            artifact = json.loads((out / "cases.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertIn("raw_judge_output", artifact)
            self.assertIn("normalized_judge_result", artifact)

    def test_expected_rubric_not_injected_into_generated_answers(self):
        from cmm.eval import _real_baseline, _real_cmm

        case = {
            "id": "CASE-1",
            "query": "Question?",
            "context": "Visible context",
            "constraints": "Visible constraints",
            "rubric_must_cover": "Hidden rubric item",
            "expected_perspectives": "Hidden perspective",
            "expected_single_model_failure_modes": "Hidden failure mode",
        }
        captured = {}

        def fake_send_to_ai(user_prompt, system_prompt="", **kwargs):
            captured["baseline_prompt"] = user_prompt
            return "baseline"

        def fake_run_cmm(query):
            captured["cmm_query"] = query
            return {"final_answer": "cmm", "trace_report": {}}

        with patch("Lib.AI_request.send_to_AI", side_effect=fake_send_to_ai):
            _real_baseline(case)
        with patch("Lib.orchestrator.run_cmm", side_effect=fake_run_cmm):
            _real_cmm(case)

        self.assertIn("Visible context", captured["baseline_prompt"])
        self.assertIn("Visible constraints", captured["baseline_prompt"])
        self.assertNotIn("Hidden rubric item", captured["baseline_prompt"])
        self.assertNotIn("Hidden perspective", captured["baseline_prompt"])
        self.assertNotIn("Hidden failure mode", captured["baseline_prompt"])
        self.assertIn("Visible context", captured["cmm_query"])
        self.assertIn("Visible constraints", captured["cmm_query"])
        self.assertNotIn("Hidden rubric item", captured["cmm_query"])
        self.assertNotIn("Hidden perspective", captured["cmm_query"])
        self.assertNotIn("Hidden failure mode", captured["cmm_query"])


if __name__ == "__main__":
    unittest.main()
