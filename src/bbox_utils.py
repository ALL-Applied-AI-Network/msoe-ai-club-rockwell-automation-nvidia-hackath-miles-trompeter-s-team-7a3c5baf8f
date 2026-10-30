"""
bbox_utils.py - Pure geometry helpers for capture_gui.py's digital zoom
(fit-to-container sizing and zoom/pan crop math). Deliberately has NO
Tkinter/OpenCV/PIL dependency so it can be unit-tested headlessly, without
a display or a camera.
"""
from __future__ import annotations

ZOOM_MIN = 1.0
ZOOM_MAX = 5.0
ZOOM_DRAG_SENSITIVITY = 200.0  # px of vertical drag per 1.0x of zoom change
ZOOM_CLICK_THRESHOLD_PX = 5  # movement below this = "a click", not a drag -> reset zoom


def compute_fit_size(container_w: int, container_h: int, w: int, h: int) -> tuple[int, int]:
    """Given an image of size (w, h) and an available box (container_w,
    container_h), return the largest (new_w, new_h) that preserves aspect
    ratio and fits inside the box."""
    scale = min(container_w / w, container_h / h)
    return max(1, int(w * scale)), max(1, int(h * scale))


def compute_zoom_crop(w: int, h: int, zoom: float, center_x: float, center_y: float) -> tuple[int, int, int, int]:
    """Return (x0, y0, crop_w, crop_h): the region of a (w, h) frame/image to
    crop for a given zoom level (1.0 = whole frame, higher = tighter crop)
    and zoom center as fractions (0..1) of width/height. The crop is clamped
    so it never runs off the edge of the frame."""
    zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
    crop_w = max(1, int(w / zoom))
    crop_h = max(1, int(h / zoom))

    cx_px = min(max(center_x, 0.0), 1.0) * w
    cy_px = min(max(center_y, 0.0), 1.0) * h

    x0 = int(cx_px - crop_w / 2)
    y0 = int(cy_px - crop_h / 2)
    x0 = max(0, min(x0, w - crop_w))
    y0 = max(0, min(y0, h - crop_h))
    return x0, y0, crop_w, crop_h
