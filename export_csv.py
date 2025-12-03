from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List


def load_records(path: Path) -> List[Dict]:
    rows: List[Dict] = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def export(records: List[Dict], out_path: Path) -> None:
    fieldnames = [
        "item_id",
        "dimension",
        "model",
        "dimension_score",
        "dimension_rationale",
        "upaya_score",
        "upaya_rationale",
    ]
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            judge = rec.get("judge") or {}
            writer.writerow(
                {
                    "item_id": rec.get("item_id"),
                    "dimension": rec.get("dimension"),
                    "model": rec.get("model"),
                    "dimension_score": judge.get("dimension_score"),
                    "dimension_rationale": judge.get("dimension_rationale"),
                    "upaya_score": judge.get("upaya_score"),
                    "upaya_rationale": judge.get("upaya_rationale"),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export JSONL results to CSV.")
    parser.add_argument("--input", default="runs/results.jsonl", help="Path to results JSONL.")
    parser.add_argument("--output", default="runs/results.csv", help="Path to write CSV.")
    args = parser.parse_args()
    records = load_records(Path(args.input))
    export(records, Path(args.output))
    print(f"Wrote {len(records)} records to {args.output}")


if __name__ == "__main__":
    main()
