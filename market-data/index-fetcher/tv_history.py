# -*- coding: utf-8 -*-
r"""
tv_history.py — Keo LICH SU GIA/KHOI LUONG theo ngay cua TUNG CO PHIEU / CHI SO tu TradingView (websocket, khong login)
qua thu vien tvDatafeed. Toi da ~5.000 nen/ma (~20 nam daily). Khong co gia tri giao dich (value) -> value_approx = close x volume.

Danh sach ma: tv_symbols.txt, moi dong `EXCHANGE:SYMBOL` (vd HOSE:VIC, HNX:SHS, UPCOM:ACV, KRX:005930, TWSE:2330, SET:PTT,
IDX:BBCA, HKEX:0005, MYX:MAYBANK, TSE:7203, SSE:600519, SZSE:000001). Dong bat dau bang # bi bo qua.
Output: tv-history.csv (long: date, tv_symbol, exchange, symbol, open, high, low, close, volume, value_approx),
merge/dedup theo (date, tv_symbol), incremental: ma da co -> chi keo 60 nen gan nhat; ma moi -> 5.000 nen.

Chay:  python tv_history.py                 # theo tv_symbols.txt
       python tv_history.py HOSE:VIC KRX:005930   # ma truyen tay
       python tv_history.py --full         # keo lai 5.000 nen cho moi ma
Luu y: gia TradingView DA DIEU CHINH chia tach/quyen (khop VCI gap-chart); websocket doi khi rot ("Connection lost")
-> thu lai 3 lan. Cai: python -m pip install --user git+https://github.com/rongardF/tvdatafeed.git
"""
import os
import sys
import time
import logging
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # D:\market-data
from mdlib import log, cffi_session as _cffi_session, safe_to_csv  # noqa: E402  (gop 14/09/2026)
SYM_FILE = os.path.join(HERE, "tv_symbols.txt")
OUT = os.path.join(HERE, "tv-history.csv")
COLS = ["date", "tv_symbol", "exchange", "symbol", "open", "high", "low", "close", "volume", "value_approx"]


def read_symbols(args):
    syms = [a for a in args if ":" in a]
    if syms:
        return syms
    if not os.path.exists(SYM_FILE):
        log(f"[!] Khong co {SYM_FILE} va khong truyen ma -> thoat")
        sys.exit(1)
    out = []
    with open(SYM_FILE, encoding="utf-8-sig") as f:
        for ln in f:
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                out += ln.split()
    return out


def fetch(tv, ex, sym, n_bars):
    from tvDatafeed import Interval
    for attempt in range(3):
        try:
            df = tv.get_hist(symbol=sym, exchange=ex, interval=Interval.in_daily, n_bars=n_bars)
            if df is not None and len(df):
                df = df.reset_index().rename(columns={"datetime": "date"})
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                df["tv_symbol"] = f"{ex}:{sym}"
                df["exchange"] = ex
                df["symbol"] = sym
                df["value_approx"] = df["close"] * df["volume"]
                return df[COLS]
        except Exception as e:
            log(f"    [{ex}:{sym}] {repr(e)[:80]}")
        time.sleep(2 + 2 * attempt)
    return None


def main():
    from tvDatafeed import TvDatafeed
    args = sys.argv[1:]
    full = "--full" in args
    syms = read_symbols(args)
    old = pd.read_csv(OUT, dtype={"date": str}) if os.path.exists(OUT) else pd.DataFrame(columns=COLS)
    tv = TvDatafeed()
    frames = []
    for s in syms:
        ex, sym = s.split(":", 1)
        have = (old["tv_symbol"] == s).any() if not old.empty else False
        n = 30 if (have and not full) else 10000      # incremental 30 nen la du (task chay hang ngay, buffer 1 thang)
        t0 = time.time()
        df = fetch(tv, ex, sym, n)
        if df is None:
            log(f"  {s:14} KHONG LAY DUOC")
            continue
        log(f"  {s:14} {len(df):5} nen  {df['date'].min()} -> {df['date'].max()}  [{time.time() - t0:.0f}s]")
        frames.append(df)
        time.sleep(0.3)
        if len(frames) % 100 == 0:                       # luu tam moi 100 ma, phong tien trinh bi kill giua chung
            old = merge_save(old, frames, full)
            frames = []
    if not frames and old.empty:
        log("Khong co du lieu moi.")
        return
    allx = merge_save(old, frames, full) if frames else old
    log(f"-> {OUT}: {len(allx)} dong, {allx['tv_symbol'].nunique()} ma")


def merge_save(old, frames, full):
    new = pd.concat(frames, ignore_index=True)
    if full and not old.empty:
        old = old[~old["tv_symbol"].isin(new["tv_symbol"].unique())]
    allx = pd.concat([old[COLS], new[COLS]], ignore_index=True) if not old.empty else new
    allx = allx.drop_duplicates(subset=["date", "tv_symbol"], keep="last").sort_values(["tv_symbol", "date"])
    allx.to_csv(OUT, index=False, encoding="utf-8-sig")
    log(f"   ... da luu {len(allx)} dong / {allx['tv_symbol'].nunique()} ma")
    return allx


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
