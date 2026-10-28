@echo off
REM ================================================================
REM  LidarTreeSegmenter - program window, ENGLISH version.
REM  Double-click it, or drag a scan (.laz/.las) onto this file -
REM  processing then starts by itself.
REM ================================================================
cd /d "%~dp0"
set "LTS_LANG=en"
where pythonw >nul 2>nul
if errorlevel 1 (
    where python >nul 2>nul
    if errorlevel 1 (
        echo.
        echo  Python not found. Install it from python.org
        echo  ^(tick "Add Python to PATH" during installation^).
        echo.
        pause
        exit /b
    )
    python "%~dp0program\LidarTreeSegmenter_okno.py" %*
    exit /b
)
start "" pythonw "%~dp0program\LidarTreeSegmenter_okno.py" %*
