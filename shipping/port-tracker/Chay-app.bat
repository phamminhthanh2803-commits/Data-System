@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set URL=http://localhost:8766/
if not exist logs mkdir logs

rem App da chay -> chi mo trinh duyet, khong khoi dong server thu 2
netstat -ano | findstr /R /C:":8766 .*LISTENING" >nul
if %errorlevel% equ 0 (
    echo   App dang chay - mo trinh duyet: %URL%
    start "" "%URL%"
    timeout /t 2 >nul
    exit /b 0
)
echo.
echo   PORT ^& VESSEL TRACKER - dang khoi dong, trinh duyet se tu mo...
echo   (de dong app: dong cua so nay)
echo.
start "" /b cmd /c "timeout /t 6 >nul & start "" "%URL%""
python -m streamlit run app.py --server.port 8766 --server.headless true --browser.gatherUsageStats false 2>> logs\app_loi.log
echo.
echo   App da dung. Neu dung bat thuong, xem logs\app_loi.log
pause
