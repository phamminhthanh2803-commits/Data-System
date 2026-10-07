@echo off
chcp 65001 >nul
REM === Keo du lieu chi so DAILY, merge vao indices-master.csv ===
REM Chay incremental (mac dinh). Dung cho Task Scheduler chay hang ngay.
cd /d "%~dp0"
python fetch_indices.py %*
if errorlevel 1 (
  echo [LOI] Script that bai, xem log ben tren.
  exit /b 1
)
exit /b 0
