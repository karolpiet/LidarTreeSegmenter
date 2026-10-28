@echo off
REM ================================================================
REM  PRZECIAGNIJ NA TEN PLIK SWOJ SKAN (.laz albo .las) MYSZKA.
REM  Zrobi wszystko po kolei:
REM    1. znajdzie drzewa i zmierzy piersnice  (tree_segmenter_tool)
REM    2. podzieli je na pien, galezie i ulistnienie   (LidarTreeSegmenter)
REM    3. zrobi raport Excel z miazszoscia i GeoPackage  (LidarTreeSegmenter)
REM    4. zrobi widok 3D chmury do przegladarki (HTML)   (LidarTreeSegmenter)
REM  Wszystkie wyniki laduja w LidarTreeSegmenter\wyniki\<nazwa_skanu>
REM ================================================================
cd /d "%~dp0"

set "LTS_LANG=pl"

if "%~1"=="" (
    echo.
    echo  Nie podales skanu.
    echo  Zlap plik .laz myszka i upusc go NA TEN PLIK ^(PRZECIAGNIJ_TU_SKAN.bat^).
    echo.
    pause
    exit /b
)

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo  Nie widze Pythona. Zainstaluj go z python.org
    echo  ^(zaznacz przy instalacji "Add Python to PATH"^), potem uruchom ZAINSTALUJ_RAZ.bat
    echo.
    pause
    exit /b
)

REM Sprawdz biblioteki - jesli czegos brakuje, doinstaluj do TEGO SAMEGO Pythona
python -c "import laspy, lazrs, numpy, pandas, scipy, sklearn, matplotlib, openpyxl" >nul 2>nul
if errorlevel 1 (
    echo.
    echo  Brakuje bibliotek - instaluje je teraz ^(tylko za pierwszym razem^)...
    python -m pip install laspy lazrs numpy pandas scipy scikit-learn matplotlib openpyxl
    python -c "import laspy, lazrs, numpy, pandas, scipy, sklearn, matplotlib, openpyxl" >nul 2>nul
    if errorlevel 1 (
        echo.
        echo  Instalacja sie nie udala - komunikat jest wyzej. Skopiuj go i wklej Claude'owi.
        pause
        exit /b
    )
)

set "SKAN=%~f1"
set "NAZWA=%~n1"
set "WYNIKI=%~dp0wyniki\%NAZWA%"
set "STARE=%~dp0..\tree_segmenter_tool\results\%NAZWA%"

echo.
echo  Skan:    %SKAN%
echo  Wyniki:  %WYNIKI%
echo.

REM Wynik z wczesniejszego przebiegu w tree_segmenter_tool\results - przenies tutaj
REM Starsze wyniki (pliki luzem) - poukladaj w podfoldery
if exist "%WYNIKI%" python "%~dp0program\lts_uklad.py" "%WYNIKI%" >nul

set "SEG=%WYNIKI%\02_CHMURY\%NAZWA%_segmenty.laz"
if not exist "%SEG%" if exist "%STARE%\%NAZWA%_segmenty.laz" (
    echo  Przenosze wczesniejszy wynik z tree_segmenter_tool\results do LidarTreeSegmenter\wyniki...
    if not exist "%WYNIKI%" mkdir "%WYNIKI%"
    move /y "%STARE%\*" "%WYNIKI%\" >nul
    rmdir "%STARE%" 2>nul
    python "%~dp0program\lts_uklad.py" "%WYNIKI%" >nul
)

if exist "%SEG%" (
    echo  === 1/4  Drzewa juz znalezione wczesniej - pomijam ===
    echo          ^(zeby policzyc od nowa, skasuj 02_CHMURY\%NAZWA%_segmenty.laz^)
) else (
    echo  === 1/4  Szukam drzew - to moze potrwac kilkanascie minut ===
    python "%~dp0program\05_wykryj_drzewa.py" "%SKAN%" --wyniki "%~dp0wyniki"
    python "%~dp0program\lts_uklad.py" "%WYNIKI%" >nul
)
if not exist "%SEG%" goto blad

echo.
echo  === 2/4  Dziele drzewa na pien, galezie i ulistnienie ===
python "%~dp0program\10_pien_galezie_liscie.py" "%SEG%" --wyniki "%~dp0wyniki"
if errorlevel 1 goto blad

echo.
echo  === 3/4  Raport Excel i miazszosc ===
python "%~dp0program\30_raport.py" "%WYNIKI%"
if errorlevel 1 goto blad

echo.
echo  === 4/4  Widok 3D w przegladarce ===
python "%~dp0program\40_widok_3d.py" "%WYNIKI%"

echo.
echo  ================================================================
echo   GOTOWE. Wszystko jest w jednym folderze:
echo     %WYNIKI%
echo  ================================================================
explorer "%WYNIKI%"
pause
exit /b

:blad
echo.
echo  Cos poszlo nie tak - komunikat bledu jest wyzej.
echo  Skopiuj go i wklej Claude'owi.
pause
