@echo off
rem Chay-app-port-tracker.bat — ban copy cua D:\shipping\port-tracker\Chay-app.bat cho mo hinh cloud (07/10/2026):
rem trackerlib.py doc du lieu o THU MUC CHA cua app (HUB) nen chay app tu ban copy D:\pipeline-data\shipping\port-tracker
rem (code chep boi Run-Local-Mini.ps1, du lieu rclone keo ve tu Drive). File goc D:\shipping\port-tracker khong sua.
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set MD_ROOT=D:\pipeline-data\market-data
set SHIP_ROOT=D:\pipeline-data\shipping
if not exist D:\pipeline-data\shipping\port-tracker\app.py (
    echo   Chua co D:\pipeline-data\shipping\port-tracker\app.py - chay local\Run-Local-Mini.ps1 (hoac seed_drive.ps1) truoc.
    pause
    exit /b 1
)
cd /d D:\pipeline-data\shipping\port-tracker
set URL=http://localhost:8766/
if not exist logs mkdir logs

netstat -ano | findstr /R /C:":8766 .*LISTENING" >nul
if %errorlevel% equ 0 (
    echo   App dang chay - mo trinh duyet: %URL%
    start "" "%URL%"
    timeout /t 2 >nul
    exit /b 0
)
echo.
echo   PORT ^& VESSEL TRACKER (du lieu: %SHIP_ROOT%) - dang khoi dong, trinh duyet se tu mo...
echo   (de dong app: dong cua so nay)
echo.
start "" /b cmd /c "timeout /t 6 >nul & start "" "%URL%""
python -m streamlit run app.py --server.port 8766 --server.headless true --browser.gatherUsageStats false 2>> logs\app_loi.log
echo.
echo   App da dung. Neu dung bat thuong, xem logs\app_loi.log
pause
