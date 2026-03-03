@echo off
title SENTINEL Installer
echo.
echo  ========================================
echo   SENTINEL - AI Face and Gesture System
echo   One-Click Installer for Windows
echo  ========================================
echo.
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install from python.org
    pause
    exit /b 1
)
if not exist ".venv" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
)
echo [2/3] Installing dependencies...
call .venv\Scripts\activate.bat
pip install --upgrade pip >nul 2>nul
pip install -r requirements.txt
echo [3/3] Downloading AI models...
python -c "from modules.face_recognition import ensure_face_model, ensure_hand_model; ensure_face_model(); ensure_hand_model()"
echo.
echo  Installation Complete!
echo  Run: double-click run_sentinel.bat
echo  Browser: http://localhost:8501
pause
