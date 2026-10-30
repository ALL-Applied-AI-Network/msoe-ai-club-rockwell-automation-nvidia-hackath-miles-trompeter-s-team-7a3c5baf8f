"""
Shared helpers used by capture_gui.py and order_status.py. Keeping config
loading, path resolution, and metadata I/O in one place means the two
scripts can never drift out of sync with each other.

This module is STREAM-AGNOSTIC: every function takes a `cfg` dict (as
returned by load_config()) and never hardcodes which stream (vial_fill,
tank_level, cap_seal) it's working with. `--config config.vial_fill.yaml`,
`--config config.tank_level.yaml`, or `--config config.cap_seal.yaml` is
what picks the stream; this file just reads whatever cfg it's handed.

Labeling, splitting into Training/Testing/Validation, and dataset
verification are handled by a separate process outside this repo - this
module (and the rest of src/) is capture-only: get real images and video
out of the three cameras, with enough metadata (timestamps, order_id,
batch_id) to hand off to that process.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.vial_fill.yaml"

# Cross-stream (not under any one data/<stream>/ tree) - persists the
# auto-incrementing counter behind next_auto_batch_id() across GUI restarts.
BATCH_ID_STATE_PATH = REPO_ROOT / "data" / "batch_id_state.json"

# Logged at capture time (data/<stream>/capture_metadata.csv). `order_id`
# is what correlates one physical unit's images ACROSS streams as it moves
# down the line (filled -> tank level reading at that moment -> capped/
# sealed) - set it once per unit in capture_gui.py's "Order / Run #" field
# and capture that unit at each station's camera as it arrives there, all
# under the same order_id. Each row's own `captured_at` is that station's
# lifecycle timestamp for the unit - the same value is also embedded in the
# saved JPEG's own EXIF DateTime/DateTimeOriginal tags AND burned visibly
# into the image itself (see camera.py's save_jpeg_with_timestamp), so the
# capture time is never only available in this one CSV.
CAPTURE_METADATA_FIELDS = [
    "filename",
    "captured_at",
    "batch_id",
    "order_id",
    "camera_device",
    "width",
    "height",
    "notes",
]


def load_config(config_path: os.PathLike | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found at {config_path}. Run scripts from the repo "
            f"root, or pass --config config.vial_fill.yaml / config.tank_level.yaml."
        )
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)
    return cfg


def display_name(cfg: dict[str, Any]) -> str:
    return cfg.get("project", {}).get("display_name", cfg.get("project", {}).get("name", "Inspection"))


def resolve_path(cfg: dict[str, Any], key: str) -> Path:
    """Resolve a paths.* entry from the config file relative to the repo root."""
    rel = cfg["paths"][key]
    return (REPO_ROOT / rel).resolve()


def ensure_detection_dirs(cfg: dict[str, Any]) -> None:
    """Create every directory this stream captures into, if it doesn't
    already exist (images/incoming + videos)."""
    for key in ("detection_images_incoming", "detection_videos_dir"):
        resolve_path(cfg, key).mkdir(parents=True, exist_ok=True)


def append_metadata_row(metadata_csv: Path, row: dict[str, Any], fieldnames: list[str]) -> None:
    """Append one row to a metadata CSV, creating it with a header if it
    doesn't exist yet. Pass CAPTURE_METADATA_FIELDS for the fieldnames."""
    metadata_csv.parent.mkdir(parents=True, exist_ok=True)
    file_exists = metadata_csv.exists()
    with open(metadata_csv, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in fieldnames})


def read_metadata(metadata_csv: Path) -> list[dict[str, str]]:
    if not metadata_csv.exists():
        return []
    with open(metadata_csv, "r", newline="") as f:
        return list(csv.DictReader(f))


def next_auto_batch_id(now: dt.datetime | None = None) -> str:
    """Auto-generated "Batch / session ID" for capture_gui.py: <year>-<month>-<seq>,
    e.g. 2026-09-0000, 2026-09-0001, ... The sequence resets to 0000 at the
    start of each new year-month and otherwise keeps counting up across GUI
    restarts (persisted in BATCH_ID_STATE_PATH, cross-stream since Batch ID
    is shared by all three cameras). Still fully editable in the GUI once
    generated - this is just the starting value."""
    now = now or dt.datetime.now()
    year_month = now.strftime("%Y-%m")

    state = {}
    if BATCH_ID_STATE_PATH.exists():
        try:
            state = json.loads(BATCH_ID_STATE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            state = {}

    seq = state.get("next_seq", 0) if state.get("year_month") == year_month else 0

    BATCH_ID_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BATCH_ID_STATE_PATH.write_text(json.dumps({"year_month": year_month, "next_seq": seq + 1}))

    return f"{year_month}-{seq:04d}"
