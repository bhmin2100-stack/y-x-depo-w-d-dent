@echo off
setlocal
cd /d "%~dp0"

if exist "dist\DentDepositionModel.exe" (
    start "" "dist\DentDepositionModel.exe"
) else (
    python -c "import PySide6" >nul 2>nul
    if errorlevel 1 (
        python -m pip install -r requirements_windows.txt
    )
    python desktop_app.py
)
