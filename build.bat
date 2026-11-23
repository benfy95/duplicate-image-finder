@echo off
rem Builds the app for distribution. Double-click to rebuild after any change.
rem
rem   release\DuplicateImageFinder.exe   single ready-to-run exe (ship this one)
rem                                      - unpacks itself next to it on first launch
rem   dist\DuplicateImageFinder\         the same app as a plain folder
rem
rem Uses a clean venv (.venv-build) so nothing dev-only, like PyTorch, ends up in it.
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "BV=%~dp0.venv-build"
set "PY=%BV%\Scripts\python.exe"

if not exist "models\dinov2_vits14_224.onnx" (
    echo [error] models\dinov2_vits14_224.onnx is missing. Run tools\export_onnx.py first.
    goto :fail
)
if not exist "%PY%" (
    echo [build] Creating clean build environment .venv-build ...
    rem PYTHON=... picks a specific interpreter (used by GitHub Actions)
    if defined PYTHON (
        "%PYTHON%" -m venv "%BV%"
    ) else (
        py -3 -m venv "%BV%" 2>nul || python -m venv "%BV%"
    )
)
if not exist "%PY%" (
    echo [error] Could not create .venv-build. Is 64-bit Python 3.13 installed?
    goto :fail
)
"%PY%" -c "import sys, platform; print('[build] Python', sys.version.split()[0], platform.machine())"
echo [build] Checking build packages ...
"%PY%" -m pip install --upgrade pip -q
"%PY%" -m pip install -q -r requirements.txt "pyinstaller>=6.10"
if errorlevel 1 goto :fail
rem The JPEG XL plugin is GPL-3.0: keep it out of the MIT-licensed exe.
for /f "usebackq eol=# tokens=*" %%P in ("requirements-optional.txt") do (
    if /i not "%%P"=="pillow-jxl-plugin" "%PY%" -m pip install -q "%%P" || echo [warn] optional %%P not installed
)
"%PY%" -m pip uninstall -y -q pillow-jxl-plugin pillow-heif >nul 2>nul

echo [build] Step 1/2: PyInstaller (app folder) ...
"%PY%" -m PyInstaller --noconfirm --clean DuplicateImageFinder.spec
if errorlevel 1 goto :fail

echo [build] Step 2/2: packing the single exe ...
"%PY%" tools\pack_single_exe.py
if errorlevel 1 goto :fail

echo.
echo [done] release\DuplicateImageFinder.exe   ^<- ship this single file
echo        dist\DuplicateImageFinder\          (same app as a folder)
echo.
pause
exit /b 0

:fail
echo [error] Build failed.
pause
exit /b 1
