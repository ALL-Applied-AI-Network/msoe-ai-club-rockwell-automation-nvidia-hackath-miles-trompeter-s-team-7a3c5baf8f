#!/bin/bash
# start_capture.sh - launches the three-camera capture tool.
# New operators: see the Capture SOP for how to use it once it opens.
#
# Usage: double-click this file (or run `./start_capture.sh` in a terminal)
# from the fill-line-inspection folder.
cd "$(dirname "$0")"
source .venv/bin/activate
python3 src/capture_gui.py
