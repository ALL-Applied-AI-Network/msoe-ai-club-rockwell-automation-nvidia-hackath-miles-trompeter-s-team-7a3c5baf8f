"""Fine-tune YOLO26 on the prepared vial-only jar-cropping dataset."""

import argparse
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent
API_DIR = MODEL_DIR.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=API_DIR / "data_vial/data.yaml")
    parser.add_argument("--model", choices=[f"yolo26{s}.pt" for s in "nsmlx"], default="yolo26n.pt")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--workers", type=int, default=0)
    args = parser.parse_args()
    if not args.data.is_file():
        parser.error("Dataset missing. From api, run: uv run python scripts/vials.py prepare")

    import yaml
    from ultralytics import YOLO

    config = yaml.safe_load(args.data.read_text())
    names = config.get("names")
    if names not in (["vial"], {0: "vial"}):
        parser.error("--data must describe the prepared single-class vial dataset")
    model = YOLO(args.model)
    model.train(
        data=str(args.data.resolve()), epochs=args.epochs, imgsz=args.imgsz,
        batch=args.batch, device=args.device, workers=args.workers,
        project=str(MODEL_DIR / "runs"), name="train",
    )
    print(f"Best weights: {model.trainer.best}")
    print("Visual test: uv run python models/jar_crop/test.py")


if __name__ == "__main__":
    main()
