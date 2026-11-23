"""Optional NVIDIA CUDA backend (PyTorch).

Used automatically when PyTorch with CUDA support is installed (e.g. the dev
environment). The packaged exe does not include PyTorch and uses DirectML / CPU.

On CUDA the GPU runs:
  * the DINOv2 feature model (same weights as the ONNX files, fp16);
  * the nearest-neighbour searches (pHash and AI features), at any library size;
  * ORB descriptor matching (same result as OpenCV BFMatcher + ratio test);
  * a batched RANSAC pre-check that rejects keypoint matches which cannot pass
    the geometric check, so the CPU only verifies plausible crops.

torch is imported lazily: importing this module is cheap.
"""

import functools
import importlib.util
import os
import sys

import numpy as np

torch = None


def installed():
    """Cheap check (no import): is a CUDA build of PyTorch installed?"""
    try:
        if importlib.util.find_spec("torch") is None:
            return False
        from importlib.metadata import version
        v = version("torch")
        if "+cu" in v:
            return True
        # Linux: PyTorch from PyPI is a CUDA build without the "+cu" tag
        # (CPU-only builds say "+cpu"); available() confirms a GPU is there.
        return sys.platform.startswith("linux") and "+" not in v
    except Exception:
        return False


@functools.lru_cache(maxsize=1)
def available():
    """Imports torch; True when a CUDA device can be used."""
    global torch
    if not installed():
        return False
    try:
        import torch as _t
        if not _t.cuda.is_available():
            return False
        torch = _t
        torch.backends.cuda.matmul.allow_tf32 = False     # exact fp32 scores
        return True
    except Exception:
        return False


def device_name():
    return torch.cuda.get_device_name(0) if available() else ""


# ---------------------------------------------------------------- feature model
class TorchEmbedder:
    """DINOv2-small on CUDA; same interface and outputs as features.Embedder."""

    def __init__(self, model_name):
        if not available():
            raise RuntimeError("CUDA is not available")
        import timm
        import torch.nn.functional as F
        self._F = F
        self.device = "cuda"
        self.fell_back = None
        self._fallback = None
        self.dev = torch.device("cuda")
        try:
            net = timm.create_model(model_name, pretrained=True, num_classes=0, img_size=224,
                                    **self._cached_weights(model_name))
        except Exception as e:  # weights not cached and no network
            raise RuntimeError(f"could not load {model_name} weights ({type(e).__name__}: {e})")
        self.net = net.eval().to(self.dev).half()
        self.dim = int(self.net.num_features)
        self.mean = torch.tensor([0.485, 0.456, 0.406], device=self.dev).view(1, 3, 1, 1) * 255
        self.std = torch.tensor([0.229, 0.224, 0.225], device=self.dev).view(1, 3, 1, 1) * 255

    @staticmethod
    def _cached_weights(model_name):
        """Point timm at the already-downloaded weights file, so loading the model
        makes no network request; {} (normal download) when it is not cached."""
        try:
            from huggingface_hub import try_to_load_from_cache
            for fn in ("model.safetensors", "pytorch_model.bin"):
                p = try_to_load_from_cache("timm/" + model_name, fn)
                if isinstance(p, str) and os.path.exists(p):
                    return {"pretrained_cfg_overlay": {"file": p}}
        except Exception:
            pass
        return {}

    @property
    def label(self):
        if self._fallback is not None:
            return self._fallback.label
        return f"GPU: {device_name()} (CUDA)"

    def embed(self, batch):
        """batch: uint8 [B,224,224,3] RGB -> float16 [B,dim] (L2-normalized)."""
        if self._fallback is not None:
            return self._fallback.embed(batch)
        try:
            return self._embed(batch)
        except Exception as e:
            # driver problem / out of memory: continue with the ONNX model
            from . import features
            self._fallback = features.Embedder("dml" if features.has_dml() else "cpu")
            self.device = self._fallback.device
            self.fell_back = f"CUDA failed ({type(e).__name__}); continuing with {self._fallback.label}"
            return self._fallback.embed(batch)

    def _embed(self, batch):
        with torch.inference_mode():
            x = torch.from_numpy(np.ascontiguousarray(batch)).to(self.dev, non_blocking=True)
            x = (x.permute(0, 3, 1, 2).float() - self.mean) / self.std
            y = self._F.normalize(self.net(x.half()).float(), dim=1)
            return y.half().cpu().numpy()


