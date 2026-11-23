# Third-party notices

Duplicate Image Finder's own source code is licensed under the MIT License (see `LICENSE`).
It uses the following third-party software. The packaged apps (Windows exe, Linux AppImage / .deb /
.rpm, macOS .dmg) bundle the components marked **bundled**; the others are only used when running
from source.

| Component | Used for | License | In the packaged apps |
|---|---|---|---|
| [Python](https://www.python.org/) | runtime | PSF License | bundled |
| [Qt 6](https://www.qt.io/) / [PySide6](https://doc.qt.io/qtforpython-6/) | user interface | LGPL-3.0 | bundled (as separate, replaceable DLLs) |
| [ONNX Runtime](https://onnxruntime.ai/) (DirectML build on Windows) | AI model and GPU search | MIT | bundled |
| [DirectML](https://github.com/microsoft/DirectML) | GPU access on Windows | Microsoft redistributable (shipped with ONNX Runtime) | bundled (Windows only) |
| [DINOv2](https://github.com/facebookresearch/dinov2) model weights (ViT-S/14, Meta AI) | image features | Apache-2.0 | bundled (converted to ONNX) |
| [OpenCV](https://opencv.org/) (`opencv-python-headless`) | keypoint matching | Apache-2.0 | bundled |
| [NumPy](https://numpy.org/) | numerics | BSD-3-Clause | bundled |
| [Pillow](https://python-pillow.org/) | image decoding | MIT-CMU (HPND) | bundled |
| [pi-heif](https://github.com/bigcat88/pillow_heif) | HEIC / HEIF (decode only) | BSD-3-Clause; bundles libheif (LGPL-3.0) and libde265 (LGPL-3.0) | bundled |
| [pillow-jxl-plugin](https://github.com/Isotr0py/pillow-jpegxl-plugin) | JPEG XL | GPL-3.0-or-later | no — optional when running from source; never bundled |
| [rawpy](https://github.com/letmaik/rawpy) / LibRaw | camera RAW | MIT / LGPL-2.1 or CDDL-1.0 | bundled |
| [Send2Trash](https://github.com/arsenetar/send2trash) | Recycle Bin | BSD-3-Clause | bundled |
| [PyInstaller](https://pyinstaller.org/) bootloader | packaging | GPL-2.0 with bootloader exception | bundled |
| [PyTorch](https://pytorch.org/), [timm](https://github.com/huggingface/pytorch-image-models) | optional CUDA mode, model export | BSD-3-Clause, Apache-2.0 | no |

The full license texts of the bundled packages are included in their folders inside
`data\app\_internal\` (Windows single exe), `_internal/` (folder builds and Linux packages) or
`Contents/Frameworks/` (macOS app), where the packages provide them.
