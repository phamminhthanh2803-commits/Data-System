@echo off
chcp 65001 >nul
title PDF -^> Markdown  (dan duong dan)

:menu
echo.
echo ============================================================
echo   PDF  -^>  Markdown   ^|   OCR tieng Viet, giu bang
echo ============================================================
echo   Dan duong dan 1 FILE .pdf hoac 1 THU MUC roi nhan Enter.
echo   (De trong roi Enter = thoat)
echo   Meo: Shift + chuot phai vao file -^> "Copy as path"
echo ------------------------------------------------------------
set "pdfpath="
set /p "pdfpath=Duong dan: "

REM thoat neu de trong
if not defined pdfpath goto end

REM bo dau ngoac kep neu dan kem (Copy as path co san ngoac kep)
set "pdfpath=%pdfpath:"=%"

echo.
echo Dang xu ly: %pdfpath%
echo.
python "%~dp0pdf2md.py" "%pdfpath%" -r

echo.
echo ------------------------------------------------------------
echo   Xong. Dan duong dan khac de lam tiep, hoac de trong de thoat.
goto menu

:end
echo Tam biet.
timeout /t 1 >nul
