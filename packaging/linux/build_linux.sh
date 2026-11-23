#!/usr/bin/env bash
# Build the Linux packages: AppImage (runs on most distros), .deb and .rpm.
#
#   packaging/linux/build_linux.sh            # from the project folder
#
# Needs: python3.13 (or PYTHON=...), curl, and for .deb/.rpm: ruby + fpm, rpm (rpmbuild).
# Output in release/:
#   DuplicateImageFinder-<ver>-x86_64.AppImage
#   duplicate-image-finder_<ver>_amd64.deb
#   duplicate-image-finder-<ver>-1.x86_64.rpm
set -euo pipefail
cd "$(dirname "$0")/../.."

PY="${PYTHON:-python3.13}"
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' dif/__init__.py)
ARCH=x86_64
NAME=duplicate-image-finder
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

# ---- 2. PyInstaller folder build ----
"$VPY" -m PyInstaller --noconfirm --clean DuplicateImageFinder.spec
APP=dist/DuplicateImageFinder
test -x "$APP/DuplicateImageFinder"

# ---- 3. AppImage ----
APPDIR=build/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib/$NAME" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp -a "$APP/." "$APPDIR/usr/lib/$NAME/"
cp packaging/linux/$NAME.desktop "$APPDIR/$NAME.desktop"
cp packaging/linux/$NAME.desktop "$APPDIR/usr/share/applications/"
cp assets/icon_512.png "$APPDIR/$NAME.png"
cp assets/icon_512.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/$NAME.png"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/duplicate-image-finder/DuplicateImageFinder" "$@"
EOF
chmod +x "$APPDIR/AppRun"
TOOL=build/appimagetool-$ARCH.AppImage
if [ ! -x "$TOOL" ]; then
    curl -fsSL -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
    chmod +x "$TOOL"
fi
# --appimage-extract-and-run: works without FUSE (CI containers)
ARCH=$ARCH "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT/DuplicateImageFinder-$VER-$ARCH.AppImage"

# ---- 4. .deb and .rpm (installed to /opt, launcher in /usr/bin) ----
if command -v fpm >/dev/null 2>&1; then
    STAGE=build/pkgroot
    rm -rf "$STAGE"
    mkdir -p "$STAGE/opt/$NAME" "$STAGE/usr/bin" "$STAGE/usr/share/applications" \
             "$STAGE/usr/share/icons/hicolor/512x512/apps" "$STAGE/usr/share/doc/$NAME"
    cp -a "$APP/." "$STAGE/opt/$NAME/"
    ln -s "/opt/$NAME/DuplicateImageFinder" "$STAGE/usr/bin/$NAME"
    cp packaging/linux/$NAME.desktop "$STAGE/usr/share/applications/"
    cp assets/icon_512.png "$STAGE/usr/share/icons/hicolor/512x512/apps/$NAME.png"
    cp LICENSE THIRD_PARTY_NOTICES.md README.md "$STAGE/usr/share/doc/$NAME/"
    COMMON=(-s dir -C "$STAGE" -n "$NAME" -v "$VER" --license MIT
            --maintainer "Ben <ben@benfy95.net>" --url "https://github.com/benfy95/duplicate-image-finder"
            --description "Find exact, resized, re-encoded and cropped duplicate images")
    # Qt needs a few X11 / Wayland system libraries
    fpm "${COMMON[@]}" -t deb -a amd64 -p "$OUT/${NAME}_${VER}_amd64.deb" --force \
        -d libxcb-cursor0 -d libxkbcommon-x11-0 -d libegl1 -d libfontconfig1 -d libdbus-1-3 .
    if command -v rpmbuild >/dev/null 2>&1; then
        fpm "${COMMON[@]}" -t rpm -a x86_64 -p "$OUT/${NAME}-${VER}-1.x86_64.rpm" --force \
            -d xcb-util-cursor -d libxkbcommon-x11 -d mesa-libEGL -d fontconfig -d dbus-libs .
    else
        echo "[warn] rpmbuild not found: skipping .rpm"
    fi
else
    echo "[warn] fpm not found: skipping .deb / .rpm (gem install fpm)"
fi

echo "[done]"; ls -lh "$OUT"
