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

    def test_scoring_detects_coverage_and_winner(self):
        from cmm.eval import score_case

        case = {
            "case_id": "CASE-1",
            "rubric_must_cover": "limited budget | hybrid university",
            "expected_perspectives": "strategy | risk",
            "expected_single_model_failure_modes": "generic advice",
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
                "cmm_mode": "FULL_CMM",
                "router_decision": {"complexity": "high", "estimated_cost_class": "L"},
                "estimated_cost_class": "L",
            },
        }

        result = score_case(case, baseline, cmm)

        self.assertEqual(result["winner"], "CMM")
        self.assertGreater(result["rubric_coverage_delta"], 0)
        self.assertGreater(result["perspective_coverage_delta"], 0)
        self.assertEqual(result["cmm_mode"], "FULL_CMM")
        self.assertEqual(result["router_complexity"], "high")
        self.assertEqual(result["estimated_cost_class"], "L")

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
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["results"]), 1)
            self.assertIn("cmm_mode", payload["results"][0])
            self.assertIn("router_complexity", payload["results"][0])
            self.assertIn("estimated_cost_class", payload["results"][0])


if __name__ == "__main__":
    unittest.main()
