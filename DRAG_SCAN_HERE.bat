@echo off
REM ================================================================
REM  DRAG YOUR SCAN (.laz or .las) ONTO THIS FILE WITH THE MOUSE.
REM  ENGLISH version. It does everything in order:
REM    1. finds the trees and measures DBH      (tree_segmenter_tool)
REM    2. splits them into stem, branches and foliage   (LidarTreeSegmenter)
REM    3. makes an Excel report with volume and a GeoPackage  (LidarTreeSegmenter)
REM    4. makes a 3D view of the cloud for the browser (HTML) (LidarTreeSegmenter)
REM  All results go to LidarTreeSegmenter\wyniki\<scan_name>
REM ================================================================
cd /d "%~dp0"
set "LTS_LANG=en"

if "%~1"=="" (
    echo.
    echo  No scan given.
    echo  Grab a .laz file with the mouse and drop it ONTO THIS FILE ^(DRAG_SCAN_HERE.bat^).
    echo.
    pause
    exit /b
)

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo  Python not found. Install it from python.org
    echo  ^(tick "Add Python to PATH" during installation^), then run INSTALL_ONCE.bat
    echo.
    pause
    exit /b
)

REM Check the libraries - if something is missing, install it into THE SAME Python
python -c "import laspy, lazrs, numpy, pandas, scipy, sklearn, matplotlib, openpyxl" >nul 2>nul
if errorlevel 1 (
    echo.
    echo  Libraries are missing - installing them now ^(first time only^)...
    python -m pip install laspy lazrs numpy pandas scipy scikit-learn matplotlib openpyxl
    python -c "import laspy, lazrs, numpy, pandas, scipy, sklearn, matplotlib, openpyxl" >nul 2>nul
    if errorlevel 1 (
        echo.
        echo  Installation failed - the message is above. Copy it and paste it to Claude.
        pause
        exit /b
    )
)

set "SKAN=%~f1"
set "NAZWA=%~n1"
set "WYNIKI=%~dp0wyniki\%NAZWA%"
set "STARE=%~dp0..\tree_segmenter_tool\results\%NAZWA%"

echo.
echo  Scan:     %SKAN%
echo  Results:  %WYNIKI%
echo.

REM Result of an earlier run in tree_segmenter_tool\results - move it here
REM Older results (loose files) - sort them into subfolders
if exist "%WYNIKI%" python "%~dp0program\lts_uklad.py" "%WYNIKI%" >nul

set "SEG=%WYNIKI%\02_CHMURY\%NAZWA%_segmenty.laz"
if not exist "%SEG%" if exist "%STARE%\%NAZWA%_segmenty.laz" (
    echo  Moving the earlier result from tree_segmenter_tool\results to LidarTreeSegmenter\wyniki...
    if not exist "%WYNIKI%" mkdir "%WYNIKI%"
    move /y "%STARE%\*" "%WYNIKI%\" >nul
    rmdir "%STARE%" 2>nul
    python "%~dp0program\lts_uklad.py" "%WYNIKI%" >nul
)

if exist "%SEG%" (
    echo  === 1/4  Trees already found earlier - skipping ===
    echo          ^(to compute again, delete 02_CHMURY\%NAZWA%_segmenty.laz^)
) else (
    echo  === 1/4  Searching for trees - this may take 10-20 minutes ===
    python "%~dp0program\05_wykryj_drzewa.py" "%SKAN%" --wyniki "%~dp0wyniki"
    python "%~dp0program\lts_uklad.py" "%WYNIKI%" >nul
)
if not exist "%SEG%" goto blad

echo.
echo  === 2/4  Splitting trees into stem, branches and foliage ===
python "%~dp0program\10_pien_galezie_liscie.py" "%SEG%" --wyniki "%~dp0wyniki"
if errorlevel 1 goto blad

echo.
echo  === 3/4  Excel report and volume ===
python "%~dp0program\30_raport.py" "%WYNIKI%"
if errorlevel 1 goto blad

echo.
echo  === 4/4  3D view in the browser ===
python "%~dp0program\40_widok_3d.py" "%WYNIKI%"

echo.
echo  ================================================================
echo   DONE. Everything is in one folder:
echo     %WYNIKI%
echo  ================================================================
explorer "%WYNIKI%"
pause
exit /b

:blad
echo.
echo  Something went wrong - the error message is above.
echo  Copy it and paste it to Claude.
pause
