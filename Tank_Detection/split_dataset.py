"""Split the labeled images in Tank_Detection/train into an Ultralytics dataset.

Creates Tank_Detection/dataset with:
    images/train  images/val  labels/train  labels/val

Run once from anywhere: python split_dataset.py
Safe to re-run: it deletes and rebuilds the dataset folder each time.
"""
import random
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "train"          # folder holding your 300 images (and their .txt labels)
OUT = HERE / "dataset"        # folder this script creates
VAL_FRACTION = 0.2            # 20% of images go to validation
IMAGE_TYPES = {".jpg", ".jpeg", ".png"}


def main():
    if not SRC.exists():
        raise SystemExit(f"Source folder not found: {SRC}")

    imgs = sorted(p for p in SRC.rglob("*") if p.suffix.lower() in IMAGE_TYPES)
    if not imgs:
        raise SystemExit(f"No images found in {SRC}")

    if OUT.exists():
        shutil.rmtree(OUT)

    random.seed(0)
    random.shuffle(imgs)
    n_val = int(len(imgs) * VAL_FRACTION)

    missing = 0
    for i, img in enumerate(imgs):
        split = "val" if i < n_val else "train"
        (OUT / "images" / split).mkdir(parents=True, exist_ok=True)
        (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)
        shutil.copy2(img, OUT / "images" / split / img.name)

        # Label is expected next to the image, or in a sibling "labels" folder.
        candidates = [img.with_suffix(".txt"), img.parent.parent / "labels" / (img.stem + ".txt")]
        lbl = next((c for c in candidates if c.exists()), None)
        if lbl:
            shutil.copy2(lbl, OUT / "labels" / split / lbl.name)
        else:
            missing += 1
            print("NO LABEL for", img.name)

    print(f"\n{len(imgs) - n_val} train, {n_val} val -> {OUT}")
    print(f"{len(imgs) - missing} of {len(imgs)} images have a label file.")
    if missing > len(imgs) * 0.5:
        shutil.rmtree(OUT)
        raise SystemExit(
            "\nSTOP: most images have no .txt label file, so training would fail.\n"
            f"Put the synthetic images AND their .txt files directly in {SRC} and run this again."
        )
    if missing:
        print(f"WARNING: {missing} images have no label file.")


if __name__ == "__main__":
    main()
