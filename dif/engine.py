"""Scan pipeline: enumerate -> analyze (cached) -> exact -> visual -> crop -> group.

Designed for very large libraries:
  * per-file results are cached in SQLite, so a canceled / crashed scan resumes;
  * decoding runs in worker processes, in bounded chunks (bounded memory);
  * a stalled or crashed decoder is detected, the pool is restarted and the
    offending file is skipped and reported;
  * similarity search is blockwise top-k (never an N x N matrix).
"""

import hashlib
import multiprocessing as mp
import os
import queue
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from . import features, sysinfo, worker
from .cache import Cache
from .formats import available_exts, ext_of, format_rank, sniff
from .variants import DEFAULT_PATTERNS, apply_variants

SKIP_DIRS = {"$recycle.bin", "system volume information", ".venv", "__pycache__", ".git"}


class Cancelled(Exception):
    pass


@dataclass
class ScanOptions:
    folders: list
    recursive: bool = True
    detect_crops: bool = True
    sniff: bool = False
    phash_dist: int = 7          # max differing bits out of 64 for "similar"
    crop_sim: float = 0.80       # min feature cosine for a crop candidate
    device: str = "auto"         # "auto" | "cpu"
    exclude: list = field(default_factory=list)
    workers: int = 0             # 0 = auto
    max_group: int = 5000
    variant_patterns: list = field(default_factory=lambda: list(DEFAULT_PATTERNS))
    prefix_len: int = 0          # exception rule "same first N characters"; 0 = off


@dataclass
class Member:
    idx: int
    kind: str       # keep | exact | similar | cropped | variant
    score: float
    remove: bool
    base_kind: str = ""   # match type before exception rules were applied
    reason: str = ""      # why it is an exception: "pattern" or "prefix:N"


@dataclass
class Group:
    members: list   # members[0] is the best-quality file


class FileTable:
    def __init__(self, paths, sizes, mtimes):
        n = len(paths)
        self.paths = paths
        self.size = np.asarray(sizes, np.int64)
        self.mtime = np.asarray(mtimes, np.int64)
        self.w = np.zeros(n, np.int32)
        self.h = np.zeros(n, np.int32)
        self.fmt = [""] * n
        self.phash = np.zeros(n, np.int64)
        self.sha = [None] * n
        self.error = [None] * n
        self.valid = np.zeros(n, bool)
        self.emb = None
        self.has_emb = np.zeros(n, bool)
        self.tiny = np.zeros((n, 192), np.uint8)

    def __len__(self):
        return len(self.paths)

    def quality_key(self, i):
        return (int(self.w[i]) * int(self.h[i]), format_rank(self.fmt[i]),
                int(self.size[i]), -int(self.mtime[i]))


@dataclass
class ScanResult:
    files: FileTable
    groups: list
    roots: list
    device_label: str
    stats: dict
    warnings: list
    # groups the user kept earlier ("not duplicates"), hidden from the list:
    # [(group, cache group ids)] so they can be shown again
    hidden: list = field(default_factory=list)


class WorkerPool:
    def __init__(self, n):
        self.n = n
        self.ctx = mp.get_context("spawn")
        self.pool = None
        self._start()

    def _start(self):
        self.pool = self.ctx.Pool(self.n, initializer=worker.init_worker)

    def restart(self):
        try:
            self.pool.terminate()
            self.pool.join()
        except Exception:
            pass
        self._start()

    def close(self):
        try:
            self.pool.terminate()
            self.pool.join()
        except Exception:
            pass

    def run(self, fn, keys, payloads, on_result, on_fail, check, on_chunk=None, chunk=1024, stall=120):
        """Run fn over payloads with bounded memory and crash/hang recovery.

        fn receives (pos, payload) and returns (pos, result);
        on_result(key, result) / on_fail(key, message) get the caller's key."""
        for cs in range(0, len(payloads), chunk):
            batch = payloads[cs:cs + chunk]
            bkeys = keys[cs:cs + chunk]
            pending = set(range(len(batch)))
            q = queue.Queue()
            for k, item in enumerate(batch):
                self.pool.apply_async(fn, ((k, item),), callback=q.put,
                                      error_callback=lambda e, k=k: q.put((k, None)))
            idle = 0.0
            while pending:
                check()
                try:
                    k, r = q.get(timeout=0.5)
                except queue.Empty:
                    idle += 0.5
                    if idle >= stall:
                        break
                    continue
                idle = 0.0
                if r is None:
                    if k in pending:
                        pending.discard(k)
                        on_fail(bkeys[k], "worker error")
                    continue
                if k in pending:
                    pending.discard(k)
                    on_result(bkeys[k], r)
            if pending:
                # A worker hung or died: restart and retry the remaining items one by one.
                self.restart()
                for k in sorted(pending):
                    check()
                    try:
                        _, r = self.pool.apply_async(fn, ((k, batch[k]),)).get(timeout=stall)
                        on_result(bkeys[k], r)
                    except Exception as e:
                        self.restart()
                        on_fail(bkeys[k], f"decoder crashed or timed out ({type(e).__name__})")
            if on_chunk:
                on_chunk()


