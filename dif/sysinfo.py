"""Computer resources and the work sizes derived from them.

The scan adapts to the machine: GPU batch sizes follow the graphics card's memory
(VRAM), worker processes and in-memory buffers follow the free system RAM. Small
GPUs get small batches (measured: keypoint matching costs ~150 MB of VRAM per pair
per GPU call, with almost no speed difference between 1 and 16 pairs), and if the
GPU still runs out, the GPU code halves its batch and retries before falling back
to the CPU.

For testing, DIF_SIM_VRAM_MB / DIF_SIM_RAM_MB pretend a smaller machine.
"""

import ctypes
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass


# ---------------------------------------------------------------- system RAM
def ram_mb():
    """(total, available) system memory in MB, best effort."""
    total = avail = 0
    try:
        if sys.platform == "win32":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEMORYSTATUSEX()
            m.dwLength = ctypes.sizeof(m)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            total, avail = m.ullTotalPhys >> 20, m.ullAvailPhys >> 20
        elif sys.platform == "darwin":
            total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                                       timeout=5).stdout) >> 20
            vm = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5).stdout
            page = 16384 if "16384" in vm.splitlines()[0] else 4096
            pages = sum(int(ln.split(":")[1].strip(" .")) for ln in vm.splitlines()
                        if ln.startswith(("Pages free", "Pages inactive", "Pages speculative")))
            avail = pages * page >> 20
        else:
            info = {}
            with open("/proc/meminfo") as f:
                for ln in f:
                    k, v = ln.split(":", 1)
                    info[k] = int(v.split()[0]) >> 10          # kB -> MB
            total, avail = info.get("MemTotal", 0), info.get("MemAvailable", info.get("MemFree", 0))
    except Exception:
        pass
    sim = os.environ.get("DIF_SIM_RAM_MB")
    if sim:
        total = avail = int(sim)
    return int(total), int(avail or total // 2)


# ---------------------------------------------------------------- GPU memory
class _GUID(ctypes.Structure):
    _fields_ = [("data", ctypes.c_ubyte * 16)]

    def __init__(self, s):
        super().__init__()
        ctypes.memmove(self.data, uuid.UUID(s).bytes_le, 16)


def _dxgi_vram_mb():
    """Dedicated memory of the first hardware adapter (the one DirectML uses)."""
    class DESC1(ctypes.Structure):
        _fields_ = [("Description", ctypes.c_wchar * 128), ("VendorId", ctypes.c_uint), ("DeviceId", ctypes.c_uint),
                    ("SubSysId", ctypes.c_uint), ("Revision", ctypes.c_uint),
                    ("DedicatedVideoMemory", ctypes.c_size_t), ("DedicatedSystemMemory", ctypes.c_size_t),
                    ("SharedSystemMemory", ctypes.c_size_t), ("LuidLow", ctypes.c_uint32),
                    ("LuidHigh", ctypes.c_int32), ("Flags", ctypes.c_uint)]

    def call(obj, index, *args, argtypes=()):
        vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtbl[index])(obj, *args)

    factory = ctypes.c_void_p()
    if ctypes.windll.dxgi.CreateDXGIFactory1(ctypes.byref(_GUID("{770aae78-f26f-4dba-a829-253c83d1b387}")),
                                             ctypes.byref(factory)) != 0:
        return 0
    try:
        for i in range(8):
            adapter = ctypes.c_void_p()
            if call(factory, 12, ctypes.c_uint(i), ctypes.byref(adapter),            # EnumAdapters1
                    argtypes=(ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))) != 0:
                break
            d = DESC1()
            call(adapter, 10, ctypes.byref(d), argtypes=(ctypes.POINTER(DESC1),))     # GetDesc1
            call(adapter, 2)                                                           # Release
            if not d.Flags & 2:                                                        # not the software adapter
                return d.DedicatedVideoMemory >> 20
    finally:
        call(factory, 2)
    return 0


