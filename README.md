# Duplicate Image Finder

A fast desktop app for **Windows, Linux and macOS** that finds duplicate images — exact copies, resized or re-compressed
copies, images saved in another format, and **cropped** copies — and helps you keep the
best one. It uses your GPU when it can and falls back to the CPU when it can't.

<!-- TODO: add a screenshot, e.g. docs/screenshot.png -->
<!-- ![Duplicate Image Finder](docs/screenshot.png) -->

## Features

- **Finds every kind of duplicate**
  - Exact copies (byte-identical files)
  - Similar copies: resized, re-compressed or converted (e.g. PNG → JPG)
  - Cropped copies, found with an AI model (DINOv2) and confirmed by keypoint matching
- **Keeps the best copy by default** — highest resolution, then the better format, then the larger file
- **GPU accelerated** — Windows: any DirectX 12 GPU (NVIDIA, AMD, Intel) through DirectML;
  macOS: Apple GPU / Neural Engine through Core ML; NVIDIA CUDA when running from source with PyTorch
  (Windows and Linux); automatic fallback to the CPU
- **Scales to large libraries** — tested on 33,000 images; designed for hundreds of thousands to millions.
  Results are cached, so a rescan of an unchanged folder takes seconds
- **Many formats** — JPG, JPEG, PNG, WebP, GIF, BMP, TIFF, AVIF, HEIC/HEIF, JPEG 2000, PSD,
  ICO, DDS, TGA, and camera RAW (CR2, CR3, NEF, ARW, DNG, ORF, RAF, RW2), among others.
  JPEG XL is supported when running from source (its plugin is GPL-licensed, so the packaged apps leave it out)
- **Review before anything happens**
  - Side-by-side preview and a full-size viewer (zoom, pan, arrow keys)
  - Sort by name, match, resolution, size, date, format or folder; reorder and hide columns
  - Tick / untick files per group; *Select* menu shortcuts for common choices
- **Safe actions** — move duplicates to a folder (keeping the folder structure), send them to the
  Recycle Bin, or delete them permanently. One copy of every group is always kept
- **Exceptions** — keep look-alike images that are *not* duplicates, such as the pages of one post
  (`12345678_p0`, `12345678_p1`) or a numbered series (`image_01`, `image_02`)
- **Groups you keep are remembered** — groups where you keep every file are hidden from later scans
  (with a *Show hidden* button to bring them back)
- **Save your progress** — save or export a scan with your selections (readable XML) and load it later,
  even after clearing the cache
- **English, 繁體中文, 简体中文, 日本語** — light and dark theme

## Download and run

Get the file for your system from the [Releases](../../releases) page. No Python needed.

| System | File | |
|---|---|---|
| Windows 10 / 11 (64-bit) | `DuplicateImageFinder-<version>-Windows-x64.exe` | single portable exe |
| Linux (x86-64) | `DuplicateImageFinder-<version>-x86_64.AppImage` | runs on most distros |
| Ubuntu / Debian | `duplicate-image-finder_<version>_amd64.deb` | installs to `/opt`, adds a menu entry |
| Fedora / openSUSE | `duplicate-image-finder-<version>-1.x86_64.rpm` | installs to `/opt`, adds a menu entry |
| macOS 12+ (Apple Silicon) | `DuplicateImageFinder-<version>-macOS-arm64.dmg` | drag the app to Applications |

