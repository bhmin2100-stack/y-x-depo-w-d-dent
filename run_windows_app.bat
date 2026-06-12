@echo off
setlocal
cd /d "%~dp0"

if exist "dist\DentDepositionModel.exe" (
    start "" "dist\DentDepositionModel.exe"
) else (
    python desktop_app.py
)
