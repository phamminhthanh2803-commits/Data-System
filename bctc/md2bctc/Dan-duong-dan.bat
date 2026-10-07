@echo off
chcp 65001 >nul
title BCTC Markdown -^> CSV  (dan duong dan)

:menu
echo.
echo ============================================================
echo   BCTC .md  -^>  bctc_master.csv + bctc_notes.csv
echo ============================================================
echo   Dan duong dan 1 FILE .md hoac 1 THU MUC roi nhan Enter.
echo   (De trong roi Enter = thoat)
echo   Meo: Shift + chuot phai vao file/thu muc -^> "Copy as path"
echo ------------------------------------------------------------
set "mdpath="
set /p "mdpath=Duong dan: "

REM thoat neu de trong
if not defined mdpath goto end

REM bo dau ngoac kep neu dan kem (Copy as path co san ngoac kep)
set "mdpath=%mdpath:"=%"

echo.
echo Dang xu ly: %mdpath%
echo.
REM -r = quet ca thu muc con neu la thu muc
python "%~dp0md2bctc.py" "%mdpath%" -r

echo.
echo ------------------------------------------------------------
echo   Xong. Dan duong dan khac de lam tiep, hoac de trong de thoat.
goto menu

:end
echo Tam biet.
timeout /t 1 >nul
