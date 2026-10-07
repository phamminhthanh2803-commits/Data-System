# -*- coding: utf-8 -*-
r"""
RUN DAILY — chạy tuần tự cả pipeline Market Valuation, ghi log theo ngày.
Được Task Scheduler gọi qua Chay-hang-ngay.bat (10h30, sau Index Fetcher 10h).

Thứ tự: fetch_valuation (thị trường) -> sectors (ngành) -> stocks (từng mã,
đọc tickers.txt) -> adjust (P/E,P/B loại trừ, đọc nhom-loai.txt).
Một bước lỗi KHÔNG chặn các bước sau. Log: logs\YYYY-MM-DD.log
"""
import datetime
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG = os.path.join(LOG_DIR, datetime.date.today().isoformat() + ".log")


def doc_config(fname):
    path = os.path.join(BASE, fname)
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8-sig") as f:
        for ln in f:
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                out += ln.split()
    return out


def chay(ten, cmd, log):
    log.write(f"\n===== {ten} | {datetime.datetime.now():%H:%M:%S} =====\n")
    log.flush()
    r = subprocess.run([sys.executable] + cmd, cwd=BASE, stdout=log, stderr=log,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    log.write(f"----- {ten}: {'OK' if r.returncode == 0 else f'LOI (exit {r.returncode})'}\n")
    log.flush()
    return r.returncode == 0


def main():
    nhom_loai = doc_config("nhom-loai.txt")
    with open(LOG, "a", encoding="utf-8") as log:
        log.write(f"\n################ {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ################\n")
        kq = {}
        kq["thi_truong"] = chay("1/5 THI TRUONG (fetch_valuation)", ["fetch_valuation.py"], log)
        kq["nganh"] = chay("2/5 NGANH (sectors)", ["sectors.py"], log)
        if doc_config("tickers.txt"):
            kq["tung_ma"] = chay("3/5 TUNG MA (stocks)", ["stocks.py", "--file", "tickers.txt"], log)
        else:
            log.write("3/5 TUNG MA: bo qua (tickers.txt trong)\n")
        if nhom_loai:
            kq["dieu_chinh"] = chay("4/5 DIEU CHINH (adjust)", ["adjust.py"] + nhom_loai, log)
        else:
            log.write("4/5 DIEU CHINH: bo qua (nhom-loai.txt trong)\n")
        kq["eps_tuyet_doi"] = chay("5/5 EPS TUYET DOI (market_eps)", ["market_eps.py"], log)
        loi = [k for k, v in kq.items() if not v]
        log.write(f"\nKET THUC: {'OK het' if not loi else 'LOI: ' + ', '.join(loi)}\n")
    sys.exit(1 if loi else 0)


if __name__ == "__main__":
    main()
