"""Demonstration of reproducible QA using only synthetic measurements.

No external datasets or unpublished research workflows are used.
"""

from __future__ import annotations

import csv
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

MIN_VALUE = 0.0  # Arbitrary illustrative threshold, not a scientific standard.
MAX_VALUE = 100.0


def classify(value: float | None) -> str:
    """Preserve separate categories for missing and invalid observations."""
    if value is None:
        return "missing"
    if not math.isfinite(value) or not MIN_VALUE <= value <= MAX_VALUE:
        return "out_of_range"
    return "valid"


def generate_records(seed: int = 2026, periods: int = 24) -> list[dict]:
    """Construct deterministic fictional data with deliberately missing values."""
    if periods < 1:
        raise ValueError("periods must be positive")
    rng = random.Random(seed)
    records = []
    for group_index, group in enumerate(("Group A", "Group B", "Group C")):
        for period in range(1, periods + 1):
            value = (45.0 + group_index * 4.0
                     + 8.0 * math.sin(2.0 * math.pi * period / 12.0)
                     + rng.gauss(0, 3.0))
            if (period + group_index) % 13 == 0:
                value = None
            if group_index == 1 and period == 5:
                value = 125.0  # Fictional out-of-range example.
            records.append({
                "group": group,
                "period": period,
                "measurement": value,
                "qa_status": classify(value),
            })
    return records


def summarize(records: list[dict]) -> list[dict]:
    """Report completeness and valid means without silently imputing data."""
    by_group = defaultdict(list)
    for record in records:
        by_group[record["group"]].append(record)

    summaries = []
    for group in sorted(by_group):
        group_records = by_group[group]
        valid = [r["measurement"] for r in group_records
                 if r["qa_status"] == "valid"]
        total = len(group_records)
        missing = sum(r["qa_status"] == "missing" for r in group_records)
        invalid = sum(r["qa_status"] == "out_of_range" for r in group_records)
        summaries.append({
            "group": group,
            "n_total": total,
            "n_valid": len(valid),
            "n_missing": missing,
            "n_out_of_range": invalid,
            "valid_fraction": round(len(valid) / total, 4),
            "valid_mean": round(statistics.fmean(valid), 3) if valid else None,
        })
    return summaries


def write_table(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    data = generate_records()
    summary = summarize(data)
    output = Path("output")
    write_table(output / "synthetic_observations.csv", data,
                ["group", "period", "measurement", "qa_status"])
    write_table(output / "qa_summary.csv", summary,
                ["group", "n_total", "n_valid", "n_missing",
                 "n_out_of_range", "valid_fraction", "valid_mean"])
    print("Generated two reproducible CSV files in output/")
    for row in summary:
        print(row)


if __name__ == "__main__":
    main()
