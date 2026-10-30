# Fill Line Inspection - Three-Camera Capture Tool

Capture-only tool for three independent cameras on the same fill line: one
watching **vials as they're filled**, one watching the **supply tank's
liquid level as it drains**, and one watching **caps/seals as they're
applied**. Gets clean, well-timestamped images and video out of all three
cameras and hands off to a separate process for labeling and splitting
into Training/Testing/Validation - this repo doesn't do either of those.

See **[docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)** for the "why"
- what's been built, why it's shaped this way, and the goal it's building
toward. This file is the command reference.

## The three streams

| Stream | Camera watches | Config file |
|---|---|---|
| **vial_fill** | Vials as they're filled | `config.vial_fill.yaml` |
| **tank_level** | Supply tank's liquid level as it drains | `config.tank_level.yaml` |
| **cap_seal** | Caps/seals as they're applied | `config.cap_seal.yaml` |

Nothing about one stream's captures ever touches another's - they land
entirely under `data/vial_fill/`, `data/tank_level/`, and `data/cap_seal/`
respectively.

**Every saved image's timestamp is recorded three ways**, so it's never
only available in one place: burned visibly into the image itself (so two
images from different cameras can be matched up by eye), the JPEG's own
EXIF `DateTime`/`DateTimeOriginal` tags, and `captured_at` in that stream's
`capture_metadata.csv`.

## Repository layout

```
config.vial_fill.yaml     # camera + paths for the vial_fill stream
config.tank_level.yaml    # same, for the tank_level stream
config.cap_seal.yaml      # same, for the cap_seal stream
src/
  common.py                # shared config/path/CSV helpers (stream-agnostic)
  bbox_utils.py              # pure geometry: digital zoom fit/crop math
  camera.py                   # USB camera open/probe + timestamped JPEG saving
  capture_gui.py                # multi-camera capture GUI
  order_status.py                 # correlate captures across streams by order_id
data/
  vial_fill/                 # this stream's images, video, capture_metadata.csv
  tank_level/                 # same, for tank_level
  cap_seal/                   # same, for cap_seal
docs/
  PROJECT_OVERVIEW.md           # why this exists, how it fits together, the goal
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo apt install python3-tk ffmpeg   # GUI + video encoding (not pip packages)
```

Three USB cameras plugged in. Each stream's config file has its own
`camera.device_index` - check which is which with a quick probe (or just
try 0, 1, and 2, which is the default) and edit the configs to match. See
each config's comment for why a stable `/dev/v4l/by-id/...` path is safer
than a raw index if your cameras share a USB hub.

## Capture

```bash
python3 src/capture_gui.py
```

Or double-click `start_capture.sh` in this folder.

Opens ONE window with all three camera feeds side by side - Vial Fill,
Tank Level, then Cap/Seal by default. Each panel's live preview, zoom, and
Notes field are fully independent - one camera being unplugged never
blocks the others. A shared "Batch / session ID" field at the top tags
every stream's captures so a run can be correlated later (auto-generated
as `<year>-<month>-<seq>`, e.g. `2026-09-0003`, but editable).

**Periodic still photos - all three cameras together.** Instead of their
own separate Manual/Burst/Timelapse controls, all three panels have one
**"Periodic Still Photos (JPEG)"** bar below the top row. Set a photo
interval and click **Start Photos**. Until you click **Stop Photos**, every
interval all three cameras save a frame under one shared timestamp. The
matching JPEGs therefore have the same `captured_at` and EXIF
`DateTimeOriginal`, and each metadata row is tagged `[periodic-still]`.
This mode creates JPEG photos, not video.

**Continuous video - all three cameras at once.** Use the separate
**"Continuous Video (MP4)"** bar to record real-time H.264 video from all
three cameras simultaneously, from one shared **Start Recording** to one
shared **Stop Recording**. This writes every live camera frame with actual
wall-clock timing; it is not a JPEG burst or a sped-up review video. Each
camera's timestamped `.mp4`, including a visible timestamp on every frame,
lands under `recordings/<stream>/`. Video and periodic still photos can run
together when both outputs are needed. All three MP4s share one recording ID;
if any camera disconnects or any encoder fails, all three recordings stop
together so the session cannot silently produce mismatched clip lengths.

