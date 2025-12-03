from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


def load_records(path: Path) -> List[Dict]:
    records: List[Dict] = []
    if not path.exists():
        raise FileNotFoundError(f"No results file at {path}")
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def summarize(records: List[Dict]) -> Tuple[Dict, Dict]:
    per_model: Dict[str, Dict] = defaultdict(lambda: {"dim": [], "upaya": [], "by_dim": defaultdict(list)})
    for rec in records:
        model = rec.get("model", "unknown")
        dimension = rec.get("dimension", "unknown")
        judge = rec.get("judge") or {}
        dim_score = judge.get("dimension_score")
        upaya_score = judge.get("upaya_score")
        if isinstance(dim_score, int):
            per_model[model]["dim"].append(dim_score)
            per_model[model]["by_dim"][dimension].append(dim_score)
        if isinstance(upaya_score, int):
            per_model[model]["upaya"].append(upaya_score)
    return per_model, records


def mean(values: List[int]) -> float:
    return sum(values) / len(values) if values else float("nan")


def report(path: Path, threshold: int) -> None:
    records = load_records(path)
    per_model, _ = summarize(records)

    print(f"Loaded {len(records)} records from {path}")
    print("\nModel averages:")
    for model, data in per_model.items():
        dim_avg = mean(data["dim"])
        upaya_vals = data["upaya"]
        upaya_avg = mean(upaya_vals) if upaya_vals else float("nan")
        upaya_str = f"{upaya_avg:.2f}" if upaya_vals else "n/a"
        print(f"- {model}: dimension_avg={dim_avg:.2f} ({len(data['dim'])} items), upaya_avg={upaya_str}")

    print("\nPer-dimension averages by model:")
    for model, data in per_model.items():
        print(f"{model}:")
        for dimension, scores in data["by_dim"].items():
            print(f"  - {dimension}: {mean(scores):.2f} ({len(scores)})")

    print(f"\nLow scores (threshold < {threshold}):")
    low_found = False
    for rec in records:
        model = rec.get("model", "unknown")
        item_id = rec.get("item_id", "?")
        dimension = rec.get("dimension", "?")
        judge = rec.get("judge") or {}
        dim_score = judge.get("dimension_score")
        upaya_score = judge.get("upaya_score")
        dim_reason = judge.get("dimension_rationale")
        upaya_reason = judge.get("upaya_rationale")

        if isinstance(dim_score, int) and dim_score < threshold:
            low_found = True
            print(f"- {model} {item_id} ({dimension}) dimension_score={dim_score}: {dim_reason}")
        if isinstance(upaya_score, int) and upaya_score < threshold:
            low_found = True
            print(f"- {model} {item_id} ({dimension}) upaya_score={upaya_score}: {upaya_reason}")

    if not low_found:
        print("No low scores.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize benchmark results.")
    parser.add_argument("--input", default="runs/results.jsonl", help="Path to results JSONL file.")
    parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        help="Scores below this value are reported as low (applies to dimension and upaya).",
    )
    args = parser.parse_args()
    report(Path(args.input), args.threshold)


if __name__ == "__main__":
    main()
