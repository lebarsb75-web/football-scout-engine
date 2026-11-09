#!/usr/bin/env python3
"""Evaluate a labelled collection without launching any GPU jobs.

Manifest format:
{"sequences": [{"name": "clip-01", "result": "results/01.json",
                "annotations": "labels/01.json"}]}
Paths are resolved relative to the manifest.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ground_truth_validation import evaluate_tracking_ground_truth


def evaluate_suite(manifest_path: Path, minimum_sequences: int = 10) -> dict:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sequences = manifest.get("sequences")
    if not isinstance(sequences, list):
        raise ValueError("manifest.sequences must be a list")
    names = set()
    reports = []
    for item in sequences:
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k].strip() for k in ("name", "result", "annotations")):
            raise ValueError("each sequence needs nonempty name, result and annotations paths")
        name = item["name"]
        if name in names:
            raise ValueError(f"duplicate sequence name: {name}")
        names.add(name)
        row = {"name": name}
        try:
            result_path = manifest_path.parent / item["result"]
            labels_path = manifest_path.parent / item["annotations"]
            result = json.loads(result_path.read_text(encoding="utf-8"))
            annotations = json.loads(labels_path.read_text(encoding="utf-8"))
            row["tracking"] = evaluate_tracking_ground_truth(result, annotations)
            row["passed"] = row["tracking"]["ground_truth_tracking_gate_passed"]
        except (OSError, ValueError, TypeError, KeyError, ZeroDivisionError) as exc:
            row["passed"] = False
            row["error"] = f"{type(exc).__name__}: {exc}"
        reports.append(row)
    passed_count = sum(bool(row["passed"]) for row in reports)
    all_pass = len(reports) >= minimum_sequences and passed_count == len(reports)
    return {
        "sequence_count": len(reports),
        "required_sequence_count": minimum_sequences,
        "passed_sequence_count": passed_count,
        "failed_sequence_count": len(reports) - passed_count,
        "tracking_validation_passed": all_pass,
        "commercial_readiness": "NOT_ASSESSED",
        "note": "Tracking validation alone does not validate touches, possession, actions or distance.",
        "sequences": reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate at least ten independently annotated football clips")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, help="Write a JSON report to this path")
    parser.add_argument("--minimum-sequences", type=int, default=10)
    args = parser.parse_args()
    if args.minimum_sequences < 1:
        parser.error("--minimum-sequences must be >= 1")
    try:
        report = evaluate_suite(args.manifest, args.minimum_sequences)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Invalid validation manifest: {exc}\n")
    output = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0 if report["tracking_validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
