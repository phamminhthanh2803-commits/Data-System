# -*- coding: utf-8 -*-
"""Khoi ngoai theo TUNG CO PHIEU tu Vietcap IQ (price-history) - lich su tu 2000.

VNDirect v4/foreigns chi co tu 30/08/2018 (va keo theo ngay), CafeF chi giu ~3 thang.
Vietcap tra moi ma toan bo lich su (1000 phien/trang), tach khop lenh / thoa thuan, kem
room + % so huu NN + GTGD toan phien.

Luu tung ma: raw/vci_foreign/<MA>.csv (chay lai duoc, ma da co thi bo qua khi --full),
roi gop ra raw/vn_foreign_stocks_vci.parquet cho app.

Chay:  python fetch_foreign_vci.py --full            (backfill toan bo, ~30-40 phut, 8 luong)
       python fetch_foreign_vci.py --recent 40       (cap nhat 40 phien gan nhat moi ma)
       python fetch_foreign_vci.py --combine         (chi gop file)"""
import argparse
import glob
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
DIR = os.path.join(RAW, "vci_foreign")
OUT = os.path.join(RAW, "vn_foreign_stocks_vci.parquet")
URL = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/{}/price-history"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/128.0.0.0 Safari/537.36",
       "Referer": "https://trading.vietcap.com.vn/", "Origin": "https://trading.vietcap.com.vn"}
PAGE = 1000
COT = {"tradingDate": "date", "foreignBuyValueTotal": "buyVal", "foreignSellValueTotal": "sellVal",
       "foreignNetValueTotal": "netVal", "foreignBuyValueDeal": "buyVal_deal",
       "foreignSellValueDeal": "sellVal_deal", "foreignBuyVolumeTotal": "buyVol",
       "foreignSellVolumeTotal": "sellVol", "foreignTotalRoom": "totalRoom",
       "foreignCurrentRoom": "currentRoom", "foreignOwnedPercentage": "owned_pct",
       "totalValue": "totalValue", "closePrice": "close"}
_lock = threading.Lock()


def log(*a):
    with _lock:
        print(*a, flush=True)


def _get(tk, page, size):
    for lan in range(5):
        try:
            r = requests.get(URL.format(tk), params={"timeFrame": "ONE_DAY", "page": page, "size": size},
                             headers=HDR, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                raise RuntimeError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return (r.json().get("data") or {})
        except Exception as e:
            if lan == 4:
                raise
            time.sleep(4 * (lan + 1))
            _ = e
    return {}


def keo_ma(tk, recent=None):
    rows, page = [], 0
    size = min(recent, PAGE) if recent else PAGE
    while True:
        d = _get(tk, page, size)
        c = d.get("content") or []
        rows += c
        if recent or d.get("last", True) or not c:
            break
        page += 1
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df[[c for c in COT if c in df.columns]].rename(columns=COT)
    df["date"] = df.date.astype(str).str[:10]
    df.insert(0, "code", tk)
    return df


def luu_ma(tk, df):
    f = os.path.join(DIR, f"{tk}.csv")
    if os.path.exists(f):
        df = pd.concat([pd.read_csv(f, dtype={"date": str, "code": str}), df], ignore_index=True)
    df = df.drop_duplicates("date", keep="last").sort_values("date")
    df.to_csv(f, index=False)
    return len(df)


def danh_sach_ma():
    ma = set(pd.read_csv(os.path.join(RAW, "vn_screener_meta.csv"), usecols=["name"]).name.dropna())
    for f in glob.glob(os.path.join(RAW, "vn_foreign_stocks_20*.csv")):
        ma |= set(pd.read_csv(f, usecols=["code"], dtype=str).code.dropna())
    return sorted(m for m in ma if isinstance(m, str) and m.isalnum() and 3 <= len(m) <= 4)


def gop():
    fs = glob.glob(os.path.join(DIR, "*.csv"))
    d = pd.concat([pd.read_csv(f, dtype={"date": str, "code": str}) for f in fs], ignore_index=True)
    d["date"] = pd.to_datetime(d.date)
    d.to_parquet(OUT, index=False)
    log(f"-> {os.path.basename(OUT)}: {len(d):,} dong, {d.code.nunique()} ma, "
        f"{d.date.min():%Y-%m-%d}..{d.date.max():%Y-%m-%d}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--recent", type=int)
    ap.add_argument("--combine", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--tickers")
    a = ap.parse_args()
    os.makedirs(DIR, exist_ok=True)
    if a.combine:
        return gop()
    ma = a.tickers.split(",") if a.tickers else danh_sach_ma()
    if a.full and not a.tickers:
        da_co = {os.path.basename(f)[:-4] for f in glob.glob(os.path.join(DIR, "*.csv"))}
        ma = [m for m in ma if m not in da_co]
    recent = None if a.full else (a.recent or 40)
    log(f"Che do: {'full' if a.full else f'recent {recent}'} - {len(ma)} ma, {a.workers} luong")
    t0, xong, loi, trong = time.time(), 0, [], 0
    with ThreadPoolExecutor(a.workers) as ex:
        fut = {ex.submit(keo_ma, m, recent): m for m in ma}
        for f in as_completed(fut):
            m = fut[f]
            try:
                df = f.result()
                if df.empty:
                    trong += 1
                else:
                    luu_ma(m, df)
            except Exception as e:
                loi.append(m)
                log(f"  ! {m}: {e}")
            xong += 1
            if xong % 100 == 0:
                log(f"  {xong}/{len(ma)} ma [{time.time() - t0:.0f}s]")
    log(f"Da luu {xong - len(loi) - trong} ma, trong {trong}, LOI {len(loi)}: {','.join(loi[:30])}")
    gop()


if __name__ == "__main__":
    main()
