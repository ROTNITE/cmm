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
            "rubric_desirable": "pilot",
            "reference_outline": "Use a pilot",
            "expected_single_model_failure_modes": "generic advice | no metrics",
            "expected_mode": "LIGHT_CMM",
        }
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class EvalHarnessTests(unittest.TestCase):
    def test_parse_pipe_list(self):
        from cmm.eval import parse_pipe_list

        self.assertEqual(parse_pipe_list("a | b | c"), ["a", "b", "c"])
        self.assertEqual(parse_pipe_list("  a  |  | b "), ["a", "b"])
        self.assertEqual(parse_pipe_list(""), [])

    def test_loader_reads_fixture_and_reports_schema(self):
        from cmm.eval import load_dataset

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dataset.csv"
            _write_fixture(path)

            rows, schema = load_dataset(str(path))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["case_id"], "CASE-1")
        self.assertEqual(schema["row_count"], 1)
        self.assertIn("expected_domain_expert", schema["missing_optional_columns"])
        self.assertEqual(rows[0]["expected_mode"], "LIGHT_CMM")

    def test_scoring_detects_coverage_and_winner(self):
        from cmm.eval import score_case

        case = {
            "case_id": "CASE-1",
            "rubric_must_cover": "limited budget | hybrid university",
            "expected_perspectives": "strategy | risk",
            "expected_single_model_failure_modes": "generic advice",
            "expected_mode": "FULL_CMM",
            "schema_warnings": [],
        }
        baseline = {
            "answer": "generic advice",
            "trace_report": {"roles_used": []},
        }
        cmm = {
            "answer": "limited budget and hybrid university with generic advice mitigation",
            "trace_report": {
                "roles_used": [
                    {"perspective_tag": "strategy"},
                    {"perspective_tag": "risk"},
                ],
                "roles_used_unique": [
                    {"key": "strategist", "perspective_tag": "strategy", "rounds": ["initial"], "dynamic": False}
                ],
                "cmm_mode": "FULL_CMM",
                "router_decision": {"complexity": "high", "estimated_cost_class": "L"},
                "estimated_cost_class": "L",
                "estimated_call_count": 7,
                "estimated_stage_count": 9,
                "answer_chars": 64,
                "warnings_count": 1,
                "errors_count": 0,
                "plan_critique_score_source": "rule_recomputed",
                "plan_critique_stall_reason": "ignored_sets_not_shrinking",
                "answer_generation_source": "model",
                "best_effort_trigger_reason": "",
            },
        }

        result = score_case(case, baseline, cmm)

        self.assertEqual(result["winner"], "CMM")
        self.assertGreater(result["rubric_coverage_delta"], 0)
        self.assertGreater(result["perspective_coverage_delta"], 0)
        self.assertEqual(result["cmm_mode"], "FULL_CMM")
        self.assertEqual(result["expected_mode"], "FULL_CMM")
        self.assertEqual(result["actual_mode"], "FULL_CMM")
        self.assertTrue(result["router_mode_match"])
        self.assertEqual(result["router_complexity"], "high")
        self.assertEqual(result["estimated_cost_class"], "L")
        self.assertEqual(result["cmm_final_state"], "")
        self.assertEqual(result["expert_valid_contributions"], 0)
        self.assertIn("planner_raw_format", result)
        self.assertIn("strategist", result["roles_used_unique"])
        self.assertEqual(result["estimated_call_count"], 7)
        self.assertEqual(result["estimated_stage_count"], 9)
        self.assertEqual(result["answer_chars"], 64)
        self.assertEqual(result["warnings_count"], 1)
        self.assertEqual(result["errors_count"], 0)
        self.assertEqual(result["plan_critique_score_source"], "rule_recomputed")
        self.assertEqual(result["plan_critique_stall_reason"], "ignored_sets_not_shrinking")
        self.assertEqual(result["answer_generation_source"], "model")

    def test_score_can_tie(self):
        from cmm.eval import score_case

        case = {
            "case_id": "CASE-1",
            "rubric_must_cover": "alpha",
            "expected_perspectives": "",
            "expected_single_model_failure_modes": "",
            "schema_warnings": [],
        }
        output = {"answer": "alpha", "trace_report": {}}

        result = score_case(case, output, output)

        self.assertEqual(result["winner"], "TIE")

    def test_mock_cli_writes_csv_and_json_without_real_calls(self):
        from cmm.eval import main

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dataset = tmp_path / "dataset.csv"
            output_dir = tmp_path / "out"
            _write_fixture(dataset)

            with patch("Lib.AI_request.send_to_AI", side_effect=AssertionError("no API in mock")), patch(
                "Lib.orchestrator.run_cmm", side_effect=AssertionError("no real CMM in mock")
            ):
                exit_code = main(
                    [
                        "--dataset",
                        str(dataset),
                        "--limit",
                        "1",
                        "--mode",
                        "mock",
                        "--output-dir",
                        str(output_dir),
                    ]
                )

            csv_path = output_dir / "results.csv"
            json_path = output_dir / "results.json"
            self.assertEqual(exit_code, 0)
            self.assertTrue(csv_path.exists())
            self.assertTrue(json_path.exists())
            self.assertTrue((output_dir / "routing_review.csv").exists())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["results"]), 1)
            self.assertEqual(payload["results"][0]["expected_mode"], "LIGHT_CMM")
            self.assertEqual(payload["results"][0]["actual_mode"], "LIGHT_CMM")
            self.assertTrue(payload["results"][0]["router_mode_match"])
            self.assertIn("cmm_mode", payload["results"][0])
            self.assertIn("router_complexity", payload["results"][0])
            self.assertIn("estimated_cost_class", payload["results"][0])
            self.assertIn("cmm_final_state", payload["results"][0])
            self.assertIn("expert_invalid_json_contributions", payload["results"][0])
            self.assertIn("roles_used_unique", payload["results"][0])
            self.assertIn("estimated_call_count", payload["results"][0])
            self.assertIn("answer_chars", payload["results"][0])

    def test_mock_eval_summary_contains_router_metrics(self):
        from cmm.eval import run_eval

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dataset = tmp_path / "dataset.csv"
            output_dir = tmp_path / "out"
            _write_fixture(dataset)

            result = run_eval(str(dataset), limit=1, mode="mock", output_dir=str(output_dir))

        summary = result["summary"]
        self.assertEqual(summary["router_expected_cases"], 1)
        self.assertEqual(summary["router_mode_matches"], 1)
        self.assertEqual(summary["router_mode_accuracy"], 1.0)
        self.assertIn("actual_mode_distribution", summary)
        self.assertIn("technical_failures_by_mode", summary)
        self.assertIn("average_cmm_answer_length", summary)
        self.assertIn("average_estimated_cost_score", summary)

    def test_real_judge_none_writes_human_and_routing_review_files(self):
        from cmm.eval import run_eval

        fake_baseline = {"answer": "baseline", "trace_report": {"mode": "baseline"}}
        fake_cmm = {
            "answer": "limited budget hybrid university strategy",
            "final_answer": "limited budget hybrid university strategy",
            "trace_report": {
                "cmm_mode": "LIGHT_CMM",
                "router_decision": {"mode": "LIGHT_CMM", "complexity": "medium", "estimated_cost_class": "M"},
                "estimated_cost_class": "M",
                "final_state": "FINALIZE",
                "answer_chars": 41,
                "warnings": [],
                "errors": [],
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dataset = tmp_path / "dataset.csv"
            output_dir = tmp_path / "real"
            _write_fixture(dataset)
            with patch("cmm.eval._real_baseline", return_value=fake_baseline), patch(
                "cmm.eval._real_cmm", return_value=fake_cmm
            ):
                result = run_eval(str(dataset), limit=1, mode="real", judge_mode="none", output_dir=str(output_dir))

            self.assertTrue((output_dir / "human_review.jsonl").exists())
            self.assertTrue((output_dir / "human_review.csv").exists())
            self.assertTrue((output_dir / "routing_review.csv").exists())
            summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))

        self.assertEqual(result["results"][0]["expected_mode"], "LIGHT_CMM")
        self.assertEqual(result["results"][0]["actual_mode"], "LIGHT_CMM")
        self.assertTrue(result["results"][0]["router_mode_match"])
        self.assertIn("human_review_csv", summary["output_paths"])
        self.assertIn("routing_review_csv", summary["output_paths"])
        self.assertEqual(summary["router_mode_accuracy"], 1.0)

    def test_run_eval_real_honors_explicit_model_and_judge_model(self):
        from cmm.eval import run_eval

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dataset = tmp_path / "dataset.csv"
            _write_fixture(dataset)

            with patch("cmm.eval._run_real_judged_eval", return_value={"summary": {}, "results": []}) as mock_run:
                run_eval(
                    str(dataset),
                    limit=1,
                    mode="real",
                    judge_mode="llm",
                    output_dir=str(tmp_path / "out"),
                    model="kr/claude-sonnet-4.5",
                    judge_model="kr/claude-sonnet-4.5",
                )

        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["model"], "kr/claude-sonnet-4.5")
        self.assertEqual(kwargs["judge_model"], "kr/claude-sonnet-4.5")

    def test_run_eval_real_uses_explicit_model_for_judge_when_judge_model_missing(self):
        from cmm.eval import run_eval

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dataset = tmp_path / "dataset.csv"
            _write_fixture(dataset)

            with patch("cmm.eval._run_real_judged_eval", return_value={"summary": {}, "results": []}) as mock_run:
                run_eval(
                    str(dataset),
                    limit=1,
                    mode="real",
                    judge_mode="llm",
                    output_dir=str(tmp_path / "out"),
                    model="kr/claude-sonnet-4.5",
                )

        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs["model"], "kr/claude-sonnet-4.5")
        self.assertEqual(kwargs["judge_model"], "kr/claude-sonnet-4.5")


if __name__ == "__main__":
    unittest.main()
