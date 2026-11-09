#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ground_truth_validation import evaluate_tracking_ground_truth


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate tracking against frame annotations")
    parser.add_argument("engine_result", type=Path)
    parser.add_argument("annotations", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_tracking_ground_truth(
        json.loads(args.engine_result.read_text(encoding="utf-8")),
        json.loads(args.annotations.read_text(encoding="utf-8")),
    )
    encoded = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
