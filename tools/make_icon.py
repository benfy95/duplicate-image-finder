"""Draws the app icon (two overlapping photos = a duplicate) -> assets/icon.ico, icon.png, icon_512.png, icon.icns.

    python tools/make_icon.py
"""

import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")
S = 1024  # drawn large, downscaled for crisp small sizes


def card(draw, x0, y0, x1, y1, frame, sky, hill1, hill2, sun, shadow=True):
    r = int(S * 0.06)
    if shadow:
        off = int(S * 0.018)
        draw.rounded_rectangle((x0 + off, y0 + off, x1 + off, y1 + off), r, fill=(0, 0, 0, 70))
    draw.rounded_rectangle((x0, y0, x1, y1), r, fill=frame)
    pad = int(S * 0.045)
    ix0, iy0, ix1, iy1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad
    w, h = ix1 - ix0, iy1 - iy0
    pic = Image.new("RGBA", (w, h), sky)
    d = ImageDraw.Draw(pic)
    d.ellipse((w * 0.62, h * 0.14, w * 0.84, h * 0.36), fill=sun)                      # sun
    d.polygon([(0, h), (w * 0.34, h * 0.42), (w * 0.62, h)], fill=hill1)               # back hill
    d.polygon([(w * 0.30, h), (w * 0.66, h * 0.52), (w, h * 0.80), (w, h)], fill=hill2)  # front hill
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), int(r * 0.6), fill=255)
    return pic, mask, (ix0, iy0)


def main():
    os.makedirs(OUT, exist_ok=True)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    # back photo (the copy): muted
    p, m, pos = card(draw, int(S * .06), int(S * .08), int(S * .70), int(S * .66),
                     (236, 240, 247), (150, 178, 214), (96, 128, 170), (120, 150, 190), (236, 224, 170))
    img.paste(p, pos, m)
    # front photo (the original): vivid
    p, m, pos = card(draw, int(S * .30), int(S * .32), int(S * .94), int(S * .90),
                     (255, 255, 255), (98, 170, 245), (46, 125, 90), (70, 168, 104), (255, 206, 64))
    img.paste(p, pos, m)
    # small "=" badge: these two are the same picture
    bx0, by0, bx1, by1 = int(S * .70), int(S * .06), int(S * .96), int(S * .32)
    draw.ellipse((bx0, by0, bx1, by1), fill=(207, 34, 46))
    cx, cy, bw, bh = (bx0 + bx1) / 2, (by0 + by1) / 2, (bx1 - bx0) * .46, (by1 - by0) * .085
    for dy in (-bh * 1.6, bh * 1.6):
        draw.rounded_rectangle((cx - bw / 2, cy + dy - bh, cx + bw / 2, cy + dy + bh), bh, fill="white")

    img.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "icon.png"))
    img.save(os.path.join(OUT, "icon.ico"), sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
                                                     (48, 48), (64, 64), (128, 128), (256, 256)])
    # macOS (.app / .dmg) and Linux (.desktop, AppImage) icons
    img.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, "icon.icns"),
                                                sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512)])
    img.resize((512, 512), Image.LANCZOS).save(os.path.join(OUT, "icon_512.png"))
    print("saved", os.path.join(OUT, "icon.ico"), "+ icon.png, icon_512.png, icon.icns")


if __name__ == "__main__":
    main()
