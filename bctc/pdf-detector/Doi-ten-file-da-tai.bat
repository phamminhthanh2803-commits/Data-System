@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   DOI TEN FILE PDF DA TAI  -^>  "BCTC - <MA CK> - <ky>.pdf"
echo ============================================================
echo.
set /p folder=Thu muc chua PDF (Enter = downloads):
if "%folder%"=="" set folder=downloads
set /p tk=Ma chung khoan (vd SSI, BVS, MBS...):
echo.
python pdf_detector.py --rename-dir "%folder%" --ticker %tk%
echo.
pause
