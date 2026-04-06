@echo off
REM Briefing Bot — Quick launcher for Windows
REM Double-click this file or run it from PowerShell/CMD

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Setting up virtual environment for the first time...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

python main.py run
pause
