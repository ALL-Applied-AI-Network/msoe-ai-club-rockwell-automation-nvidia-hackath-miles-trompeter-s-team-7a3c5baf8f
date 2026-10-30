#!/usr/bin/env python3
"""
order_status.py - Join the three streams' captures back together by
`order_id` (the "Order / Run #" field set in capture_gui.py - see
common.py's CAPTURE_METADATA_FIELDS), with each stream's matching image
filenames and timestamps side by side so they can be pulled up together
for one physical unit. Labeling/verdicts are handled by a separate process
outside this repo, so this only reports what was CAPTURED, not pass/fail.

For a given order_id, each stream contributes a status:
    - "captured"  that stream has at least one image for this order
    - "missing"   that stream has no image at all for this order

Usage
-----
    python3 src/order_status.py
    python3 src/order_status.py --order 42
    python3 src/order_status.py --configs config.vial_fill.yaml config.tank_level.yaml
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, load_config, read_metadata, resolve_path  # noqa: E402

DEFAULT_CONFIGS = ["config.vial_fill.yaml", "config.tank_level.yaml", "config.cap_seal.yaml"]
OUTPUT_CSV = REPO_ROOT / "data" / "order_status.csv"


def _stream_order_data(cfg: dict) -> dict[str, dict]:
    """order_id -> {"filenames": [...], "captured_ats": [...]} for one
    stream, from that stream's capture_metadata.csv."""
    metadata_rows = read_metadata(resolve_path(cfg, "capture_metadata_csv"))

    by_order: dict[str, dict] = defaultdict(lambda: {"filenames": [], "captured_ats": []})
    for row in metadata_rows:
        order_id = row.get("order_id", "").strip()
        if not order_id:
            continue  # captured before the Order # field existed, or left blank
        by_order[order_id]["filenames"].append(row["filename"])
        by_order[order_id]["captured_ats"].append(row.get("captured_at", ""))
    return dict(by_order)


def _stream_status(order_data: dict[str, dict], order_id: str) -> tuple[str, str, str]:
    """(status, filenames_joined, captured_ats_joined) for one stream/order_id."""
    entry = order_data.get(order_id)
    if not entry:
        return "missing", "", ""
    return "captured", ";".join(entry["filenames"]), ";".join(entry["captured_ats"])


def build_order_table(configs: list[dict], stream_keys: list[str]) -> list[dict]:
    per_stream = {key: _stream_order_data(cfg) for key, cfg in zip(stream_keys, configs)}

    all_order_ids = sorted(
        {oid for data in per_stream.values() for oid in data},
        key=lambda s: (len(s), s),  # numeric-friendly sort without assuming order_id is always an int
    )

    table = []
    for order_id in all_order_ids:
        row = {"order_id": order_id}
        statuses = []
        for key in stream_keys:
            status, filenames, captured_ats = _stream_status(per_stream[key], order_id)
            row[f"{key}_status"] = status
            row[f"{key}_filenames"] = filenames
            row[f"{key}_captured_at"] = captured_ats
            statuses.append(status)

        row["complete"] = "YES" if all(s == "captured" for s in statuses) else "NO"
        table.append(row)
    return table


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--configs", nargs="+", default=DEFAULT_CONFIGS, help="Config files to correlate (default: all three streams)")
    parser.add_argument("--order", default=None, help="Only show this one order_id")
    args = parser.parse_args()

    configs = [load_config(c) for c in args.configs]
    stream_keys = [Path(c).stem.removeprefix("config.") for c in args.configs]

    table = build_order_table(configs, stream_keys)
    if args.order is not None:
        table = [row for row in table if row["order_id"] == args.order]

    if not table:
        print("No orders found - capture some images with the 'Order / Run #' field set first.")
        return 0

    fieldnames = ["order_id"] + [f"{k}_{suffix}" for k in stream_keys for suffix in ("status", "filenames", "captured_at")] + ["complete"]
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(table)

    header = f"{'Order':<10}" + "".join(f"{k:>14}" for k in stream_keys) + f"{'Complete':>10}"
    print(header)
    print("-" * len(header))
    for row in table:
        print(f"{row['order_id']:<10}" + "".join(f"{row[f'{k}_status']:>14}" for k in stream_keys) + f"{row['complete']:>10}")

    complete_count = sum(1 for row in table if row["complete"] == "YES")
    print("-" * len(header))
    print(f"{len(table)} order(s): {complete_count} complete (captured on all {len(stream_keys)} streams), {len(table) - complete_count} incomplete.")
    print(f"\nWrote {OUTPUT_CSV.relative_to(REPO_ROOT)} (includes each stream's matching filename(s) and timestamp(s) per order for pulling the images up together).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
