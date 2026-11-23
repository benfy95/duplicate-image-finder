#!/usr/bin/env bash
# Build the macOS app and disk image.
#
#   packaging/macos/build_macos.sh            # from the project folder, on a Mac
#
# Builds for the Mac's own architecture (Apple Silicon = arm64, Intel = x86_64).
# Needs: python3.13 (or PYTHON=...). Output in release/:
#   DuplicateImageFinder-<ver>-macOS-<arch>.dmg
#
# The app is ad-hoc signed only (no Apple Developer ID), so the first time users
# open it they right-click the app > Open (or allow it in System Settings >
# Privacy & Security).
set -euo pipefail
cd "$(dirname "$0")/../.."

PY="${PYTHON:-python3.13}"
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' dif/__init__.py)
ARCH=$(uname -m)                      # arm64 | x86_64
OUT=release
mkdir -p "$OUT"

# ---- 1. clean build environment (no PyTorch, no GPL plugins) ----
if [ ! -x .venv-build/bin/python ]; then
    "$PY" -m venv .venv-build
fi
VPY=.venv-build/bin/python
"$VPY" -m pip install -q --upgrade pip
"$VPY" -m pip install -q -r requirements.txt "pyinstaller>=6.10"
grep -v '^#' requirements-optional.txt | grep -v '^\s*$' | grep -vi 'jxl' | while read -r pkg; do
    "$VPY" -m pip install -q "$pkg" || echo "[warn] optional $pkg not installed"
done
"$VPY" -m pip uninstall -y -q pillow-jxl-plugin pillow-heif >/dev/null 2>&1 || true

# ---- 2. PyInstaller .app ----
"$VPY" -m PyInstaller --noconfirm --clean DuplicateImageFinder.spec
APP="dist/Duplicate Image Finder.app"
test -x "$APP/Contents/MacOS/DuplicateImageFinder"
codesign --force --deep --sign - "$APP"          # ad-hoc signature (required on Apple Silicon)

# ---- 3. .dmg with an Applications shortcut ----
STAGE=build/dmg
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp LICENSE THIRD_PARTY_NOTICES.md "$STAGE/"
DMG="$OUT/DuplicateImageFinder-$VER-macOS-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -volname "Duplicate Image Finder" -srcfolder "$STAGE" -ov -format UDZO "$DMG"

echo "[done]"; ls -lh "$OUT"