class ScanEngine:
    def __init__(self, opts, cache_path, progress=None, log=None, is_cancelled=None):
        self.o = opts
        self.cache_path = cache_path
        self._progress = progress or (lambda stage, done, total: None)
        self._log = log or (lambda msg: None)
        self._cancelled = is_cancelled or (lambda: False)
        self._last_emit = 0.0
        self.warnings = []
        self.budget = sysinfo.Budget()      # replaced by sysinfo.plan() once the device is known

    # ---------- helpers ----------
    def check(self):
        if self._cancelled():
            raise Cancelled()

    def progress(self, stage, done, total, force=False):
        now = time.monotonic()
        if force or now - self._last_emit > 0.15 or done >= total:
            self._last_emit = now
            self._progress(stage, done, total)

    def warn(self, msg):
        self.warnings.append(msg)
        self._log(msg)

    # ---------- stage 1: enumerate ----------
    def enumerate(self):
        exts = available_exts()
        roots = []
        recurse = {}
        for f in self.o.folders:
            # each entry is a path, or (path, include_subfolders)
            path, rec = (f, self.o.recursive) if isinstance(f, str) else (f[0], bool(f[1]))
            a = os.path.abspath(path)
            if os.path.isdir(a) and a not in roots:
                roots.append(a)
                recurse[a] = rec
        excl = {os.path.normcase(os.path.abspath(e)) for e in self.o.exclude if e}
        seen = set()
        paths, sizes, mtimes = [], [], []
        from .loader import long_path
        for root in roots:
            rec = recurse[root]
            stack = [root]
            while stack:
                self.check()
                d = stack.pop()
                if os.path.normcase(d) in excl:
                    continue
                try:
                    with os.scandir(long_path(d)) as it:
                        entries = list(it)
                except OSError as e:
                    self.warn(f"Cannot read folder {d}: {e}")
                    continue
                for e in entries:
                    try:
                        full = os.path.join(d, e.name)
                        if e.is_dir(follow_symlinks=False):
                            if rec and e.name.lower() not in SKIP_DIRS:
                                stack.append(full)
                            continue
                        if not e.is_file(follow_symlinks=False):
                            continue
                        ext = ext_of(e.name)
                        if ext not in exts and not (self.o.sniff and sniff(long_path(full))):
                            continue
                        key = os.path.normcase(full)
                        if key in seen:
                            continue
                        seen.add(key)
                        st = e.stat(follow_symlinks=False)
                        if st.st_size == 0:
                            continue
                        paths.append(full)
                        sizes.append(st.st_size)
                        mtimes.append(st.st_mtime_ns)
                    except OSError:
                        continue
                self.progress("enumerate", len(paths), 0)
        self.progress("enumerate", len(paths), len(paths), force=True)
        return roots, paths, sizes, mtimes

    # ---------- stage 2: analyze ----------
    def analyze(self, ft, todo, cache, pool, embedder):
        need_emb = embedder is not None
        emb_batch, emb_idx = [], []
        done = [0]
        # The AI model runs in its own thread (ONNX Runtime releases the GIL), so
        # collecting decoded images from the workers never waits for it.
        emb_exec = ThreadPoolExecutor(1) if need_emb else None
        emb_futs = []

        def _embed(batch, idx):
            ft.emb[idx] = embedder.embed(batch)
            ft.has_emb[idx] = True

        def flush_emb(wait=False):
            if emb_batch:
                emb_futs.append(emb_exec.submit(_embed, np.stack(emb_batch), list(emb_idx)))
                emb_batch.clear()
                emb_idx.clear()
            # bounded: at most 2 batches queued, so memory stays flat
            while emb_futs and (wait or len(emb_futs) > 2):
                emb_futs.pop(0).result()

        def row_of(i):
            emb = ft.emb[i].tobytes() if need_emb and ft.has_emb[i] else None
            return (ft.paths[i], int(ft.size[i]), int(ft.mtime[i]), int(ft.w[i]), int(ft.h[i]),
                    ft.fmt[i], int(ft.phash[i]), ft.sha[i], emb,
                    features.MODEL_ID if emb is not None else None, ft.error[i],
                    None if ft.error[i] else ft.tiny[i].tobytes())

        pending_rows = []

        def on_result(i, r):
            done[0] += 1
            if r.get("error"):
                ft.error[i] = r["error"]
                ft.valid[i] = False
            else:
                ft.w[i], ft.h[i], ft.fmt[i], ft.phash[i] = r["w"], r["h"], r["fmt"], r["phash"]
                ft.tiny[i] = np.frombuffer(r["tiny"], np.uint8)
                ft.valid[i] = True
                ft.error[i] = None
                if need_emb and r.get("thumb") is not None:
                    emb_batch.append(r["thumb"])
                    emb_idx.append(i)
                    if len(emb_batch) >= self.budget.embed_batch:
                        flush_emb()
            pending_rows.append(i)
            self.progress("analyze", done[0], len(todo))

        def on_fail(i, msg):
            on_result(i, {"error": msg})

        def on_chunk():
            if need_emb:
                flush_emb(wait=True)     # rows are written only once their features exist
            cache.upsert([row_of(i) for i in pending_rows])
            pending_rows.clear()

        payloads = [(ft.paths[i], need_emb) for i in todo]
        try:
            pool.run(worker.analyze_task, todo, payloads, on_result, on_fail, self.check, on_chunk=on_chunk)
            on_chunk()
        finally:
            if emb_exec:
                emb_exec.shutdown(wait=True)

    # ---------- stage 3: exact ----------
    def exact(self, ft, cache):
        by_size = defaultdict(list)
        for i in np.nonzero(ft.valid)[0]:
            by_size[int(ft.size[i])].append(int(i))
        cand = [g for g in by_size.values() if len(g) > 1]
        flat = [i for g in cand for i in g if ft.sha[i] is None]
        from .loader import long_path

        def quick(i):
            try:
                with open(long_path(ft.paths[i]), "rb") as f:
                    return i, hashlib.blake2b(f.read(65536), digest_size=16).hexdigest()
            except OSError:
                return i, None

        def full(i):
            try:
                h = hashlib.sha256()
                with open(long_path(ft.paths[i]), "rb") as f:
                    for blk in iter(lambda: f.read(1 << 20), b""):
                        h.update(blk)
                return i, h.hexdigest()
            except OSError:
                return i, None

        total = len(flat)
        q = {}
        with ThreadPoolExecutor(8) as ex:
            for n, (i, hq) in enumerate(ex.map(quick, flat), 1):
                q[i] = hq
                if n % 256 == 0:
                    self.check()
                self.progress("exact", n // 2, total)
            groups = defaultdict(list)
            for i in flat:
                if q.get(i):
                    groups[(int(ft.size[i]), q[i])].append(i)
            need_full = [i for g in groups.values() if len(g) > 1 for i in g]
            saved = []
            for n, (i, hs) in enumerate(ex.map(full, need_full), 1):
                if hs:
                    ft.sha[i] = hs
                    saved.append((hs, ft.paths[i]))
                if n % 64 == 0:
                    self.check()
                self.progress("exact", total // 2 + n * (total - total // 2) // max(1, len(need_full)), total)
        cache.set_sha(saved)
        by_sha = defaultdict(list)
        for i in np.nonzero(ft.valid)[0]:
            if ft.sha[i]:
                by_sha[ft.sha[i]].append(int(i))
        pairs = [(g[0], j) for g in by_sha.values() if len(g) > 1 for j in g[1:]]
        self.progress("exact", total, total, force=True)
        return pairs

    # ---------- main ----------
    def run(self):
        t0 = time.time()
        o = self.o
        stats = {}
        roots, paths, sizes, mtimes = self.enumerate()
        ft = FileTable(paths, sizes, mtimes)
        n = len(ft)
        stats["files"] = n
        device, dev_label = features.pick_device(o.device)
        self._match_device = device

        embedder = None
        need_emb = o.detect_crops and n > 1
        if need_emb and not (features.HAS_ORT or device == "cuda"):
            self.warn("ONNX Runtime is not installed: crop detection disabled.")
            need_emb = False
        if need_emb:
            ft.emb = np.zeros((n, features.EMB_DIM), np.float16)

        cache = Cache(self.cache_path)
        pool = None
        try:
            # --- cache lookup ---
            todo = []
            for s in range(0, n, 5000):
                self.check()
                rows = cache.lookup(ft.paths[s:s + 5000])
                for i in range(s, min(n, s + 5000)):
                    r = rows.get(ft.paths[i])
                    if r is None or r[1] != ft.size[i] or r[2] != ft.mtime[i]:
                        todo.append(i)
                        continue
                    if r[10]:
                        ft.error[i] = r[10]
                        continue
                    if r[11] is None:      # cached by an older version
                        todo.append(i)
                        continue
                    ft.tiny[i] = np.frombuffer(r[11], np.uint8)
                    ft.w[i], ft.h[i], ft.fmt[i], ft.phash[i], ft.sha[i] = r[3], r[4], r[5], r[6], r[7]
                    ft.valid[i] = True
                    if need_emb:
                        if r[8] is not None and r[9] == features.MODEL_ID:
                            ft.emb[i] = np.frombuffer(r[8], np.float16)
                            ft.has_emb[i] = True
                        else:
                            todo.append(i)
                self.progress("cache", min(n, s + 5000), n)
            stats["cached"] = n - len(todo)

            # The AI model is loaded only when some files need features
            # (a fully cached rescan does not pay for starting it).
            if need_emb and todo:
                self.progress("model", 0, 1, force=True)
                try:
                    embedder = features.make_embedder(device)
                    if embedder.device != device:   # GPU backend could not start
                        if embedder.device == "dml":
                            self.warn("CUDA could not be used; using the GPU through DirectML.")
                        else:
                            self.warn("GPU could not be used; running the AI model on the CPU.")
                        device, dev_label = embedder.device, embedder.label
                        self._match_device = device
                except Exception as e:
                    self.warn(f"Could not load the AI model (crop detection disabled): {e}")
                    need_emb = False
                    ft.emb = None
            self._log(f"Device: {dev_label}")

            # work sizes for this computer: GPU memory, free RAM, CPU cores (dif/sysinfo.py)
            self.budget = sysinfo.plan(device, o.workers)
            sysinfo.set_current(self.budget)
            self._log(self.budget.describe())
            nworkers = self.budget.workers
            if todo or need_emb:
                pool = WorkerPool(nworkers)
            if todo:
                self._log(f"Analyzing {len(todo)} files with {nworkers} workers")
                self.analyze(ft, todo, cache, pool, embedder)
                if embedder.fell_back if embedder else False:
                    self.warn(embedder.fell_back)
                    dev_label = "CPU"
                    device = self._match_device = "cpu"   # GPU failed once: stay on the CPU
            # The AI model is not needed after this point: give its GPU memory back
            # before the keypoint check (matters on small graphics cards).
            embedder = None
            import gc
            gc.collect()
            from . import cuda
            if cuda.torch is not None:
                cuda.torch.cuda.empty_cache()

            # --- exact duplicates ---
            exact_pairs = self.exact(ft, cache)

            # --- visual (pHash) ---
            vidx = np.nonzero(ft.valid)[0]
            ph_pairs = []
            if len(vidx) > 1:
                x = features.phash_to_pm1(ft.phash[vidx])
                min_score = 64 - 2 * o.phash_dist
                a, b = features.knn_pairs(x, 10, min_score, device,
                                          progress=lambda d, t: self.progress("visual", d, t),
                                          check=self.check)
                ph_pairs = list(zip(vidx[a].tolist(), vidx[b].tolist()))

            # --- crops (features + keypoint verification) ---
            verified = {}
            if need_emb:
                eidx = np.nonzero(ft.valid & ft.has_emb)[0]
                if len(eidx) > 1:
                    a, b = features.knn_pairs(ft.emb[eidx], 8, o.crop_sim, device,
                                              progress=lambda d, t: self.progress("features", d, t),
                                              check=self.check, margin=0.02, kref=16)
                    linked = set()
                    for p in exact_pairs:
                        linked.add((min(p), max(p)))
                    cands = []
                    for i, j in zip(eidx[a].tolist(), eidx[b].tolist()):
                        key = (min(i, j), max(i, j))
                        if key in linked or self._quick(ft, i, j):
                            continue
                        cands.append(key)
                    stats["crop_candidates"] = len(cands)
                    self._verify(ft, cands, verified, pool, cache)
            self.verified = verified

            # --- grouping ---
            self.progress("group", 0, 1, force=True)
            groups = self.build_groups(ft, exact_pairs, ph_pairs, verified, need_emb, pool, cache)
            groups = apply_variants(groups, ft, o.variant_patterns, o.prefix_len)
            groups, hidden_groups = self.drop_ignored(ft, groups, cache)
            stats["hidden"] = len(hidden_groups)
            self.progress("group", 1, 1, force=True)
        finally:
            if pool:
                pool.close()
            cache.close()

        stats["groups"] = len(groups)
        stats["duplicates"] = sum(1 for g in groups for m in g.members if m.remove)
        stats["variants"] = sum(1 for g in groups for m in g.members if m.kind == "variant")
        stats["errors"] = sum(1 for e in ft.error if e)
        stats["seconds"] = round(time.time() - t0, 1)
        return ScanResult(ft, groups, roots, dev_label, stats, self.warnings, hidden_groups)

    @staticmethod
    def drop_ignored(ft, groups, cache):
        """Hide groups the user already kept entirely: every member must belong to
        the same remembered group with unchanged size and modified time."""
        index = cache.ignored_index()
        if not index:
            return groups, []
        shown, hidden = [], []
        for g in groups:
            gids = {index.get((ft.paths[m.idx], int(ft.size[m.idx]), int(ft.mtime[m.idx]))) for m in g.members}
            if len(gids) == 1 and None not in gids:
                hidden.append((g, sorted(gids)))
                continue
            shown.append(g)
        return shown, hidden

    VERIFY_CHUNK = 1024      # pairs per step of the keypoint check

    def _verify(self, ft, pairs, verified, pool, cache, device=None):
        """Keypoint check of candidate crop pairs.

        Each image's keypoints are extracted once (worker processes) and reused for
        all of its pairs. Descriptor matching runs on the GPU when available, in a
        background thread that overlaps the CPU work; the geometric check runs in
        the worker processes. Results equal worker.verify_pair."""
        if not pairs:
            return

        def stamp(a, b):
            return f"{ft.size[a]}:{ft.mtime[a]}:{ft.size[b]}:{ft.mtime[b]}:{worker.MIN_INLIERS}"

        known = cache.get_pairs([(ft.paths[a], ft.paths[b], stamp(a, b)) for a, b in pairs])
        todo = []
        for a, b in pairs:
            r = known.get((ft.paths[a], ft.paths[b]))
            if r is not None:
                verified[(a, b)] = r
            else:
                todo.append((a, b))

        if device is None:
            device = getattr(self, "_match_device", "cpu")
        matcher = None
        if todo and features.is_gpu(device):
            try:
                if device == "cuda":
                    from . import cuda
                    matcher = cuda.Matcher()
                else:
                    matcher = features.OrbMatcher()
            except Exception as e:
                self._log(f"GPU keypoint matching unavailable ({type(e).__name__}: {e}); using the CPU")
        self._log(f"Keypoint checks: {len(pairs) - len(todo)} cached, {len(todo)} to run"
                  + (f" (matching on {'GPU (' + device.upper() + ')' if matcher else 'CPU'})" if todo else ""))
        prechecked = [0]
        if not todo:
            return

        done = [0]
        new_rows = []

        def on_result(key, r):
            done[0] += 1
            verified[key] = r
            a, b = key
            new_rows.append((ft.paths[a], ft.paths[b], stamp(a, b), r))
            self.progress("verify", done[0], len(todo))

        def on_fail(key, msg):
            on_result(key, {"ok": False, "reason": msg})

        def flush():
            cache.put_pairs(new_rows)
            new_rows.clear()

        todo.sort()
        refs = defaultdict(int)
        for a, b in todo:
            refs[a] += 1
            refs[b] += 1
        kp = {}     # image index -> keypoints dict (or {"error": ...})

        def extract(chunk):
            need = sorted({i for p in chunk for i in p if i not in kp})
            if need:
                pool.run(worker.orb_task, need, [ft.paths[i] for i in need],
                         lambda i, r: kp.__setitem__(i, r),
                         lambda i, msg: kp.__setitem__(i, {"error": msg}), self.check, stall=60)

        def split(chunk):
            """Pairs ready for matching; the others are decided right away."""
            ready = []
            for a, b in chunk:
                fa, fb = kp[a], kp[b]
                if "error" in fa or "error" in fb:
                    on_result((a, b), {"ok": False, "reason": fa.get("error") or fb.get("error")})
                elif not worker.enough_features(fa) or not worker.enough_features(fb):
                    on_result((a, b), {"ok": False, "reason": "few features"})
                else:
                    ready.append((a, b))
            return ready

        def release(chunk, keep):
            for a, b in chunk:
                for i in (a, b):
                    refs[i] -= 1
                    if refs[i] <= 0:
                        kp.pop(i, None)
            cap = self.budget.keypoint_sets          # ~120 KB each, sized to free RAM
            if len(kp) > cap:                        # bound memory: recompute later if needed
                for i in [i for i in kp if i not in keep][:len(kp) - cap]:
                    del kp[i]

        def check_pairs(ready, fut):
            nonlocal matcher
            matches = None
            if fut is not None:
                try:
                    matches = fut.result()
                except Exception as e:
                    if matcher is not None:
                        self.warn(f"GPU keypoint matching failed ({type(e).__name__}); continuing on CPU")
                    matcher = None
            if matches is not None:
                todo_geo, payloads = [], []
                for (a, b), m in zip(ready, matches):
                    if len(m) == 3 and not m[2]:
                        # CUDA pre-check: no homography is supported by enough matches
                        prechecked[0] += 1
                        on_result((a, b), {"ok": False, "reason": "weak match (GPU pre-check)"})
                        continue
                    todo_geo.append((a, b))
                    payloads.append((kp[a]["pts"][m[0]], kp[b]["pts"][m[1]], kp[a]["shape"], kp[b]["shape"]))
                pool.run(worker.geometry_task, todo_geo, payloads, on_result, on_fail, self.check,
                         on_chunk=flush, stall=60)
            else:
                pool.run(worker.match_check_task, ready, [(kp[a], kp[b]) for a, b in ready],
                         on_result, on_fail, self.check, on_chunk=flush, stall=60)
            flush()

        gpu = ThreadPoolExecutor(1) if matcher else None
        try:
            prev = None     # (chunk, ready pairs, GPU future) waiting for the geometric check
            for cs in range(0, len(todo), self.VERIFY_CHUNK):
                self.check()
                chunk = todo[cs:cs + self.VERIFY_CHUNK]
                extract(chunk)
                ready = split(chunk)
                fut = None
                if matcher and ready:
                    if hasattr(matcher, "match_filter"):      # CUDA: matching + RANSAC pre-check
                        fut = gpu.submit(matcher.match_filter, [(kp[a]["desc"], kp[b]["desc"], kp[a]["pts"], kp[b]["pts"])
                                                                for a, b in ready])
                    else:
                        fut = gpu.submit(matcher.match, [(kp[a]["desc"], kp[b]["desc"]) for a, b in ready])
                if prev:    # CPU geometry of the previous chunk overlaps this chunk's GPU matching
                    check_pairs(prev[1], prev[2])
                    release(prev[0], {i for p in chunk for i in p})
                prev = (chunk, ready, fut)
            if prev:
                check_pairs(prev[1], prev[2])
                release(prev[0], set())
        finally:
            if gpu:
                gpu.shutdown(wait=False, cancel_futures=True)
            flush()
        if prechecked[0]:
            self._log(f"GPU pre-check rejected {prechecked[0]} of {len(todo)} pairs without the CPU check")

    # ---------- grouping ----------
    # ---------- pair decisions ----------
    @staticmethod
    def _same_aspect(ft, a, b):
        ar_a = ft.w[a] / max(1, ft.h[a])
        ar_b = ft.w[b] / max(1, ft.h[b])
        return abs(ar_a - ar_b) / max(ar_a, 1e-6) <= 0.02

    @staticmethod
    def _cos(ft, a, b):
        return float(ft.emb[a].astype(np.float32) @ ft.emb[b].astype(np.float32))

    def _quick(self, ft, a, b):
        """Decide without keypoints: ('exact'|'similar'|'cropped', score) or None."""
        if ft.sha[a] and ft.sha[a] == ft.sha[b]:
            return "exact", 1.0
        d = features.hamming(ft.phash[a], ft.phash[b])
        both_emb = ft.emb is not None and ft.has_emb[a] and ft.has_emb[b]
        if d <= self.o.phash_dist and self._same_aspect(ft, a, b):
            # Same framing + close hash = resized / recompressed / converted copy.
            # Flat images can collide on pHash, so a second signal must agree:
            # the AI features when available, else the 8x8 color layout.
            if both_emb:
                ok = self._cos(ft, a, b) >= 0.90
            else:
                ok = float(np.abs(ft.tiny[a].astype(np.int16) - ft.tiny[b].astype(np.int16)).mean()) <= 20
            if ok:
                return "similar", 1.0 - d / 64.0
        return None

    def _gate(self, ft, best, m, small):
        """Does (best, m) need a keypoint check to decide membership?"""
        if self._quick(ft, best, m):
            return False
        if ft.emb is None or not (ft.has_emb[best] and ft.has_emb[m]):
            return False
        if features.hamming(ft.phash[best], ft.phash[m]) <= self.o.phash_dist:
            return True     # close hash but different framing: possible crop
        # The feature gate only finds candidates. Inside a small, already-linked
        # component the keypoint check alone decides (catches e.g. sky-heavy crops).
        return self._cos(ft, best, m) >= (self.o.crop_sim - 0.15 if small else self.o.crop_sim)

    def _relation(self, ft, best, m, verified, need_emb, pool, small_comp=False):
        q = self._quick(ft, best, m)
        if q:
            return q
        if not need_emb or not self._gate(ft, best, m, small_comp):
            return None
        cos = self._cos(ft, best, m)
        key = (min(best, m), max(best, m))
        r = verified.get(key)
        if r is None:  # not checked yet (only reached through a chain): verify now
            _, r = worker.verify_task((key, (ft.paths[key[0]], ft.paths[key[1]])))
            verified[key] = r
        if not r.get("ok"):
            return None
        # cover of the *best* image by the other one
        cover = r["cover_ab"] if key[0] == m else r["cover_ba"]
        other = r["cover_ba"] if key[0] == m else r["cover_ab"]
        if cover >= 0.985 and other >= 0.985:
            return "similar", cos
        return "cropped", cos

    def build_groups(self, ft, exact_pairs, ph_pairs, verified, need_emb, pool, cache):
        n = len(ft)
        parent = np.arange(n)

        def find(x):
            root = x
            while parent[root] != root:
                root = parent[root]
            while parent[x] != root:
                parent[x], x = root, parent[x]
            return root

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        edges = list(exact_pairs) + list(ph_pairs) + [k for k, r in verified.items() if r.get("ok")]
        for a, b in edges:
            union(a, b)
        comps = defaultdict(set)
        for a, b in edges:
            r = find(a)
            comps[r].add(a)
            comps[r].add(b)

        # Pre-pass: run the keypoint checks grouping will need (best vs each member)
        # in parallel, instead of one by one while grouping.
        if need_emb and pool is not None:
            needed = []
            for comp in comps.values():
                best = max(comp, key=ft.quality_key)
                small = len(comp) <= 200
                for m in comp:
                    if m != best:
                        key = (min(best, m), max(best, m))
                        if key not in verified and self._gate(ft, best, m, small):
                            needed.append(key)
            if needed:
                self._verify(ft, needed, verified, pool, cache)

        groups = []
        for ci, comp in enumerate(comps.values()):
            if ci % 200 == 0:
                self.check()
            remaining = sorted(comp, key=ft.quality_key, reverse=True)
            small = len(comp) <= 200
            while len(remaining) >= 2:
                best = remaining[0]
                members = [Member(best, "keep", 1.0, False)]
                rest = []
                for m in remaining[1:]:
                    rel = self._relation(ft, best, m, verified, need_emb, pool, small) \
                        if len(members) < self.o.max_group else None
                    if rel:
                        members.append(Member(m, rel[0], rel[1], True))
                    else:
                        rest.append(m)
                if len(members) >= 2:
                    groups.append(Group(members))
                remaining = rest
        groups.sort(key=lambda g: -sum(int(ft.size[m.idx]) for m in g.members[1:]))
        return groups
