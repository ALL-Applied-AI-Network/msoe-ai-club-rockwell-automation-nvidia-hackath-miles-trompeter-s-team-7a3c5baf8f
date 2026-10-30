#!/usr/bin/env python3
"""
capture_gui.py - Multi-camera capture GUI: one window, one independent
camera panel per stream side by side (Vial Fill, Tank Level, and Cap/Seal
by default). Built on Tkinter (no extra system dependencies beyond
Pillow), directly adapted from the single-camera capture GUI in the
tray-inspection-dataset project this was forked from, each writing into
its own stream's data/<stream>/ folder (config.vial_fill.yaml /
config.tank_level.yaml / config.cap_seal.yaml).

This repo is CAPTURE-ONLY - labeling and splitting into Training/Testing/
Validation are handled by a separate process outside this repo. What this
tool guarantees on its end: every saved image's capture timestamp is
recorded in three places - burned visibly into the image itself (so two
images from different cameras can be matched up by eye), the JPEG's own
EXIF DateTime/DateTimeOriginal tags, and capture_metadata.csv's
captured_at - so nothing downstream depends on a single point of failure
to know when an image was taken.

Vial Fill + Tank Level + Cap/Seal panels (all three)
------------------------------------------------------
All three are driven together by the "Periodic Still Photos" control below
the top bar, instead of their own Manual/Burst/Timelapse controls (see
CameraPanel's `sync_controlled` flag): set a photo interval and click Start:
every `interval` seconds, from Start until Stop, all three cameras save a
frame under ONE shared timestamp per tick, so their captured_at (and each
JPEG's own EXIF DateTime) match exactly rather than merely being close in
time - each row is tagged "[periodic-still]" in notes. Reconnecting a
dropped camera is still handled per-panel with its own "Reconnect Camera"
button. This mode writes JPEG photos; it is not video recording.

Continuous Video (MP4) - all 3 cameras
-----------------------------------------
A separate "Continuous Video (MP4)" control (also below the top bar) records
real-time, continuous H.264 video from ALL THREE cameras at once, from one
shared Start to one shared Stop - a plain synchronized recording, not a
burst of still photos or a sped-up Timelapse review video. Each camera's
own timestamped .mp4 lands under recordings/<stream>/, with the same visible timestamp
burn-in as saved stills. Can run alongside Periodic Still Photos - they
don't conflict.

Shared across all panels
------------------------
- Live preview fills most of each panel; right-click and hold, then drag
  up/down, to digitally zoom in/out for a closer look (preview only - the
  saved image is always the full frame). Each panel has its own Notes
  field. If a camera isn't detected at startup, that panel shows a
  "Reconnect Camera" button independently of the others - one camera being
  unplugged never blocks the rest.
- One "Batch / session ID" field at the top (every panel's capture_metadata
  rows are tagged with it, so a run's vial_fill, tank_level, and cap_seal
  images can be correlated later), plus "Order / Run #" to tie one
  physical unit's images together across stations.
- Minimize / Enlarge / Exit in the bottom-right corner apply to the whole
  window (all cameras are released cleanly on Exit).

Usage
-----
    python3 src/capture_gui.py
    python3 src/capture_gui.py --vial-fill-device 0 --tank-level-device 1 --cap-seal-device 2
    python3 src/capture_gui.py --batch-id line1-run3
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import shutil
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import cv2

try:
    from PIL import Image, ImageTk
except ImportError:
    print(
        "ERROR: Pillow is required for the GUI (pip install -r requirements.txt)."
    )
    raise SystemExit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bbox_utils import (  # noqa: E402
    ZOOM_CLICK_THRESHOLD_PX,
    ZOOM_DRAG_SENSITIVITY,
    ZOOM_MAX,
    ZOOM_MIN,
    compute_fit_size,
    compute_zoom_crop,
)
from camera import camera_settings, open_camera, save_jpeg_with_timestamp  # noqa: E402
from common import (  # noqa: E402
    CAPTURE_METADATA_FIELDS,
    REPO_ROOT,
    append_metadata_row,
    display_name,
    ensure_detection_dirs,
    load_config,
    next_auto_batch_id,
    resolve_path,
)

DEFAULT_GEOMETRY = "2700x850"
PREVIEW_REFRESH_MS = 30
SHARED_CLOCK_TICK_MS = 10  # see MultiCaptureApp.shared_clock / _tick_shared_clock

# Burst capture defaults/limits. MAX_COUNT is a sanity cap against a
# fat-fingered typo locking up the session for a long time.
BURST_DEFAULT_COUNT = 10
BURST_MIN_COUNT = 1
BURST_MAX_COUNT = 200
BURST_DEFAULT_INTERVAL_S = 1.5
BURST_MIN_INTERVAL_S = 0.2
BURST_MAX_INTERVAL_S = 30.0

# Periodic still-photo defaults/limits (all 3 cameras - see
# MultiCaptureApp). Open-ended like Timelapse (Start/Stop, no fixed count),
# but fires every panel each tick under one shared timestamp instead of
# one panel on its own.
SYNC_DEFAULT_INTERVAL_S = 2.0
SYNC_MIN_INTERVAL_S = 0.2
SYNC_MAX_INTERVAL_S = 60.0

# Timelapse defaults/limits. Duration of 0 means "run until Stop is clicked".
TIMELAPSE_DEFAULT_INTERVAL_S = 5.0
TIMELAPSE_MIN_INTERVAL_S = 1.0
TIMELAPSE_MAX_INTERVAL_S = 300.0
TIMELAPSE_DEFAULT_DURATION_MIN = 0.0
TIMELAPSE_MAX_DURATION_MIN = 480.0
TIMELAPSE_VIDEO_FPS = 15.0
# H.264/libx264 via a real ffmpeg subprocess -- not cv2.VideoWriter, whose
# 'mp4v' fourcc only produces an old MPEG-4 Part 2 stream most default OS
# video apps can no longer decode. Needs `sudo apt install ffmpeg`.
TIMELAPSE_FFMPEG_PRESET = "veryfast"
TIMELAPSE_FFMPEG_CRF = "23"

# Continuous Video Capture (all 3 cameras, one shared Start/Stop - see
# MultiCaptureApp). Unlike periodic stills or Timelapse, this writes every
# live camera frame from Start until Stop. FFmpeg timestamps frames from the
# wall clock and keeps variable frame timing, so a busy GUI or a slower camera
# cannot make the saved clip play too fast merely because fewer than 30 frames
# arrived in a second. This is only the rawvideo input's nominal fallback rate;
# arrival timestamps determine actual playback timing.
VIDEO_CAPTURE_FPS = 30.0
# Per-vial ground truth written with every recording (recordings/vial_log.csv
# plus a .json sidecar next to each .mp4) - the labels for later analysis/RCA.
VIAL_LOG_CSV = REPO_ROOT / "recordings" / "vial_log.csv"
VIAL_LOG_FIELDS = [
    "recording_id", "batch_id", "vial_id", "started_at", "stopped_at", "duration_s",
    "intended_ryb", "actual_ryb", "fault_type", "notes", "files", "frames",
]
FAULT_TYPES = ["none", "wrong_recipe", "dose_error", "missed_dose", "carryover", "short_fill",
               "occlusion", "position", "lighting", "bubbles", "baseline_empty", "baseline_clear", "other"]
VIDEO_CAPTURE_FFMPEG_PRESET = "veryfast"
VIDEO_CAPTURE_FFMPEG_CRF = "12"  # near-lossless: vial colour is the measurement


class CameraPanel:
    """One camera's live preview + Manual/Burst/Timelapse controls, built
    inside a parent ttk.Frame the caller provides. Mirrors the tray project's
    single-camera capture GUI almost exactly, just scoped as one instance of
    several rather than the whole window."""

    def __init__(self, parent: ttk.Frame, root: tk.Tk, stream_key: str, cfg: dict, device: int | str, batch_id_var: tk.StringVar, order_id_var: tk.StringVar, shared_clock: list[dt.datetime], sync_controlled: bool = False, video_failure_callback=None):
        self.root = root
        self.stream_key = stream_key
        self.cfg = cfg
        self.label = display_name(cfg)
        self.device = device
        self.batch_id_var = batch_id_var  # shared across panels
        self.order_id_var = order_id_var  # shared across panels - see "Order / Run #" in MultiCaptureApp
        # One-element list, shared by reference across all panels, kept
        # current by MultiCaptureApp's own ticker independent of any
        # panel's camera frame rate - see _write_video_capture_frame().
        # Each panel's own preview loop runs at a slightly different
        # effective rate (different cameras, Tkinter after() jitter), so
        # video frames timestamped from dt.datetime.now() called inside
        # each panel's own tick drift apart from each other (measured:
        # ~30ms at start, growing past 40ms within a few seconds) -
        # reading from this shared clock instead keeps all three streams'
        # burned-in timestamps consistent with each other.
        self.shared_clock = shared_clock
        # Continuous video is one atomic three-camera session. If this
        # camera or its encoder fails, notify MultiCaptureApp so it can stop
        # every stream together instead of silently leaving mismatched clips.
        self.video_failure_callback = video_failure_callback
        # True for the panels driven by MultiCaptureApp's "Synchronized
        # Capture" control (all 3 cameras) instead of their own
        # Manual/Burst/Timelapse UI - see sync_capture_once() below.
        self.sync_controlled = sync_controlled
        self.notes_var = tk.StringVar(value="")

        self.images_dir = resolve_path(cfg, "detection_images_incoming")
        self.metadata_csv = resolve_path(cfg, "capture_metadata_csv")
        self.videos_dir = resolve_path(cfg, "detection_videos_dir")
        ensure_detection_dirs(cfg)

        self.cap: cv2.VideoCapture | None = None
        self.state = "connecting"  # connecting -> live -> review, or "disconnected"
        self.frozen_frame = None
        self.session_count = 0

        # Burst capture
        self.burst_active = False
        self.burst_total = 0
        self.burst_saved = 0
        self.burst_after_id: str | None = None
        self._burst_interval_ms = int(BURST_DEFAULT_INTERVAL_S * 1000)
        self.burst_count_var = tk.StringVar(value=str(BURST_DEFAULT_COUNT))
        self.burst_interval_var = tk.StringVar(value=str(BURST_DEFAULT_INTERVAL_S))
        self.burst_status_var = tk.StringVar(value="")

        # Timelapse
        self.timelapse_active = False
        self.timelapse_proc: subprocess.Popen | None = None
        self.timelapse_video_path: Path | None = None
        self.timelapse_start_monotonic = 0.0
        self.timelapse_duration_s = 0.0
        self.timelapse_stills_saved = 0
        self.timelapse_video_frames = 0
        self.timelapse_still_after_id: str | None = None
        self._timelapse_interval_s = TIMELAPSE_DEFAULT_INTERVAL_S
        self._last_live_frame = None
        self.timelapse_interval_var = tk.StringVar(value=str(TIMELAPSE_DEFAULT_INTERVAL_S))
        self.timelapse_duration_var = tk.StringVar(value=str(TIMELAPSE_DEFAULT_DURATION_MIN))
        self.timelapse_status_var = tk.StringVar(value="")

        # Continuous Video Capture (all 3 cameras, driven by
        # MultiCaptureApp's shared Start/Stop - see start_video_capture()).
        self.video_capture_active = False
        self.video_capture_proc: subprocess.Popen | None = None
        self.video_capture_path: Path | None = None
        self.video_capture_frames = 0

        # Digital zoom (preview only)
        self.zoom_level = ZOOM_MIN
        self.zoom_center = (0.5, 0.5)
        self._zoom_drag_start_xy: tuple[int, int] | None = None
        self._zoom_drag_start_level: float | None = None
        self._zoom_drag_moved = 0
        self._last_render: dict | None = None

        self.status_var = tk.StringVar(value="Starting camera...")

        self._build_ui(parent)
        self._try_connect_camera(initial=True)
        self.root.after(PREVIEW_REFRESH_MS, self._tick)

    # ------------------------------------------------------------------ UI

    def _build_ui(self, parent: ttk.Frame) -> None:
        outer = ttk.LabelFrame(parent, text=self.label, padding=(8, 6))
        outer.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.outer = outer

        notes_row = ttk.Frame(outer)
        notes_row.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))
        ttk.Label(notes_row, text="Notes:").pack(side=tk.LEFT)
        ttk.Entry(notes_row, textvariable=self.notes_var).pack(side=tk.LEFT, padx=(4, 0), fill=tk.X, expand=True)

        preview_frame = ttk.Frame(outer)
        preview_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 6))
        self.video_label = ttk.Label(preview_frame, anchor="center", background="black")
        self.video_label.pack(fill=tk.BOTH, expand=True)

        self.video_label.bind("<ButtonPress-3>", self._on_zoom_press)
        self.video_label.bind("<B3-Motion>", self._on_zoom_drag)
        self.video_label.bind("<ButtonRelease-3>", self._on_zoom_release)

        self.zoom_indicator = tk.Label(
            preview_frame, text="", bg="black", fg="#39d353", font=("TkDefaultFont", 9, "bold")
        )
        self.zoom_indicator.place(relx=0.0, rely=0.0, x=6, y=4, anchor="nw")
        self._update_zoom_indicator()

        ttk.Label(outer, textvariable=self.status_var, padding=(2, 2)).pack(side=tk.TOP, fill=tk.X)

        self.action_area = ttk.Frame(outer)
        self.action_area.pack(side=tk.TOP, fill=tk.X, pady=(4, 0))
        self._render_live_controls()

    def _clear_action_area(self) -> None:
        for w in self.action_area.winfo_children():
            w.destroy()

    def _render_connecting_controls(self, message: str) -> None:
        self._clear_action_area()
        ttk.Label(self.action_area, text=message, foreground="#c0392b").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(self.action_area, text="Reconnect Camera", command=self._on_reconnect_clicked).pack(side=tk.LEFT)

    def _render_live_controls(self) -> None:
        self._clear_action_area()

        if self.sync_controlled:
            # Manual/Burst/Timelapse are replaced by the app-level
            # "Periodic Still Photos" control for this panel - see
            # MultiCaptureApp. Camera reconnect is still handled per-panel
            # above (_render_connecting_controls), since that's a
            # per-camera hardware concern independent of the sync burst.
            ttk.Label(
                self.action_area,
                text="Controlled by Periodic Still Photos above (all 3 cameras).",
                foreground="#6b6252",
            ).pack(side=tk.LEFT)
            return

        # Capture gets its own full-width row - it used to share a row with
        # Burst, but once panels were forced to equal width (see
        # MultiCaptureApp's "uniform" column group) that made Burst's
        # trigger button get squeezed down to where it was easy to miss
        # entirely, or mistake for the "Burst:" label right before it.
        row1 = ttk.Frame(self.action_area)
        row1.pack(side=tk.TOP, fill=tk.X)
        capture_btn = ttk.Button(row1, text="●  Capture", command=self.on_capture)
        capture_btn.pack(side=tk.LEFT, ipadx=10, ipady=6)
        self._style_big_button(capture_btn)

        # Burst and Timelapse each get their own bordered, titled group
        # (like the app-level Periodic Still Photos / Continuous Video bars)
        # instead of an unlabeled inline row, so the "start" button reads
        # as a distinct control belonging to that group, not loose text.
        burst_frame = ttk.LabelFrame(self.action_area, text="Burst Capture", padding=(8, 6))
        burst_frame.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))
        ttk.Label(burst_frame, text="Count:").grid(row=0, column=0, padx=(0, 4))
        ttk.Spinbox(
            burst_frame, from_=BURST_MIN_COUNT, to=BURST_MAX_COUNT, width=4,
            textvariable=self.burst_count_var, justify="center",
        ).grid(row=0, column=1)
        ttk.Label(burst_frame, text="every").grid(row=0, column=2, padx=(8, 4))
        ttk.Spinbox(
            burst_frame, from_=BURST_MIN_INTERVAL_S, to=BURST_MAX_INTERVAL_S, increment=0.5, width=4,
            textvariable=self.burst_interval_var, justify="center",
        ).grid(row=0, column=3)
        ttk.Label(burst_frame, text="s").grid(row=0, column=4, padx=(2, 10))
        ttk.Button(burst_frame, text="●  Start Burst", command=self.on_burst_start).grid(row=0, column=5)

        timelapse_frame = ttk.LabelFrame(self.action_area, text="Timelapse", padding=(8, 6))
        timelapse_frame.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))
        ttk.Label(timelapse_frame, text="Every").grid(row=0, column=0, padx=(0, 4))
        ttk.Spinbox(
            timelapse_frame, from_=TIMELAPSE_MIN_INTERVAL_S, to=TIMELAPSE_MAX_INTERVAL_S, increment=1, width=4,
            textvariable=self.timelapse_interval_var, justify="center",
        ).grid(row=0, column=1)
        ttk.Label(timelapse_frame, text="s, for").grid(row=0, column=2, padx=(4, 4))
        ttk.Spinbox(
            timelapse_frame, from_=0, to=TIMELAPSE_MAX_DURATION_MIN, increment=1, width=4,
            textvariable=self.timelapse_duration_var, justify="center",
        ).grid(row=0, column=3)
        ttk.Label(timelapse_frame, text="min (0 = until stopped)").grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 6))
        ttk.Button(timelapse_frame, text="●  Start Timelapse", command=self.on_timelapse_start).grid(row=0, column=4, rowspan=2, padx=(10, 0))

    def _render_burst_controls(self) -> None:
        self._clear_action_area()
        ttk.Label(
            self.action_area, textvariable=self.burst_status_var, foreground="#2ecc71", wraplength=420,
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(self.action_area, text="Cancel Burst", command=self.on_burst_cancel).pack(side=tk.LEFT)

    def _render_timelapse_controls(self) -> None:
        self._clear_action_area()
        ttk.Label(
            self.action_area, textvariable=self.timelapse_status_var, foreground="#e67e22", wraplength=420,
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(self.action_area, text="Stop Timelapse", command=self.on_timelapse_stop).pack(side=tk.LEFT)

    def _render_review_controls(self) -> None:
        self._clear_action_area()
        save_btn = ttk.Button(self.action_area, text="Save", command=self.on_save)
        save_btn.pack(side=tk.LEFT, ipadx=10, ipady=6)
        self._style_big_button(save_btn)
        ttk.Button(self.action_area, text="Retake", command=self.on_retake).pack(side=tk.LEFT, padx=(12, 3), ipady=6)

    @staticmethod
    def _style_big_button(btn: ttk.Button) -> None:
        style = ttk.Style()
        style.configure("Big.TButton", font=("TkDefaultFont", 12, "bold"))
        btn.configure(style="Big.TButton")

    # ------------------------------------------------------------ camera

    def _try_connect_camera(self, initial: bool = False) -> None:
        try:
            self.cap = open_camera(self.device, self.cfg)
            self.state = "live"
            self.status_var.set(f"Camera connected ({self.device}). Ready to capture.")
            self._render_live_controls()
        except RuntimeError as e:
            self.cap = None
            self.state = "disconnected"
            self.status_var.set(str(e))
            self._render_connecting_controls(
                "No camera detected." if initial else "Still no camera detected."
            )

    def _on_reconnect_clicked(self) -> None:
        self.status_var.set("Trying to connect to the camera...")
        self.root.update_idletasks()
        self._try_connect_camera(initial=False)

    # ------------------------------------------------------------ main loop

    def _tick(self) -> None:
        if self.state == "live" and self.cap is not None:
            ok, frame = self.cap.read()
            if ok:
                self._last_live_frame = frame
                self._show_frame(frame)
                if self.video_capture_active:
                    self._write_video_capture_frame(frame)
            else:
                self.status_var.set("Lost connection to camera.")
                self.state = "disconnected"
                self._render_connecting_controls("Camera disconnected.")
                if self.video_capture_active:
                    self._report_video_failure("camera disconnected")
        elif self.state == "review" and self.frozen_frame is not None:
            self._show_frame(self.frozen_frame)

        self.root.after(PREVIEW_REFRESH_MS, self._tick)

    def _show_frame(self, frame_bgr) -> None:
        container_w = max(self.video_label.winfo_width(), 360)
        container_h = max(self.video_label.winfo_height(), 270)

        h, w = frame_bgr.shape[:2]

        if self.zoom_level > ZOOM_MIN:
            cx, cy = self.zoom_center
            x0, y0, crop_w, crop_h = compute_zoom_crop(w, h, self.zoom_level, cx, cy)
            source = frame_bgr[y0 : y0 + crop_h, x0 : x0 + crop_w]
        else:
            x0, y0, crop_w, crop_h = 0, 0, w, h
            source = frame_bgr

        new_w, new_h = compute_fit_size(container_w, container_h, crop_w, crop_h)
        resized = cv2.resize(source, (new_w, new_h), interpolation=cv2.INTER_AREA)

        self._last_render = {
            "offset_x": (container_w - new_w) / 2,
            "offset_y": (container_h - new_h) / 2,
            "disp_w": new_w,
            "disp_h": new_h,
            "crop_x0": x0,
            "crop_y0": y0,
            "crop_w": crop_w,
            "crop_h": crop_h,
            "frame_w": w,
            "frame_h": h,
        }

        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        photo = ImageTk.PhotoImage(image=img)
        self.video_label.configure(image=photo)
        self.video_label.image = photo  # keep a reference or Tkinter will garbage-collect it

    # ------------------------------------------------------------ zoom (right-click + hold)

    def _widget_xy_to_frame_fraction(self, x: int, y: int) -> tuple[float, float] | None:
        r = self._last_render
        if r is None or r["disp_w"] <= 0 or r["disp_h"] <= 0:
            return None
        rel_x = min(max(x - r["offset_x"], 0), r["disp_w"])
        rel_y = min(max(y - r["offset_y"], 0), r["disp_h"])
        crop_x = rel_x / r["disp_w"] * r["crop_w"]
        crop_y = rel_y / r["disp_h"] * r["crop_h"]
        frac_x = (r["crop_x0"] + crop_x) / r["frame_w"]
        frac_y = (r["crop_y0"] + crop_y) / r["frame_h"]
        return frac_x, frac_y

    def _on_zoom_press(self, event) -> None:
        if self.state not in ("live", "review"):
            return
        self._zoom_drag_start_xy = (event.x, event.y)
        self._zoom_drag_start_level = self.zoom_level
        self._zoom_drag_moved = 0
        frac = self._widget_xy_to_frame_fraction(event.x, event.y)
        if frac is not None:
            self.zoom_center = frac

    def _on_zoom_drag(self, event) -> None:
        if self._zoom_drag_start_xy is None:
            return
        start_x, start_y = self._zoom_drag_start_xy
        dx, dy = event.x - start_x, event.y - start_y
        self._zoom_drag_moved = max(self._zoom_drag_moved, abs(dx), abs(dy))
        delta = -dy / ZOOM_DRAG_SENSITIVITY
        self.zoom_level = max(ZOOM_MIN, min(ZOOM_MAX, self._zoom_drag_start_level + delta))
        self._update_zoom_indicator()

    def _on_zoom_release(self, event) -> None:
        if self._zoom_drag_start_xy is None:
            return
        if self._zoom_drag_moved < ZOOM_CLICK_THRESHOLD_PX:
            self.zoom_level = ZOOM_MIN
            self.zoom_center = (0.5, 0.5)
            self._update_zoom_indicator()
        self._zoom_drag_start_xy = None
        self._zoom_drag_start_level = None
        self._zoom_drag_moved = 0

    def _update_zoom_indicator(self) -> None:
        if self.zoom_level > ZOOM_MIN + 0.01:
            self.zoom_indicator.configure(text=f"{self.zoom_level:.1f}x")
        else:
            self.zoom_indicator.configure(text="right-click+drag to zoom")

    # ------------------------------------------------------------ actions

    def on_capture(self) -> None:
        if self.state != "live" or self.cap is None:
            return
        ok, frame = self.cap.read()
        if not ok:
            messagebox.showwarning("Capture failed", "Could not read a frame from the camera.")
            return
        self.frozen_frame = frame
        self.state = "review"
        self.status_var.set("Frame frozen. Save it, or Retake.")
        self._render_review_controls()

    def on_retake(self) -> None:
        self.frozen_frame = None
        self.state = "live"
        self.status_var.set("Live. Ready to capture.")
        self._render_live_controls()

    def on_save(self) -> None:
        if self.frozen_frame is None:
            return
        filename = self._save_capture(self.frozen_frame)
        self.session_count += 1
        self.status_var.set(f"Saved {filename}. Session total: {self.session_count}.")
        self.frozen_frame = None
        self.state = "live"
        self._render_live_controls()

    # ------------------------------------------------------ periodic still photos

    def sync_capture_once(self, when: dt.datetime) -> str | None:
        """Save whatever frame the live preview loop most recently grabbed
        (self._last_live_frame, same source Timelapse stills use) under the
        given shared timestamp. Called back-to-back for both sync-controlled
        panels from MultiCaptureApp's single tick, so using the
        already-fetched preview frame - rather than each panel blocking on
        its own fresh cap.read() - keeps the two panels' actual capture
        instants as close together as this hardware allows. Returns None
        (skips the save) if this panel isn't live yet."""
        if self.state != "live" or self._last_live_frame is None:
            return None
        filename = self._save_capture(self._last_live_frame, notes_suffix="[periodic-still]", when=when)
        self.session_count += 1
        self.status_var.set(f"Periodic still photos: {self.session_count} saved (last: {filename}).")
        return filename

    # ------------------------------------------------------------ burst capture

    def on_burst_start(self) -> None:
        if self.state != "live" or self.cap is None:
            messagebox.showwarning("Camera not ready", f"Connect the {self.label} camera before starting a burst.")
            return

        try:
            count = int(self.burst_count_var.get())
        except ValueError:
            messagebox.showwarning("Invalid burst count", "Enter a whole number of images.")
            return
        if not (BURST_MIN_COUNT <= count <= BURST_MAX_COUNT):
            messagebox.showwarning(
                "Invalid burst count", f"Enter a number between {BURST_MIN_COUNT} and {BURST_MAX_COUNT}."
            )
            return

        try:
            interval = float(self.burst_interval_var.get())
        except ValueError:
            messagebox.showwarning("Invalid interval", "Enter a number of seconds between shots.")
            return
        if not (BURST_MIN_INTERVAL_S <= interval <= BURST_MAX_INTERVAL_S):
            messagebox.showwarning(
                "Invalid interval", f"Enter an interval between {BURST_MIN_INTERVAL_S} and {BURST_MAX_INTERVAL_S} seconds."
            )
            return

        self.burst_active = True
        self.burst_total = count
        self.burst_saved = 0
        self._burst_interval_ms = int(interval * 1000)
        self.burst_status_var.set(f"Burst: 0/{count} captured...")
        self._render_burst_controls()
        self._burst_capture_one()

    def _burst_capture_one(self) -> None:
        self.burst_after_id = None
        if not self.burst_active:
            return

        if self.state != "live" or self.cap is None:
            self.status_var.set(f"Burst stopped: camera disconnected after {self.burst_saved}/{self.burst_total}.")
            self._end_burst()
            return

        ok, frame = self.cap.read()
        if ok:
            filename = self._save_capture(frame)
            self.session_count += 1
            self.burst_saved += 1
            self.burst_status_var.set(f"Burst: {self.burst_saved}/{self.burst_total} captured (last: {filename})")
        else:
            self.burst_status_var.set(f"Burst: {self.burst_saved}/{self.burst_total} captured (skipped a bad frame)")

        if self.burst_saved >= self.burst_total:
            self.status_var.set(f"Burst complete: {self.burst_saved} image(s) saved. Session total: {self.session_count}.")
            self._end_burst()
            return

        self.burst_after_id = self.root.after(self._burst_interval_ms, self._burst_capture_one)

    def on_burst_cancel(self) -> None:
        self.status_var.set(f"Burst cancelled after {self.burst_saved}/{self.burst_total} image(s). Session total: {self.session_count}.")
        self._end_burst()

    def _end_burst(self) -> None:
        self.burst_active = False
        if self.burst_after_id is not None:
            self.root.after_cancel(self.burst_after_id)
            self.burst_after_id = None
        if self.state == "live":
            self._render_live_controls()

    def _unique_timestamp_filename(self, when: dt.datetime) -> str:
        """Filename that sorts and reads by capture time AND names its
        source camera - e.g. vial_fill_20260922_143005_123456.jpg - rather
        than an opaque incrementing counter, so the filename alone (no need
        to open the file or check which folder it's in) says which camera
        and when, useful once images from different streams end up mixed
        together (a zip export, a shared drive, ...). Microsecond precision
        makes a same-stream collision essentially impossible, but this
        still checks and appends -1, -2, ... just in case."""
        base = f"{self.stream_key}_{when.strftime('%Y%m%d_%H%M%S_%f')}"
        candidate = f"{base}.jpg"
        n = 1
        while (self.images_dir / candidate).exists():
            candidate = f"{base}-{n}.jpg"
            n += 1
        return candidate

    def _save_capture(self, frame, notes_suffix: str = "", when: dt.datetime | None = None) -> str:
        # `when` lets a caller pin the exact timestamp instead of reading
        # the clock here - MultiCaptureApp's periodic photo capture computes
        # ONE timestamp and passes it to both the Vial Fill and Tank Level
        # panels so their captured_at (and EXIF DateTime) match exactly,
        # not just approximately.
        now = when or dt.datetime.now()
        filename = self._unique_timestamp_filename(now)
        out_path = self.images_dir / filename
        # Same timestamp goes three places: burned visibly into the image
        # itself (so two images from different cameras can be matched up
        # by eye, e.g. a Vial Fill and Tank Level frame from a
        # synchronized burst), the JPEG's own EXIF DateTime/
        # DateTimeOriginal tags, and capture_metadata.csv's captured_at -
        # never only available in one place.
        stamped = self._burn_timestamp(frame, now)
        save_jpeg_with_timestamp(out_path, stamped, quality=95, when=now)

        h, w = frame.shape[:2]
        notes = self.notes_var.get()
        if notes_suffix:
            notes = f"{notes} {notes_suffix}".strip()
        append_metadata_row(
            self.metadata_csv,
            {
                "filename": filename,
                "captured_at": now.isoformat(timespec="seconds"),
                "batch_id": self.batch_id_var.get(),
                "order_id": self.order_id_var.get(),
                "camera_device": self.device,
                "width": w,
                "height": h,
                "notes": notes,
            },
            fieldnames=CAPTURE_METADATA_FIELDS,
        )
        print(f"[{self.label}] saved {out_path.relative_to(REPO_ROOT)}")
        return filename

    # ------------------------------------------------------------ timelapse

    def on_timelapse_start(self) -> None:
        if self.state != "live" or self.cap is None:
            messagebox.showwarning("Camera not ready", f"Connect the {self.label} camera before starting a timelapse.")
            return
        if self._last_live_frame is None:
            messagebox.showwarning("No frame yet", "Waiting for the first camera frame -- try again in a moment.")
            return

        try:
            interval = float(self.timelapse_interval_var.get())
        except ValueError:
            messagebox.showwarning("Invalid interval", "Enter a number of seconds between stills.")
            return
        if not (TIMELAPSE_MIN_INTERVAL_S <= interval <= TIMELAPSE_MAX_INTERVAL_S):
            messagebox.showwarning(
                "Invalid interval",
                f"Enter an interval between {TIMELAPSE_MIN_INTERVAL_S:.0f} and {TIMELAPSE_MAX_INTERVAL_S:.0f} seconds.",
            )
            return

        try:
            duration_min = float(self.timelapse_duration_var.get())
        except ValueError:
            messagebox.showwarning("Invalid duration", "Enter a number of minutes (0 = run until stopped).")
            return
        if not (0 <= duration_min <= TIMELAPSE_MAX_DURATION_MIN):
            messagebox.showwarning(
                "Invalid duration", f"Enter a duration between 0 and {TIMELAPSE_MAX_DURATION_MIN:.0f} minutes."
            )
            return

        if shutil.which("ffmpeg") is None:
            messagebox.showerror(
                "ffmpeg not found",
                "Timelapse video recording needs the ffmpeg command-line tool. Install it with:\n\n"
                "    sudo apt install ffmpeg\n\nthen try again.",
            )
            return

        h, w = self._last_live_frame.shape[:2]
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_tag = self.batch_id_var.get().strip().replace(" ", "_") or "session"
        self.timelapse_video_path = self.videos_dir / f"timelapse_{self.stream_key}_{batch_tag}_{ts}.mp4"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{w}x{h}", "-r", str(TIMELAPSE_VIDEO_FPS),
            "-i", "-",
            "-an", "-c:v", "libx264", "-preset", TIMELAPSE_FFMPEG_PRESET, "-crf", TIMELAPSE_FFMPEG_CRF,
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(self.timelapse_video_path),
        ]
        try:
            self.timelapse_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        except OSError as e:
            messagebox.showerror("Timelapse failed", f"Could not start ffmpeg: {e}")
            self.timelapse_proc = None
            return

        self.timelapse_active = True
        self.timelapse_start_monotonic = time.monotonic()
        self.timelapse_duration_s = duration_min * 60.0
        self._timelapse_interval_s = interval
        self.timelapse_stills_saved = 0
        self.timelapse_video_frames = 0
        self._update_timelapse_status()
        self._render_timelapse_controls()
        self._timelapse_capture_still()

    def _write_timelapse_frame(self, frame, when: dt.datetime | None = None) -> None:
        if self.timelapse_proc is None or self.timelapse_proc.stdin is None:
            return
        try:
            self.timelapse_proc.stdin.write(self._burn_timestamp(frame, when).tobytes())
        except (BrokenPipeError, OSError):
            self._stop_timelapse(reason="video encoder process died unexpectedly")
            return
        self.timelapse_video_frames += 1
        self._update_timelapse_status()

    @staticmethod
    def _burn_timestamp(frame, when: dt.datetime | None = None):
        """Stamp `when` (default: now) into the bottom-left corner of a copy
        of `frame`, readable at a glance - used for every saved image (see
        _save_capture) and every recorded video frame (Timelapse, Video
        Capture), so two images/frames from different cameras can be lined
        up by eye without pulling up metadata."""
        out = frame.copy()
        text = (when or dt.datetime.now()).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        origin = (10, out.shape[0] - 16)
        cv2.putText(out, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(out, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)
        return out

    def _timelapse_capture_still(self) -> None:
        self.timelapse_still_after_id = None
        if not self.timelapse_active:
            return
        if self.state != "live" or self.cap is None or self._last_live_frame is None:
            self._stop_timelapse(reason="camera disconnected")
            return

        frame = self._last_live_frame
        now = dt.datetime.now()
        self._save_capture(frame, notes_suffix="[timelapse]", when=now)
        self.session_count += 1
        self.timelapse_stills_saved += 1
        self._write_timelapse_frame(frame, when=now)
        self._update_timelapse_status()

        if (
            self.timelapse_duration_s > 0
            and (time.monotonic() - self.timelapse_start_monotonic) >= self.timelapse_duration_s
        ):
            self._stop_timelapse(reason="duration reached")
            return

        interval_ms = int(self._timelapse_interval_s * 1000)
        self.timelapse_still_after_id = self.root.after(interval_ms, self._timelapse_capture_still)

    def _update_timelapse_status(self) -> None:
        elapsed = time.monotonic() - self.timelapse_start_monotonic
        video_name = self.timelapse_video_path.name if self.timelapse_video_path else "?"
        speedup = self._timelapse_interval_s * TIMELAPSE_VIDEO_FPS
        self.timelapse_status_var.set(
            f"Timelapse: {elapsed:0.0f}s elapsed, {self.timelapse_stills_saved} still(s) "
            f"(~{speedup:.0f}x speedup) -> {video_name}"
        )

    def on_timelapse_stop(self) -> None:
        self._stop_timelapse(reason="stopped by user")

    def _stop_timelapse(self, reason: str) -> None:
        if not self.timelapse_active:
            return
        self.timelapse_active = False
        if self.timelapse_still_after_id is not None:
            self.root.after_cancel(self.timelapse_still_after_id)
            self.timelapse_still_after_id = None
        if self.timelapse_proc is not None:
            try:
                if self.timelapse_proc.stdin is not None:
                    self.timelapse_proc.stdin.close()
                self.timelapse_proc.wait(timeout=30)
            except (subprocess.TimeoutExpired, OSError):
                self.timelapse_proc.kill()
            self.timelapse_proc = None

        video_path = self.timelapse_video_path
        stills, frames = self.timelapse_stills_saved, self.timelapse_video_frames
        self.timelapse_video_path = None
        self.status_var.set(
            f"Timelapse ended ({reason}): {stills} still(s), {frames} video frame(s) -> "
            f"{video_path.name if video_path else '?'}. Session total: {self.session_count}."
        )
        if self.state == "live":
            self._render_live_controls()

    # ------------------------------------------------------ continuous video capture

    def start_video_capture(self, batch_tag: str, recording_id: str) -> bool:
        """Start this panel's leg of the all-3-camera Video Capture (see
        MultiCaptureApp.on_video_capture_start). Returns True on success;
        False if this camera isn't live yet or ffmpeg couldn't start,
        leaving this panel's state unchanged either way."""
        if self.state != "live" or self._last_live_frame is None:
            return False
        h, w = self._last_live_frame.shape[:2]
        self.video_capture_path = self.videos_dir / f"video_{self.stream_key}_{batch_tag}_{recording_id}.mp4"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-use_wallclock_as_timestamps", "1",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{w}x{h}", "-framerate", str(VIDEO_CAPTURE_FPS),
            "-i", "-",
            "-an", "-c:v", "libx264", "-preset", VIDEO_CAPTURE_FFMPEG_PRESET, "-crf", VIDEO_CAPTURE_FFMPEG_CRF,
            "-pix_fmt", "yuv420p", "-fps_mode", "vfr", "-copyts", "-start_at_zero",
            "-movflags", "+faststart",
            str(self.video_capture_path),
        ]
        try:
            self.video_capture_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        except OSError:
            self.video_capture_proc = None
            self.video_capture_path = None
            return False
        self.video_capture_active = True
        self.video_capture_frames = 0
        return True

    def _write_video_capture_frame(self, frame) -> None:
        if self.video_capture_proc is None or self.video_capture_proc.stdin is None:
            return
        try:
            self.video_capture_proc.stdin.write(self._burn_timestamp(frame, self.shared_clock[0]).tobytes())
        except (BrokenPipeError, OSError):
            self._report_video_failure("video encoder stopped unexpectedly")
            return
        self.video_capture_frames += 1

    def _report_video_failure(self, reason: str) -> None:
        """Escalate a recording failure to the shared three-camera owner.

        The callback stops all panels as one session. The fallback keeps this
        panel safe when it is used outside MultiCaptureApp (for example in a
        focused test or a future single-camera wrapper).
        """
        if self.video_failure_callback is not None:
            self.video_failure_callback(self, reason)
        else:
            self.stop_video_capture()

    def stop_video_capture(self) -> tuple[Path | None, int]:
        """Stop this panel's leg of Video Capture. Returns (video_path,
        frame_count), or (None, 0) if it wasn't running."""
        if not self.video_capture_active:
            return None, 0
        self.video_capture_active = False
        if self.video_capture_proc is not None:
            try:
                if self.video_capture_proc.stdin is not None:
                    self.video_capture_proc.stdin.close()
                self.video_capture_proc.wait(timeout=30)
            except (subprocess.TimeoutExpired, OSError):
                self.video_capture_proc.kill()
            self.video_capture_proc = None
        path, frames = self.video_capture_path, self.video_capture_frames
        self.video_capture_path = None
        return path, frames

    # ------------------------------------------------------------ cleanup

    def cleanup(self) -> None:
        if self.burst_after_id is not None:
            self.root.after_cancel(self.burst_after_id)
            self.burst_after_id = None
        self.burst_active = False
        if self.timelapse_still_after_id is not None:
            self.root.after_cancel(self.timelapse_still_after_id)
            self.timelapse_still_after_id = None
        if self.timelapse_proc is not None:
            try:
                if self.timelapse_proc.stdin is not None:
                    self.timelapse_proc.stdin.close()
                self.timelapse_proc.wait(timeout=30)
            except (subprocess.TimeoutExpired, OSError):
                self.timelapse_proc.kill()
            self.timelapse_proc = None
        self.timelapse_active = False
        self.stop_video_capture()
        if self.cap is not None:
            self.cap.release()

    def print_summary(self) -> None:
        print(f"\n[{self.label}] session total: {self.session_count} image(s) saved.")
        print(f"[{self.label}] images saved under: {self.images_dir}")
        print(f"[{self.label}] timelapse videos (if any) saved under: {self.videos_dir}")


