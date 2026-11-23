"""Supported file types, content sniffing and format quality ranking."""

import os

# Always available through Pillow.
PILLOW_EXTS = {
    ".jpg", ".jpeg", ".jpe", ".jfif",          # JPEG
    ".png", ".apng",                          # PNG
    ".webp",                                  # WebP
    ".gif", ".bmp", ".dib", ".tif", ".tiff", ".ico",
    ".avif",
    ".jp2", ".j2k", ".jpx",                   # JPEG 2000
    ".tga", ".ppm", ".pgm", ".pbm", ".pnm", ".pcx", ".dds", ".psd",
}
HEIF_EXTS = {".heic", ".heif"}
JXL_EXTS = {".jxl"}
RAW_EXTS = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".raf"}

# Format "quality" rank used as a tie-breaker after resolution:
# 2 = lossless / original, 1 = modern codec (may be lossy), 0 = lossy / palette.
_FORMAT_RANK = {
    "PNG": 2, "TIFF": 2, "BMP": 2, "DIB": 2, "PSD": 2, "RAW": 2, "TGA": 2, "PPM": 2,
    "WEBP": 1, "AVIF": 1, "HEIF": 1, "JXL": 1, "JPEG2000": 1,
    "JPEG": 0, "MPO": 0, "GIF": 0, "ICO": 0, "PCX": 0, "DDS": 0,
}


def format_rank(fmt):
    return _FORMAT_RANK.get((fmt or "").upper(), 0)


def available_exts():
    """Extensions whose decoder is actually installed."""
    from . import loader
    exts = set(PILLOW_EXTS)
    if loader.HAS_HEIF:
        exts |= HEIF_EXTS
    if loader.HAS_JXL:
        exts |= JXL_EXTS
    if loader.HAS_RAW:
        exts |= RAW_EXTS
    return exts


def ext_of(path):
    return os.path.splitext(path)[1].lower()


def sniff(path):
    """True if the file content looks like an image, regardless of extension."""
    try:
        with open(path, "rb") as f:
            h = f.read(32)
    except OSError:
        return False
    if len(h) < 12:
        return False
    if h[:3] == b"\xff\xd8\xff":                      # JPEG
        return True
    if h[:8] == b"\x89PNG\r\n\x1a\n":                 # PNG
        return True
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return True
    if h[:4] in (b"II*\x00", b"MM\x00*"):              # TIFF (and many RAWs)
        return True
    if h[:2] == b"BM" and len(h) >= 18 and h[14] in (12, 40, 52, 56, 64, 108, 124):
        return True
    if h[4:8] == b"ftyp" and h[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"avif", b"avis", b"hevc"):
        return True
    if h[:2] == b"\xff\x0a" or h[:12] == b"\x00\x00\x00\x0cJXL \r\n\x87\n":
        return True
    if h[:12] == b"\x00\x00\x00\x0cjP  \r\n\x87\n":   # JPEG 2000
        return True
    if h[:4] == b"8BPS" or h[:4] == b"DDS ":
        return True
    return False


def describe_supported():
    """Human-readable list (used in the About box)."""
    return sorted(available_exts())
