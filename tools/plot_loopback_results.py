#!/usr/bin/env python3
"""Rebuild one figure from retained evidence. Standard library; no experiments.

This checks the plotted numeric derivation, not the complete chain of custody.
Run the study's verify_publication.py for its independent integrity checks.
"""
import argparse
import csv
import hashlib
import html
import io
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "studies/loopback-framing-comparison/reproduction/studies/loopback-framing-comparison"
FIGURE = ROOT / "docs/results/loopback-framing-ratios.svg"
RUNS = ("run-001", "run-002")
CASES = ("activation_decode", "activation_prefill_16", "activation_prefill_64", "audit_reply")
FRAME_BYTES = (2368, 36928, 147520, 196676)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same_number(actual, expected, label):
    require(type(actual) in (int, float) and math.isfinite(actual), f"{label}: not finite numeric data")
    require(math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12), f"{label}: source mismatch")


def summary(values):
    quartiles = statistics.quantiles(values, method="inclusive")
    return {"median": statistics.median(values), "min": min(values),
            "max": max(values), "iqr": quartiles[2] - quartiles[0]}


def derive_points(runs, csv_rows):
    """Reconstruct all 128 numeric summaries from the 160 retained timing rows."""
    require(len(runs) == 2, "Exactly two retained runs are required")
    expected_cells = [(run, case) for run in RUNS for case in CASES]
    require([(row["run"], row["case"]) for row in csv_rows] == expected_cells,
            "CSV must contain every case/run once in retained order")
    points = []
    for run_index, (name, run) in enumerate(zip(RUNS, runs)):
        require(run["mode"] == name and run["status"] == "complete", "Run identity/status mismatch")
        rows = run["rows"]
        require(len(rows) == 80, f"{name}: expected 80 measured rows")
        require([item["case"] for item in run["summary"]] == list(CASES), "JSON summary case mismatch")
        batches = {case: {"baseline": [], "candidate": []} for case in CASES}
        offset = 0
        for block in range(10):
            for case_index, case in enumerate(CASES):
                order = ("baseline", "candidate") if (block + case_index) % 2 == 0 else ("candidate", "baseline")
                for variant in order:
                    row = rows[offset]
                    require((row["case"], row["variant"], row["phase"]) == (case, variant, "measure"),
                            f"{name}: measured schedule mismatch")
                    for field, expected in (("block", block), ("index", offset + 8), ("iterations", 10)):
                        require(type(row[field]) is int and row[field] == expected, f"{name}: {field} mismatch")
                    require(type(row["wall_ns"]) is int and row["wall_ns"] > 0, "Invalid batch duration")
                    per_exchange = row["wall_ns"] / row["iterations"]
                    same_number(row["wall_ns_per_exchange"], per_exchange, "Raw batch mean")
                    batches[case][variant].append(per_exchange)
                    offset += 1
        for case_index, case in enumerate(CASES):
            baseline = batches[case]["baseline"]
            candidate = batches[case]["candidate"]
            paired = [b / a for a, b in zip(baseline, candidate)]
            derived = {"baseline_ns": summary(baseline), "candidate_ns": summary(candidate),
                       "paired_ratio": summary(paired),
                       "paired_difference_ns": summary([b - a for a, b in zip(baseline, candidate)])}
            csv_row = csv_rows[run_index * 4 + case_index]
            require(csv_row["paired_batches"] == "10" and csv_row["exchanges_per_batch"] == "10",
                    "CSV denominator mismatch")
            for statistic, values in derived.items():
                for measure, value in values.items():
                    same_number(run["summary"][case_index][statistic][measure], value, "JSON summary")
                    same_number(float(csv_row[f"{statistic}_{measure}"]), value, "CSV summary")
            require(run["fixtures"][case]["frame_bytes"] == FRAME_BYTES[case_index], "Frame-size mismatch")
            points.append({"run": name, "case": case,
                           "ratio": derived["paired_ratio"]["median"], "frame_bytes": FRAME_BYTES[case_index]})
    return points


def table_rows(points):
    cells = {(point["run"], point["case"]): point for point in points}
    return [f"| {case} | {FRAME_BYTES[index]:,} | {cells[('run-001', case)]['ratio']:.6f} | "
            f"{cells[('run-002', case)]['ratio']:.6f} |" for index, case in enumerate(CASES)]


def check_document(document, points):
    for row in table_rows(points):
        require(document.count(row) == 1, "RESULTS.md numeric table differs from source")


