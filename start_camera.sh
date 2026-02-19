#!/usr/bin/env bash
# start_camera.sh – launch PiCamViewer with recommended defaults.
#
# Usage:
#   ./start_camera.sh [extra args passed to main.py]
#
# The script assumes it lives in the same directory as main.py.
# Adjust PICAMVIEWER_DIR if you install the files elsewhere.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PICAMVIEWER_DIR="${PICAMVIEWER_DIR:-$SCRIPT_DIR}"

# Export DISPLAY so the preview knows which X server to connect to.
# When launched from an autostart entry DISPLAY is already set; this
# default covers manual runs from a desktop terminal.
export DISPLAY="${DISPLAY:-:0}"

echo "[start_camera.sh] Starting PiCamViewer from ${PICAMVIEWER_DIR} on ${DISPLAY} …"

exec python3 "${PICAMVIEWER_DIR}/main.py" \
    --width 1920 \
    --height 1080 \
    --framerate 30 \
    --fullscreen \
    "$@"