> **GPU in the downloads:** the Windows exe uses **DirectML**, which works on any DirectX 12 GPU
> (NVIDIA, AMD, Intel) — including NVIDIA cards, which show as "(DirectML)" in the status bar.
> The Mac app uses Core ML; the Linux packages use the CPU.
> **NVIDIA CUDA** is faster on large first scans (up to about 2×) but is **not included in the downloads**
> (it needs about 3 GB of PyTorch and NVIDIA libraries). To use CUDA, clone the repository and run
> from source — see [Optional: NVIDIA CUDA](#optional-nvidia-cuda).

### Windows

1. Put the exe in any folder you can write to (Desktop, Documents, a USB drive — not *Program Files*).
2. Double-click it. The first launch unpacks the app next to the exe (about 10–20 seconds);
   later launches start right away.

> **Windows SmartScreen** may show "Windows protected your PC" on first run because the exe is not
> code-signed. Click **More info → Run anyway**.

After the first run the folder looks like this:

```
DuplicateImageFinder.exe   ← the only file you need to copy or share
data\        settings and cache (data\app\ holds the unpacked program)
logs\        only if you turn on logging
```

### Linux

```bash
chmod +x DuplicateImageFinder-*-x86_64.AppImage
./DuplicateImageFinder-*-x86_64.AppImage
```

or install a package: `sudo apt install ./duplicate-image-finder_*_amd64.deb` (Ubuntu / Debian) or
`sudo dnf install ./duplicate-image-finder-*.x86_64.rpm` (Fedora), then start it from the app menu or with
`duplicate-image-finder`. Settings and cache are kept in `~/.local/share/DuplicateImageFinder`.

### macOS

Open the `.dmg` and drag **Duplicate Image Finder** to **Applications**. The app is not notarized by
Apple, so the first time **right-click the app → Open → Open** (or allow it in *System Settings →
Privacy & Security*). Settings and cache are kept in `~/Library/Application Support/DuplicateImageFinder`.

## How to use

1. **Add folders** (or drag them onto the list). Untick *Subfolders* to scan a folder on its own.
2. Press **Scan**. The status bar shows the current stage and the time left.
3. Review the groups. In each group the best copy is kept (★) and the others are ticked for **REMOVE**.
   Click a group to preview it; double-click an image to open the viewer.
4. Choose what happens to ticked files — **Move to folder**, **Recycle Bin** or **Delete permanently** —
   and press **Apply**.

Tips:

- **Visual similarity** (default 89%) controls how close resized / re-compressed copies must be.
- **Crop match** (default 80%): lower finds smaller crops but checks more pairs.
- **File → Save progress** keeps your selections for these folders; **Export scan…** writes them to an XML file.
- **Settings → Device** chooses *Auto* (GPU if available) or *CPU only*.

## How it works

| Stage | What happens | Runs on |
|---|---|---|
| Analyze | Each image is decoded once; a perceptual hash, a small color fingerprint and an AI feature vector (DINOv2-small) are computed and cached | CPU + GPU |
| Exact copies | Files of the same size are compared by hash | CPU |
| Similar copies | Nearest-neighbor search on perceptual hashes, confirmed by the AI features | CPU / GPU |
| Cropped copies | Nearest-neighbor search on AI features finds candidates; ORB keypoints and a RANSAC homography confirm that one image contains the other | GPU + CPU |
| Grouping | Matches are grouped and the best-quality file of each group is kept | CPU |

Everything runs locally. No images or file names leave your computer.

## Run from source

Requirements: Python 3.13 (64-bit) on Windows 10/11, Linux or macOS 12+.

```bat
run.bat          :: Windows
```

```bash
./run.sh         # Linux / macOS
```

Both create a virtual environment in `.venv`, install `requirements.txt` and the optional format
plugins (`requirements-optional.txt`: HEIF, RAW, and JPEG XL), and start the app.

### Optional: NVIDIA CUDA

CUDA is only available when running from source; the downloadable apps never include it
(Windows uses DirectML, macOS Core ML, Linux the CPU). With an NVIDIA GPU and a recent driver:

1. Clone the repository and start it once, so `run.bat` / `run.sh` creates `.venv`:

   ```bash
   git clone https://github.com/benfy95/duplicate-image-finder.git
   cd duplicate-image-finder
   ```

   then run `run.bat` (Windows) or `./run.sh` (Linux) and close the app.

2. Install PyTorch with CUDA into that environment (about 3 GB):

   ```bat
   .venv\Scripts\python -m pip install -r requirements-cuda.txt --index-url https://download.pytorch.org/whl/cu128 --extra-index-url https://pypi.org/simple
   ```

   On Linux use `.venv/bin/python` instead of `.venv\Scripts\python`.

3. Start the app again with `run.bat` / `./run.sh`. With **Settings → Device → Auto**, the status bar
   shows "GPU: … (CUDA)". CUDA runs the AI model, the nearest-match search and the keypoint pre-check
   on the GPU.

### Build the packages

Each system builds its own packages (PyInstaller cannot cross-compile). All builds use a clean
environment (`.venv-build`) without PyTorch or GPL plugins and write to `release/`.

| System | Command | Output |
|---|---|---|
| Windows | `build.bat` | `release\DuplicateImageFinder.exe` (single self-unpacking exe), `dist\DuplicateImageFinder\` (folder) |
| Linux | `bash packaging/linux/build_linux.sh` | AppImage, `.deb`, `.rpm` (the last two need `fpm` and `rpmbuild`) |
| macOS | `bash packaging/macos/build_macos.sh` | `.dmg` for the Mac's own architecture |

The Windows single-file launcher (`launcher\Launcher.cs`) is compiled with the C# compiler that ships
with Windows; nothing extra to install.

### Release with GitHub Actions

`.github/workflows/release.yml` builds and tests all of the above on GitHub's Windows, Linux and macOS
machines. Push a version tag to get a **draft** release with every file attached:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Each build is checked with a headless scan of generated test images (`tools/smoke_test.py`) before it
is attached. Review the draft on the Releases page, then publish it.

### Project layout

```
main.py                 entry point (GUI, or --cli for a headless scan)
dif\                    the app: scan engine, cache, features, GUI, translations
models\                 ONNX models (DINOv2 feature model and small GPU helper graphs)
tools\                  developer scripts: export the models, build the icon, pack the exe
launcher\               C# source of the single-file launcher
packaging\              Linux (AppImage / .deb / .rpm) and macOS (.dmg) build scripts
.github\workflows\      GitHub Actions: build, test and draft a release for all systems
run.bat / run.sh        run from source (Windows / Linux, macOS)
build.bat               build the Windows release
```

The ONNX models in `models\` are generated by `tools\export_onnx.py`, `tools\export_knn.py`,
`tools\export_orbmatch.py` and `tools\export_ransac.py` (needs `requirements-dev.txt`).

## Benchmarks

On an RTX 3090 with a 32-thread CPU:

| Library | CPU only | DirectML | CUDA |
|---|---|---|---|
| 8,726 images, first scan | 175 s | 31 s | 24 s |
| 33,049 images, first scan | — | 46 s | 22 s |
| 8,726 images, cached rescan | — | — | 2 s |

Your numbers will depend on your GPU, CPU, and especially the disk the images are on.

## Credits

Created by **Ben** ([benfy95](https://github.com/benfy95), [ben@benfy95.net](mailto:ben@benfy95.net)), with **Claude** (Anthropic).

Built with [PySide6 (Qt)](https://doc.qt.io/qtforpython-6/), [ONNX Runtime](https://onnxruntime.ai/)
(DirectML / Core ML), [OpenCV](https://opencv.org/), [Pillow](https://python-pillow.org/), NumPy, and the
[DINOv2](https://github.com/facebookresearch/dinov2) model (Meta AI, Apache 2.0) via
[timm](https://github.com/huggingface/pytorch-image-models).

## License

[MIT](LICENSE) © 2026 Ben (benfy95). Third-party components and their licenses are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
