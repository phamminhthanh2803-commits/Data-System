@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   PDF DETECTOR - quet & tai PDF theo trang
echo ============================================
python pdf_detector.py
echo.
pause
