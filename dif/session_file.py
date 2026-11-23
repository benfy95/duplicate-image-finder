"""Saved scans: a scan's groups and the user's KEEP / REMOVE ticks.

Two formats with the same content:
  * .xml      File > Export / Import scan: readable, one <File> line per image;
  * .difscan  File > Save / Load progress (internal): gzip-compressed JSON.
Both are self-contained: they do not depend on the cache, so they still load after
Settings > Clear cache or on another PC with the same folders. On load every file
is checked against the disk:
  * missing files are dropped (and groups left with one file);
  * files whose size or modified time changed are kept but unticked, since the
    comparison was made on the old content;
  * folders that no longer exist are reported.
"""

import gzip
import hashlib
import json
import os
import time
import xml.etree.ElementTree as ET

from . import __version__
from .engine import FileTable, Group, Member, ScanResult
from .loader import long_path

FORMAT = "duplicate-image-finder-scan"
VERSION = 1
EXT = ".difscan"          # internal progress files
XML_EXT = ".xml"          # exported scans
XML_ROOT = "DuplicateImageFinderScan"


class ScanFileError(Exception):
    """Not a saved scan, damaged, or from a newer version."""


def folders_key(folders):
    """Stable id for a folder selection [(path, include_subfolders)] (for Save/Load progress)."""
    norm = sorted((os.path.normcase(os.path.normpath(p)), bool(r)) for p, r in folders)
    return hashlib.sha1(json.dumps(norm).encode("utf-8")).hexdigest()[:16]


def progress_path(data_dir, folders):
    return os.path.join(data_dir, "progress", folders_key(folders) + EXT)


def save(path, result, groups, folders, options=None):
    """Write the current groups (with their ticks) to path, atomically."""
    ft = result.files
    used, files = {}, []
    out_groups = []
    for g in groups:
        rows = []
        for m in g.members:
            i = m.idx
            if i not in used:
                used[i] = len(files)
                files.append([ft.paths[i], int(ft.size[i]), int(ft.mtime[i]), int(ft.w[i]), int(ft.h[i]), ft.fmt[i]])
            rows.append([used[i], m.kind, round(float(m.score), 5), bool(m.remove), m.base_kind, m.reason])
        out_groups.append(rows)
    data = {
        "format": FORMAT, "version": VERSION, "app_version": __version__,
        "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
        "folders": [[p, bool(r)] for p, r in folders],
        "roots": list(result.roots),
        "device": result.device_label,
        "options": options or {},
        "stats": {k: v for k, v in result.stats.items() if isinstance(v, (int, float, str))},
        "files": files,
        "groups": out_groups,
    }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    if path.lower().endswith(XML_EXT):
        _to_xml(data).write(tmp, encoding="utf-8", xml_declaration=True)
    else:
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


# ---------------------------------------------------------------- XML
def _date(ns):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ns) / 1e9))
    except (OSError, OverflowError, ValueError):
        return ""


def _to_xml(data):
    """<DuplicateImageFinderScan> with <Folders>, <Options>, <Stats> and one
    <Group> per group holding a <File> element per image (path as its text)."""
    root = ET.Element(XML_ROOT, version=str(data["version"]), app=data["app_version"],
                      saved=data["saved"], device=data["device"])
    fo = ET.SubElement(root, "Folders")
    for p, r in data["folders"]:
        ET.SubElement(fo, "Folder", subfolders="yes" if r else "no").text = p
    ro = ET.SubElement(root, "Roots")
    for p in data["roots"]:
        ET.SubElement(ro, "Root").text = p
    for tag, items in (("Options", data["options"]), ("Stats", data["stats"])):
        el = ET.SubElement(root, tag)
        for k, v in items.items():
            ET.SubElement(el, "Value", name=str(k)).text = json.dumps(v, ensure_ascii=False)
    gs = ET.SubElement(root, "Groups", count=str(len(data["groups"])))
    files = data["files"]
    for n, rows in enumerate(data["groups"], 1):
        g = ET.SubElement(gs, "Group", number=str(n))
        for fi, kind, score, remove, base_kind, reason in rows:
            path, size, mtime, w, h, fmt = files[fi]
            a = {"action": "remove" if remove else "keep", "match": kind, "score": f"{score:.4f}",
                 "width": str(w), "height": str(h), "format": fmt, "bytes": str(size),
                 "modified": _date(mtime), "mtime_ns": str(mtime)}
            if base_kind and base_kind != kind:
                a["base_match"] = base_kind
            if reason:
                a["reason"] = reason
            ET.SubElement(g, "File", a).text = path
    ET.indent(root, space="  ")
    return ET.ElementTree(root)


