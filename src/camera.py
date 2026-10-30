"""
camera.py - shared USB camera helpers used by both the CLI (capture.py) and
the GUI (capture_gui.py), so opening/probing the camera behaves identically
either way.
"""
from __future__ import annotations

import datetime as dt
import os
import re

import cv2
from PIL import Image

_VIDEO_NODE = re.compile(r"^/dev/video(\d+)$")

# EXIF tag ids (from the standard Exif spec) for embedding the capture
# timestamp directly into the saved JPEG - see save_jpeg_with_timestamp().
_EXIF_TAG_DATETIME = 0x0132           # "DateTime" (file's timestamp)
_EXIF_TAG_DATETIME_ORIGINAL = 0x9003  # "DateTimeOriginal" (when the photo was taken)


def save_jpeg_with_timestamp(path, frame_bgr, quality: int = 95, when: "dt.datetime | None" = None) -> None:
    """Write frame_bgr (BGR, as read from an open_camera() capture) to
    `path` as a JPEG with the computer's clock time embedded in the file's
    EXIF DateTime/DateTimeOriginal tags - so the capture time survives even
    if the image is later separated from capture_metadata.csv (copied
    elsewhere, re-uploaded, etc). Doesn't touch the pixels, so it's safe for
    training data."""
    when = when or dt.datetime.now()
    exif_ts = when.strftime("%Y:%m:%d %H:%M:%S")  # EXIF's required datetime format
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    exif = Image.Exif()
    exif[_EXIF_TAG_DATETIME] = exif_ts
    exif[_EXIF_TAG_DATETIME_ORIGINAL] = exif_ts
    img.save(str(path), "JPEG", quality=quality, exif=exif)


def _resolve_to_index(device: int | str) -> int:
    """This build's cv2 V4L2 backend can only open a camera by its numeric
    /dev/videoN index, not by path - but a raw index gets reassigned by the
    kernel whenever a camera drops out and reconnects (common with several
    USB UVC cameras sharing one hub's bandwidth). So `device` in the config
    is normally a STABLE path under /dev/v4l/by-id/ (`ls -la
    /dev/v4l/by-id/` to find yours - tied to the physical camera, not the
    port or enumeration order), and this resolves it to whatever index it
    currently points to right before every open, so a mid-session
    renumbering heals itself on the next connect/reconnect attempt.

    Deliberately strict: if `device` doesn't exist (e.g. the by-id symlink
    is gone because the camera re-enumerated under a different USB identity
    - has happened on this rig), this raises rather than silently
    pattern-matching digits out of the unresolved path string itself, which
    previously produced a wrong-but-plausible-looking index."""
    if isinstance(device, int):
        return device
    if not os.path.exists(device):
        raise RuntimeError(
            f"{device!r} does not exist - the camera may have "
            f"re-enumerated under a different /dev/v4l/by-id/ name. Run "
            f"`ls -la /dev/v4l/by-id/` to find its current one."
        )
    real = os.path.realpath(device)
    m = _VIDEO_NODE.match(real)
    if m is None:
        raise RuntimeError(
            f"{device!r} resolved to {real!r}, which isn't a /dev/videoN "
            f"node. Check `ls -la /dev/v4l/by-id/`."
        )
    return int(m.group(1))


def list_cameras(max_index: int = 6) -> list[tuple[int, int, int]]:
    """Probe camera indices 0..max_index-1. Prints a human-readable report
    and returns [(index, width, height), ...] for every index that opened
    and returned a frame."""
    print(f"Probing camera indices 0..{max_index - 1} ...")
    working = []
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok:
                h, w = frame.shape[:2]
                print(f"  [{idx}] OK - reports frame size {w}x{h}")
                working.append((idx, w, h))
            else:
                print(f"  [{idx}] opens but returned no frame")
            cap.release()
    if not working:
        print(
            "No working camera found. Check `ls /dev/video*`, that the USB "
            "camera is plugged in, and that no other process has it open."
        )
    return working