# ---------------------------------------------------------------- nearest neighbours
def knn_topk(x, kk, progress=None, check=None):
    """Exact top-kk neighbours by dot product for every row of x [n, d].
    Yields (row_start, V [rows, kk] float32, idx [rows, kk] int64, tolerance)
    per block, best first; a row's own index can be among them."""
    n, d = x.shape
    # fp32 scores (same as the CPU search) when keys + a score block fit easily
    free = torch.cuda.mem_get_info()[0]
    dtype = np.float32 if n * d * 4 + 2.56e8 * 4 < free * 0.5 else np.float16
    keys = torch.from_numpy(np.ascontiguousarray(x, dtype=dtype)).cuda()
    kk = min(kk, n)
    # score block [rows, n]: keep it around 256M elements
    qblock = int(max(64, min(4096, 2 ** int(np.log2(max(1, 2.56e8 / n))))))
    qs = 0
    with torch.inference_mode():
        while qs < n:
            if check:
                check()
            q = keys[qs:qs + qblock]
            try:
                V, idx = (q @ keys.T).topk(kk, dim=1)
            except torch.OutOfMemoryError:
                torch.cuda.empty_cache()
                if qblock > 64:
                    qblock //= 2
                    continue
                raise
            yield qs, V.float().cpu().numpy(), idx.cpu().numpy(), 1e-4 if dtype == np.float32 else 1e-3
            qs += len(q)
            if progress:
                progress(qs, n)
    del keys
    torch.cuda.empty_cache()


