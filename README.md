# PiCamViewer

A minimal, efficient full-screen Raspberry Pi camera preview that is launchable at boot.

Tested on Raspberry Pi 3 Model B/B+ with the Camera Module V2 running
**Raspberry Pi OS Bullseye** (Desktop).  Compatible with any Pi camera module
and any Pi model.

---

## Table of Contents

1. [Files in this repository](#files-in-this-repository)
2. [Quick start](#quick-start)
3. [Step-by-step setup on a fresh Raspbian Desktop image](#step-by-step-setup)
   - [1 – Enable the camera](#1--enable-the-camera)
   - [2 – Install dependencies](#2--install-dependencies)
   - [3 – Install PiCamViewer](#3--install-picamviewer)
   - [4 – Test manual run](#4--test-manual-run)
   - [5a – X autostart (recommended for Desktop)](#5a--x-autostart-recommended-for-raspbian-desktop)
   - [5b – User-level systemd service](#5b--user-level-systemd-service)
   - [5c – System-level systemd service](#5c--system-level-systemd-service)
4. [CLI reference](#cli-reference)
5. [Checking logs and CPU usage](#checking-logs-and-cpu-usage)
6. [Fallback behaviour](#fallback-behaviour)
7. [Performance notes](#performance-notes)
8. [Troubleshooting](#troubleshooting)

---

## Files in this repository

| File | Purpose |
|------|---------|
| `main.py` | Python program – full-screen camera preview |
| `start_camera.sh` | Launcher script with recommended defaults |
| `camera-preview.service` | System-level (`/etc/systemd/system/`) service unit |
| `camera-preview-user.service` | User-level (`~/.config/systemd/user/`) service unit |
| `camera-preview.desktop` | X autostart entry for LXDE / Raspbian Desktop |

---

## Quick start

```bash
# Clone the repo
git clone https://github.com/epl692/PiCamViewer ~/PiCamViewer
cd ~/PiCamViewer

# Install dependencies (Bullseye / Bookworm)
sudo apt update && sudo apt install -y python3-picamera2 python3-pyqt5 libcamera-apps

# Run
python3 main.py --fullscreen
```

---

## Step-by-step setup

### 1 – Enable the camera

> **Bullseye / Bookworm** use the libcamera stack.  The camera is usually
> enabled by default; if not, run:

```bash
# Option A – non-interactive (scripting-friendly)
sudo raspi-config nonint do_camera 0

# Option B – interactive menu
sudo raspi-config
# Navigate: Interface Options → Camera → Enable → Finish → Reboot
```

After enabling, reboot:

```bash
sudo reboot
```

Verify the camera is detected:

```bash
libcamera-hello --list-cameras
```

You should see at least one camera listed (e.g., `imx219`).

---

### 2 – Install dependencies

#### Bullseye / Bookworm (libcamera / picamera2 stack) – recommended

```bash
sudo apt update
sudo apt install -y \
    python3-picamera2 \
    python3-pyqt5 \
    python3-pyqt5.qtopengl \
    libcamera-apps \
    libcamera-tools
```

#### Buster / older systems (legacy picamera) – fallback

```bash
sudo apt update
sudo apt install -y python3-picamera python3-rpi.gpio
```

> **Note:** `main.py` automatically detects which library is available and
> uses the appropriate one.  No manual configuration is required.

---

### 3 – Install PiCamViewer

```bash
# Clone to the home directory of your desktop user (default: pi)
git clone https://github.com/epl692/PiCamViewer ~/PiCamViewer

# Make the launcher executable
chmod +x ~/PiCamViewer/start_camera.sh
```

If you installed in a different directory, edit the `ExecStart` / `Exec`
paths in the service and desktop files before copying them.

---

### 4 – Test manual run

Open a terminal on the Raspbian Desktop and run:

```bash
python3 ~/PiCamViewer/main.py --fullscreen
```

A full-screen camera preview should appear within a few seconds.
Press **Ctrl-C** to stop.

You can also use the launcher:

```bash
~/PiCamViewer/start_camera.sh
```

Pass extra flags after the script name:

```bash
~/PiCamViewer/start_camera.sh --width 1280 --height 720 --framerate 60
```

---

### 5a – X autostart (recommended for Raspbian Desktop)

This is the **simplest and most reliable** method for Raspbian Desktop
because the preview is started by the LXDE session manager after X is
fully initialised.

```bash
mkdir -p ~/.config/autostart
cp ~/PiCamViewer/camera-preview.desktop ~/.config/autostart/

# Verify the file was copied correctly
cat ~/.config/autostart/camera-preview.desktop
```

The preview will start automatically at your **next login / reboot**.

To test without rebooting, run the launcher directly:

```bash
~/PiCamViewer/start_camera.sh
```

To **disable** autostart:

```bash
rm ~/.config/autostart/camera-preview.desktop
```

---

### 5b – User-level systemd service

Use this if you prefer systemd management within your user session.

```bash
mkdir -p ~/.config/systemd/user
cp ~/PiCamViewer/camera-preview-user.service \
   ~/.config/systemd/user/camera-preview.service

systemctl --user daemon-reload
systemctl --user enable --now camera-preview.service
```

Check the status:

```bash
systemctl --user status camera-preview.service
```

View logs:

```bash
journalctl --user -u camera-preview.service -b -f
```

For the user service to start automatically at boot **without** an
interactive login (e.g. with autologin enabled), enable lingering:

```bash
sudo loginctl enable-linger pi   # replace "pi" with your username
```

To **disable**:

```bash
systemctl --user disable --now camera-preview.service
```

---

### 5c – System-level systemd service

Use this for system-wide management (e.g. kiosk or non-interactive setups).

> **Important:** The service runs as the `pi` user.  Replace `pi` with your
> actual username if different, both in the service file and the paths below.

```bash
# Copy and edit the service file if needed
sudo cp ~/PiCamViewer/camera-preview.service /etc/systemd/system/

# If your username is not "pi", update the paths
sudo nano /etc/systemd/system/camera-preview.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now camera-preview.service
```

Check the status:

```bash
sudo systemctl status camera-preview.service
```

View logs:

```bash
journalctl -u camera-preview.service -b -f
```

To **disable**:

```bash
sudo systemctl disable --now camera-preview.service
```

#### Permissions (system service only)

The user running the preview must belong to the `video` group:

```bash
# Check current groups
groups pi

# Add to video group if needed
sudo usermod -aG video pi

# Log out and back in (or reboot) for the change to take effect
```

---

## CLI reference

```
usage: main.py [-h] [--width W] [--height H] [--framerate FPS]
               [--fullscreen | --no-fullscreen]
               [--rotation {0,90,180,270}]
               [--display DISPLAY]

optional arguments:
  --width W              Preview width  (default: 1920)
  --height H             Preview height (default: 1080)
  --framerate FPS        Camera framerate (default: 30)
  --fullscreen           Show preview full-screen (default)
  --no-fullscreen        Show preview in a window
  --rotation {0,90,180,270}
                         Camera rotation in degrees (default: 0)
  --display DISPLAY      X display to use, e.g. ':0'
```

Examples:

```bash
# 720 p at 60 fps, rotated 90°
python3 main.py --width 1280 --height 720 --framerate 60 --rotation 90

# Windowed mode for debugging
python3 main.py --no-fullscreen --width 640 --height 480

# Explicit display
python3 main.py --display :0
```

---

## Checking logs and CPU usage

### Logs

```bash
# System service
journalctl -u camera-preview.service -b -f

# User service
journalctl --user -u camera-preview.service -b -f

# All log entries since last boot
journalctl -u camera-preview.service -b
```

### CPU / memory usage

```bash
# Interactive (press q to quit)
htop

# One-shot snapshot
top -b -n 1 | grep -E 'python|picam'

# Detailed per-process stats
ps aux | grep main.py
```

On a Raspberry Pi 3 with the libcamera/picamera2 stack at 1080p/30fps you
should expect roughly **5–15 % CPU** for the preview process.  The GPU does
all the heavy lifting; Python is nearly idle during steady-state preview.

---

## Fallback behaviour

`main.py` tries the following in order:

1. **picamera2 / libcamera** (Bullseye / Bookworm) – hardware-accelerated
   EGL/Qt preview; Python never copies frame data.  _Preferred._
2. **legacy picamera** (Buster / older) – renders via GPU overlay; also
   zero-copy from Python's perspective.
3. If neither library is found, the program prints a helpful error message
   and exits with code `2`.

If no X display is available (e.g. the service starts before X), the program
exits with code `1` and a clear message.  See the service units for the
recommended `After=graphical.target` / `ExecStartPre` delay approach.

### raspivid / ffplay (alternative, no Python)

If you need a camera preview without Python at all, you can use the
command-line tools directly:

```bash
# libcamera (Bullseye+)
libcamera-hello --fullscreen -t 0

# legacy (Buster)
raspivid -t 0 -f
```

Trade-offs: no Python overhead; no clean systemd stop via SIGTERM without an
additional wrapper; harder to extend with application logic.

---

## Performance notes

| Stack | CPU (Pi 3, 1080p/30) | Memory | Notes |
|-------|----------------------|--------|-------|
| picamera2 + Qt/EGL | ~10 % | ~60 MB | Preferred; hardware path |
| legacy picamera | ~5 % | ~30 MB | GPU overlay; very low Python overhead |
| libcamera-hello (shell) | ~5 % | ~25 MB | No Python; hard to manage cleanly |

- **Fast startup**: preview is typically visible within 3–5 s of service start
  on a Pi 3 B (including the 3 s `ExecStartPre` delay in the system service).
- **No frame copying**: both picamera2 and legacy picamera render directly via
  the GPU; Python only sends configuration commands.
- To reduce startup time further, remove `ExecStartPre=/bin/sleep 3` from the
  system service if you are using the X autostart method instead (which
  already waits for X).

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `No DISPLAY environment variable` | Make sure X is running; add `--display :0` or use the X autostart method |
| `libcamera-hello` lists no cameras | Enable the camera in `raspi-config`; reboot; check ribbon cable |
| `ImportError: No module named 'picamera2'` | `sudo apt install python3-picamera2` |
| `ImportError: No module named 'picamera'` | `sudo apt install python3-picamera` |
| Preview starts but is black | Camera needs a moment to initialise; wait 2–3 s |
| Service fails immediately | Check logs: `journalctl -u camera-preview.service -b` |
| High CPU usage | Confirm picamera2/libcamera is in use (not a software-rendered fallback); use `journalctl` to see which backend was selected |
