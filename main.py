#!/usr/bin/env python3
"""
PiCamViewer – full-screen Raspberry Pi camera preview.

Supports:
  • picamera2 / libcamera  (preferred, hardware-accelerated)
  • legacy picamera         (Pi OS Buster / older systems)

Usage:
  python3 main.py [--width W] [--height H] [--framerate FPS]
                  [--fullscreen] [--no-fullscreen]
                  [--rotation {0,90,180,270}]
                  [--display :0]
"""

import argparse
import logging
import os
import signal
import sys

# ---------------------------------------------------------------------------
# Logging – goes to stdout/stderr so journalctl captures everything.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("picamviewer")

# ---------------------------------------------------------------------------
# Graceful shutdown flag shared by the signal handler and the main loop.
# ---------------------------------------------------------------------------
_running = True


def _handle_signal(signum, frame):  # noqa: ARG001
    """Handle SIGINT/SIGTERM: signal the main loop to exit."""
    global _running
    sig_name = signal.Signals(signum).name
    log.info("Received %s – shutting down …", sig_name)
    _running = False


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Show a Raspberry Pi camera preview full-screen."
    )
    parser.add_argument(
        "--width", type=int, default=1920,
        help="Preview width  (default: 1920)"
    )
    parser.add_argument(
        "--height", type=int, default=1080,
        help="Preview height (default: 1080)"
    )
    parser.add_argument(
        "--framerate", type=int, default=30,
        help="Camera framerate (default: 30)"
    )
    fs_group = parser.add_mutually_exclusive_group()
    fs_group.add_argument(
        "--fullscreen", dest="fullscreen", action="store_true", default=True,
        help="Show preview full-screen (default)"
    )
    fs_group.add_argument(
        "--no-fullscreen", dest="fullscreen", action="store_false",
        help="Show preview in a window"
    )
    parser.add_argument(
        "--rotation", type=int, choices=[0, 90, 180, 270], default=0,
        help="Camera rotation in degrees (default: 0)"
    )
    parser.add_argument(
        "--display", type=str, default=None,
        help="X display to use, e.g. ':0' (default: inherit DISPLAY env var)"
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Display / environment checks
# ---------------------------------------------------------------------------
def check_display(display_arg):
    """
    Verify that a display is available.  Sets the DISPLAY env var when
    --display is given explicitly.  Exits with a helpful message if no
    display is found.
    """
    if display_arg:
        os.environ["DISPLAY"] = display_arg

    display = os.environ.get("DISPLAY", "")
    if not display:
        log.error(
            "No DISPLAY environment variable found.  "
            "Run under X11 or pass --display :0 .  "
            "For headless (no-X) setups see the README for the DRM/KMS approach."
        )
        sys.exit(1)

    log.info("Using display: %s", display)


# ---------------------------------------------------------------------------
# picamera2 / libcamera preview (preferred)
# ---------------------------------------------------------------------------
def run_picamera2(args):
    """
    Run a preview using picamera2 (libcamera stack).

    picamera2 uses a Qt/EGL preview window that the library manages
    internally – Python never copies raw frame data.
    """
    from picamera2 import Picamera2  # type: ignore[import]

    log.info("Starting picamera2 preview (%dx%d @ %d fps) …",
             args.width, args.height, args.framerate)

    cam = Picamera2()

    # Build a preview configuration; keep memory usage low with 2 buffers
    # (sufficient for display; reduces queue depth and latency).
    config = cam.create_preview_configuration(
        main={"size": (args.width, args.height)},
        buffer_count=2,
        controls={"FrameDurationLimits": (
            int(1e6 // args.framerate),
            int(1e6 // args.framerate),
        )},
    )
    cam.configure(config)

    # Apply rotation via the transform parameter if non-zero.
    # Transforms follow the libcamera convention:
    #   90°  clockwise = transpose + hflip
    #   180°            = hflip + vflip
    #   270° clockwise  = transpose + vflip
    if args.rotation:
        from libcamera import Transform  # type: ignore[import]
        _transforms = {
            90:  Transform(hflip=True,  vflip=False, transpose=True),
            180: Transform(hflip=True,  vflip=True),
            270: Transform(hflip=False, vflip=True,  transpose=True),
        }
        cam.set_controls({"Transform": _transforms[args.rotation]})

    from PyQt5.QtWidgets import QApplication  # type: ignore[import]
    from PyQt5.QtCore import Qt  # type: ignore[import]

    app = QApplication.instance() or QApplication(sys.argv)

    # Probe whether OpenGL is usable before creating QGlPicamera2.
    # QOpenGLWidget silently shows a blank window when the OpenGL context
    # cannot be established (no exception is raised), so we test first.
    def _opengl_available():
        try:
            from PyQt5.QtGui import QOffscreenSurface, QOpenGLContext  # type: ignore[import]
            surface = QOffscreenSurface()
            surface.create()
            ctx = QOpenGLContext()
            if not ctx.create():
                return False
            try:
                return ctx.makeCurrent(surface)
            finally:
                ctx.doneCurrent()
                surface.destroy()
        except (ImportError, RuntimeError):
            return False

    # Prefer QGlPicamera2 (OpenGL/GPU, lower CPU usage) when OpenGL works.
    # Fall back to QPicamera2 (software Qt raster renderer) otherwise.
    _widget_kwargs = dict(width=args.width, height=args.height, keep_ar=True)
    _use_gl = _opengl_available()
    if _use_gl:
        try:
            from picamera2.previews.qt import QGlPicamera2  # type: ignore[import]
            preview_widget = QGlPicamera2(cam, **_widget_kwargs)
            log.info("Using QGlPicamera2 (OpenGL/GPU renderer).")
        except (ImportError, RuntimeError) as exc:
            log.warning("QGlPicamera2 init failed (%s) – falling back to QPicamera2 (software renderer).", exc)
            _use_gl = False

    if not _use_gl:
        from picamera2.previews.qt import QPicamera2  # type: ignore[import]
        preview_widget = QPicamera2(cam, **_widget_kwargs)
        log.info("Using QPicamera2 (software renderer).")

    if args.fullscreen:
        preview_widget.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        preview_widget.showFullScreen()
    else:
        preview_widget.setWindowTitle("PiCamViewer")
        preview_widget.show()

    cam.start()
    log.info("picamera2 preview running.  Press Ctrl-C to stop.")

    # Drive the Qt event loop, checking our shutdown flag periodically.
    from PyQt5.QtCore import QTimer  # type: ignore[import]

    def _check_shutdown():
        if not _running:
            log.info("Stopping picamera2 …")
            cam.stop()
            cam.close()
            app.quit()

    timer = QTimer()
    timer.timeout.connect(_check_shutdown)
    timer.start(500)  # check every 500 ms

    app.exec_()
    log.info("picamera2 preview stopped.")


# ---------------------------------------------------------------------------
# legacy picamera preview (fallback for Pi OS Buster and older)
# ---------------------------------------------------------------------------
def run_picamera_legacy(args):
    """
    Run a preview using the legacy picamera library.

    picamera renders directly to the GPU overlay so Python never touches
    raw pixel data.
    """
    import picamera  # type: ignore[import]

    log.info("Starting legacy picamera preview (%dx%d @ %d fps) …",
             args.width, args.height, args.framerate)

    with picamera.PiCamera() as cam:
        cam.resolution = (args.width, args.height)
        cam.framerate = args.framerate
        if args.rotation:
            cam.rotation = args.rotation

        # fullscreen=True fills the primary display; window is ignored then.
        cam.start_preview(fullscreen=args.fullscreen,
                          window=(0, 0, args.width, args.height))
        log.info("Legacy picamera preview running.  Press Ctrl-C to stop.")

        # Block until a signal is received.
        import time
        while _running:
            time.sleep(0.1)

        log.info("Stopping legacy picamera …")
        cam.stop_preview()

    log.info("Legacy picamera preview stopped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    args = parse_args()

    log.info("PiCamViewer starting (width=%d height=%d framerate=%d "
             "fullscreen=%s rotation=%d) …",
             args.width, args.height, args.framerate,
             args.fullscreen, args.rotation)

    check_display(args.display)

    # Try picamera2 first (libcamera stack, preferred on Bullseye+).
    try:
        import picamera2  # noqa: F401
        log.info("picamera2 detected – using libcamera stack.")
        run_picamera2(args)
        return
    except ImportError:
        log.info("picamera2 not found – trying legacy picamera …")

    # Fall back to legacy picamera (Pi OS Buster and older).
    try:
        import picamera  # noqa: F401
        log.info("legacy picamera detected.")
        run_picamera_legacy(args)
        return
    except ImportError:
        pass

    log.error(
        "Neither picamera2 nor legacy picamera is installed.\n"
        "Install one of:\n"
        "  sudo apt install -y python3-picamera2      # Bullseye/Bookworm\n"
        "  sudo apt install -y python3-picamera       # Buster (legacy)\n"
        "See README.md for full instructions."
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
