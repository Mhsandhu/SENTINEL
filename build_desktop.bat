@echo off
:: ═══════════════════════════════════════════════════════════════════
::  SENTINEL Desktop — Build Script
::  Creates SENTINEL.exe in  dist\SENTINEL\
:: ═══════════════════════════════════════════════════════════════════
title SENTINEL Build
color 0A
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║   SENTINEL Desktop Application — Build Tool     ║
echo  ╚══════════════════════════════════════════════════╝
echo.

:: ── Check Python venv ────────────────────────────────────────────
set VENV=..\.venv\Scripts
if not exist "%VENV%\python.exe" (
    echo [ERROR] Virtual-env not found at %VENV%
    echo         Run setup.bat first, then try again.
    pause
    exit /b 1
)

set PYTHON=%VENV%\python.exe
set PIP=%VENV%\pip.exe

:: ── Ensure build deps ────────────────────────────────────────────
echo [1/4] Checking build dependencies ...
%PIP% install pywebview pyinstaller --quiet 2>nul

:: ── Clean previous build ─────────────────────────────────────────
echo [2/4] Cleaning previous build ...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

:: ── Run PyInstaller ──────────────────────────────────────────────
echo [3/4] Building SENTINEL.exe  (this may take several minutes) ...
echo.
%PYTHON% -m PyInstaller SENTINEL.spec --noconfirm --clean

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Build failed. Check output above for details.
    pause
    exit /b 1
)

:: ── Copy extra runtime files ─────────────────────────────────────
echo [4/4] Copying runtime resources ...

:: Copy database and vault dirs (empty structure)
if not exist "dist\SENTINEL\database" mkdir "dist\SENTINEL\database"
if not exist "dist\SENTINEL\vault_storage" mkdir "dist\SENTINEL\vault_storage"

:: Copy .streamlit config (may already be there from spec, but ensure)
if not exist "dist\SENTINEL\.streamlit" mkdir "dist\SENTINEL\.streamlit"
copy /y ".streamlit\config.toml" "dist\SENTINEL\.streamlit\" >nul 2>nul

:: Copy models
if not exist "dist\SENTINEL\models" mkdir "dist\SENTINEL\models"
copy /y "models\*.task" "dist\SENTINEL\models\" >nul 2>nul

echo.
echo  ══════════════════════════════════════════════════
echo   BUILD COMPLETE
echo   Output:  dist\SENTINEL\SENTINEL.exe
echo  ══════════════════════════════════════════════════
echo.
echo  You can now:
echo    1. Run  dist\SENTINEL\SENTINEL.exe  directly
echo    2. Use Inno Setup with setup_installer.iss
echo       to create a proper installer .exe
echo.
pause
