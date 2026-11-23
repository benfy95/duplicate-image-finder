"""Build the single-file release exe (run by build.bat after PyInstaller).

    release\\DuplicateImageFinder.exe = launcher\\Launcher.cs (compiled) + zipped
                                       dist\\DuplicateImageFinder\\ + trailer

On first launch the exe unpacks itself to data\\app\\ next to it and starts the
app; later launches start it directly (see launcher\\Launcher.cs).
Only the Python standard library and the C# compiler that ships with Windows
(.NET Framework 4) are needed.
"""

import glob
import hashlib
import os
import re
import struct
import subprocess
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "dist", "DuplicateImageFinder")
OUT_DIR = os.path.join(ROOT, "release")
OUT = os.path.join(OUT_DIR, "DuplicateImageFinder.exe")
LAUNCHER_SRC = os.path.join(ROOT, "launcher", "Launcher.cs")
LAUNCHER_EXE = os.path.join(ROOT, "build", "launcher", "launcher.exe")
SKIP_TOP = {"data", "logs", "cli_output.txt"}     # created by test runs of the folder build
MAGIC = b"DIFPACK1"


def find_csc():
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for fw in ("Framework64", "Framework"):
        found = sorted(glob.glob(os.path.join(windir, "Microsoft.NET", fw, "v4.*", "csc.exe")))
        if found:
            return found[-1]
    raise SystemExit("[error] C# compiler (csc.exe, .NET Framework 4) not found")


def compile_launcher():
    os.makedirs(os.path.dirname(LAUNCHER_EXE), exist_ok=True)
    cmd = [find_csc(), "/nologo", "/optimize+", "/target:winexe", "/platform:anycpu",
           "/r:System.IO.Compression.dll", "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll",
           f"/win32icon:{os.path.join(ROOT, 'assets', 'icon.ico')}", f"/out:{LAUNCHER_EXE}", LAUNCHER_SRC]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        raise SystemExit("[error] launcher did not compile")


def version():
    with open(os.path.join(ROOT, "dif", "__init__.py"), encoding="utf-8") as f:
        m = re.search(r'__version__\s*=\s*"([^"]+)"', f.read())
    return m.group(1) if m else "0"


def app_files():
    for dirpath, dirnames, filenames in os.walk(APP):
        rel_dir = os.path.relpath(dirpath, APP)
        if rel_dir == ".":
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_TOP]
            filenames = [f for f in filenames if f.lower() not in SKIP_TOP]
        for name in filenames:
            full = os.path.join(dirpath, name)
            yield full, os.path.relpath(full, APP).replace(os.sep, "/")


def main():
    if not os.path.exists(os.path.join(APP, "DuplicateImageFinder.exe")):
        raise SystemExit(f"[error] {APP} is missing: run PyInstaller first")
    t0 = time.time()
    compile_launcher()
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = OUT + ".partial"
    files = list(app_files())
    total = sum(os.path.getsize(f) for f, _ in files)
    # The zip is written to its own file first so its internal offsets start at 0
    # (zipfile writing after the launcher bytes stores offsets from the exe start).
    zpath = os.path.join(os.path.dirname(LAUNCHER_EXE), "app.zip")
    done = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for i, (full, arc) in enumerate(files):
            z.write(full, arc)
            done += os.path.getsize(full)
            if i % 200 == 0 or done == total:
                print(f"\r[pack] compressing {done * 100 // max(1, total):3d}%", end="", flush=True)
    print()
    with open(tmp, "wb") as out:
        with open(LAUNCHER_EXE, "rb") as f:
            out.write(f.read())
        start = out.tell()
        with open(zpath, "rb") as f:
            for blk in iter(lambda: f.read(1 << 22), b""):
                out.write(blk)
        end = out.tell()
    os.remove(zpath)
    # build id = app version + hash of the packed app: a new build re-unpacks once
    h = hashlib.sha256()
    with open(tmp, "rb") as f:
        f.seek(start)
        for blk in iter(lambda: f.read(1 << 22), b""):
            h.update(blk)
    build_id = f"{version()}-{h.hexdigest()}"[:24].ljust(24).encode("ascii")
    with open(tmp, "ab") as out:
        out.write(struct.pack("<q", end - start) + build_id + MAGIC)
    os.replace(tmp, OUT)
    print(f"[pack] {OUT}  ({os.path.getsize(OUT) / 2**20:.0f} MB, {len(files)} files, "
          f"build {build_id.decode().strip()}, {time.time() - t0:.0f} s)")


if __name__ == "__main__":
    sys.exit(main())
