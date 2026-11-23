"""Headless scan for testing:  python -m dif.cli <folder> [--no-crop] [--cpu] [--cache PATH]"""

import argparse
import multiprocessing as mp
import os
import sys

from . import CACHE_PATH
from .engine import ScanEngine, ScanOptions
from .i18n import human_size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--no-crop", action="store_true")
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--sniff", action="store_true")
    ap.add_argument("--cache", default=CACHE_PATH)
    ap.add_argument("--phash-dist", type=int, default=7)
    ap.add_argument("--crop-sim", type=float, default=0.80)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    last = [None]

    def prog(stage, done, total):
        if stage != last[0]:
            print()
            last[0] = stage
        print(f"\r  {stage:10s} {done}/{total}", end="", flush=True)

    opts = ScanOptions(folders=a.folders, detect_crops=not a.no_crop, sniff=a.sniff,
                       device="cpu" if a.cpu else "auto", phash_dist=a.phash_dist, crop_sim=a.crop_sim)
    eng = ScanEngine(opts, a.cache, progress=prog, log=lambda m: print("\n[log]", m))
    res = eng.run()
    ft = res.files
    print("\n")
    print("device:", res.device_label)
    print("stats:", res.stats)
    if not a.quiet:
        for gi, g in enumerate(res.groups, 1):
            print(f"\nGroup {gi}")
            for m in g.members:
                i = m.idx
                print(f"  {'KEEP  ' if not m.remove else 'REMOVE'} {m.kind:8s} {m.score:5.3f}  "
                      f"{ft.w[i]}x{ft.h[i]} {human_size(ft.size[i]):>9s} {ft.fmt[i]:5s} {os.path.basename(ft.paths[i])}")
        errs = [(p, e) for p, e in zip(ft.paths, ft.error) if e]
        if errs:
            print("\nErrors:")
            for p, e in errs[:20]:
                print(" ", p, "->", e)
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
