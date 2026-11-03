@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    python desktop.py %*
) else (
    py -3 desktop.py %*
)
pause
