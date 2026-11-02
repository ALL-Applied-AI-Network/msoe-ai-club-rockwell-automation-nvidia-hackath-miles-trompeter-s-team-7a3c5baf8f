"""Train a YOLO26 model to find large tanks and tell whether each is good or low.

Usage:
    1. Run split_dataset.py once to build the dataset folder.
    2. Run: python train_yolo.py

Install first: pip install ultralytics
"""
from pathlib import Path

from ultralytics import YOLO

# ======================= EDIT THESE SETTINGS =======================
BASE_MODEL = "yolo26n.pt"  # n = smallest/fastest, larger sizes are more accurate but slower
DATASET_YAML = str(Path(__file__).resolve().parent / "data.yaml")  # works no matter where you launch from
EPOCHS = 20  # raise if accuracy is still improving, lower if training is too slow
IMAGE_SIZE = 640
# ===================================================================


def main():
    model = YOLO(BASE_MODEL)
    model.train(data=DATASET_YAML, epochs=EPOCHS, imgsz=IMAGE_SIZE, device=0, batch=8)    
# The best weights are saved by Ultralytics under runs/detect/train*/weights/best.pt
    # Point MODEL_PATH in monitor_yolo.py at that file.


if __name__ == "__main__":
    main()
