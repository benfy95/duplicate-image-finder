@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Duplicate Image Finder
set "PYTHONUTF8=1"
set "VENV=%~dp0.venv"
set "PY=%VENV%\Scripts\python.exe"

rem ---------- 1. virtual environment ----------
if exist "%PY%" goto :have_venv
echo [setup] Creating virtual environment in .venv ...
py -3 -m venv "%VENV%" 2>nul
if not exist "%PY%" python -m venv "%VENV%"
if not exist "%PY%" (
    echo [error] Could not create a virtual environment. Is Python 3.10+ installed and on PATH?
    goto :fail
)
:have_venv

rem ---------- 2. dependencies (re-run when requirements change) ----------
set "STAMP=%VENV%\deps_installed.txt"
if not exist "%STAMP%" goto :install
copy /b requirements.txt+requirements-optional.txt "%VENV%\deps_now.txt" >nul
fc /b "%VENV%\deps_now.txt" "%STAMP%" >nul 2>nul
if errorlevel 1 goto :install
goto :launch

:install
echo [setup] Installing dependencies (about 250 MB) ...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

for /f "usebackq eol=# tokens=*" %%P in ("requirements-optional.txt") do (
    "%PY%" -m pip install "%%P" || echo [warn] Optional package %%P failed to install - that format will be unavailable.
)
copy /b requirements.txt+requirements-optional.txt "%STAMP%" >nul

rem ---------- 3. launch ----------
:launch
if not exist "models\dinov2_vits14_224.onnx" echo [warn] models\dinov2_vits14_224.onnx is missing - crop detection will be disabled.
echo [run] Starting Duplicate Image Finder ...
"%PY%" main.py %*
if errorlevel 1 (
    echo.
    echo [error] The program exited with an error. See the messages above.
    pause
)
exit /b 0

:fail
echo.
echo [error] Setup failed. See the messages above.
pause
exit /b 1
