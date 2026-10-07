@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ===================================================
echo   FS EXTRACTOR - keo data tai chinh VN
echo ---------------------------------------------------
echo   1 = BCTC (bao cao tai chinh, 5 bao cao)
echo   2 = VON HOA + P/E + P/B + dinh gia nganh
echo   3 = THANH KHOAN index (7 chi so)
echo   4 = TRA CUU NGANH (xem ten nganh + so ma)
echo ===================================================
set /p MODE="Chon 1 / 2 / 3 / 4: "

if "%MODE%"=="1" goto bctc
if "%MODE%"=="2" goto cap
if "%MODE%"=="3" goto liq
if "%MODE%"=="4" goto nganh
echo Lua chon khong hop le.& pause & exit /b

:bctc
call :pickma
echo.
echo Nhap khoang KY (Enter bo qua = full):
set /p FROM="  Tu ky  (vd 2020-Q1): "
set /p TO="  Den ky (vd 2024-Q4): "
set "ARGS=bctc %MA% --period quarter --out output"
goto run

:cap
call :pickma
echo.
echo Nhap khoang NGAY (Enter bo qua = tu 2015 den nay):
set /p FROM="  Tu ngay  (vd 2020-01-01): "
set /p TO="  Den ngay (vd 2026-06-23): "
set "ARGS=cap %MA% --out output_cap"
goto run

:liq
echo.
echo Nhap khoang NGAY (Enter bo qua = tu 2015 den nay):
set /p FROM="  Tu ngay  (vd 2020-01-01): "
set /p TO="  Den ngay (vd 2026-06-23): "
set "ARGS=liq --out output_liq"
goto run

:nganh
echo.
set "KW="
set /p KW="Tu khoa nganh (vd: ngan hang / Enter = xem tat ca): "
python fsx.py nganh "%KW%"
echo.
pause
exit /b

:run
set "RANGE="
if defined FROM set "RANGE=%RANGE% --from %FROM%"
if defined TO set "RANGE=%RANGE% --to %TO%"
echo.
python fsx.py %ARGS%%RANGE%
echo.
pause
exit /b

:pickma
echo.
echo Chon MA muon keo (go ten nganh KHONG CAN DAU, nhieu nganh cach nhau dau phay):
set "NGANH="
set "SAN="
set /p NGANH="  Ten nganh (vd: ngan hang / Enter = dung tickers.txt): "
if not defined NGANH set "MA=--file tickers.txt"
if not defined NGANH goto :eof
set /p SAN="  San (Enter = ca HOSE,HNX,UPCOM / vd: HOSE,HNX): "
set "MA=--nganh "%NGANH%""
if defined SAN set "MA=%MA% --san %SAN%"
goto :eof
