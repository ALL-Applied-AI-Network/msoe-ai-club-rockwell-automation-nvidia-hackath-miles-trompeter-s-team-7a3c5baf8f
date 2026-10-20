"""Prepare a vial-only dataset and crop detections from trained checkpoints."""

import argparse
import json
import math
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def vial_box(row, vial_id):
    """Validate YOLO detection/segmentation rows and retain only vial boxes."""
    fields = row.split()
    class_id = int(fields[0])
    if class_id != vial_id:
        return None
    coords = [float(value) for value in fields[1:]]
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in coords):
        raise ValueError("Coordinates must be finite and normalized to [0, 1]")
    if len(coords) == 4:
        x, y, width, height = coords
    elif len(coords) >= 6 and len(coords) % 2 == 0:
        xs, ys = coords[::2], coords[1::2]
        x, y = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        width, height = max(xs) - min(xs), max(ys) - min(ys)
    else:
        raise ValueError("Expected a box or a polygon with at least three points")
    if width <= 0 or height <= 0:
        raise ValueError("Box dimensions must be positive")
    return f"0 {x:.10f} {y:.10f} {width:.10f} {height:.10f}"


def prepare(source, destination):
    import yaml

    source, destination = source.resolve(), destination.resolve()
    if destination.exists() or destination.is_relative_to(source):
        raise ValueError("Choose a new output directory outside the source dataset")
    config = yaml.safe_load((source / "data.yaml").read_text())
    names = config["names"]
    names = dict(enumerate(names)) if isinstance(names, list) else names
    vial_ids = [int(k) for k, v in names.items() if v.lower() == "vial"]
    if len(vial_ids) != 1:
        raise ValueError("Expected exactly one class named vial")
    vial_id = vial_ids[0]
    known_ids = {int(k) for k in names}
    plan, report = [], {}
    for split in ("train", "valid", "test"):
        images = sorted((source / split / "images").glob("*"))
        images = [p for p in images if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}]
        if not images:
            raise ValueError(f"No images in {split}")
        if len({p.stem for p in images}) != len(images):
            raise ValueError(f"Duplicate image stems in {split}")
        stats = dict(images=len(images), vials=0, removed=0, polygons_converted=0)
        for image in images:
            label = source / split / "labels" / f"{image.stem}.txt"
            rows = []
            for number, row in enumerate(label.read_text().splitlines(), 1):
                if not row.strip():
                    continue
                try:
                    if int(row.split()[0]) not in known_ids:
                        raise ValueError("Unknown class ID")
                    box = vial_box(row, vial_id)
                except ValueError as exc:
                    raise ValueError(f"{label}:{number}: {exc}") from exc
                if box is None:
                    stats["removed"] += 1
                else:
                    rows.append(box)
                    stats["vials"] += 1
                    stats["polygons_converted"] += len(row.split()) != 5
            plan.append((split, image, rows))
        report[split] = stats
    # Validate the complete export before creating the derived dataset.
    for split, image, rows in plan:
        image_dir = destination / split / "images"
        label_dir = destination / split / "labels"
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image, image_dir / image.name)
        (label_dir / f"{image.stem}.txt").write_text("\n".join(rows) + ("\n" if rows else ""))
    (destination / "data.yaml").write_text(yaml.safe_dump({
        "path": destination.as_posix(), "train": "train/images",
        "val": "valid/images", "test": "test/images", "nc": 1, "names": {0: "vial"},
    }, sort_keys=False))
    (destination / "preparation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--source", type=Path, default=ROOT / "data")
    prep.add_argument("--output", type=Path, default=ROOT / "data_vial")
    crop = commands.add_parser("crop")
    crop.add_argument("--weights", type=Path, required=True)
    crop.add_argument("--source", required=True, help="Image file or directory")
    crop.add_argument("--conf", type=float, default=0.25)
    crop.add_argument("--device", default="cpu")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.source, args.output)
        return
    from ultralytics import YOLO

    if not args.weights.is_file():
        parser.error("--weights must point to an existing trained checkpoint")
    model = YOLO(str(args.weights))
    if model.task != "detect" or len(model.names) != 1 or model.names[0].lower() != "vial":
        parser.error("Cropping requires a vial-only detection checkpoint")
    for result in model.predict(source=args.source, conf=args.conf, device=args.device,
                                save=True, save_crop=True, save_txt=True, save_conf=True,
                                project=str(ROOT / "runs/detect"), name="crops", stream=True):
        print(f"{result.path}: {len(result.boxes)} vial(s); output: {result.save_dir}")


if __name__ == "__main__":
    main()
