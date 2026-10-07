# -*- coding: utf-8 -*-
r"""
tv_region.py — DINH GIA + CO BAN + FORWARD cap thi truong tu TradingView screener, MOT LAN KEO cho 12 thi truong
(gop tv_region.py cu + tv_fundamentals.py, 14/09/2026: truoc day 2 script keo trung nhau 24 request, nay 12).

Endpoint scanner.tradingview.com/<market>/scan (cong khai, khong login). Moi co phieu lay:
  von hoa, P/E ttm, P/B, ROE, co tuc, LN ttm, LN 32 quy, DT 32 quy, von chu fq/fy, LN fy, EPS du phong FY toi, gia.
Gop theo von hoa (bo co phieu uu dai — TradingView gan von hoa CP thuong cho ca uu dai -> dem doi):
  SNAPSHOT (freq D): MARKETCAP, PRICE_TO_EARNINGS (= sum mcap / sum LN ttm, GOM CA MA LO nhu VNDirect), PE_EX_LOSS,
     PRICE_TO_BOOK, BOOK_VALUE, EARNINGS_TTM, DIVIDEND_YIELD, ROE_W (binh quan ROE cong ty), PE_COVERAGE, N_STOCKS,
     ROE_TTM_PANEL (= sum LN ttm / sum von chu fq), ROE_FY (= sum LN fy / sum von chu fy),
     PE_FORWARD (= sum mcap / sum(EPS fwd x so CP)), PE_FWD_COVERAGE
  LICH SU (freq Q, date = cuoi quy lich): EARNINGS_TTM_Q, REVENUE_TTM_Q — tong 4 quy truot tren PANEL CO DINH (ma co du 20 quy)
Ma: TV_<MARKET> (TV_VN, TV_KR...) + TV_<EXCHANGE> cho san tach rieng (TV_HOSE, TV_TWSE, TV_SSE...). ROE so sanh trong wide = P/B / P/E.
Chay: python tv_region.py   (Run-Region-Daily.ps1 buoc tradingview; ~12 request, 1-2 phut)
"""
import os
import sys
import time

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # D:\market-data
from mdlib import log, cffi_session as _cffi_session, safe_to_csv  # noqa: E402  (gop 14/09/2026)
import region as R   # MASTER_CSV, WIDE_CSV, COLS, build_wide, rec

URL = "https://scanner.tradingview.com/{m}/scan"
COLS_TV = ["name", "close", "market_cap_basic", "price_earnings_ttm", "price_book_fq", "return_on_equity",
           "dividends_yield", "net_income_ttm", "net_income_fq_h", "total_revenue_fq_h", "fiscal_period_end_fq",
           "total_equity_fq", "total_equity_fy", "net_income_fy", "earnings_per_share_forecast_next_fy",
           "exchange", "subtype"]
NUM = ["close", "market_cap_basic", "price_earnings_ttm", "price_book_fq", "return_on_equity", "dividends_yield",
       "net_income_ttm", "fiscal_period_end_fq", "total_equity_fq", "total_equity_fy", "net_income_fy",
       "earnings_per_share_forecast_next_fy"]
MARKETS = {   # market -> (currency, exchanges tach rieng)
    "vietnam": ("VND", ["HOSE", "HNX", "UPCOM"]), "korea": ("KRW", []), "taiwan": ("TWD", ["TWSE", "TPEX"]),
    "hongkong": ("HKD", []), "thailand": ("THB", []), "indonesia": ("IDR", []), "malaysia": ("MYR", []),
    "japan": ("JPY", ["TSE"]), "china": ("CNY", ["SSE", "SZSE"]), "singapore": ("SGD", []),
    "philippines": ("PHP", []), "india": ("INR", ["NSE"]),
}
MKT_CODE = {"vietnam": "VN", "korea": "KR", "taiwan": "TW", "hongkong": "HK", "thailand": "TH", "indonesia": "ID",
            "malaysia": "MY", "japan": "JP", "china": "CN", "singapore": "SG", "philippines": "PH", "india": "IN"}
