#!/usr/bin/env python3
"""Aggregate per-run metrics emitted by planner/bt_controller into CSV.

Expected layout:
  <metrics_dir>/<run_id>/planner.json
  <metrics_dir>/<run_id>/bt_controller.json

The script flattens nested dictionaries into dotted keys and appends one row
per run to <metrics_dir>/summary.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict


def _flatten(obj: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten(value, next_prefix))
        return out

    if isinstance(obj, list):
        out[prefix] = json.dumps(obj, sort_keys=True)
        return out

    out[prefix] = obj
    return out


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def aggregate(metrics_dir: Path) -> Path:
    rows: list[Dict[str, Any]] = []
    for run_dir in sorted(p for p in metrics_dir.iterdir() if p.is_dir()):
        run_id = run_dir.name
        planner = _read_json(run_dir / "planner.json")
        bt_controller = _read_json(run_dir / "bt_controller.json")

        row: Dict[str, Any] = {"run_id": run_id}
        if planner:
            row.update({f"planner.{k}": v for k, v in _flatten(planner).items()})
        if bt_controller:
            row.update({f"bt_controller.{k}": v for k, v in _flatten(bt_controller).items()})
        rows.append(row)

    summary_path = metrics_dir / "summary.csv"
    if not rows:
        with summary_path.open("w", encoding="utf-8"):
            pass
        return summary_path

    headers = sorted({key for row in rows for key in row.keys()})
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    return summary_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate run metrics into a summary CSV")
    parser.add_argument(
        "--metrics-dir",
        default="/data/run_metrics",
        help="Directory containing one subdirectory per run_id",
    )
    args = parser.parse_args()

    metrics_dir = Path(args.metrics_dir)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    output = aggregate(metrics_dir)
    print(output)


if __name__ == "__main__":
    main()