**Vial log.** Before each Start Recording, fill in the *Vial log* bar: Vial ID,
Intended R/Y/B, Actual R/Y/B (blank = same as intended), Fault type and Notes. On Stop,
these values plus start/stop times and each camera's exposure/white-balance settings are
appended to `recordings/vial_log.csv` and written as a `.json` next to each `.mp4`.
Recording and still photos use whichever cameras are connected (one camera is fine).
The vial_fill camera locks its auto-settled exposure/white balance after warmup
(`camera.lock_exposure_wb`) so colour stays comparable across a session.

## Files the program writes

| Output | Location | Created by | Contents |
|---|---|---|---|
| Continuous video | `recordings/<stream>/video_<stream>_<batch>_<time>.mp4` | Continuous Video | H.264 MP4 with a visible timestamp; one file per camera per recording |
| Still photo | `data/<stream>/images/incoming/<stream>_<time>.jpg` | Periodic Still Photos (and legacy Manual/Burst/Timelapse modes) | Full camera frame with a visible timestamp and EXIF `DateTime`/`DateTimeOriginal` |
| Still-photo metadata | `data/<stream>/capture_metadata.csv` | Every saved JPEG | Filename, capture time, batch ID, order ID, camera, dimensions, and notes |
| Batch counter | `data/batch_id_state.json` | Startup when `--batch-id` is omitted | Next auto-generated monthly batch sequence number |
| Order summary | `data/order_status.csv` | `python3 src/order_status.py` | Cross-camera captured/missing status and matching filenames/timestamps per order |

`verdicts.csv`, `labeled_images.zip`, and training/validation split files
come from the separate labeling workflow; the capture GUI does not create
them. Video has its timestamp in the filename and burned into its frames,
but it does not add rows to `capture_metadata.csv` (that file is for JPEG
stills only).

**Correlating one unit across all three streams**: the shared "Order / Run
#" field next to Batch ID is what ties one physical unit's images together
across stations as it moves down the line - fill, then tank reading, then
cap/seal + palletize. Keep it the same while that unit is captured at each
station's camera in turn (whenever it physically arrives there), then
click "Next Order" once it's done and the next unit shows up at the first
station. Every saved image logs the current Order # into `order_id`
alongside its own `captured_at` timestamp in that stream's
`capture_metadata.csv` - see **Correlating captures across streams** below.

Right-click + hold + drag on any preview to zoom in for a closer look on
any panel (preview only - the saved image is always the full frame).

Override which physical camera maps to which stream, or set a starting
batch ID, without editing the config files:

```bash
python3 src/capture_gui.py --vial-fill-device 0 --tank-level-device 1 --cap-seal-device 2 --batch-id line1-run3
```

## Correlating captures across streams

Once you've been capturing with the "Order / Run #" field, join the three
streams' `capture_metadata.csv` files back together by `order_id`:

```bash
python3 src/order_status.py
python3 src/order_status.py --order 42
```

For each `order_id`, reports whether each stream `captured` an image for
it (or is `missing` one), and whether it's `complete` (captured on all
three). Written to `data/order_status.csv` with each stream's matching
filename(s) and `captured_at` timestamp(s) alongside the status, so you
can pull the three correlated images up together - e.g. fill time
(`vial_fill`'s `captured_at`), the tank reading at that moment
(`tank_level`), and when it was capped/sealed (`cap_seal`'s
`captured_at`), or compute per-order cycle time as
`cap_seal.captured_at - vial_fill.captured_at`.

## Handing off for labeling and training

This repo stops at capture. Labeling (drawing boxes/classifying) and
splitting into Training/Testing/Validation are handled by a separate
process outside this repo, which reads straight from each stream's
`data/<stream>/images/incoming/` plus `capture_metadata.csv` (and
`data/order_status.csv` if it wants the cross-stream correlation).

## Troubleshooting

- **"No camera detected"** in a panel - check `camera.device_index` in
  that stream's config file, or pass `--vial-fill-device`/
  `--tank-level-device`/`--cap-seal-device` to override without editing it.
  Each panel reconnects independently.
- **ffmpeg not found** (Timelapse, Continuous Video) - `sudo apt install ffmpeg`.
- **No module named tkinter** - `sudo apt install python3-tk`, then
  recreate your venv with `python3 -m venv .venv --system-site-packages`
  (or just install packages into the system Python).