MIN_Q = 20          # panel co dinh cho chuoi quy
SEMI_ANNUAL = {"TV_HK", "TV_SG"}   # bao cao nua nam -> chuoi quy khong tin cay, bo


def fetch_market(mkt):
    from curl_cffi import requests
    rows, start, step = [], 0, 5000
    while True:
        body = {"filter": [{"left": "type", "operation": "equal", "right": "stock"}], "options": {"lang": "en"},
                "markets": [mkt], "columns": COLS_TV, "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
                "range": [start, start + step]}
        r = None
        for attempt in range(3):
            try:
                r = requests.post(URL.format(m=mkt), json=body, impersonate="chrome", timeout=120)
                if r.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(5)
        if r is None or r.status_code != 200:
            raise RuntimeError(f"TV {mkt} HTTP {getattr(r, 'status_code', None)}")
        j = r.json()
        batch = [d["d"] for d in j.get("data", [])]
        rows += batch
        if len(batch) < step or len(rows) >= j.get("totalCount", 0):
            break
        start += step
        time.sleep(1)
    df = pd.DataFrame(rows, columns=COLS_TV)
    for c in NUM:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[(df["subtype"] != "preferred") & (df["market_cap_basic"] > 0)]


def snapshot(df):
    tot = df["market_cap_basic"].sum()
    out = {"MARKETCAP": tot, "N_STOCKS": float(len(df))}
    ni = df.dropna(subset=["net_income_ttm"])
    if len(ni) and ni["net_income_ttm"].sum() > 0:
        out["PRICE_TO_EARNINGS"] = ni["market_cap_basic"].sum() / ni["net_income_ttm"].sum()
        out["EARNINGS_TTM"] = ni["net_income_ttm"].sum()
        out["PE_COVERAGE"] = ni["market_cap_basic"].sum() / tot
    pe = df[df["price_earnings_ttm"] > 0]
    if len(pe):
        out["PE_EX_LOSS"] = pe["market_cap_basic"].sum() / (pe["market_cap_basic"] / pe["price_earnings_ttm"]).sum()
    pb = df[df["price_book_fq"] > 0]
    if len(pb):
        out["PRICE_TO_BOOK"] = pb["market_cap_basic"].sum() / (pb["market_cap_basic"] / pb["price_book_fq"]).sum()
        out["BOOK_VALUE"] = (pb["market_cap_basic"] / pb["price_book_fq"]).sum()
    ro = df.dropna(subset=["return_on_equity"])
    if len(ro):
        out["ROE_W"] = (ro["return_on_equity"] * ro["market_cap_basic"]).sum() / ro["market_cap_basic"].sum()
    dy = df.dropna(subset=["dividends_yield"])
    if len(dy):
        out["DIVIDEND_YIELD"] = (dy["dividends_yield"] * dy["market_cap_basic"]).sum() / dy["market_cap_basic"].sum()
    e = df.dropna(subset=["total_equity_fq", "net_income_ttm"]); e = e[e["total_equity_fq"] > 0]
    if len(e):
        out["ROE_TTM_PANEL"] = e["net_income_ttm"].sum() / e["total_equity_fq"].sum() * 100
    f = df.dropna(subset=["total_equity_fy", "net_income_fy"]); f = f[f["total_equity_fy"] > 0]
    if len(f):
        out["ROE_FY"] = f["net_income_fy"].sum() / f["total_equity_fy"].sum() * 100
    fw = df.dropna(subset=["earnings_per_share_forecast_next_fy", "close"]); fw = fw[fw["close"] > 0]
    fwd_earn = (fw["earnings_per_share_forecast_next_fy"] * fw["market_cap_basic"] / fw["close"]).sum()
    if fwd_earn > 0:
        out["PE_FORWARD"] = fw["market_cap_basic"].sum() / fwd_earn
        out["PE_FWD_COVERAGE"] = fw["market_cap_basic"].sum() / tot
    return out