def vram_mb(device):
    """Memory of the GPU used for `device` in MB (0 = unknown / no GPU)."""
    mb = 0
    try:
        if device == "dml" and sys.platform == "win32":
            mb = _dxgi_vram_mb()
        elif device == "cuda":
            from . import cuda
            if cuda.available():
                mb = cuda.torch.cuda.get_device_properties(0).total_memory >> 20
        elif device == "coreml":
            mb = ram_mb()[0]                 # Apple Silicon: unified memory
    except Exception:
        mb = 0
    sim = os.environ.get("DIF_SIM_VRAM_MB")
    if sim and device != "cpu":
        mb = int(sim)
    return int(mb)


# ---------------------------------------------------------------- work sizes
MATCH_MB_PER_PAIR = 150     # DirectML keypoint matching, measured per pair in one GPU call


@dataclass
class Budget:
    vram_mb: int = 0
    ram_total_mb: int = 0
    ram_avail_mb: int = 0
    workers: int = 1                # decoding processes
    embed_batch: int = 128          # images per AI-model call
    match_batch: int = 8            # image pairs per keypoint-matching call (DirectML)
    ransac_budget: int = 4096       # pairs x padded matches per pre-check call (DirectML)
    gpu_score_elems: int = int(2.56e8)   # nearest-neighbour score block on the GPU
    gpu_key_shard: int = 1 << 20    # keys per GPU search session (DirectML)
    cpu_score_rows: int = 1024      # rows per NumPy score block (x 65536 keys)
    keypoint_sets: int = 8000       # keypoint sets kept in RAM during the crop check

    def describe(self):
        gpu = f"{self.vram_mb / 1024:.1f} GB VRAM" if self.vram_mb else "no GPU memory info"
        return (f"Resources: {gpu}, RAM {self.ram_avail_mb / 1024:.1f} of {self.ram_total_mb / 1024:.1f} GB free -> "
                f"{self.workers} workers, AI batch {self.embed_batch}, match batch {self.match_batch}, "
                f"keypoint cache {self.keypoint_sets}")


def plan(device, workers=0):
    """Work sizes for this computer and device ("cuda" | "dml" | "coreml" | "cpu")."""
    total, avail = ram_mb()
    vram = vram_mb(device)
    b = Budget(vram_mb=vram, ram_total_mb=total, ram_avail_mb=avail)

    # --- RAM: each decoding process needs ~350 MB at peak (large photos); keep 1 GB spare
    cpus = os.cpu_count() or 2
    by_ram = max(1, (avail - 1024) // 350) if avail else cpus
    b.workers = workers or int(max(1, min(24, cpus - 1, by_ram)))
    b.keypoint_sets = int(max(500, min(8000, avail * 0.10 / 0.12))) if avail else 2000
    b.cpu_score_rows = 1024 if avail >= 4096 or not avail else 256

    # --- GPU: use about a third of the card, at most 2 GB (more does not make it faster)
    if device in ("dml", "cuda", "coreml"):
        if not vram:
            vram = 2048                                     # unknown: assume a small card
        budget = min(2048, vram * 0.35)
        b.match_batch = int(max(1, min(8, budget * 0.5 // MATCH_MB_PER_PAIR)))
        b.ransac_budget = 4096 if budget >= 1000 else 1024
        b.embed_batch = 128 if vram >= 4096 else (64 if vram >= 2048 else 32)
        b.gpu_score_elems = int(max(1 << 24, min(2.56e8, budget * 0.4 * (1 << 20) / 2)))
        # keys stay on the GPU while searching (384 fp16 values = 768 bytes each)
        b.gpu_key_shard = int(max(1 << 16, min(1 << 20, budget * 0.3 * (1 << 20) / 768)))
    return b


_current = Budget()


def set_current(b):
    global _current
    _current = b


def current():
    """The work sizes of the scan in progress (defaults before the first scan)."""
    return _current
