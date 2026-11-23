"""Device selection, deep image features and nearest-neighbour search.

Backends, best first:
  * "cuda": NVIDIA GPU through PyTorch (only when a CUDA build of torch is
    installed, see dif/cuda.py); also moves the keypoint pre-check to the GPU;
  * "dml":  any DirectX 12 GPU through ONNX Runtime + DirectML (the packaged exe);
  * "cpu":  ONNX Runtime / NumPy on the CPU.
"""

import functools
import os
import subprocess
import sys

import numpy as np

from . import RES_DIR

MODEL_NAME = "vit_small_patch14_dinov2.lvd142m"
MODEL_ID = MODEL_NAME + "@224"          # cache key for stored embeddings
EMB_DIM = 384                           # feature size of DINOv2-small
MODEL_PATH = os.path.join(RES_DIR, "models", "dinov2_vits14_224.onnx")            # CPU
MODEL_PATH_FP16 = os.path.join(RES_DIR, "models", "dinov2_vits14_224_fp16.onnx")  # GPU (~2x faster)

try:
    import onnxruntime as ort
    ort.set_default_logger_severity(3)
    HAS_ORT = True
except Exception:
    ort = None
    HAS_ORT = False


def _gpu_names():
    """All display adapters, best effort (Windows / macOS / Linux)."""
    if sys.platform == "win32":
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join '|'"],
            capture_output=True, text=True, timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return [n.strip() for n in out.split("|") if n.strip() and "Basic" not in n]
    if sys.platform == "darwin":
        out = subprocess.run(["system_profiler", "SPDisplaysDataType"], capture_output=True, text=True,
                             timeout=8).stdout
        return [ln.split(":", 1)[1].strip() for ln in out.splitlines() if "Chipset Model:" in ln]
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=8).stdout
        names = [n.strip() for n in out.splitlines() if n.strip()]
        if names:
            return names
    except OSError:
        pass
    out = subprocess.run(["lspci"], capture_output=True, text=True, timeout=8).stdout
    return [ln.split(":", 2)[-1].strip() for ln in out.splitlines() if " VGA " in ln or "3D controller" in ln]


@functools.lru_cache(maxsize=1)
def gpu_name():
    """Display name of the primary GPU (best effort, cached)."""
    try:
        names = _gpu_names()
        # prefer a discrete GPU when several are listed
        for key in ("NVIDIA", "AMD", "Radeon", "Arc"):
            for n in names:
                if key in n:
                    return n
        return names[0] if names else "GPU"
    except Exception:
        return "GPU"


def has_dml():
    return HAS_ORT and "DmlExecutionProvider" in ort.get_available_providers()


def has_coreml():
    """Apple GPU / Neural Engine through ONNX Runtime's CoreML provider (macOS)."""
    return sys.platform == "darwin" and HAS_ORT and "CoreMLExecutionProvider" in ort.get_available_providers()


def pick_device(pref="auto"):
    """Return (device, label); device is 'cuda', 'dml' or 'cpu'.
    'auto' prefers CUDA (if PyTorch with CUDA is installed), then DirectML."""
    from . import cuda
    if pref in ("auto", "cuda") and cuda.installed():
        return "cuda", f"GPU: {gpu_name()} (CUDA)"
    if pref in ("auto", "cuda", "dml") and has_dml():
        return "dml", f"GPU: {gpu_name()} (DirectML)"
    if pref in ("auto", "coreml") and has_coreml():
        return "coreml", f"GPU: {gpu_name()} (Core ML)"
    return "cpu", "CPU"


def is_gpu(device):
    """Devices that also run keypoint matching / large searches on the GPU.
    (Core ML runs the AI model only; the rest uses the CPU on a Mac.)"""
    return device in ("cuda", "dml")


