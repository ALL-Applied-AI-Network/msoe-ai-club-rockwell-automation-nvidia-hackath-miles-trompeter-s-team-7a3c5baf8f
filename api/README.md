# Vial detection and cropping with YOLO26

No major relabeling is needed. The Roboflow export has `Vial` (class 0)
and `liquid` (class 1). Preparation copies the images and keeps only vial
annotations in a separate dataset; the original export remains intact.
Do not merely rename both classes or use `single_cls=True`: that would teach
the detector to treat liquid annotations as vials too.

Run from `api` with [uv](https://docs.astral.sh/uv/):

```powershell
uv sync
uv run python scripts/vials.py prepare
uv run python models/jar_crop/train.py --device cpu
```

For a CUDA-enabled PyTorch installation and an NVIDIA GPU, use `--device 0`.
Training defaults to pretrained `yolo26n.pt`, 100 epochs, 640-pixel images,
batch size 8, and zero data-loader workers for Windows compatibility.
The initial training run downloads pretrained weights. CPU training can be slow.
Use `--model yolo26s.pt` to try a larger model or adjust `--batch` to available memory.
Training saves checkpoints under `models/jar_crop/runs/train/weights` and prints
the best checkpoint path; repeated runs get new output directories.
Skip preparation if `data_vial` already exists.

Visualize predictions on the first image in the held-out testing set:

```powershell
uv run python models/jar_crop/test.py
uv run python models/jar_crop/test.py --index 10
```

`test.py` selects the newest `best.pt` from this model's training runs.
Use `--weights path/to/best.pt` to select a specific checkpoint, or
`--image path/to/image.jpg` to select a specific image. It saves the image with
predicted boxes, class labels, and confidence scores under
`models/jar_crop/runs/test` (numbered on subsequent runs), along with box
coordinates and vial crops. Open the saved image to view the boxes.
If no detections exceed `--conf`, it saves an image without boxes and reports that.
Training must finish before running this visual test.

For batch cropping with an explicit checkpoint:

```powershell
uv run python scripts/vials.py crop --weights models/jar_crop/runs/train/weights/best.pt --source path/to/image.jpg
```

The source can also be an image directory. Outputs under `runs/detect/crops`
(or a numbered directory on subsequent runs) include annotated images,
normalized bounding-box labels with confidence, and individual vial crops
under `crops/vial`. `--conf 0.25` controls the detection threshold.
Ultralytics' crop saver adds a small margin around detections. These are
rectangular crops, not background-removed silhouettes. An image with no
detections produces no vial crops.

Evaluate the trained checkpoint on the held-out test split:

```powershell
uv run yolo detect val model=models/jar_crop/runs/train/weights/best.pt data=data_vial/data.yaml split=test
```

Utilities and label-conversion unit tests live in `scripts`; the model-specific
training and visual testing entry points live in `models/jar_crop`.
Default dataset/output paths are resolved from the script location.
To run the conversion unit tests: `uv run python -m unittest discover -s scripts -v`.

## Dataset audit

| Split | Images | Vial annotations | Removed liquid annotations |
|---|---:|---:|---:|
| Train | 709 | 1,383 | 135 |
| Validation | 101 | 197 | 21 |
| Test | 203 | 397 | 31 |

Three training annotations are polygons. Preparation converts them to enclosing
bounding boxes. Review these two image stems before a final training run:

- `vial_fill_20260922_172200_981522_jpg.rf.ec6c85b790d908e239fe631d1bf6ad1e`
- `vial_fill_20260922_172227_120143_jpg.rf.a8bbd3bc4ced6f84c933bc4bec428fbc`

The first contains two heavily overlapping vial polygons that may be duplicate
or inconsistent labels. They are retained for review. The audit validates label
structure, not whether every visible vial has a correct annotation.
Many filenames come from a single capture sequence; evaluation on a separate
capture session is useful to measure generalization beyond similar frames.

Preparation refuses to overwrite existing output. To regenerate after annotation
edits, use `prepare --output data_vial_v2`, then train with
`--data data_vial_v2/data.yaml`. Generated YAML uses an absolute dataset path;
regenerate it if moving the dataset to another machine.

Official references: [YOLO26](https://docs.ultralytics.com/models/yolo26/),
[training](https://docs.ultralytics.com/modes/train/),
[prediction and crops](https://docs.ultralytics.com/modes/predict/).
