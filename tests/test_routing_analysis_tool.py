import csv
import tempfile
import unittest
from pathlib import Path


class RoutingAnalysisToolTests(unittest.TestCase):
    def test_analyze_eval_routing_classifies_failures(self):
        from tools.analyze_eval_routing import analyze_file

        rows = [
            {
                "case_id": "A",
                "expected_mode": "FULL_CMM",
                "actual_mode": "FULL_CMM",
                "router_mode_match": "True",
                "winner": "CMM",
                "cmm_final_state": "FAILED",
                "cmm_errors": "plan_failed",
                "answer_chars": "0",
                "cmm_warnings": "",
            },
            {
                "case_id": "B",
                "expected_mode": "FULL_CMM",
                "actual_mode": "LIGHT_CMM",
                "router_mode_match": "False",
                "winner": "TIE",
                "cmm_final_state": "FINALIZE",
                "cmm_errors": "",
                "answer_chars": "120",
                "cmm_warnings": "warn",
            },
            {
                "case_id": "C",
                "expected_mode": "DIRECT",
                "actual_mode": "DIRECT",
                "router_mode_match": "True",
                "winner": "BASELINE",
                "cmm_final_state": "FINALIZE",
                "cmm_errors": "",
                "answer_chars": "80",
                "cmm_warnings": "",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "results.csv"
            output = tmp_path / "routing_analysis.csv"
            with source.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

            result = analyze_file(str(source), str(output))

            with output.open(encoding="utf-8", newline="") as file:
                analyzed = list(csv.DictReader(file))

        self.assertEqual(result["rows"], 3)
        self.assertEqual(analyzed[0]["failure_mode"], "technical_failure")
        self.assertEqual(analyzed[1]["failure_mode"], "router_mismatch")
        self.assertEqual(analyzed[2]["failure_mode"], "baseline_win")


if __name__ == "__main__":
    unittest.main()
