@echo off
REM Run once, on first use. Installs the required libraries.
cd /d "%~dp0"
python -m pip install -r requirements.txt
echo.
echo  Done. Now start LidarTreeSegmenter.bat (window) or drag a scan onto DRAG_SCAN_HERE.bat
pause
