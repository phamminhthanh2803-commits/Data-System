@echo off
chcp 65001 >nul
setlocal
REM Keo 1 hoac nhieu file .md (BCTC mau CTCK da OCR) tha vao file .bat nay.
REM Ket qua cong don vao: bctc_master.csv (4 BC chinh) + bctc_notes.csv (Thuyet minh)

if "%~1"=="" (
  echo.
  echo   Hay KEO-THA mot/nhieu file .md vao file .bat nay.
  echo.
  pause
  exit /b
)

:loop
if "%~1"=="" goto done
echo.
echo ============================================================
echo  Dang xu ly: %~nx1
echo ============================================================
python "%~dp0md2bctc.py" "%~1"
shift
goto loop

:done
echo.
echo  XONG. Mo bctc_master.csv (4 BC) va bctc_notes.csv (Thuyet minh).
echo.
pause