def make_embedder(device):
    """Feature model for the device. CUDA that cannot start falls back to
    DirectML, then CPU; check the returned object's .device."""
    if device == "cuda":
        from . import cuda
        try:
            return cuda.TorchEmbedder(MODEL_NAME)
        except Exception:
            device = "dml" if has_dml() else "cpu"
    if device == "coreml":
        try:
            return Embedder("coreml")
        except Exception:          # Core ML could not compile the model: CPU
            device = "cpu"
    return Embedder(device)


class Embedder:
    """DINOv2 features; robust to resizing, recompression and moderate cropping."""

    def __init__(self, device):
        if not HAS_ORT:
            raise RuntimeError("onnxruntime is not installed")
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"model file missing: {MODEL_PATH}")
        self.device = device
        self.sess = self._session(device)
        want = {"dml": "DmlExecutionProvider", "coreml": "CoreMLExecutionProvider"}.get(device)
        if want and self.sess.get_providers()[0] != want:
            self.device = "cpu"
        self.dim = int(self.sess.get_outputs()[0].shape[1])
        self.input = self.sess.get_inputs()[0].name
        self.fell_back = None

    @staticmethod
    def _session(device):
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        if device == "dml":
            so.enable_mem_pattern = False            # required by DirectML
            so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
        elif device == "coreml":
            providers = [("CoreMLExecutionProvider", {"MLComputeUnits": "ALL"}), "CPUExecutionProvider"]
        else:
            providers = ["CPUExecutionProvider"]
        path = MODEL_PATH_FP16 if device == "dml" and os.path.exists(MODEL_PATH_FP16) else MODEL_PATH
        return ort.InferenceSession(path, so, providers=providers)

    @property
    def label(self):
        if self.device == "dml":
            return f"GPU: {gpu_name()} (DirectML)"
        if self.device == "coreml":
            return f"GPU: {gpu_name()} (Core ML)"
        return "CPU"

    def embed(self, batch):
        """batch: uint8 [B,224,224,3] RGB -> float16 [B,dim] (L2-normalized)."""
        try:
            out = self.sess.run(None, {self.input: np.ascontiguousarray(batch)})[0]
        except Exception as e:
            if self.device == "cpu":
                raise
            # GPU driver problem (device lost, out of memory...): continue on CPU
            self.fell_back = f"GPU failed ({type(e).__name__}); continuing on CPU"
            self.device = "cpu"
            self.sess = self._session("cpu")
            out = self.sess.run(None, {self.input: np.ascontiguousarray(batch)})[0]
        return out.astype(np.float16)


# ---------------------------------------------------------------- keypoint matching
ORB_MATCH_PATH = os.path.join(RES_DIR, "models", "orb_match_fp16.onnx")


