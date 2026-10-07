@echo off
rem Chay-app-market.bat — ban copy cua D:\market-data\app\Chay-app.bat cho mo hinh cloud (07/10/2026):
rem app doc DU LIEU tu D:\pipeline-data\market-data (rclone keo ve moi toi boi Run-Local-Mini.ps1) qua env MD_ROOT;
rem code app van o D:\market-data\app (file goc khong sua). bond-pivot = junction -> D:\market-data\bond-pivot.
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set MD_ROOT=D:\pipeline-data\market-data
set SHIP_ROOT=D:\pipeline-data\shipping
set BCTC_ROOT=D:\bctc
cd /d D:\market-data\app
set TRANG=%~1
set URL=http://localhost:8765/
if not "%TRANG%"=="" set URL=http://localhost:8765/?trang=%TRANG%

if not exist logs mkdir logs
set VER=
for /f "delims=" %%v in ('python -c "import importlib.metadata as m; print(m.version('streamlit'))" 2^>nul') do set VER=%%v
set OLDVER=
if exist logs\streamlit_version.txt set /p OLDVER=<logs\streamlit_version.txt

netstat -ano | findstr /R /C:":8765 .*LISTENING" >nul
if %errorlevel% neq 0 goto KHOIDONG
if "%VER%"=="%OLDVER%" (
    echo   App dang chay - mo trinh duyet: %URL%
    start "" "%URL%"
    timeout /t 2 >nul
    exit /b 0
)
echo   Streamlit da doi phien ban [%OLDVER% -^> %VER%] - khoi dong lai app...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":8765 .*LISTENING"') do taskkill /PID %%p /F >nul 2>&1
timeout /t 2 >nul

:KHOIDONG
echo.
echo   MARKET DATA APP (du lieu: %MD_ROOT%) - dang khoi dong, trinh duyet se tu mo...
echo   (de dong app: dong cua so nay)
echo.
if not "%VER%"=="" >logs\streamlit_version.txt echo %VER%
start "" /b cmd /c "timeout /t 6 >nul & start "" "%URL%""
python -m streamlit run app.py --server.port 8765 --server.headless true --browser.gatherUsageStats false 2>> logs\app_loi.log
echo.
echo   App da dung. Neu dung bat thuong, xem logs\app_loi.log
pause
