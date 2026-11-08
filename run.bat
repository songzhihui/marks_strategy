@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
    echo Python was not found. Please install Python and add it to PATH.
    pause
    exit /b 1
)
python gui.py
if errorlevel 1 (
    echo.
    echo Failed to start. Please check the error above.
    pause
    exit /b 1
)
endlocal
