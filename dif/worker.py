"""Functions executed in worker processes (no torch / Qt imports here)."""

import cv2
import numpy as np
from PIL import Image

from .loader import open_image

EMB_SIZE = 224          # input size of the feature model
ORB_SIDE = 1000         # images are downscaled to this for keypoint matching
MIN_INLIERS = 30


def init_worker():
    cv2.setNumThreads(1)


def phash(im):
    """64-bit DCT perceptual hash, returned as a signed int64 (SQLite friendly)."""
    g = np.asarray(im.convert("L").resize((32, 32), Image.LANCZOS), dtype=np.float32)
    d = cv2.dct(g)[:8, :8].flatten()
    bits = d > np.median(d)
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v - (1 << 64) if v >= (1 << 63) else v


def analyze_task(arg):
    """arg = (key, (path, need_thumb)) -> (key, result dict)."""
    key, (path, need_thumb) = arg
    try:
        im, (w, h), fmt = open_image(path, max_side=512)
        res = {"w": int(w), "h": int(h), "fmt": fmt, "phash": phash(im), "thumb": None, "error": None,
               # 8x8 color layout: pHash ignores color, this catches flat-image collisions
               "tiny": np.asarray(im.resize((8, 8), Image.BOX), dtype=np.uint8).tobytes()}
        if need_thumb:
            res["thumb"] = np.ascontiguousarray(
                np.asarray(im.resize((EMB_SIZE, EMB_SIZE), Image.BILINEAR), dtype=np.uint8))
        return key, res
    except Exception as e:  # any decoder problem is reported, never raised
        return key, {"error": f"{type(e).__name__}: {e}"[:300]}


def _gray(path):
    im, _, _ = open_image(path, max_side=ORB_SIDE)
    return np.asarray(im.convert("L"))


def _coverage(H, wa, ha, wb, hb):
    """Fraction of image B's area covered by image A projected through H."""
    corners = np.float32([[0, 0], [wa, 0], [wa, ha], [0, ha]]).reshape(-1, 1, 2)
    proj = cv2.perspectiveTransform(corners, H).reshape(-1, 2).astype(np.float32)
    if not cv2.isContourConvex(proj.reshape(-1, 1, 2)):
        return None
    rect = np.float32([[0, 0], [wb, 0], [wb, hb], [0, hb]])
    inter, _ = cv2.intersectConvexConvex(proj, rect)
    return float(inter) / float(wb * hb)


ORB_FEATURES = 3000
MIN_FEATURES = 15
RATIO = 0.75            # Lowe's ratio test for descriptor matches


def orb_features(path):
    """Keypoints of one image for the crop check: positions [n, 2] float32,
    ORB descriptors [n, 32] uint8 (None when there are none) and image shape."""
    g = _gray(path)
    kp, desc = cv2.ORB_create(nfeatures=ORB_FEATURES).detectAndCompute(g, None)
    pts = np.float32([k.pt for k in kp]).reshape(-1, 2)
    return {"pts": pts, "desc": desc, "shape": g.shape[:2]}


def enough_features(f):
    return f["desc"] is not None and len(f["pts"]) >= MIN_FEATURES


def match_cpu(desc_a, desc_b):
    """Brute-force Hamming matches A -> B passing the ratio test: (query idx, train idx).
    features.OrbMatcher gives the same result on the GPU."""
    matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(desc_a, desc_b, k=2)
    good = [m[0] for m in matches if len(m) == 2 and m[0].distance < RATIO * m[1].distance]
    return (np.array([m.queryIdx for m in good], np.int64),
            np.array([m.trainIdx for m in good], np.int64))


def geometry(src, dst, shape_a, shape_b):
    """Decide from matched keypoint positions (src in A, dst in B, [k, 2]) whether
    A and B show the same content (possibly cropped).

    Returns dict(ok, inliers, cover_ab, cover_ba) where cover_ab is the share of
    B's area that A covers, and cover_ba the share of A that B covers.
    """
    if len(src) < 15:
        return {"ok": False, "reason": "few matches"}
    src = np.float32(src).reshape(-1, 1, 2)
    dst = np.float32(dst).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None:
        return {"ok": False, "reason": "no homography"}
    inliers = int(mask.sum())
    if inliers < 15 or inliers / len(src) < 0.25:
        return {"ok": False, "reason": "few inliers"}
    # Reject strongly perspective / mirrored transforms: crops & resizes are near-similarity.
    if np.linalg.det(H[:2, :2]) <= 0 or abs(H[2, 0]) > 2e-3 or abs(H[2, 1]) > 2e-3:
        return {"ok": False, "reason": "bad transform"}
    ha_, wa_ = shape_a
    hb_, wb_ = shape_b
    try:
        cab = _coverage(H, wa_, ha_, wb_, hb_)
        cba = _coverage(np.linalg.inv(H), wb_, hb_, wa_, ha_)
    except Exception:
        return {"ok": False, "reason": "projection failed"}
    if cab is None or cba is None:
        return {"ok": False, "reason": "non-convex"}
    # Real crops/resizes: plenty of geometric inliers AND one image lies inside the other.
    # (Unrelated images that match by chance give ~15 inliers and partial overlap.)
    if inliers < MIN_INLIERS or max(cab, cba) < 0.9:
        return {"ok": False, "reason": "weak match", "inliers": inliers, "cover_ab": cab, "cover_ba": cba}
    return {"ok": True, "inliers": inliers, "cover_ab": cab, "cover_ba": cba}


def match_and_check(fa, fb):
    """Full check of two images' keypoints on the CPU (matching + geometry)."""
    if not enough_features(fa) or not enough_features(fb):
        return {"ok": False, "reason": "few features"}
    qi, ti = match_cpu(fa["desc"], fb["desc"])
    return geometry(fa["pts"][qi], fb["pts"][ti], fa["shape"], fb["shape"])


def verify_pair(path_a, path_b):
    """Keypoint check that A and B show the same content (possibly cropped)."""
    return match_and_check(orb_features(path_a), orb_features(path_b))


def verify_task(arg):
    """arg = (key, (path_a, path_b)) -> (key, result dict)."""
    key, (pa, pb) = arg
    try:
        return key, verify_pair(pa, pb)
    except Exception as e:
        return key, {"ok": False, "reason": f"{type(e).__name__}: {e}"[:200]}


def orb_task(arg):
    """arg = (key, path) -> (key, keypoints dict or {"error": message})."""
    key, path = arg
    try:
        return key, orb_features(path)
    except Exception as e:
        return key, {"error": f"{type(e).__name__}: {e}"[:200]}


def geometry_task(arg):
    """arg = (key, (src, dst, shape_a, shape_b)) -> (key, result dict)."""
    key, (src, dst, sa, sb) = arg
    try:
        return key, geometry(src, dst, sa, sb)
    except Exception as e:
        return key, {"ok": False, "reason": f"{type(e).__name__}: {e}"[:200]}


def match_check_task(arg):
    """arg = (key, (features_a, features_b)) -> (key, result dict)."""
    key, (fa, fb) = arg
    try:
        return key, match_and_check(fa, fb)
    except Exception as e:
        return key, {"ok": False, "reason": f"{type(e).__name__}: {e}"[:200]}
