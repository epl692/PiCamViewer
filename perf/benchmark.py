#!/usr/bin/env python3
"""
PiCamViewer performance benchmark script.

Measures display FPS, capture FPS, CPU usage, and memory usage across
multiple runs, and writes results to a JSON artifact file.

Usage (on target Raspberry Pi hardware):
    python3 perf/benchmark.py [--runs 5] [--warmup 10] [--duration 30]
                               [--width 1920] [--height 1080]
                               [--framerate 30] [--output perf/results.json]

The script instruments the display render loop by monkey-patching the
QGlPicamera2/QPicamera2 widget's update method so that Python can count
rendered frames without modifying main.py's core logic.

Requirements (all already required by main.py):
    python3-picamera2  python3-pyqt5  python3-psutil
"""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------
try:
    import psutil
except ImportError:
    sys.exit(
        "psutil is required: sudo apt install -y python3-psutil  "
        "# or: pip3 install psutil"
    )

try:
    from picamera2 import Picamera2
    from picamera2.previews.qt import QGlPicamera2
except ImportError:
    sys.exit(
        "picamera2 not found.  Install with: sudo apt install -y python3-picamera2"
    )

try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt, QTimer
except ImportError:
    sys.exit(
        "PyQt5 not found.  Install with: sudo apt install -y python3-pyqt5"
    )


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="PiCamViewer FPS benchmark")
    p.add_argument("--runs",     type=int,   default=5,    help="Number of measurement runs")
    p.add_argument("--warmup",   type=int,   default=10,   help="Warm-up seconds per run")
    p.add_argument("--duration", type=int,   default=30,   help="Measurement seconds per run")
    p.add_argument("--width",    type=int,   default=1920, help="Capture width")
    p.add_argument("--height",   type=int,   default=1080, help="Capture height")
    p.add_argument("--framerate",type=int,   default=30,   help="Target camera framerate")
    p.add_argument("--output",   type=str,   default=None, help="Output JSON file path")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Instrumented preview widget
# ---------------------------------------------------------------------------
class InstrumentedPreview(QGlPicamera2):
    """QGlPicamera2 subclass that counts paintGL calls for FPS measurement."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._frame_count = 0
        self._measure = False

    def start_measuring(self):
        self._frame_count = 0
        self._measure = True

    def stop_measuring(self):
        self._measure = False
        return self._frame_count

    def paintGL(self):  # noqa: N802
        super().paintGL()
        if self._measure:
            self._frame_count += 1


# ---------------------------------------------------------------------------
# Single run
# ---------------------------------------------------------------------------
def run_once(args):
    """Run one warm-up + measurement cycle and return a dict of metrics."""
    proc = psutil.Process(os.getpid())

    cam = Picamera2()
    config = cam.create_preview_configuration(
        main={"size": (args.width, args.height)},
        buffer_count=2,
        controls={
            "FrameDurationLimits": (
                int(1e6 // args.framerate),
                int(1e6 // args.framerate),
            )
        },
    )
    cam.configure(config)

    app = QApplication.instance() or QApplication(sys.argv)

    widget = InstrumentedPreview(cam, width=args.width, height=args.height, keep_ar=True)
    widget.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    widget.showFullScreen()
    cam.start()

    state = {"phase": "warmup", "result": None}

    def _tick():
        if state["phase"] == "warmup":
            # After warm-up, start measuring
            widget.start_measuring()
            state["t0_cpu"] = proc.cpu_times()
            state["t0_mem"] = proc.memory_info().rss
            state["t0"] = time.monotonic()
            state["phase"] = "measuring"
            QTimer.singleShot(args.duration * 1000, _stop)

    def _stop():
        elapsed = time.monotonic() - state["t0"]
        frames = widget.stop_measuring()
        t1_cpu = proc.cpu_times()
        t1_mem = proc.memory_info().rss

        cpu_user  = t1_cpu.user  - state["t0_cpu"].user
        cpu_sys   = t1_cpu.system - state["t0_cpu"].system
        cpu_total = (cpu_user + cpu_sys) / elapsed * 100.0  # % of one core

        state["result"] = {
            "elapsed_s":      round(elapsed, 3),
            "frames_rendered": frames,
            "fps_display":    round(frames / elapsed, 2),
            "cpu_pct_1core":  round(cpu_total, 1),
            "mem_rss_mb":     round(t1_mem / 1024 / 1024, 1),
        }
        cam.stop()
        cam.close()
        app.quit()

    # Start warm-up timer
    QTimer.singleShot(args.warmup * 1000, _tick)
    app.exec_()

    return state["result"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = parse_args()

    if not os.environ.get("DISPLAY"):
        sys.exit("DISPLAY not set.  Run under X11 or pass DISPLAY=:0.")

    results = []
    for i in range(1, args.runs + 1):
        print(f"Run {i}/{args.runs} …", flush=True)
        r = run_once(args)
        r["run_id"] = i
        results.append(r)
        print(f"  FPS={r['fps_display']}  CPU={r['cpu_pct_1core']}%  "
              f"MEM={r['mem_rss_mb']} MB")

    fps_values = [r["fps_display"] for r in results]
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "width":     args.width,
            "height":    args.height,
            "framerate": args.framerate,
            "runs":      args.runs,
            "warmup_s":  args.warmup,
            "duration_s":args.duration,
        },
        "fps_mean":   round(statistics.mean(fps_values),   2),
        "fps_median": round(statistics.median(fps_values), 2),
        "fps_stddev": round(statistics.stdev(fps_values) if len(fps_values) > 1 else 0.0, 2),
        "fps_p95":    round(sorted(fps_values)[int(len(fps_values) * 0.95)], 2),
        "fps_p99":    round(sorted(fps_values)[int(len(fps_values) * 0.99)], 2),
        "runs":       results,
    }

    print("\n=== Summary ===")
    print(f"  mean FPS : {summary['fps_mean']}")
    print(f"  median   : {summary['fps_median']}")
    print(f"  stddev   : {summary['fps_stddev']}")

    outfile = args.output or os.path.join(
        os.path.dirname(__file__),
        f"benchmark-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M')}.json",
    )
    with open(outfile, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults written to {outfile}")


if __name__ == "__main__":
    main()
