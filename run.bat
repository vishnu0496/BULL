@echo off
SETLOCAL EnableDelayedExpansion

echo ===================================================
echo   BULL: Local Indian Stock Research Dashboard
echo ===================================================

REM Check if Python is installed
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: Python is not installed or not in system PATH.
    echo Please install Python 3.8+ and try again.
    pause
    exit /b 1
)

REM Create virtual environment if it does not exist
if not exist .venv (
    echo [1/3] Creating virtual environment in .venv...
    python -m venv .venv
    if !ERRORLEVEL! neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Virtual environment found (.venv).
)

REM Install dependencies
echo [2/3] Installing/Updating dependencies...
.venv\Scripts\python -m pip install --upgrade pip >nul
.venv\Scripts\python -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

echo [3/3] Launching FastAPI Web Application...
.venv\Scripts\python -m uvicorn api.server:app --host 127.0.0.1 --port 8501 --reload

pause
