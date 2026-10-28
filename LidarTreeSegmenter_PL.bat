@echo off
REM ================================================================
REM  LidarTreeSegmenter - okno programu.
REM  Kliknij dwa razy, albo przeciagnij skan (.laz/.las) na ten plik -
REM  wtedy liczenie zacznie sie samo.
REM ================================================================
cd /d "%~dp0"

set "LTS_LANG=pl"
where pythonw >nul 2>nul
if errorlevel 1 (
    where python >nul 2>nul
    if errorlevel 1 (
        echo.
        echo  Nie widze Pythona. Zainstaluj go z python.org
        echo  ^(zaznacz przy instalacji "Add Python to PATH"^).
        echo.
        pause
        exit /b
    )
    python "%~dp0program\LidarTreeSegmenter_okno.py" %*
    exit /b
)
start "" pythonw "%~dp0program\LidarTreeSegmenter_okno.py" %*
