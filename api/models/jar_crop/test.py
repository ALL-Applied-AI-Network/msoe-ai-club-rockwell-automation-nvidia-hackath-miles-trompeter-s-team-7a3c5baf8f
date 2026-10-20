"""Draw predicted vial boxes on a held-out test image and save the crops."""

import argparse
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent
API_DIR = MODEL_DIR.parents[1]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, help="Default: newest best.pt in jar_crop/runs/train*")
    parser.add_argument("--image", type=Path, help="Optional image; defaults to a held-out test image")
    parser.add_argument("--test-dir", type=Path, default=API_DIR / "data_vial/test/images")
    parser.add_argument("--index", type=int, default=0, help="Zero-based index in sorted test images")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    if not 0 <= args.conf <= 1:
        parser.error("--conf must be between 0 and 1")
    weights = args.weights
    if weights is None:
        candidates = list((MODEL_DIR / "runs").glob("train*/weights/best.pt"))
        if not candidates:
            parser.error("No trained checkpoint found. Run models/jar_crop/train.py first or pass --weights.")
        weights = max(candidates, key=lambda path: path.stat().st_mtime)
    if not weights.is_file():
        parser.error(f"Checkpoint does not exist: {weights}")
    image = args.image
    if image is None:
        images = sorted(p for p in args.test_dir.glob("*") if p.suffix.lower() in IMAGE_EXTENSIONS)
        if not 0 <= args.index < len(images):
            parser.error(f"--index must select one of {len(images)} test images (starting at 0)")
        image = images[args.index]
    if not image.is_file():
        parser.error(f"Image does not exist: {image}")

    from ultralytics import YOLO

    model = YOLO(str(weights.resolve()))
    if model.task != "detect" or model.names != {0: "vial"}:
        parser.error("Expected a trained single-class vial detection model")
    results = model.predict(
        source=str(image.resolve()), conf=args.conf, imgsz=args.imgsz,
        device=args.device, save=True, save_txt=True, save_conf=True, save_crop=True,
        show_labels=True, show_conf=True, line_width=3,
        project=str(MODEL_DIR / "runs"), name="test",
    )
    result = results[0]
    print(f"Checkpoint: {weights.resolve()}")
    print(f"Image: {image.resolve()}")
    print(f"Detected {len(result.boxes)} vial(s)")
    print(f"Annotated image and crops saved in: {Path(result.save_dir).resolve()}")
    if len(result.boxes) == 0:
        print("No detections exceeded the confidence threshold; the saved image has no boxes.")


if __name__ == "__main__":
    main()
