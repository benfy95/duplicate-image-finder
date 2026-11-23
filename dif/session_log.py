"""Optional, per-session diagnostic log (File > Enable logging).

Off by default. When switched on, a new file logs/session_YYYYMMDD_HHMMSS.log is
created for this session only, so logs never grow without limit; only the
newest KEEP files are kept.
"""

import glob
import os
import platform
import sys
import time

KEEP = 20


class SessionLog:
    def __init__(self, log_dir):
        self.log_dir = log_dir
        self.path = None
        self.f = None

    @property
    def enabled(self):
        return self.f is not None

    def start(self, header_lines=()):
        if self.f:
            return self.path
        os.makedirs(self.log_dir, exist_ok=True)
        if self.path is None:                       # one file per session; re-enabling appends
            self.path = os.path.join(self.log_dir, time.strftime("session_%Y%m%d_%H%M%S.log"))
            self._prune()
        self.f = open(self.path, "a", encoding="utf-8", buffering=1)
        self.write("=" * 70)
        self.write("Logging enabled")
        self.write(f"Python {sys.version.split()[0]} · {platform.platform()}")
        for line in header_lines:
            self.write(line)
        return self.path

    def stop(self):
        if self.f:
            self.write("Logging disabled")
            self.f.close()
            self.f = None

    def write(self, msg):
        if self.f:
            stamp = time.strftime("%H:%M:%S")
            for line in str(msg).splitlines() or [""]:
                self.f.write(f"{stamp}  {line}\n")

    def _prune(self):
        files = sorted(glob.glob(os.path.join(self.log_dir, "session_*.log")))
        for old in files[:max(0, len(files) - (KEEP - 1))]:
            try:
                os.remove(old)
            except OSError:
                pass
