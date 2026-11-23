"""Robust image loading for every supported format.

open_image() always returns an RGB PIL image with EXIF orientation applied,
plus the original pixel size (after orientation) and a format name.
"""

import io
import os

import numpy as np
from PIL import Image, ImageFile, ImageOps

from .formats import RAW_EXTS, ext_of

# Tolerate slightly truncated files instead of failing outright.
ImageFile.LOAD_TRUNCATED_IMAGES = True
# Allow big scans/maps but still stop decompression bombs.
Image.MAX_IMAGE_PIXELS = 250_000_000

# HEIC / HEIF: pi-heif is the decode-only build of pillow-heif (no GPL x265
# encoder); pillow-heif is still accepted when running from source.
HAS_HEIF = False
for _mod in ("pi_heif", "pillow_heif"):
    try:
        __import__(_mod).register_heif_opener()
        HAS_HEIF = True
        break
    except Exception:
        pass

# JPEG XL: pillow-jxl-plugin is GPL-3.0, so it is only used when running from
# source (if installed) and is never bundled into the MIT-licensed exe.
try:
    import pillow_jxl  # noqa: F401  (registers the JXL plugin on import)
    HAS_JXL = True
except Exception:
    HAS_JXL = False

try:
    import rawpy
    HAS_RAW = True
except Exception:
    rawpy = None
    HAS_RAW = False


def long_path(p):
    """Add the Windows long-path prefix when a path is near the 260-char limit."""
    if os.name == "nt" and len(p) >= 240 and not p.startswith("\\\\?\\"):
        p = os.path.abspath(p)
        if p.startswith("\\\\"):
            return "\\\\?\\UNC\\" + p[2:]
        return "\\\\?\\" + p
    return p


def _to_rgb(im):
    if im.mode in ("I;16", "I;16B", "I;16L", "I;16N", "I", "F"):
        a = np.asarray(im, dtype=np.float32)
        mx = float(a.max()) if a.size else 1.0
        if mx > 255:
            a = a * (255.0 / mx)
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L")
    if im.mode in ("RGBA", "LA", "PA", "RGBa", "La") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    if im.mode != "RGB":
        im = im.convert("RGB")
    return im


def _open_raw(path, max_side):
    with rawpy.imread(path) as raw:
        w, h = raw.sizes.width, raw.sizes.height
        if raw.sizes.flip in (5, 6):
            w, h = h, w
        im = None
        try:
            thumb = raw.extract_thumb()
            if thumb.format == rawpy.ThumbFormat.JPEG:
                im = Image.open(io.BytesIO(thumb.data))
                im.load()
                im = ImageOps.exif_transpose(im) or im
            elif thumb.format == rawpy.ThumbFormat.BITMAP:
                im = Image.fromarray(thumb.data)
        except Exception:
            im = None
        # Use the full decode when there is no preview or it is tiny.
        if im is None or (max_side and max(im.size) < min(max_side, 256)) or (not max_side and max(im.size) < max(w, h) // 2):
            rgb = raw.postprocess(half_size=bool(max_side), use_camera_wb=True, no_auto_bright=False)
            im = Image.fromarray(rgb)
    return im, (w, h), "RAW"


def open_image(path, max_side=None):
    """Return (rgb_image, (orig_w, orig_h), format_name).

    max_side: if given, the returned image is downscaled so its longest side
    is at most max_side (JPEGs are decoded at reduced size, which is much faster).
    """
    p = long_path(path)
    if ext_of(path) in RAW_EXTS and HAS_RAW:
        im, size, fmt = _open_raw(p, max_side)
        im = _to_rgb(im)
    else:
        # Read the whole file and close it at once: Pillow can otherwise keep the
        # handle open (e.g. PNG/APNG), which blocks moving/deleting the file.
        with open(p, "rb") as fh:
            data = fh.read()
        im = Image.open(io.BytesIO(data))
        fmt = (im.format or ext_of(path).lstrip(".")).upper()
        if getattr(im, "n_frames", 1) > 1:
            im.seek(0)
        w, h = im.size
        orientation = 1
        try:
            orientation = im.getexif().get(0x0112, 1) or 1
        except Exception:
            pass
        if orientation in (5, 6, 7, 8):
            w, h = h, w
        size = (w, h)
        if max_side and fmt in ("JPEG", "MPO"):
            try:
                im.draft("RGB", (max_side, max_side))
            except Exception:
                pass
        im.load()
        try:
            im = ImageOps.exif_transpose(im) or im
        except Exception:
            pass
        im = _to_rgb(im)
    if max_side and max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.BILINEAR, reducing_gap=2.0)
    return im, size, fmt
