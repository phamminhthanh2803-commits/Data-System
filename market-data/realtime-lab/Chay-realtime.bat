@echo off
rem Bo thu real-time DNSE (muc B). Task Scheduler "Realtime DNSE" goi file nay 08:40 T2-T6; script tu thoat sau 15:10.
rem 09/10/2026: them vong tu khoi dong lai - neu script sap (loi mang, loi DuckDB...) truoc 15:10 ngay T2-T6 thi chay lai sau 15 s.
cd /d D:\market-data\realtime-lab
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set VNSTOCK_DISABLE_AGENT_SETUP=1
for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set D=%%c%%b%%a

:again
echo [%time%] khoi dong dnse_stream.py >> logs\realtime_%D%.log
python dnse_stream.py >> logs\realtime_%D%.log 2>&1
set RC=%errorlevel%
rem con trong gio giao dich (T2-T6, truoc 15:10) thi chay lai
for /f %%r in ('powershell -NoProfile -Command "$n=Get-Date; if ($n.DayOfWeek -in 'Saturday','Sunday' -or $n.TimeOfDay -gt [TimeSpan]'15:10' -or $n.TimeOfDay -lt [TimeSpan]'08:30') {0} else {1}"') do set INSESSION=%%r
if "%INSESSION%"=="1" (
    echo [%time%] dnse_stream.py thoat ma %RC% trong gio giao dich - chay lai sau 15 s >> logs\realtime_%D%.log
    timeout /t 15 /nobreak >nul
    goto again
)
echo [%time%] ket thuc (ma %RC%) >> logs\realtime_%D%.log