def render_svg(points):
    """Directly labeled paired dot plot; exactly eight observations, no intervals."""
    values = {(point["run"], point["case"]): point for point in points}
    left, right = 320, 920
    # Include zero, every observed median and the equal-latency reference.
    xmax = max(1.0, max(point["ratio"] for point in points)) * 1.08
    def x(value):
        return left + value / xmax * (right - left)
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="650" viewBox="0 0 1000 650" role="img" aria-labelledby="title description">',
        '  <title id="title">Complete delivery-and-ACK latency: candidate / baseline</title>',
        '  <desc id="description">Four synthetic payload cases, two runs on one host. '
        + html.escape("; ".join(f"{p['case']}, {p['run']}: {p['ratio']:.6f}" for p in points))
        + '. Each point is the median of ten paired batch-mean ratios. Lower is better; 1 means equal latency. No uncertainty intervals are shown.</desc>',
        '  <rect width="1000" height="650" fill="#ffffff"/>',
        '  <g font-family="DejaVu Sans, Arial, sans-serif" fill="#17202b">',
        '    <text x="30" y="44" font-size="26" font-weight="700">Less time for this loopback exchange</text>',
        '    <text x="30" y="76" font-size="17">Complete delivery-and-ACK latency, not throughput or model performance</text>',
        '    <circle cx="40" cy="115" r="6" fill="#0072b2"/>',
        '    <text x="56" y="121" font-size="16">run-001</text>',
        '    <rect x="172" y="109" width="12" height="12" fill="#b95106"/>',
        '    <text x="194" y="121" font-size="16">run-002</text>',
        '    <text x="920" y="121" font-size="15" text-anchor="end">Same host; runs are not independent hosts</text>',
    ]
    for tick in (0, 0.25, 0.5, 0.75, 1):
        marker = ' id="reference-one"' if tick == 1 else ''
        stroke = '#69717b' if tick == 1 else '#e1e5e9'
        dash = ' stroke-dasharray="5 5"' if tick == 1 else ''
        lines.append(f'    <line{marker} x1="{x(tick):.3f}" y1="165" x2="{x(tick):.3f}" y2="520" stroke="{stroke}"{dash}/>')
        lines.append(f'    <text x="{x(tick):.3f}" y="546" font-size="16" text-anchor="middle">{tick:g}</text>')
    lines.append(f'    <text x="{x(1):.3f}" y="154" font-size="15" text-anchor="middle">Equal latency</text>')
    for case_index, case in enumerate(CASES):
        y = 202 + case_index * 92
        lines.append(f'    <text x="30" y="{y}" font-size="17" font-weight="600">{case}</text>')
        lines.append(f'    <text x="30" y="{y + 24}" font-size="15" fill="#53606e">{FRAME_BYTES[case_index]:,} frame bytes</text>')
        for run_index, run in enumerate(RUNS):
            point = values[(run, case)]
            px, py = x(point["ratio"]), y - 8 + run_index * 29
            label = f'{run}/{case}'
            if run_index == 0:
                lines.append(f'    <circle data-point="{label}" cx="{px:.3f}" cy="{py}" r="6" fill="#0072b2"/>')
            else:
                lines.append(f'    <rect data-point="{label}" x="{px - 6:.3f}" y="{py - 6}" width="12" height="12" fill="#b95106"/>')
            lines.append(f'    <text x="{px + 13:.3f}" y="{py + 5}" font-size="16">{point["ratio"]:.6f}</text>')
    lines += [
        '    <text x="620" y="578" font-size="18" text-anchor="middle">Paired median candidate / baseline latency</text>',
        '    <text x="320" y="607" font-size="15">Lower values favor candidate</text>',
        '    <text x="920" y="607" font-size="15" text-anchor="end">No uncertainty intervals; descriptive medians only</text>',
        '    <text x="30" y="635" font-size="14" fill="#53606e">Source: retained run-001/run-002 result.json and SUMMARY.csv; 10 paired batches per point.</text>',
        '  </g>', '</svg>', '',
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, default=STUDY, help="Retained evidence directory")
    parser.add_argument("--output", type=Path, default=FIGURE, help="SVG destination")
    parser.add_argument("--document", type=Path, default=ROOT / "RESULTS.md", help="Reader-facing numeric table")
    parser.add_argument("--check", action="store_true", help="Check existing figure byte-for-byte; write nothing")
    args = parser.parse_args(argv)
    source_files = [args.study / run / "result.json" for run in RUNS] + [args.study / "SUMMARY.csv"]
    blobs = [path.read_bytes() for path in source_files]
    runs = [json.loads(blob) for blob in blobs[:2]]
    csv_rows = list(csv.DictReader(io.StringIO(blobs[2].decode("utf-8"))))
    points = derive_points(runs, csv_rows)
    check_document(args.document.read_text(encoding="utf-8"), points)
    svg = render_svg(points).encode("utf-8")
    if args.check:
        require(args.output.read_bytes() == svg, "SVG differs from deterministic source rendering")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(svg)
    print(json.dumps({"status": "PASS", "measured_rows_checked": 160, "numeric_summaries_checked": 128,
                      "points": points, "figure_sha256": hashlib.sha256(svg).hexdigest(),
                      "source_sha256": {str(path.relative_to(args.study)): hashlib.sha256(blob).hexdigest()
                                        for path, blob in zip(source_files, blobs)}}, indent=2))


if __name__ == "__main__":
    main()
