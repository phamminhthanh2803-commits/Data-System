# -*- coding: utf-8 -*-
"""Tu doanh CTCK mua/ban theo TUNG CO PHIEU (VNDirect v4/proprietary_trading, type:STOCK).

So lieu tu doanh theo ma chi co tu 17/05/2022 (VNDirect; CafeF tu 11/2022, Vietcap khong co).
Chi co dong cho ma CO giao dich tu doanh trong phien. Moi lan chay keo lai BUFFER_DAYS ngay
roi merge dedup (code, date) -> raw/vn_prop_stocks.csv. App: tab Khoi ngoai -> Soi dong tien.

Chay:  python fetch_prop_stocks.py                 (incremental)
       python fetch_prop_stocks.py --from 2022-01-01   (keo lai tu ngay chi dinh / backfill)"""
import argparse
import os
import sys
import time
from datetime import date, timedelta

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "raw", "vn_prop_stocks.csv")
sys.path.insert(0, HERE)
import fetch_flows as F  # noqa: E402

BUFFER_DAYS = 7
MAC_DINH_TU = "2022-01-01"
COT = ["code", "date", "floor", "buyingVal", "sellingVal", "netVal", "buyingVol", "sellingVol", "netVol",
       "buyingValPct", "sellingValPct"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="tu")
    a = ap.parse_args()
    cu = pd.read_csv(OUT, dtype={"date": str, "code": str}) if os.path.exists(OUT) else pd.DataFrame(columns=COT)
    cuoi = cu.date.max() if len(cu) else None
    tu = a.tu or (str((pd.Timestamp(cuoi) - timedelta(days=BUFFER_DAYS)).date()) if cuoi else MAC_DINH_TU)
    print(f"Che do: {'full' if a.tu or not cuoi else 'incremental'} {tu}..{date.today()} (du lieu cu den {cuoi})")
    t0 = time.time()
    rows = F._get(F.API_PROP, f"type:STOCK~date:gte:{tu}", "date")
    print(f"  keo {len(rows)} dong [{time.time() - t0:.0f}s]")
    if not rows:
        print("Khong co dong moi.")
        return
    moi = pd.DataFrame(rows)
    moi = moi[[c for c in COT if c in moi.columns]]
    moi["date"] = moi.date.astype(str).str[:10]
    d = (pd.concat([cu, moi] if len(cu) else [moi], ignore_index=True)
         .drop_duplicates(["code", "date"], keep="last").sort_values(["date", "code"]))
    d.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"-> {os.path.basename(OUT)}: {len(d)} dong, {d.code.nunique()} ma, {d.date.min()}..{d.date.max()}")
    print(f"Da luu {len(moi)} dong keo moi, phien cuoi {moi.date.max()}")


if __name__ == "__main__":
    main()
