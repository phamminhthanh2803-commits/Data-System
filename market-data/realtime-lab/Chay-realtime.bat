@echo off
rem Bo thu real-time DNSE (muc B). Task Scheduler "Realtime DNSE" goi file nay 08:40 T2-T6; script tu thoat sau 15:10.
cd /d D:\market-data\realtime-lab
set PYTHONIOENCODING=utf-8
set VNSTOCK_DISABLE_AGENT_SETUP=1
for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set D=%%c%%b%%a
python dnse_stream.py >> logs\realtime_%D%.log 2>&1