def open_camera(device: int | str, cfg: dict) -> cv2.VideoCapture:
    """Open `device` with the resolution/format from config.yaml's `camera`
    section. `device` may be a numeric /dev/videoN index (unstable across
    reconnects/reboots - the kernel can renumber nodes) or a device path,
    e.g. one of the stable symlinks under /dev/v4l/by-id/ (`ls -la
    /dev/v4l/by-id/` to find them) which stay tied to the physical USB
    camera regardless of enumeration order - resolved to its current index
    every time this is called. Raises RuntimeError with a helpful message
    if it can't open or actually deliver a frame."""
    cam_cfg = cfg["camera"]
    index = _resolve_to_index(device)
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not cap.isOpened():
        # Fall back to default backend (helps on some non-V4L2 setups)
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open camera {device!r} (resolved to /dev/video"
            f"{index}). Check that the USB camera is plugged in and not "
            f"in use by another application."
        )

    fourcc = cv2.VideoWriter_fourcc(*cam_cfg.get("fourcc", "MJPG"))
    cap.set(cv2.CAP_PROP_FOURCC, fourcc)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam_cfg.get("width", 1920))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_cfg.get("height", 1080))

    # Let auto-exposure/white-balance settle before we start showing frames.
    # Also confirms the open is real - some UVC devices report isOpened()
    # True over a starved USB hub link but never actually deliver a frame.
    got_frame = False
    for _ in range(cam_cfg.get("warmup_frames", 15)):
        ok, _ = cap.read()
        got_frame = got_frame or ok
    if not got_frame:
        cap.release()
        raise RuntimeError(
            f"Camera {device!r} (/dev/video{index}) opened but never "
            f"returned a frame. This usually means the USB hub/controller "
            f"can't supply enough bandwidth for every camera at once "
            f"(common with 3+ 1080p MJPG UVC cameras on one hub) - try a "
            f"powered hub, spreading the cameras across separate USB "
            f"controllers, or lowering camera.width/height in the config."
        )

    if cam_cfg.get("lock_exposure_wb", False):
        lock_exposure_wb(cap)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera opened at {device!r} (/dev/video{index}): {actual_w}x{actual_h} {camera_settings(cap)}")
    return cap


def lock_exposure_wb(cap: cv2.VideoCapture) -> None:
    """Freeze the exposure/white balance the camera auto-settled on during
    warmup, so colour stays comparable across a whole session (auto WB
    otherwise shifts with each vial's colour). V4L2: AUTO_EXPOSURE 1 = manual."""
    exposure = cap.get(cv2.CAP_PROP_EXPOSURE)
    wb = cap.get(cv2.CAP_PROP_WB_TEMPERATURE)
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
    if exposure > 0:
        cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
    cap.set(cv2.CAP_PROP_AUTO_WB, 0)
    if wb > 0:
        cap.set(cv2.CAP_PROP_WB_TEMPERATURE, wb)


def camera_settings(cap: cv2.VideoCapture) -> dict:
    """Current exposure/white-balance/image controls, logged with each recording."""
    props = {
        "auto_exposure": cv2.CAP_PROP_AUTO_EXPOSURE, "exposure": cv2.CAP_PROP_EXPOSURE,
        "auto_wb": cv2.CAP_PROP_AUTO_WB, "wb_temperature": cv2.CAP_PROP_WB_TEMPERATURE,
        "gain": cv2.CAP_PROP_GAIN, "brightness": cv2.CAP_PROP_BRIGHTNESS,
        "contrast": cv2.CAP_PROP_CONTRAST, "saturation": cv2.CAP_PROP_SATURATION,
        "focus": cv2.CAP_PROP_FOCUS, "autofocus": cv2.CAP_PROP_AUTOFOCUS,
    }
    return {name: cap.get(prop) for name, prop in props.items()}