# ---------------------------------------------------------------- keypoint matching
class Matcher:
    """ORB matching + RANSAC pre-check on CUDA.

    match_filter(items) with items = [(desc_a, desc_b, pts_a, pts_b)] returns per
    pair (query idx, train idx, plausible). The matches equal worker.match_cpu;
    plausible=False means no homography supports enough matches for the geometric
    check (worker.geometry needs >= MIN_INLIERS), so the CPU check can be skipped."""

    # same settings as the DirectML pre-check (features.PRECHECK_*)
    from .features import (PRECHECK_HYPOTHESES as HYPOTHESES, PRECHECK_REPROJ as REPROJ,
                           PRECHECK_MIN_SUPPORT as MIN_SUPPORT)

    def __init__(self):
        if not available():
            raise RuntimeError("CUDA is not available")
        self.dev = torch.device("cuda")
        lut = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1)   # bit order as OpenCV
        self.lut = torch.tensor(lut, dtype=torch.float16, device=self.dev) * 2 - 1   # [256, 8] of +-1
        self.gen = torch.Generator(device=self.dev)

    def _pm1(self, descs, n):
        """list of uint8 [k, 32] -> fp16 [P, n, 256] of +-1 (zero rows as padding)."""
        P = len(descs)
        out = torch.zeros((P, n, 256), dtype=torch.float16, device=self.dev)
        for i, d in enumerate(descs):
            t = torch.from_numpy(d).to(self.dev).long()
            out[i, :len(d)] = self.lut[t].reshape(len(d), 256)
        return out

    def match_filter(self, items, ratio=0.75):
        out = []
        with torch.inference_mode():
            s = 0
            while s < len(items):
                # pairs per call: keep the [P, na, nb] score tensor under ~600 MB
                longest = max(max(len(a), len(b)) for a, b, _, _ in items[s:s + 64])
                P = int(max(1, min(64, 3e8 // max(1, longest * longest))))
                out += self._batch(items[s:s + P], ratio)
                s += P
        return out

    def _batch(self, items, ratio):
        na = max(len(a) for a, _, _, _ in items)
        nb = max(len(b) for _, b, _, _ in items)
        A = self._pm1([a for a, _, _, _ in items], na)
        B = self._pm1([b for _, b, _, _ in items], nb)
        S = torch.bmm(A, B.transpose(1, 2))                       # 256 - 2 * hamming
        for i, (_, b, _, _) in enumerate(items):
            S[i, :, len(b):] = -30000                                # padding never wins
        V, J = S.topk(2, dim=2)
        d = (256 - V.float()) / 2
        # a tie for best makes the second best as close as the best: rejected, as in OpenCV
        good = d[..., 0] < ratio * d[..., 1]
        good_c, J1 = good.cpu().numpy(), J[..., 0].cpu().numpy()
        res = []
        srcs, dsts = [], []
        for i, (a, _, pa, pb) in enumerate(items):
            q = np.nonzero(good_c[i, :len(a)])[0].astype(np.int64)
            t = J1[i, q].astype(np.int64)
            res.append((q, t))
            srcs.append(pa[q])
            dsts.append(pb[t])
        plaus = self.support(srcs, dsts) >= self.MIN_SUPPORT
        return [(q, t, bool(p)) for (q, t), p in zip(res, plaus)]

    def support(self, srcs, dsts):
        """Most matches agreeing with one sampled homography, per pair (int array)."""
        from .features import precheck_todo
        todo, best = precheck_todo(srcs)
        if not todo:
            return best
        self.gen.manual_seed(12345)                                 # repeatable results
        Hn = self.HYPOTHESES
        s = 0
        while s < len(todo):
            k_max = max(len(srcs[i]) for i in todo[s:s + 64])
            P = int(max(1, min(64, 6e7 // (Hn * k_max))))
            part = todo[s:s + P]
            best[part] = self._support(srcs, dsts, part, Hn)
            s += P
        return best

    def _support(self, srcs, dsts, part, Hn):
        dev = self.dev
        P = len(part)
        k = max(len(srcs[i]) for i in part)
        S = torch.zeros((P, k, 2), device=dev)
        D = torch.zeros((P, k, 2), device=dev)
        valid = torch.zeros((P, k), dtype=torch.bool, device=dev)
        n = torch.zeros(P, device=dev)
        for r, i in enumerate(part):
            m = len(srcs[i])
            S[r, :m] = torch.from_numpy(np.ascontiguousarray(srcs[i], np.float32)).to(dev)
            D[r, :m] = torch.from_numpy(np.ascontiguousarray(dsts[i], np.float32)).to(dev)
            valid[r, :m] = True
            n[r] = m
        # normalize both point sets (conditioning of the 8x8 solve)
        w = valid.unsqueeze(-1).float()
        cs = (S * w).sum(1, keepdim=True) / n.view(P, 1, 1)
        cd = (D * w).sum(1, keepdim=True) / n.view(P, 1, 1)
        ss = (((S - cs).abs() * w).sum((1, 2)) / (2 * n)).clamp_min(1e-6).view(P, 1, 1)
        sd = (((D - cd).abs() * w).sum((1, 2)) / (2 * n)).clamp_min(1e-6).view(P, 1, 1)
        Sn, Dn = (S - cs) / ss, (D - cd) / sd
        # random 4-point samples inside each pair's own matches
        idx = (torch.rand((P, Hn, 4), device=dev, generator=self.gen) * n.view(P, 1, 1)).long()
        idx = idx.clamp_max(k - 1)
        g = lambda X: torch.gather(X, 1, idx.view(P, Hn * 4, 1).expand(-1, -1, 2)).view(P, Hn, 4, 2)
        s4, d4 = g(Sn), g(Dn)
        x, y, u, v = s4[..., 0], s4[..., 1], d4[..., 0], d4[..., 1]
        z, o = torch.zeros_like(x), torch.ones_like(x)
        A = torch.cat([torch.stack([x, y, o, z, z, z, -u * x, -u * y], -1),
                       torch.stack([z, z, z, x, y, o, -v * x, -v * y], -1)], -2)    # [P,Hn,8,8]
        b = torch.cat([u, v], -1).unsqueeze(-1)
        h, info = torch.linalg.solve_ex(A, b)
        H = torch.cat([h.squeeze(-1), torch.ones_like(x[..., :1])], -1).view(P, Hn, 3, 3)
        # reprojection error of every match under every hypothesis, in pixels of B
        pr = torch.einsum("phij,pkj->phki", H, torch.cat([Sn, torch.ones_like(Sn[..., :1])], -1))
        xy = pr[..., :2] / pr[..., 2:3]
        err = ((xy - Dn.unsqueeze(1)) * sd.unsqueeze(1)).square().sum(-1)        # [P,Hn,k]
        inl = (err < self.REPROJ ** 2) & valid.unsqueeze(1)
        cnt = inl.sum(-1)
        cnt = torch.where(info == 0, cnt, torch.zeros_like(cnt))
        return cnt.max(1).values.cpu().numpy()