class MultiCaptureApp:
    def __init__(self, root: tk.Tk, panel_configs: list[tuple[str, dict, int]], batch_id: str, start_order_id: str = "1"):
        self.root = root
        self.maximized = False
        self.batch_id_var = tk.StringVar(value=batch_id)
        self.order_id_var = tk.StringVar(value=start_order_id)

        # One-element list (mutable-by-reference, so every CameraPanel sees
        # the same object) kept current by _tick_shared_clock() below,
        # independent of any single camera's frame rate. Video Capture
        # frames read this instead of calling datetime.now() inside their
        # own panel's tick, so all three streams' burned-in timestamps stay
        # consistent with each other rather than drifting apart (measured:
        # independent per-panel timestamps drifted ~30-40ms and growing
        # over a few seconds - this keeps them within one clock-tick
        # interval of each other instead).
        self.shared_clock: list[dt.datetime] = [dt.datetime.now()]
        self._tick_shared_clock()

        self.root.title("Fill Line Inspection - Capture")
        self.root.geometry(DEFAULT_GEOMETRY)
        self.root.minsize(1000, 560)
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)

        top = ttk.Frame(self.root, padding=(10, 8))
        top.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(top, text="Batch / session ID (applies to all cameras):").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.batch_id_var, width=24).pack(side=tk.LEFT, padx=(6, 0))

        # "Order / Run #" is what ties one physical unit's images together
        # ACROSS the three stations as it moves down the line (fill ->
        # tank reading -> cap/seal + palletize) - see CAPTURE_METADATA_FIELDS
        # in common.py. It's independent of Batch ID (which tags a whole
        # session): set/keep it the same while a given unit is captured at
        # each station's camera in turn, then click "Next Order" once that
        # unit is done and the next one arrives at the first station.
        ttk.Label(top, text="   Order / Run # (same unit across all cameras):").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.order_id_var, width=10).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(top, text="Next Order ▸", command=self.on_next_order).pack(side=tk.LEFT, padx=(6, 0))

        # ---- Continuous Video (all 3 cameras) -------------------------------
        # Continuous real-time recording, every panel, one shared Start/Stop -
        # separate from (and can run alongside) Periodic Still Photos. Placed
        # above Periodic Still Photos so both "all cameras" controls sit
        # together directly above the camera row.
        self.video_capture_active = False
        self.video_status_after_id: str | None = None
        self.video_start_monotonic = 0.0
        self.video_status_var = tk.StringVar(value="Not recording.")

        video_bar = ttk.LabelFrame(self.root, text="Continuous Video (MP4) - All Connected Cameras", padding=(10, 8))
        video_bar.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 8))
        self.video_start_btn = ttk.Button(video_bar, text="●  Start Recording", command=self.on_video_capture_start)
        self.video_start_btn.pack(side=tk.LEFT)
        self.video_stop_btn = ttk.Button(video_bar, text="Stop Recording", command=self.on_video_capture_stop, state=tk.DISABLED)
        self.video_stop_btn.pack(side=tk.LEFT, padx=(6, 14))
        ttk.Label(video_bar, textvariable=self.video_status_var).pack(side=tk.LEFT)

        # ---- Vial log (ground truth saved with each recording) -------------
        self.vial_id_var = tk.StringVar(value="B01-1")
        self.intended_var = tk.StringVar(value="40/0/0")
        self.actual_var = tk.StringVar(value="")
        self.fault_var = tk.StringVar(value="none")
        self.vial_notes_var = tk.StringVar(value="")
        log_bar = ttk.LabelFrame(self.root, text="Vial log (saved with each recording; R/Y/B; Actual blank = same as intended)", padding=(10, 8))
        log_bar.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 8))
        for text, var, width in (("Vial ID", self.vial_id_var, 9), ("Intended R/Y/B", self.intended_var, 10),
                                 ("Actual R/Y/B", self.actual_var, 10)):
            ttk.Label(log_bar, text=text).pack(side=tk.LEFT)
            ttk.Entry(log_bar, textvariable=var, width=width).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(log_bar, text="Fault").pack(side=tk.LEFT)
        ttk.Combobox(log_bar, textvariable=self.fault_var, values=FAULT_TYPES, width=14, state="readonly").pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(log_bar, text="Notes").pack(side=tk.LEFT)
        ttk.Entry(log_bar, textvariable=self.vial_notes_var, width=40).pack(side=tk.LEFT, padx=(4, 0), fill=tk.X, expand=True)
        self.recording_panels: list[CameraPanel] = []
        self.recording_meta: dict = {}

        # ---- Periodic Still Photos (all 3 cameras) -------------------------
        # Fires all three cameras together on a fixed rate, under one shared
        # timestamp per tick, from Start until Stop - replaces those panels'
        # own Manual/Burst/Timelapse controls (see CameraPanel's
        # sync_controlled flag).
        self.sync_active = False
        self.sync_after_id: str | None = None
        self.sync_count = 0
        self.sync_start_monotonic = 0.0
        self.sync_interval_var = tk.StringVar(value=str(SYNC_DEFAULT_INTERVAL_S))
        self.sync_status_var = tk.StringVar(value="Stopped. Saves timestamped JPEG photos, not video.")

        sync_bar = ttk.LabelFrame(self.root, text="Periodic Still Photos (JPEG) - All 3 Cameras", padding=(10, 8))
        sync_bar.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 8))
        ttk.Label(sync_bar, text="Photo interval: every").pack(side=tk.LEFT)
        ttk.Spinbox(
            sync_bar, from_=SYNC_MIN_INTERVAL_S, to=SYNC_MAX_INTERVAL_S, increment=0.5, width=5,
            textvariable=self.sync_interval_var, justify="center",
        ).pack(side=tk.LEFT, padx=(4, 4))
        ttk.Label(sync_bar, text="s").pack(side=tk.LEFT, padx=(0, 14))
        self.sync_start_btn = ttk.Button(sync_bar, text="●  Start Photos", command=self.on_sync_start)
        self.sync_start_btn.pack(side=tk.LEFT)
        self.sync_stop_btn = ttk.Button(sync_bar, text="Stop Photos", command=self.on_sync_stop, state=tk.DISABLED)
        self.sync_stop_btn.pack(side=tk.LEFT, padx=(6, 14))
        ttk.Label(sync_bar, textvariable=self.sync_status_var).pack(side=tk.LEFT)

        panes = ttk.Frame(self.root)
        panes.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(0, 6))
        panes.rowconfigure(0, weight=1)

        # grid + a shared "uniform" group forces every column to the SAME
        # width regardless of how much each panel's content asks for (pack
        # would only distribute leftover space equally, so e.g. a
        # disconnected panel's narrower "Reconnect Camera" controls would
        # make its column visibly thinner than a connected panel's wider
        # Manual/Burst/Timelapse controls).
        SYNC_STREAM_KEYS = ("vial_fill", "tank_level", "cap_seal")
        self.panels: list[CameraPanel] = []
        for i, (stream_key, cfg, device) in enumerate(panel_configs):
            panes.columnconfigure(i, weight=1, uniform="camera_panel")
            col = ttk.Frame(panes)
            col.grid(row=0, column=i, sticky="nsew", padx=4)
            sync_controlled = stream_key in SYNC_STREAM_KEYS
            self.panels.append(
                CameraPanel(
                    col,
                    self.root,
                    stream_key,
                    cfg,
                    device,
                    self.batch_id_var,
                    self.order_id_var,
                    self.shared_clock,
                    sync_controlled,
                    self._on_panel_video_failure,
                )
            )
        self.sync_panels = [p for p in self.panels if p.stream_key in SYNC_STREAM_KEYS]

        bottom = ttk.Frame(self.root, padding=(10, 8))
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(bottom, text="Minimize", command=self.on_minimize).pack(side=tk.RIGHT, padx=4)
        self.enlarge_btn = ttk.Button(bottom, text="Enlarge", command=self.on_toggle_enlarge)
        self.enlarge_btn.pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text="Exit", command=self.on_exit).pack(side=tk.RIGHT, padx=4)

    def on_next_order(self) -> None:
        current = self.order_id_var.get().strip()
        self.order_id_var.set(str(int(current) + 1) if current.isdigit() else current)

    def _tick_shared_clock(self) -> None:
        """Keeps self.shared_clock[0] current, independent of any panel's
        own camera tick - runs continuously from app startup (not just
        during Video Capture) so it's never stale the moment recording
        starts. See CameraPanel.shared_clock."""
        self.shared_clock[0] = dt.datetime.now()
        self.root.after(SHARED_CLOCK_TICK_MS, self._tick_shared_clock)

    # ------------------------------------------------------ periodic still photos

    def on_sync_start(self) -> None:
        try:
            interval = float(self.sync_interval_var.get())
        except ValueError:
            messagebox.showwarning("Invalid rate", "Enter a number of seconds between shots.")
            return
        if not (SYNC_MIN_INTERVAL_S <= interval <= SYNC_MAX_INTERVAL_S):
            messagebox.showwarning(
                "Invalid rate", f"Enter a rate between {SYNC_MIN_INTERVAL_S} and {SYNC_MAX_INTERVAL_S} seconds."
            )
            return
        self.sync_live_panels = [p for p in self.sync_panels if p.state == "live"]
        if not self.sync_live_panels:
            messagebox.showwarning("Cameras not ready", "No camera is connected.")
            return

        self.sync_active = True
        self._sync_interval_ms = int(interval * 1000)
        self.sync_count = 0
        self.sync_start_monotonic = time.monotonic()
        self.sync_status_var.set("Starting...")
        self.sync_start_btn.configure(state=tk.DISABLED)
        self.sync_stop_btn.configure(state=tk.NORMAL)
        self._sync_tick()

    def _sync_tick(self) -> None:
        self.sync_after_id = None
        if not self.sync_active:
            return

        not_live = [p.label for p in self.sync_live_panels if p.state != "live"]
        if not_live:
            self.sync_status_var.set(f"Stopped - lost connection to: {', '.join(not_live)}.")
            self._end_sync()
            return

        # One shared timestamp, passed to every panel's save so their
        # captured_at (and each JPEG's own EXIF DateTime) match exactly -
        # that's the whole point of firing them from one tick instead of
        # each panel timing its own shots independently.
        now = dt.datetime.now()
        saved = [p.sync_capture_once(now) for p in self.sync_live_panels]
        if all(saved):
            self.sync_count += 1

        elapsed = time.monotonic() - self.sync_start_monotonic
        self.sync_status_var.set(f"Saving photos: {self.sync_count} set(s) from {len(self.sync_live_panels)} camera(s), {elapsed:0.0f}s elapsed.")
        self.sync_after_id = self.root.after(self._sync_interval_ms, self._sync_tick)

    def on_sync_stop(self) -> None:
        self.sync_status_var.set(f"Stopped after {self.sync_count} three-camera photo set(s).")
        self._end_sync()

    def _end_sync(self) -> None:
        self.sync_active = False
        if self.sync_after_id is not None:
            self.root.after_cancel(self.sync_after_id)
            self.sync_after_id = None
        self.sync_start_btn.configure(state=tk.NORMAL)
        self.sync_stop_btn.configure(state=tk.DISABLED)

    # ------------------------------------------------------ video capture (all 3)

    def on_video_capture_start(self) -> None:
        live = [p for p in self.panels if p.state == "live"]
        if not live:
            messagebox.showwarning("Cameras not ready", "No camera is connected.")
            return
        if shutil.which("ffmpeg") is None:
            messagebox.showerror(
                "ffmpeg not found",
                "Continuous Video needs the ffmpeg command-line tool. Install it with:\n\n"
                "    sudo apt install ffmpeg\n\nthen try again.",
            )
            return

        batch_tag = self.batch_id_var.get().strip().replace(" ", "_") or "session"
        # One identifier is shared by all three filenames, including
        # microseconds so back-to-back recordings cannot collide.
        recording_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        started: list[CameraPanel] = []
        for p in live:
            if p.start_video_capture(batch_tag, recording_id):
                started.append(p)
            else:
                for sp in started:
                    sp.stop_video_capture()
                messagebox.showerror("Recording failed", f"Could not start recording for {p.label}.")
                return

        self.recording_panels = started
        self.recording_meta = {
            "recording_id": recording_id, "batch_id": batch_tag,
            "vial_id": self.vial_id_var.get().strip(), "started_at": dt.datetime.now().isoformat(timespec="milliseconds"),
            "intended_ryb": self.intended_var.get().strip(), "actual_ryb": self.actual_var.get().strip(),
            "fault_type": self.fault_var.get(), "notes": self.vial_notes_var.get().strip(),
            "cameras": {p.stream_key: {"device": str(p.device), "settings": camera_settings(p.cap) if p.cap is not None else None}
                        for p in started},
        }
        self.video_capture_active = True
        self.video_start_monotonic = time.monotonic()
        self.video_start_btn.configure(state=tk.DISABLED)
        self.video_stop_btn.configure(state=tk.NORMAL)
        self._video_status_tick()

    def _video_status_tick(self) -> None:
        self.video_status_after_id = None
        if not self.video_capture_active:
            return
        stopped = [p for p in self.recording_panels if not p.video_capture_active]
        if stopped:
            self._on_panel_video_failure(stopped[0], "recording stopped unexpectedly")
            return
        elapsed = time.monotonic() - self.video_start_monotonic
        counts = ", ".join(f"{p.label}: {p.video_capture_frames}f" for p in self.recording_panels)
        self.video_status_var.set(f"Recording: {elapsed:0.0f}s elapsed - {counts}.")
        self.video_status_after_id = self.root.after(1000, self._video_status_tick)

    def on_video_capture_stop(self) -> None:
        results = self._stop_video_panels()
        self._end_video_capture()
        self.video_status_var.set("Stopped. " + "; ".join(results) if results else "Stopped.")

    def _stop_video_panels(self) -> list[str]:
        results, files = [], {}
        for p in self.recording_panels:
            path, frames = p.stop_video_capture()
            if path is not None:
                results.append(f"{p.label}: {frames}f -> {path.name}")
                files[p.stream_key] = {"path": str(path), "frames": frames}
        if self.recording_meta:
            try:
                self._write_vial_log(files)
            except OSError as e:
                messagebox.showerror("Vial log not saved", str(e))
        return results

    def _write_vial_log(self, files: dict) -> None:
        """Append this recording's ground truth to vial_log.csv and write a
        .json sidecar next to each .mp4. Logs failed/partial recordings too."""
        meta = dict(self.recording_meta)
        self.recording_meta = {}
        meta["stopped_at"] = dt.datetime.now().isoformat(timespec="milliseconds")
        meta["duration_s"] = round(time.monotonic() - self.video_start_monotonic, 2)
        meta["actual_ryb"] = meta["actual_ryb"] or meta["intended_ryb"]
        meta["files"] = files
        for info in files.values():
            Path(info["path"]).with_suffix(".json").write_text(json.dumps(meta, indent=1))
        VIAL_LOG_CSV.parent.mkdir(parents=True, exist_ok=True)
        new = not VIAL_LOG_CSV.exists()
        with VIAL_LOG_CSV.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=VIAL_LOG_FIELDS, extrasaction="ignore")
            if new:
                writer.writeheader()
            row = dict(meta)
            row["files"] = ";".join(Path(i["path"]).name for i in files.values())
            row["frames"] = ";".join(str(i["frames"]) for i in files.values())
            writer.writerow(row)
        print(f"[vial log] {meta['vial_id']} intended {meta['intended_ryb']} actual {meta['actual_ryb']} "
              f"fault {meta['fault_type']} -> {VIAL_LOG_CSV}")

    def _on_panel_video_failure(self, failed_panel: CameraPanel, reason: str) -> None:
        """Stop the complete recording if any one camera/encoder fails."""
        if not self.video_capture_active:
            failed_panel.stop_video_capture()
            return
        results = self._stop_video_panels()
        self._end_video_capture()
        detail = "; ".join(results)
        status = f"Stopped automatically: {failed_panel.label} {reason}."
        if detail:
            status += f" {detail}"
        self.video_status_var.set(status)
        messagebox.showerror(
            "Recording stopped",
            f"All recordings were stopped together because {failed_panel.label} {reason}.",
        )

    def _end_video_capture(self) -> None:
        self.video_capture_active = False
        if self.video_status_after_id is not None:
            self.root.after_cancel(self.video_status_after_id)
            self.video_status_after_id = None
        self.video_start_btn.configure(state=tk.NORMAL)
        self.video_stop_btn.configure(state=tk.DISABLED)

    def on_minimize(self) -> None:
        self.root.iconify()

    def on_toggle_enlarge(self) -> None:
        self.maximized = not self.maximized
        if self.maximized:
            self._set_maximized(True)
            self.enlarge_btn.configure(text="Restore")
        else:
            self._set_maximized(False)
            self.root.geometry(DEFAULT_GEOMETRY)
            self.enlarge_btn.configure(text="Enlarge")

    def _set_maximized(self, on: bool) -> None:
        try:
            self.root.state("zoomed" if on else "normal")
            return
        except tk.TclError:
            pass
        try:
            self.root.attributes("-zoomed", on)
            return
        except tk.TclError:
            pass
        if on:
            w, h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            self.root.geometry(f"{w}x{h}+0+0")

    def on_exit(self) -> None:
        self._end_sync()
        self._end_video_capture()
        for panel in self.panels:
            panel.cleanup()  # also stops that panel's video capture, if any
        self.root.destroy()

    def print_summary(self) -> None:
        for panel in self.panels:
            panel.print_summary()


