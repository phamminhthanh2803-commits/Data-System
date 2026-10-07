# -*- coding: utf-8 -*-
r"""run_nganh_bds.py — chạy toàn bộ pipeline ngành BĐS (file local D:\bctc\nganh-bat-dong-san\Nganh_BDS.xlsx).

  python run_nganh_bds.py              đọc lại dump VCI + giá/market-data mới nhất, dựng lại file (~2-3 phút)
  python run_nganh_bds.py --refresh    kéo lại BCTC VCI cho mọi mã BĐS (fsx.py bctc, gộp vào dump toàn sàn, ~15-20 phút)
                                       rồi dựng lại — dùng khi có BCTC quý mới
  python run_nganh_bds.py --no-com     không mở Excel để tính lại/kiểm tra (file vẫn tự tính khi mở)
Bước: [0 refresh VCI] -> 1 build_nganh_bds (Data_FS, nhóm) -> 2 build_valuation_bds (định giá ngày, drivers) -> 3 build_workbook_bds.
Không gắn Task Scheduler (user chọn chạy tay, 21/09/2026).
"""
import argparse
import os
import subprocess
import sys
import time

import pandas as pd

from common_bds import FSX_DIR, NHOM_CSV, log, utf8_stdout


def refresh_vci():
    extra = []
    if os.path.exists(NHOM_CSV):
        extra = pd.read_csv(NHOM_CSV, dtype=str).ticker.dropna().tolist()
    cmd = [sys.executable, "fsx.py", "bctc", "--nganh", "bat dong san", "--period", "quarter", "--from", "2018-Q1"] + extra
    log(f"[0] kéo BCTC VCI: {len(extra)} mã trong nhom_bds.csv + ICB 'bat dong san' (gộp vào {FSX_DIR}\\output) ...")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run(cmd, cwd=FSX_DIR, env=env)
    if r.returncode != 0:
        log(f"  fsx.py trả mã {r.returncode} - vẫn dựng lại từ dump hiện có")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="kéo lại BCTC VCI cho các mã BĐS trước khi dựng")
    ap.add_argument("--no-com", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    if a.refresh:
        refresh_vci()
    import build_nganh_bds, build_valuation_bds, build_workbook_bds
    log("[1] BCTC ngành (Data_FS, nhóm) ...")
    build_nganh_bds.build(force=a.refresh)
    log("[2] định giá ngày + drivers ...")
    build_valuation_bds.main()
    log("[3] file Excel ...")
    build_workbook_bds.build(no_com=a.no_com)
    log(f"XONG sau {time.time() - t0:.0f}s")


if __name__ == "__main__":
    utf8_stdout()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