def _from_xml(path):
    """Same dict as the JSON format, from an exported .xml scan."""
    root = ET.parse(path).getroot()
    if root.tag != XML_ROOT:
        raise ScanFileError("not a Duplicate Image Finder scan file")

    def values(tag):
        out = {}
        for v in root.findall(f"{tag}/Value"):
            try:
                out[v.get("name", "")] = json.loads(v.text or "null")
            except ValueError:
                out[v.get("name", "")] = v.text
        return out

    files, index, groups = [], {}, []
    for g in root.findall("Groups/Group"):
        rows = []
        for f in g.findall("File"):
            p = (f.text or "").strip()
            if not p:
                continue
            if p not in index:
                index[p] = len(files)
                files.append([p, int(f.get("bytes", 0)), int(f.get("mtime_ns", 0)), int(f.get("width", 0)),
                              int(f.get("height", 0)), f.get("format", "")])
            kind = f.get("match", "similar")
            rows.append([index[p], kind, float(f.get("score", 0)), f.get("action") == "remove",
                         f.get("base_match", kind), f.get("reason", "")])
        groups.append(rows)
    return {
        "format": FORMAT, "version": int(root.get("version", "1")), "app_version": root.get("app", "?"),
        "saved": root.get("saved", ""), "device": root.get("device", ""),
        "folders": [[(f.text or "").strip(), f.get("subfolders") == "yes"] for f in root.findall("Folders/Folder")],
        "roots": [(r.text or "").strip() for r in root.findall("Roots/Root")],
        "options": values("Options"), "stats": values("Stats"),
        "files": files, "groups": groups,
    }


def read(path):
    """Raw saved data (dict); raises ScanFileError if it is not a usable scan file."""
    try:
        with open(path, "rb") as f:
            head = f.read(2)
        if head == b"\x1f\x8b":                      # gzip: internal JSON format
            with gzip.open(path, "rt", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = _from_xml(path)
    except ScanFileError:
        raise
    except (OSError, EOFError, ValueError, ET.ParseError, TypeError) as e:
        raise ScanFileError(f"{type(e).__name__}: {e}")
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ScanFileError("not a Duplicate Image Finder scan file")
    if int(data.get("version", 0)) > VERSION:
        raise ScanFileError(f"saved by a newer version ({data.get('app_version', '?')})")
    for key in ("folders", "files", "groups"):
        if not isinstance(data.get(key), list):
            raise ScanFileError(f"damaged file (no {key})")
    return data


def build(data):
    """(ScanResult, report) from read() data, checked against the disk.

    report: missing_folders [paths], missing_files int, changed_files int,
            dropped_groups int, saved (time text)"""
    files = data["files"]
    state = []                       # per file: "ok" | "missing" | "changed"
    for rec in files:
        p, size, mtime = rec[0], int(rec[1]), int(rec[2])
        try:
            st = os.stat(long_path(p))
            state.append("ok" if (st.st_size == size and st.st_mtime_ns == mtime) else "changed")
        except OSError:
            state.append("missing")

    keep = [k for k, s in enumerate(state) if s != "missing"]
    new_idx = {k: n for n, k in enumerate(keep)}
    ft = FileTable([files[k][0] for k in keep], [int(files[k][1]) for k in keep], [int(files[k][2]) for k in keep])
    for n, k in enumerate(keep):
        ft.w[n], ft.h[n], ft.fmt[n] = int(files[k][3]), int(files[k][4]), str(files[k][5])
    ft.valid[:] = True

    groups, dropped = [], 0
    for rows in data["groups"]:
        members = []
        for fi, kind, score, remove, base_kind, reason in rows:
            if state[fi] == "missing":
                continue
            # changed since the scan: the match may no longer hold, never delete it blindly
            members.append(Member(new_idx[fi], kind, float(score), bool(remove) and state[fi] == "ok",
                                  base_kind or "", reason or ""))
        if len(members) >= 2:
            groups.append(Group(members))
        else:
            dropped += 1

    stats = dict(data.get("stats", {}))
    stats["groups"] = len(groups)
    stats["duplicates"] = sum(1 for g in groups for m in g.members if m.remove)
    result = ScanResult(ft, groups, list(data.get("roots", [])), str(data.get("device", "")), stats, [])
    report = {
        "missing_folders": [p for p, _ in data["folders"] if not os.path.isdir(long_path(p))],
        "missing_files": state.count("missing"),
        "changed_files": state.count("changed"),
        "dropped_groups": dropped,
        "saved": str(data.get("saved", "")),
    }
    return result, report
