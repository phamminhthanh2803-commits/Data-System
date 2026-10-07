# -*- coding: utf-8 -*-
"""Khoi ngoai mua/ban theo TUNG CO PHIEU (VNDirect v4/foreigns, type:STOCK) - keo incremental.

Luu raw/vn_foreign_stocks_<nam>.csv (cung schema file 2025h2/2026 da co): moi nam 1 file.
Moi lan chay keo lai BUFFER_DAYS ngay gan nhat (VNDirect co the sua so phien cuoi) roi
merge dedup (code, date). App (tab Khoi ngoai -> theo nhom nganh) doc cac file nay.

Chay:  python fetch_foreign_stocks.py            (incremental)
       python fetch_foreign_stocks.py --from 2026-01-01   (keo lai tu ngay chi dinh)"""
import argparse
import glob
import os
import sys
import time
from datetime import date, timedelta

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
sys.path.insert(0, HERE)
import fetch_flows as F  # noqa: E402

BUFFER_DAYS = 7
MAC_DINH_TU = "2025-09-01"


def ngay_cuoi():
    ds = []
    for f in glob.glob(os.path.join(RAW, "vn_foreign_stocks_*.csv")):
        ds.append(pd.read_csv(f, usecols=["date"], dtype=str).date.max())
    return max(ds) if ds else None


def file_nam(nam):
    """2025 -> file 2025h2 da co; cac nam khac -> vn_foreign_stocks_<nam>.csv."""
    if nam == 2025:
        return os.path.join(RAW, "vn_foreign_stocks_2025h2.csv")
    return os.path.join(RAW, f"vn_foreign_stocks_{nam}.csv")


def keo(tu, den):
    rows = []
    a = pd.Timestamp(tu)
    while a <= pd.Timestamp(den):   # theo tung thang cho phan trang khong qua sau
        b = min(a + pd.offsets.MonthEnd(0), pd.Timestamp(den))
        t0 = time.time()
        q = f"type:STOCK~tradingDate:gte:{a:%Y-%m-%d}~tradingDate:lte:{b:%Y-%m-%d}"
        r = F._get(F.API_FOREIGN, q, "tradingDate")
        print(f"  {a:%Y-%m-%d}..{b:%Y-%m-%d}: {len(r)} dong [{time.time() - t0:.0f}s]", flush=True)
        rows += r
        a = b + timedelta(days=1)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="tu")
    a = ap.parse_args()
    cuoi = ngay_cuoi()
    tu = a.tu or (str((pd.Timestamp(cuoi) - timedelta(days=BUFFER_DAYS)).date()) if cuoi else MAC_DINH_TU)
    den = str(date.today())
    print(f"Che do: {'full' if a.tu else 'incremental'} {tu}..{den} (du lieu cu den {cuoi})")
    moi = keo(tu, den)
    if moi.empty:
        print("Khong co dong moi.")
        return
    moi["date"] = moi["tradingDate"].astype(str).str[:10]
    tong = 0
    for nam, g in moi.groupby(moi.date.str[:4].astype(int)):
        f = file_nam(nam)
        cu = pd.read_csv(f, dtype={"date": str}) if os.path.exists(f) else pd.DataFrame()
        d = (pd.concat([cu, g], ignore_index=True)
             .drop_duplicates(["code", "date"], keep="last").sort_values(["date", "code"]))
        d.to_csv(f, index=False, encoding="utf-8-sig")
        tong += len(g)
        print(f"-> {os.path.basename(f)}: {len(d)} dong, {d.date.min()}..{d.date.max()}")
    print(f"Da luu {tong} dong keo moi, phien cuoi {moi.date.max()}")


if __name__ == "__main__":
    main()
