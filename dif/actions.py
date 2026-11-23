"""Move / recycle / delete duplicates, with a CSV log of everything done."""

import csv
import os
import shutil
import time

from .loader import long_path

MOVE, RECYCLE, DELETE = "move", "recycle", "delete"


def root_for(path, roots):
    """The scan root that contains path (longest match)."""
    np_ = os.path.normcase(os.path.abspath(path))
    best = None
    for r in roots:
        rn = os.path.normcase(os.path.abspath(r))
        if np_.startswith(rn.rstrip("\\/") + os.sep) and (best is None or len(r) > len(best)):
            best = r
    return best


def unique_dest(dest):
    if not os.path.exists(long_path(dest)):
        return dest
    base, ext = os.path.splitext(dest)
    n = 1
    while os.path.exists(long_path(f"{base} ({n}){ext}")):
        n += 1
    return f"{base} ({n}){ext}"


def move_target(path, roots, dest_dir):
    """dest_dir/<root folder name>/<path relative to root> (keeps structure)."""
    root = root_for(path, roots)
    if root:
        rel = os.path.relpath(path, root)
        name = os.path.basename(root.rstrip("\\/")) or root[0]
        return os.path.join(dest_dir, name, rel)
    return os.path.join(dest_dir, os.path.basename(path))


def safe_move(src, dst):
    """Move without ever leaving two copies behind.

    Same drive: a plain rename, which either fully happens or not at all.
    Other drive: copy, then delete the original; if the original can't be
    deleted (e.g. open in another program) the copy is removed again."""
    try:
        os.rename(src, dst)
        return
    except OSError as e:
        cross_drive = getattr(e, "winerror", None) == 17 or e.errno == 18   # ERROR_NOT_SAME_DEVICE / EXDEV
        if not cross_drive:
            raise
    shutil.copy2(src, dst)
    try:
        os.remove(src)
    except OSError:
        try:
            os.remove(dst)
        except OSError:
            pass
        raise


def apply_one(path, mode, roots, dest_dir):
    """Returns (ok, destination_or_message)."""
    if not os.path.exists(long_path(path)):
        return False, "file no longer exists"
    try:
        if mode == MOVE:
            target = unique_dest(move_target(path, roots, dest_dir))
            os.makedirs(long_path(os.path.dirname(target)), exist_ok=True)
            safe_move(long_path(path), long_path(target))
            return True, target
        if mode == RECYCLE:
            from send2trash import send2trash
            send2trash(os.path.abspath(path))
            return True, "Recycle Bin"
        if mode == DELETE:
            os.remove(long_path(path))
            return True, "deleted"
        return False, f"unknown action {mode}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


class ActionLog:
    def __init__(self, log_dir):
        os.makedirs(log_dir, exist_ok=True)
        self.path = os.path.join(log_dir, time.strftime("actions_%Y%m%d.csv"))
        new = not os.path.exists(self.path)
        # utf-8-sig so Excel shows Chinese file names correctly
        self.f = open(self.path, "a", newline="", encoding="utf-8-sig")
        self.w = csv.writer(self.f)
        if new:
            self.w.writerow(["time", "action", "file", "result", "destination_or_error", "kept_file"])

    def write(self, action, path, ok, info, kept):
        self.w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), action, path,
                         "ok" if ok else "failed", info, kept])

    def close(self):
        self.f.close()
