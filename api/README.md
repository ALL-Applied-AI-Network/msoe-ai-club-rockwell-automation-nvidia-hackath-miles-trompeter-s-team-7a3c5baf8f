# Vial detection and cropping with YOLO26

For Cosmos Reason verification of a cropped vial against source jugs, a recipe,
and previous results, see [color verification](models/color_verification/README.md).

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

## Camera replay dashboard

Start the API from `api`: `uv sync`, then `uv run python main.py`.
In another terminal, from `client`: `bun install`, then `bun run dev`.
Open the Vite URL and click **Start cameras**. Both recordings share
play/pause controls; the vial video is the playback clock. Vite proxies `/api`
to port 8000 (also configured for `bun run preview`).

The demo uses `content/vial_fill_video_5.mp4` and `content/tank_level_video_5.mp4`
explicitly so recipe timestamps cannot accidentally attach to another recording.
Videos are served with byte-range support; analysis uses the current vial
playback timestamp and the newest trained `jar_crop/runs/train*/weights/best.pt`.

The completion heuristic requires a jar center within 43-53% of frame width
for at least one second, followed by a matching leftward departure. Matching
allows fast conveyor steps and up to one second of missing detections, while
checking vertical box alignment. A missing detection alone never triggers a crop.
The last centered crop is retained to avoid displaying a blurred moving jar.
These thresholds are calibrated to this fixed camera; they estimate completion
from conveyor departure, not liquid flow or fill level.

Analysis samples every 0.25 seconds in video order, processing at most eight
frames per request. Slow inference creates a backlog instead of dropping frames
or resetting jar history. The sidebar reports when analysis is catching up;
pausing playback lets analysis finish the pending frames. Rewinding
restarts analysis from the beginning. Viewer sessions expire after 30 minutes
without observations. Regression fixtures include model detections for the first
four departures (28.5, 75, 121.5, and 162.5 seconds) from the current vial video.

Run tracker regression tests from `api`: `uv run python -m unittest test_replay -v`.

### Tonight's Cosmos demonstration

Keep the Cosmos server running on Brev, and run this in **local WSL**:

```bash
brev port-forward cosmos-reasoner --port 8001:8000
```

Set `COSMOS_BASE_URL=http://127.0.0.1:8001/v1`,
`COSMOS_MODEL=nvidia/Cosmos-Reason2-8B`, and the running server's
`COSMOS_API_KEY` in `api/.env`. Restart the API after changing environment settings.
Keep the API and frontend terminals running, open the Vite URL, and start cameras.

Each departure queues a separate background job. Jobs match crop time against
`content/video5_vial_recipes.json`, with up to five seconds after fill end and
never crossing the next fill start. Unmatched timestamps produce an error,
not a guessed recipe. The first crop is around 28 seconds of video time.

Jobs pair that crop with the static reference
`samples/tank_level_20260922_170432_316717 (1).jpg`. Tank IDs are ordered
100, 200, 300, 400 from left to right. The moving tank video is a display feed;
the model uses the supplied static screenshot. The preceding three recipes
are included as unreviewed context, never as known-good results.

The assessment history shows queued/running/error states and the model's plain-text
answer: Looks good / Doesn't look good / Uncertain, with observations and possible
causes. Errors can be retried. Inference is serial and never holds up camera
analysis. Pausing playback still lets detection catch up and assessments finish.
The recordings stop at the end, avoiding repeated inference on automatic loops.

Each job is saved under `api/assessment_runs/` with its crop, tank screenshot,
recipe, prompt, model (on success), and answer. These local artifacts are git-ignored.
The live history is scoped to the current replay session; refreshing the browser
starts a new session. Saved files remain available after API restarts, but pending
jobs are not automatically resumed and past sessions are not reloaded into the UI.

This demo does not use the older strict-JSON `verify_color` client. It displays
model text without treating it as a verified quality label. Source-color recognition
and mixture reasoning can be wrong; photos cannot establish actual dispensing
ratios, dye concentrations, contamination, or chemical quality. Review all judgments.

Validate with `uv run python -m unittest test_assessments test_replay`.
