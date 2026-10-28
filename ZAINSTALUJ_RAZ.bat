@echo off
REM Uruchom raz, przy pierwszym uzyciu. Doinstalowuje biblioteki.
cd /d "%~dp0"
python -m pip install -r requirements.txt
echo.
echo  Gotowe. Teraz uruchom LidarTreeSegmenter_PL.bat (okno) albo przeciagnij skan na PRZECIAGNIJ_TU_SKAN.bat
pause