def _parse_device_arg(value: str) -> int | str:
    """--*-device accepts either a plain /dev/videoN index (unstable across
    reconnects) or a device path such as /dev/v4l/by-id/usb-...-video-index0
    (stable - see camera.py's open_camera docstring)."""
    return int(value) if value.isdigit() else value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vial-fill-config", default=str(REPO_ROOT / "config.vial_fill.yaml"))
    parser.add_argument("--tank-level-config", default=str(REPO_ROOT / "config.tank_level.yaml"))
    parser.add_argument("--cap-seal-config", default=str(REPO_ROOT / "config.cap_seal.yaml"))
    parser.add_argument("--vial-fill-device", type=_parse_device_arg, default=None, help="Camera index or /dev/... path override for the vial_fill stream")
    parser.add_argument("--tank-level-device", type=_parse_device_arg, default=None, help="Camera index or /dev/... path override for the tank_level stream")
    parser.add_argument("--cap-seal-device", type=_parse_device_arg, default=None, help="Camera index or /dev/... path override for the cap_seal stream")
    parser.add_argument("--batch-id", default=None, help="Session/batch identifier stored in every stream's capture_metadata.csv (editable in the GUI too). Defaults to an auto-incrementing <year>-<month>-<seq> id (e.g. 2026-09-0000) if not given.")
    parser.add_argument("--start-order-id", default="1", help="Starting value for the 'Order / Run #' field that correlates one unit's images across all three cameras (editable in the GUI too)")
    args = parser.parse_args()

    vial_fill_cfg = load_config(args.vial_fill_config)
    tank_level_cfg = load_config(args.tank_level_config)
    cap_seal_cfg = load_config(args.cap_seal_config)

    vial_fill_device = args.vial_fill_device if args.vial_fill_device is not None else vial_fill_cfg["camera"]["device_index"]
    tank_level_device = args.tank_level_device if args.tank_level_device is not None else tank_level_cfg["camera"]["device_index"]
    cap_seal_device = args.cap_seal_device if args.cap_seal_device is not None else cap_seal_cfg["camera"]["device_index"]

    panel_configs = [
        ("vial_fill", vial_fill_cfg, vial_fill_device),
        ("tank_level", tank_level_cfg, tank_level_device),
        ("cap_seal", cap_seal_cfg, cap_seal_device),
    ]

    batch_id = args.batch_id if args.batch_id is not None else next_auto_batch_id()

    root = tk.Tk()
    app = MultiCaptureApp(root, panel_configs, batch_id, args.start_order_id)
    root.mainloop()
    app.print_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
