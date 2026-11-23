"""Smoke test for a build (used by the GitHub Actions release workflow).

    python tools/smoke_test.py                      # test the source (python main.py)
    python tools/smoke_test.py path/to/binary       # test a built app's executable

Generates a small set of images (an original, an exact copy, a resized JPEG, a
crop and an unrelated image), runs a headless scan with `--cli` and checks that
the copies are grouped and the unrelated image is not. Exits non-zero on failure.
"""

import ast
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def picture(seed, w=1200, h=800):
    """A textured, photo-like test image (enough detail for keypoints and the AI model)."""
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 256, (h // 20, w // 20, 3), dtype=np.uint8)
    im = Image.fromarray(base).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(3))
    d = ImageDraw.Draw(im)
    for _ in range(40):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        r = int(rng.integers(15, 90))
        color = tuple(int(c) for c in rng.integers(0, 256, 3))
        if rng.random() < .5:
            d.ellipse((x - r, y - r, x + r, y + r), fill=color, outline=(0, 0, 0), width=3)
        else:
            d.rectangle((x - r, y - r // 2, x + r, y + r // 2), fill=color, outline=(255, 255, 255), width=3)
    return im


def make_set(folder):
    a = picture(1)
    a.save(os.path.join(folder, "photo.png"))
    shutil.copy(os.path.join(folder, "photo.png"), os.path.join(folder, "photo - Copy.png"))      # exact
    a.resize((600, 400), Image.LANCZOS).save(os.path.join(folder, "photo_small.jpg"), quality=85)  # similar
    a.crop((150, 100, 1050, 700)).save(os.path.join(folder, "photo_crop.jpg"), quality=92)          # cropped
    picture(2).save(os.path.join(folder, "other.png"))                                              # unrelated


def run(binary, folder, home):
    env = dict(os.environ, DIF_HOME=home, QT_QPA_PLATFORM="offscreen")
    cmd = ([binary] if binary else [sys.executable, os.path.join(ROOT, "main.py")]) + \
          ["--cli", folder, "--cache", os.path.join(home, "cache.db")]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env=env)
    out = p.stdout
    log = os.path.join(home, "cli_output.txt")      # windowed Windows exe writes here instead
    if "stats:" not in out and os.path.exists(log):
        out = open(log, encoding="utf-8").read()
    print(out[-3000:])
    if p.returncode != 0:
        print(p.stderr[-3000:])
        raise SystemExit(f"[fail] exit code {p.returncode}")
    return out


def main():
    binary = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
    tmp = tempfile.mkdtemp(prefix="dif_smoke_")
    try:
        imgs = os.path.join(tmp, "images")
        os.makedirs(imgs)
        make_set(imgs)
        out = run(binary, imgs, tmp)
        line = next((ln for ln in out.splitlines() if ln.startswith("stats:")), None)
        if not line:
            raise SystemExit("[fail] no stats line in the output")
        stats = ast.literal_eval(line.split(":", 1)[1].strip())
        groups = [blk for blk in out.split("\nGroup ")[1:]]
        grouped = " ".join(groups)
        checks = {
            "scanned 5 files": stats.get("files") == 5,
            "no unreadable files": stats.get("errors") == 0,
            "exact copy found": "photo - Copy.png" in grouped,
            "resized copy found": "photo_small.jpg" in grouped,
            "unrelated image not grouped": "other.png" not in grouped,
        }
        for name, ok in checks.items():
            print(("[ ok ] " if ok else "[FAIL] ") + name)
        print("[info] crop found:", "photo_crop.jpg" in grouped)
        dev = next((ln for ln in out.splitlines() if ln.startswith("device:")), "device: ?")
        print("[info]", dev)
        if not all(checks.values()):
            raise SystemExit(1)
        print("[pass] smoke test")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
