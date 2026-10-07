@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
setlocal

rem Cap nhat toan bo: quet thu muc theo config.csv -> unpivot -> phan nganh -> gop BCTC nganh.
rem Chi parse file moi/da sua (cache). Them file moi vao thu muc roi chay lai file .bat nay.

python "%~dp0run_pipeline.py" %*

echo.
echo Output o: %~dp0output
echo   - fiinprox_facts_all.csv         (master long, cho SQL)
echo   - by_nganh_L2\                    (tach theo nganh)
echo   - industry\<Nganh>\               (BCTC gop toan nganh, .xlsx mo Excel)
pause