def quarter_series(df, col):
    """Lich su quy (moi nhat truoc) + fiscal_period_end_fq (epoch quy cuoi) -> Series tong theo cuoi quy lich, panel co dinh."""
    recs = {}
    panel = 0
    for h, qe in zip(df[col], df["fiscal_period_end_fq"]):
        if not isinstance(h, list) or pd.isna(qe) or sum(x is not None for x in h[:MIN_Q]) < MIN_Q:
            continue
        panel += 1
        q_end = pd.Timestamp(qe, unit="s").normalize() + pd.offsets.QuarterEnd(0)
        for i, v in enumerate(h[:MIN_Q + 4]):
            if v is None:
                continue
            q = (q_end - pd.offsets.QuarterEnd(i)) if i else q_end
            a = recs.setdefault(q, [0.0, 0]); a[0] += float(v); a[1] += 1
    if not recs:
        return pd.Series(dtype=float), 0
    s = pd.DataFrame({q: {"sum": v[0], "n": v[1]} for q, v in recs.items()}).T.sort_index()
    s = s[s["n"] >= 0.9 * panel]
    return s["sum"].rolling(4).sum().dropna(), panel


def main():
    d = pd.Timestamp.now().normalize()
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    ds = d.strftime("%Y-%m-%d")
    recs = []
    for mkt, (cur, exchanges) in MARKETS.items():
        t0 = time.time()
        try:
            df = fetch_market(mkt)
        except Exception as e:
            log(f"  {mkt:12} [LOI] {repr(e)[:100]}")
            continue
        groups = [("TV_" + MKT_CODE[mkt], df)] + [("TV_" + ex, df[df["exchange"] == ex]) for ex in exchanges]
        for code, sub in groups:
            if sub.empty:
                continue
            a = snapshot(sub)
            recs += [R.rec(code, ds, k, v, cur, "D", "tradingview") for k, v in a.items()]
            info = ""
            if code == "TV_" + MKT_CODE[mkt] and code not in SEMI_ANNUAL:     # chuoi quy chi cho cap thi truong
                for col, ratio in [("net_income_fq_h", "EARNINGS_TTM_Q"), ("total_revenue_fq_h", "REVENUE_TTM_Q")]:
                    ttm, panel = quarter_series(sub, col)
                    recs += [R.rec(code, q.strftime("%Y-%m-%d"), ratio, v, cur, "Q", "tradingview") for q, v in ttm.items()]
                    if ratio == "EARNINGS_TTM_Q" and len(ttm) >= 5:
                        info = f" | LN ttm YoY {ttm.iloc[-1] / ttm.iloc[-5] - 1:+.0%} (panel {panel})"
            log(f"  {code:8} n={len(sub):5} pe={a.get('PRICE_TO_EARNINGS', np.nan):5.1f} fwd={a.get('PE_FORWARD', np.nan):5.1f} "
                f"pb={a.get('PRICE_TO_BOOK', np.nan):4.2f} roe={a.get('ROE_TTM_PANEL', np.nan):4.1f}%{info} [{time.time() - t0:.0f}s]")
        time.sleep(1)
    recs = [x for x in recs if x]
    if not recs:
        log("Khong co du lieu.")
        return
    new = pd.DataFrame(recs)
    old = pd.read_csv(R.MASTER_CSV, dtype={"date": str, "currency": str, "freq": str}) if os.path.exists(R.MASTER_CSV) \
        else pd.DataFrame(columns=R.COLS)
    master = pd.concat([old[R.COLS], new[R.COLS]], ignore_index=True) if not old.empty else new[R.COLS]
    master["value"] = pd.to_numeric(master["value"], errors="coerce")
    master = master.dropna(subset=["value"]).drop_duplicates(subset=["code", "date", "ratio"], keep="last")
    master = master.sort_values(["code", "ratio", "date"]).reset_index(drop=True)
    master.to_csv(R.MASTER_CSV, index=False, encoding="utf-8-sig")
    R.build_wide(master).to_csv(R.WIDE_CSV, index=False, encoding="utf-8-sig")
    log(f"-> master {len(master)} dong")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
