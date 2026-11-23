# PyInstaller spec for Windows, Linux and macOS. Build on each OS (PyInstaller
# cannot cross-compile), in a clean venv without PyTorch:
#   Windows  build.bat                      -> dist\DuplicateImageFinder\ (+ release\*.exe)
#   Linux    packaging/linux/build_linux.sh -> dist/DuplicateImageFinder/ (+ AppImage, .deb, .rpm)
#   macOS    packaging/macos/build_macos.sh -> dist/Duplicate Image Finder.app (+ .dmg)

import os
import re
import sys

block_cipher = None
WIN, MAC = sys.platform == "win32", sys.platform == "darwin"
with open(os.path.join("dif", "__init__.py"), encoding="utf-8") as f:
    VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', f.read()).group(1)

# Things that must never be bundled (dev-only or unused, and huge).
EXCLUDES = [
    "torch", "torchvision", "timm", "onnx", "onnxscript", "onnx_ir", "sympy", "networkx",
    # GPL-licensed format plugins: keep the app MIT-compatible (HEIF uses pi_heif instead)
    "pillow_jxl", "pillow_jxl_plugin", "pillow_heif",
    "tkinter", "matplotlib", "IPython", "scipy", "pandas", "pytest", "setuptools",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtPdf", "PySide6.QtNetwork", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtOpenGL",
]

# Unneeded large binaries pulled in by hooks (matched anywhere in the file name).
DROP_BINARIES = (
    "opengl32sw.dll",          # Qt software OpenGL fallback (widgets don't need it)
    "opencv_videoio_ffmpeg",   # OpenCV video codecs (we only read still images)
    "Qt6Pdf", "Qt6Quick", "Qt6Qml", "Qt6Network", "Qt6VirtualKeyboard", "Qt6OpenGL",
    "QtPdf", "QtQuick", "QtQml", "QtNetwork", "QtVirtualKeyboard",   # macOS framework names
)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("models/dinov2_vits14_224.onnx", "models"), ("models/dinov2_vits14_224_fp16.onnx", "models"),
           ("models/knn_fp16.onnx", "models"), ("models/knn_fp32.onnx", "models"),
           ("models/orb_match_fp16.onnx", "models"), ("models/ransac_support.onnx", "models"),
           ("assets/icon.ico", "assets"), ("assets/icon_512.png", "assets"),
           ("LICENSE", "."), ("THIRD_PARTY_NOTICES.md", ".")],
    hiddenimports=["dif.worker", "dif.onnx_min", "dif.lang_zh_cn", "dif.lang_ja", "pi_heif", "rawpy", "send2trash"],
    excludes=EXCLUDES,
    noarchive=False,
    cipher=block_cipher,
)
a.binaries = [b for b in a.binaries if not any(d.lower() in b[0].lower() for d in DROP_BINARIES)]
a.datas = [d for d in a.datas if not d[0].replace("\\", "/").startswith("PySide6/translations/qtwebengine")]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DuplicateImageFinder",
    console=False,             # GUI app: no console window
    icon="assets/icon.ico" if WIN else ("assets/icon.icns" if MAC else None),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="DuplicateImageFinder", upx=False)

if MAC:
    app = BUNDLE(
        coll,
        name="Duplicate Image Finder.app",
        icon="assets/icon.icns",
        bundle_identifier="io.github.benfy95.duplicateimagefinder",
        version=VERSION,
        info_plist={
            "CFBundleName": "Duplicate Image Finder",
            "CFBundleDisplayName": "Duplicate Image Finder",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,      # follow light / dark mode
            "LSMinimumSystemVersion": "12.0",
            "NSHumanReadableCopyright": "Copyright (c) 2026 Ben (benfy95). MIT License.",
        },
    )