class OrbMatcher:
    """ORB descriptor matching on the GPU (DirectML): for every descriptor of A its
    best and second-best key in B, then the ratio test. Same result as
    worker.match_cpu (OpenCV BFMatcher + knnMatch(k=2)); see tools/export_orbmatch.py."""

    BATCH = 16          # image pairs per GPU call (fixed shapes: no re-planning)
    ROWS = 3072         # descriptors per image are padded to a multiple of this

    def __init__(self):
        if not os.path.exists(ORB_MATCH_PATH):
            raise FileNotFoundError(ORB_MATCH_PATH)
        so = ort.SessionOptions()
        so.enable_mem_pattern = False
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.sess = ort.InferenceSession(ORB_MATCH_PATH, so, providers=["DmlExecutionProvider"])
        if self.sess.get_providers()[0] != "DmlExecutionProvider":
            raise RuntimeError("DirectML is not available")
        self._support = None

    def match(self, pairs, ratio=0.75):
        """pairs: list of (desc_a, desc_b) uint8 [n, 32] arrays.
        Returns, per pair, (query indices into A, matching indices into B)."""
        out = []
        P = self.BATCH
        for s in range(0, len(pairs), P):
            batch = pairs[s:s + P]
            longest = max(max(len(da), len(db)) for da, db in batch)
            n = -(-longest // self.ROWS) * self.ROWS
            DA = np.zeros((P, n, 32), np.uint8)
            DB = np.zeros((P, n, 32), np.uint8)
            MB = np.full((P, 1, n), -30000, np.float16)     # padding never wins
            for i, (da, db) in enumerate(batch):
                DA[i, :len(da)] = da
                DB[i, :len(db)] = db
                MB[i, 0, :len(db)] = 0
            J1, V1, V2, CNT = self.sess.run(None, {"DA": DA, "DB": DB, "MB": MB})
            for i, (da, db) in enumerate(batch):
                k = len(da)
                d1 = (256 - V1[i, :k, 0].astype(np.float32)) / 2
                # several keys tied for best -> the second best is as close as the best
                d2 = np.where(CNT[i, :k, 0] >= 2, d1, (256 - V2[i, :k, 0].astype(np.float32)) / 2)
                q = np.nonzero(d1 < ratio * d2)[0]
                out.append((q.astype(np.int64), J1[i, q, 0].astype(np.int64)))
        return out


    def match_filter(self, items, ratio=0.75):
        """items: [(desc_a, desc_b, pts_a, pts_b)] -> per pair (query idx, train idx,
        plausible); same contract as cuda.Matcher.match_filter. plausible=False:
        no sampled homography is supported by enough matches to pass the geometric
        check, so the CPU check can be skipped."""
        matches = self.match([(a, b) for a, b, _, _ in items], ratio)
        srcs = [pa[q] for (q, _), (_, _, pa, _) in zip(matches, items)]
        dsts = [pb[t] for (_, t), (_, _, _, pb) in zip(matches, items)]
        try:
            if self._support is None:
                self._support = RansacSupport()
            best = self._support.best(srcs, dsts)
        except Exception:
            best = np.full(len(items), PRECHECK_MIN_SUPPORT, np.int64)   # no pre-check: CPU decides
        return [(q, t, bool(b >= PRECHECK_MIN_SUPPORT)) for (q, t), b in zip(matches, best)]


# ---------------------------------------------------------------- RANSAC pre-check
RANSAC_PATH = os.path.join(RES_DIR, "models", "ransac_support.onnx")
PRECHECK_HYPOTHESES = 2048   # random 4-match samples per pair
PRECHECK_REPROJ = 5.0        # px, same as cv2.findHomography in worker.geometry
# worker.geometry needs >= 30 inliers. On real pairs the best sampled hypothesis
# always reached >= 0.83x the OpenCV count; 20 leaves ample margin.
PRECHECK_MIN_SUPPORT = 20
# Only pairs with few matches are pre-checked: they are the ones OpenCV's RANSAC is
# slow on (low inlier ratio -> maximum iterations) and that end up rejected. Pairs
# with many matches are fast for OpenCV and are passed on unchanged.
PRECHECK_MAX_MATCHES = 256


def precheck_todo(srcs):
    """(indices to pre-check, initial best counts): fewer than 15 matches can never
    pass (count 0); more than PRECHECK_MAX_MATCHES always go to the CPU check."""
    best = np.array([0 if len(x) < 15 else PRECHECK_MIN_SUPPORT for x in srcs], np.int64)
    return [i for i, x in enumerate(srcs) if 15 <= len(x) <= PRECHECK_MAX_MATCHES], best


def _square_to_quad(q):
    """Homographies mapping the unit square to quads q [..., 4, 2] -> [..., 3, 3]."""
    x0, x1, x2, x3 = (q[..., i, 0] for i in range(4))
    y0, y1, y2, y3 = (q[..., i, 1] for i in range(4))
    dx1, dx2, dx3 = x1 - x2, x3 - x2, x0 - x1 + x2 - x3
    dy1, dy2, dy3 = y1 - y2, y3 - y2, y0 - y1 + y2 - y3
    with np.errstate(divide="ignore", invalid="ignore"):
        den = dx1 * dy2 - dx2 * dy1
        g = (dx3 * dy2 - dx2 * dy3) / den
        hh = (dx1 * dy3 - dx3 * dy1) / den
    one = np.ones_like(x0)
    return np.stack([x1 - x0 + g * x1, x3 - x0 + hh * x3, x0,
                     y1 - y0 + g * y1, y3 - y0 + hh * y3, y0,
                     g, hh, one], -1).reshape(*q.shape[:-2], 3, 3)


def _adjugate(m):
    a, b, c = m[..., 0, 0], m[..., 0, 1], m[..., 0, 2]
    d, e, f = m[..., 1, 0], m[..., 1, 1], m[..., 1, 2]
    g, h_, i = m[..., 2, 0], m[..., 2, 1], m[..., 2, 2]
    return np.stack([e * i - f * h_, c * h_ - b * i, b * f - c * e,
                     f * g - d * i, a * i - c * g, c * d - a * f,
                     d * h_ - e * g, b * g - a * h_, a * e - b * d], -1).reshape(m.shape)


def _mul3(a, b):
    """Batched 3x3 product, written out (NumPy's matmul is slow for tiny matrices)."""
    return np.stack([a[..., i, 0] * b[..., 0, j] + a[..., i, 1] * b[..., 1, j] + a[..., i, 2] * b[..., 2, j]
                     for i in range(3) for j in range(3)], -1).reshape(a.shape)


def precheck_inputs(src, dst, rng, hyps=PRECHECK_HYPOTHESES):
    """Normalized points and hyps candidate homographies (src -> dst) from random
    4-match samples of one pair. Degenerate samples give NaN/inf (never count)."""
    src = np.asarray(src, np.float32)
    dst = np.asarray(dst, np.float32)
    cs, cd = src.mean(0), dst.mean(0)
    ss = max(float(np.abs(src - cs).mean()), 1e-6)
    sd = max(float(np.abs(dst - cd).mean()), 1e-6)
    sn, dn = (src - cs) / ss, (dst - cd) / sd
    idx = rng.integers(0, len(src), (hyps, 4))
    with np.errstate(all="ignore"):
        H = _mul3(_square_to_quad(dn[idx]), _adjugate(_square_to_quad(sn[idx])))
        H /= np.abs(H).max(axis=(1, 2), keepdims=True)              # keep fp32 in range
    H[~np.isfinite(H).all(axis=(1, 2))] = np.nan
    return sn.astype(np.float32), dn.astype(np.float32), H.astype(np.float32), (PRECHECK_REPROJ / sd) ** 2


class RansacSupport:
    """Best RANSAC support per pair on the GPU (DirectML), see tools/export_ransac.py."""

    BUDGET = 64 * 128   # pairs x padded matches per GPU call

    def __init__(self):
        if not os.path.exists(RANSAC_PATH):
            raise FileNotFoundError(RANSAC_PATH)
        so = ort.SessionOptions()
        so.enable_mem_pattern = False
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.sess = ort.InferenceSession(RANSAC_PATH, so, providers=["DmlExecutionProvider"])
        if self.sess.get_providers()[0] != "DmlExecutionProvider":
            raise RuntimeError("DirectML is not available")

    def best(self, srcs, dsts):
        todo, out = precheck_todo(srcs)
        rng = np.random.default_rng(12345)                        # repeatable results
        by_k = {}
        for i in todo:
            # pad to 128, 256, 512, ...: few distinct shapes (DirectML plans each once)
            by_k.setdefault(max(128, 1 << int(np.ceil(np.log2(len(srcs[i]))))), []).append(i)
        Hn = PRECHECK_HYPOTHESES
        for K, idxs in by_k.items():
            P = max(1, self.BUDGET // K)
            for s in range(0, len(idxs), P):
                part = idxs[s:s + P]
                HM = np.full((P, Hn, 3, 3), np.nan, np.float32)      # unused slots count 0
                ST = np.zeros((P, 1, 3, K), np.float32)
                DX = np.zeros((P, 1, K), np.float32)
                DY = np.zeros((P, 1, K), np.float32)
                MK = np.zeros((P, 1, K), np.float32)
                TH = np.zeros((P, 1, 1), np.float32)
                for r, i in enumerate(part):
                    sn, dn, H, th = precheck_inputs(srcs[i], dsts[i], rng)
                    m = len(sn)
                    HM[r] = H
                    ST[r, 0, 0, :m], ST[r, 0, 1, :m], ST[r, 0, 2, :m] = sn[:, 0], sn[:, 1], 1
                    DX[r, 0, :m], DY[r, 0, :m], MK[r, 0, :m] = dn[:, 0], dn[:, 1], 1
                    TH[r] = th
                cnt = self.sess.run(None, {"HM": HM, "ST": ST, "DX": DX, "DY": DY, "MK": MK, "TH": TH})[0]
                out[part] = np.rint(cnt[:len(part)]).astype(np.int64)
        return out


# ---------------------------------------------------------------- similarity search
def _block_candidates(s, qs, ks, lo, kref):
    """Entries of a score block worth keeping: everything >= lo (sparse case),
    or each row's top kref when a block is unusually dense (many look-alikes)."""
    nq, nk = s.shape
    hit = s >= lo
    nnz = int(np.count_nonzero(hit))
    if nnz <= nq * 64:
        r, c = np.nonzero(hit)
        v = s[r, c]
    else:
        kk = min(kref + 1, nk)
        c = np.argpartition(-s, kk - 1, axis=1)[:, :kk]
        v = np.take_along_axis(s, c, 1)
        r = np.repeat(np.arange(nq), kk)
        c, v = c.ravel(), v.ravel()
        keep = v >= lo
        r, c, v = r[keep], c[keep], v[keep]
    c = c + ks
    keep = (r + qs) != c                       # drop self-matches
    return r[keep], c[keep], v[keep]


KNN_CHUNK = 512          # must match tools/export_knn.py
KNN_ORT_MIN_N = 20000    # below this NumPy is fast enough and simpler


KNN_SHARD = 1 << 20      # max keys per GPU session (1M x 384 fp16 = 768 MB)


class _KeyShard:
    """One ONNX session searching a contiguous slice of the keys."""

    def __init__(self, keys, offset, gpu, dtype):
        C = KNN_CHUNK
        self.offset, self.n = offset, len(keys)
        npad = -(-self.n // C) * C
        kt = np.zeros((keys.shape[1], npad), dtype)   # zero padding scores 0 -> below any threshold
        kt[:, :self.n] = keys.T
        self.feed = {"shape3": np.array([0, npad // C, C], np.int64),
                     "expand": np.array([1, 1, C], np.int64)}
        so = ort.SessionOptions()
        if gpu:
            so.enable_mem_pattern = False
            so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            with open(os.path.join(RES_DIR, "models", "knn_fp16.onnx"), "rb") as f:
                template = f.read()
            # Keys become a constant of the graph: ONNX Runtime uploads them once,
            # to the session's own DirectML device.
            from .onnx_min import add_initializer
            model = add_initializer(template, "KT", kt)
            del kt
            self.sess = ort.InferenceSession(model, so, providers=["DmlExecutionProvider"])
            del model
        else:
            self.feed["KT"] = kt                       # CPU: plain input, used in place
            self.sess = ort.InferenceSession(os.path.join(RES_DIR, "models", "knn_fp32.onnx"), so,
                                             providers=["CPUExecutionProvider"])
        self.npad = npad

    def topk(self, q, kk):
        V, J, CI = self.sess.run(None, dict(self.feed, Q=q, k=np.array([kk], np.int64)))
        C = KNN_CHUNK
        idx = np.take_along_axis(CI, J // C, 1) * C + J % C
        V = V.astype(np.float32)
        V[idx >= self.n] = -np.inf                     # padding
        return V, idx + self.offset


def _knn_ort(x, k, min_score, margin, kref, device, progress, check):
    """Top-(kref+1) per row with the block-top-k ONNX graph (GPU via DirectML,
    or multithreaded CPU). Keys stay on the device; only [rows, kref+1] results
    come back. Very large key sets are split into shards and merged."""
    n, d = x.shape
    gpu = device == "dml"
    dtype = np.float16 if gpu else np.float32
    xq = np.ascontiguousarray(x, dtype=dtype)
    shard_size = KNN_SHARD if gpu else n
    shards = [_KeyShard(xq[s:s + shard_size], s, gpu, dtype) for s in range(0, n, shard_size)]
    kk = kref + 1                                      # +1 for the row itself
    # keep each [rows, keys] score block around 256M elements (~512 MB in fp16)
    widest = max(s.npad for s in shards)
    qblock = int(max(64, min(1024, 2 ** int(np.log2(max(1, 2.56e8 / widest))))))
    out_i, out_j = [], []
    qs = 0
    while qs < n:
        if check:
            check()
        q = xq[qs:qs + qblock]
        try:
            parts = [s.topk(q, kk) for s in shards]
        except Exception:
            if qblock > 64:                            # likely GPU memory: smaller blocks
                qblock //= 2
                continue
            raise
        V = np.concatenate([p[0] for p in parts], 1)
        idx = np.concatenate([p[1] for p in parts], 1)
        if len(parts) > 1:                             # merge shards: best kk overall
            sel = np.argsort(-V, axis=1, kind="stable")[:, :kk]
            V, idx = np.take_along_axis(V, sel, 1), np.take_along_axis(idx, sel, 1)
        i, j = _select_topk(qs, V, idx, k, kref, min_score, margin)
        out_i.append(i)
        out_j.append(j)
        qs += len(q)
        if progress:
            progress(qs, n)
    return np.concatenate(out_i), np.concatenate(out_j)


def _select_topk(qs, V, idx, k, kref, min_score, margin, tol=1e-3):
    """From sorted top-(kref+1) scores V / indices idx of rows qs.. keep the pairs
    (row, neighbour) that pass min_score and the margin test."""
    rows = np.arange(qs, qs + len(V))[:, None]
    valid = (idx != rows) & np.isfinite(V)
    # keep kref non-self entries per row, best first (TopK output is sorted)
    order = np.argsort(~valid, axis=1, kind="stable")[:, :kref]
    V = np.take_along_axis(V, order, 1)
    idx = np.take_along_axis(idx, order, 1)
    ok = np.take_along_axis(valid, order, 1)
    if V.shape[1] < kref:                       # fewer rows than kref: no margin reference
        ref = np.full((len(V), 1), -np.inf, np.float32)
    else:
        ref = V[:, -1:] if margin > 0 else np.full((len(V), 1), -np.inf, np.float32)
    kq = min(k, V.shape[1])
    m = ok[:, :kq] & (V[:, :kq] >= min_score - tol) & (V[:, :kq] >= ref + margin)
    return np.broadcast_to(rows, (len(V), kq))[m], idx[:, :kq][m]


def _knn_cuda(x, k, min_score, margin, kref, progress, check):
    from . import cuda
    if not cuda.available():
        raise RuntimeError("CUDA is not available")
    out_i, out_j = [], []
    for qs, V, idx, tol in cuda.knn_topk(x, kref + 1, progress, check):
        i, j = _select_topk(qs, V, idx, k, kref, min_score, margin, tol)
        out_i.append(i)
        out_j.append(j)
    if not out_i:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    return np.concatenate(out_i), np.concatenate(out_j)


def knn_pairs(x, k, min_score, device=None, progress=None, check=None, margin=0.0, kref=16,
              qblock=1024, kblock=65536):
    """Pairs (i<j) where j is among i's k most similar rows (dot product) with
    score >= min_score. With margin > 0 a neighbour must also beat i's kref-th
    neighbour by that margin, i.e. stand out from look-alikes.

    Large sets: exact block-top-k on ONNX Runtime (GPU or CPU), never an N x N matrix.
    Small sets / no ONNX Runtime: exact sparse NumPy search."""
    n = x.shape[0]
    if n < 2:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    k = max(1, min(k, n - 1))
    kref = max(k, kref)
    if device == "cuda" and n < KNN_ORT_MIN_N:
        # Small set: the exact NumPy search is fast, and its tie order is the same
        # on every device, so results do not depend on the GPU.
        device = "cpu"
    if device == "cuda":
        try:
            i, j = _knn_cuda(x, k, min_score, margin, kref, progress, check)
            return _unique_pairs(i, j, n)
        except Exception as e:
            if type(e).__name__ == "Cancelled":
                raise
            device = "dml" if has_dml() else "cpu"          # CUDA failed: next best backend
    if HAS_ORT and n >= KNN_ORT_MIN_N:
        dev = device if device in ("dml", "cpu") else "cpu"
        try:
            i, j = _knn_ort(x, k, min_score, margin, kref, dev, progress, check)
        except Exception as e:
            if dev != "dml" or type(e).__name__ == "Cancelled":
                raise
            i, j = _knn_ort(x, k, min_score, margin, kref, "cpu", progress, check)  # GPU failed
        return _unique_pairs(i, j, n)
    x = np.ascontiguousarray(x, dtype=np.float32)
    use_margin = margin > 0 and n - 1 >= kref
    lo = min_score - (margin if use_margin else 0.0) - 1e-4
    out_i, out_j = [], []
    for qs in range(0, n, qblock):
        if check:
            check()
        q = x[qs:qs + qblock]
        rs, cs, vs = [], [], []
        for ks in range(0, n, kblock):
            r, c, v = _block_candidates(q @ x[ks:ks + kblock].T, qs, ks, lo, kref)
            rs.append(r)
            cs.append(c)
            vs.append(v)
        r, c, v = np.concatenate(rs), np.concatenate(cs), np.concatenate(vs)
        if len(r):
            order = np.lexsort((-v, r))          # by row, best score first
            r, c, v = r[order], c[order], v[order]
            starts = np.flatnonzero(np.r_[True, r[1:] != r[:-1]])
            counts = np.diff(np.r_[starts, len(r)])
            rank = np.arange(len(r)) - np.repeat(starts, counts)
            if use_margin:
                # kref-th best of the row, if the row has that many near neighbours;
                # otherwise it is below lo and the margin test passes automatically
                ref = np.where(counts >= kref, v[np.minimum(starts + kref - 1, len(v) - 1)], -np.inf)
                ref = np.repeat(ref, counts)
            else:
                ref = np.full(len(r), -np.inf, np.float32)
            m = (rank < k) & (v >= min_score - 1e-4) & (v >= ref + margin)
            out_i.append(r[m] + qs)
            out_j.append(c[m])
        if progress:
            progress(min(qs + qblock, n), n)
    if not out_i:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    return _unique_pairs(np.concatenate(out_i), np.concatenate(out_j), n)


def _unique_pairs(i, j, n):
    if len(i) == 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    a = np.minimum(i, j).astype(np.int64)
    b = np.maximum(i, j).astype(np.int64)
    key = np.unique(a * n + b)
    return key // n, key % n


def phash_to_pm1(hashes):
    """int64 hashes -> float32 matrix of +/-1 so that dot = 64 - 2*hamming."""
    bits = np.unpackbits(hashes.astype(np.int64).view(np.uint8).reshape(-1, 8), axis=1)
    return bits.astype(np.float32) * 2.0 - 1.0


def hamming(a, b):
    return bin((int(a) ^ int(b)) & 0xFFFFFFFFFFFFFFFF).count("1")
