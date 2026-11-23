"""Duplicate Image Finder core package."""

import os
import sys

FROZEN = getattr(sys, "frozen", False)
# Bundled read-only resources (the ONNX model). In a PyInstaller build they live
# in the unpacked bundle; from source they are in the project folder.
RES_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Writable data (settings, cache, logs) lives next to the .exe / run.bat.
# The single-file release exe unpacks the app into data\app\ and sets DIF_HOME to
# its own folder, so the data stays beside the file the user actually launched.
# On Linux / macOS an installed app (AppImage, .deb/.rpm, .app) is read-only, so
# the packaged app keeps its data in the user's own folder instead.


def _user_data_dir():
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/DuplicateImageFinder")
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "DuplicateImageFinder")


_home = os.environ.get("DIF_HOME", "")
if _home and os.path.isdir(_home):
    APP_DIR = _home
elif FROZEN and sys.platform != "win32":
    APP_DIR = _user_data_dir()
else:
    APP_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(APP_DIR, "data")
LOG_DIR = os.path.join(APP_DIR, "logs")
CACHE_PATH = os.path.join(DATA_DIR, "cache.db")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

__version__ = "0.1.0"
PROJECT_URL = "https://github.com/benfy95/duplicate-image-finder"
