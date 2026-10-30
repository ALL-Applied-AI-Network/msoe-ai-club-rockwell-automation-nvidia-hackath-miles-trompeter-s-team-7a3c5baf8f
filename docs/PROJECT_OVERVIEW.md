# Project Overview: Fill Line Inspection

The "why" document for this repo - what's been built, why each piece
exists, how the pieces fit together, and the goal it's building toward.
**README.md** is the day-to-day command reference; this file is the map
that ties those commands back to the point of the project.

## The goal

Get clean, reliably-timestamped images and video out of three cameras on
the fill line - one watching vials as they're filled, one watching the
supply tank's liquid level, one watching caps/seals as they're applied -
and hand that off to a separate labeling/training pipeline outside this
repo. This repo's job stops at capture: it doesn't draw boxes, classify
anything, or split data into Training/Testing/Validation. What it does
guarantee is that every image can be trusted for *when* it was taken and
*which physical unit* it belongs to, since that's the part a downstream
pipeline can't reconstruct after the fact if capture gets it wrong.

## Why this is a fork, not a new design

This project started from the pipeline built for
[tray-inspection-dataset](../tray-inspection-dataset) - originally a full
capture -> annotate -> split -> verify -> train tool, generalized to run
three streams side by side instead of one. The annotation/split/verify
half was later removed (a separate process now owns labeling and
splitting), so what's left is purely the capture half, but a few design
choices from that shared history are still why this repo looks the way it
does:

- **Multiple streams, one codebase, zero shared state.** Rather than merge
  three different cameras' concerns into one capture flow, each stream
  gets its own config file (`config.vial_fill.yaml` / `config.tank_level.yaml`
  / `config.cap_seal.yaml`) and its own `data/<stream>/` tree. This means
  `src/` never needed a "vial_fill mode" vs. "tank_level mode" branch
  anywhere - the same helpers in `common.py` just read whichever config
  they're given, so adding the third (`cap_seal`) stream was purely a
  matter of adding a new config file and a new capture panel, no code
  branching.
- **One capture window, N cameras.** `capture_gui.py`'s `CameraPanel` class
  (per-camera state, live preview, Manual/Burst/Timelapse logic) is
  instantiated once per stream by `MultiCaptureApp`, side by side, sharing
  one window, one Exit/cleanup, and one "Batch / session ID" field so a
  single production run's vial_fill, tank_level, and cap_seal captures can
  be correlated later - while each panel's camera connection, capture
  state, and Notes field stay fully independent (one camera being
  unplugged never affects the others).
- **Timestamps are load-bearing, not incidental.** Since a separate
  process does the labeling later, possibly much later, this repo can't
  assume the CSV metadata and the image files will always travel together.
  Every saved image's capture time is written three different ways - burned
  visibly into the pixels, into the JPEG's own EXIF tags, and into
  `capture_metadata.csv` - so no single lost file or renamed folder loses
  the timing information a downstream pipeline needs.
- **Two capture modes exist specifically to keep multiple cameras
  provably in sync.** Synchronized Capture (all three cameras) and
  Video Capture (all three) both exist because "cameras happened to
  save something around the same time" isn't good enough for correlating
  a fill event with a tank reading and a cap/seal check - they need the
  *same* timestamp, not merely close ones. Both work by computing one
  timestamp and handing it to every camera's save call in the same tick,
  rather than letting each camera time its own shots independently.

## How it's meant to work, end to end

1. Run `capture_gui.py` (or double-click `start_capture.sh`) - all three
   cameras live in one window.
2. Set "Order / Run #" to the unit currently at the first station, and
   capture it at each station as it physically arrives there, via
   Synchronized Capture across all three cameras. Click "Next Order" once
   it's done.
3. Use Video Capture for a plain continuous recording across all three
   cameras when that's more useful than discrete stills (e.g. reviewing an
   entire shift).
4. Run `order_status.py` any time to see which orders are captured on all
   three streams and pull up their matching files.
5. Hand `data/<stream>/images/incoming/`, `capture_metadata.csv`, and
   `data/order_status.csv` off to the separate labeling/training process.

## Where things stand / what's still ahead

The multi-camera capture GUI (Synchronized Capture and Video Capture, both
across all three cameras), timestamp handling (visible burn-in, EXIF, CSV), and cross-stream
correlation (`order_status.py`) are built and tested for all three
streams. What's ahead is on the other side of the hand-off this repo
exists to feed: the separate labeling/splitting process, then training,
then whatever inference/verdict logic that pipeline wants to run against
its own labels. This repo's job is done once a capture session produces
clean, correlated, well-timestamped images and video - everything above
exists in service of that one hand-off being trustworthy.
