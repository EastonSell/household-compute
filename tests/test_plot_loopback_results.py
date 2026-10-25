"""Read-only figure regressions; never import or execute the experiment."""
import copy
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
import statistics
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
STUDY = Path(os.environ.get(
    "LOOPBACK_STUDY", str(ROOT / "studies/loopback-framing-comparison/reproduction/studies/loopback-framing-comparison")
))
SCRIPT = ROOT / "tools/plot_loopback_results.py"


class LoopbackFigureTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "The source-checking figure generator is not implemented")
        spec = importlib.util.spec_from_file_location("loopback_plot", SCRIPT)
        self.plot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.plot)
        self.runs = [json.loads((STUDY / run / "result.json").read_text())
                     for run in ("run-001", "run-002")]
        self.csv_rows = list(csv.DictReader(io.StringIO((STUDY / "SUMMARY.csv").read_text())))

    def points(self):
        return self.plot.derive_points(self.runs, self.csv_rows)

    def test_all_eight_values_match_reviewed_results(self):
        points = self.points()
        self.assertEqual(len(points), 8)
        self.assertEqual([point["ratio"] for point in points], [
            0.6117624069462284, 0.33639316090210064,
            0.2676333030704318, 0.25569411118476454,
            0.5346045437976167, 0.307108879624717,
            0.27452246756916865, 0.2635728485517217,
        ])

    def test_statistic_is_paired_median_not_ratio_of_medians(self):
        point = self.points()[0]
        rows = [row for row in self.runs[0]["rows"] if row["case"] == "activation_decode"]
        baseline = [row["wall_ns_per_exchange"] for row in rows if row["variant"] == "baseline"]
        candidate = [row["wall_ns_per_exchange"] for row in rows if row["variant"] == "candidate"]
        self.assertAlmostEqual(point["ratio"], statistics.median(b / a for a, b in zip(baseline, candidate)))
        self.assertGreater(abs(point["ratio"] - statistics.median(candidate) / statistics.median(baseline)), 0.02)

    def test_missing_run_is_rejected(self):
        with self.assertRaises(ValueError):
            self.plot.derive_points(self.runs[:1], self.csv_rows)

    def test_duplicate_csv_cell_is_rejected(self):
        self.csv_rows[-1] = copy.deepcopy(self.csv_rows[0])
        with self.assertRaises(ValueError):
            self.points()

    def test_missing_raw_row_is_rejected(self):
        self.runs[0]["rows"].pop()
        with self.assertRaises(ValueError):
            self.points()

    def test_reordered_or_duplicated_pair_is_rejected(self):
        self.runs[0]["rows"][0] = copy.deepcopy(self.runs[0]["rows"][1])
        with self.assertRaises(ValueError):
            self.points()

    def test_bad_batch_duration_is_rejected(self):
        for value in (True, 0, -1, float("nan"), float("inf")):
            with self.subTest(value=value):
                altered = copy.deepcopy(self.runs)
                altered[0]["rows"][0]["wall_ns"] = value
                with self.assertRaises(ValueError):
                    self.plot.derive_points(altered, self.csv_rows)

    def test_batch_mean_mismatch_is_rejected(self):
        self.runs[0]["rows"][0]["wall_ns_per_exchange"] += 1
        with self.assertRaises(ValueError):
            self.points()

    def test_csv_statistic_mismatch_is_rejected(self):
        self.csv_rows[0]["paired_ratio_median"] = "0.5"
        with self.assertRaises(ValueError):
            self.points()

    def test_json_summary_mismatch_is_rejected(self):
        self.runs[0]["summary"][0]["paired_ratio"]["median"] = 0.5
        with self.assertRaises(ValueError):
            self.points()

    def test_warmups_cannot_become_measured_rows(self):
        self.runs[0]["rows"][0]["phase"] = "warmup"
        with self.assertRaises(ValueError):
            self.points()

    def test_figure_has_eight_marks_and_reference_one(self):
        svg = self.plot.render_svg(self.points())
        root = ET.fromstring(svg)
        marks = [node for node in root.iter() if node.get("data-point")]
        self.assertEqual(len(marks), 8)
        self.assertEqual(len({node.get("data-point") for node in marks}), 8)
        reference = [node for node in root.iter() if node.get("id") == "reference-one"]
        self.assertEqual(len(reference), 1)
        self.assertIn("No uncertainty intervals", svg)
        self.assertNotIn("<script", svg)

    def test_figure_is_deterministic(self):
        self.assertEqual(self.plot.render_svg(self.points()), self.plot.render_svg(self.points()))

    def test_readme_table_matches_source_and_rejects_drift(self):
        document = (ROOT / "RESULTS.md").read_text()
        self.plot.check_document(document, self.points())
        with self.assertRaises(ValueError):
            self.plot.check_document(document.replace("0.611762", "0.500000"), self.points())

    def test_committed_figure_matches_generator(self):
        self.assertEqual((ROOT / "docs/results/loopback-framing-ratios.svg").read_text(),
                         self.plot.render_svg(self.points()))


if __name__ == "__main__":
    unittest.main()
