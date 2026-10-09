# -*- coding: utf-8 -*-
r"""
poll_realtime.py — SCRIPT MAU gan real-time (1 phut) cho TTCK Viet Nam, KHONG can tai khoan.
Khao sat 07/10/2026 (realtime-lab/DE-XUAT.md). Khong dung chung pipeline hien tai.

Moi vong poll (mac dinh 60 s, chi trong 08:55-15:05 ngay giao dich):
  1. Nen 1 phut cac CHI SO + PHAI SINH : VNDirect dchart (chinh) -> fallback Entrade/DNSE -> fallback SSI iBoard chart
        VNINDEX VN30 HNX HNX30 UPCOM VNMID VNSML VN100 VN30F1M VN30F2M
  2. Bang gia TOAN THI TRUONG (HOSE/HNX/UPCOM, ~1.500 ma): SSI iBoard query (1 request/san)
        gia khop, thay doi, KL/GTGD luy ke, KHOI NGOAI mua/ban trong phien, room, bid/ask 1, phien (PRE/LO/ATC/...)
        -> fallback Vietcap price/symbols/getList (cung truong, theo danh sach ma da cache o symbols.txt)
  3. Tong hop: do rong (tang/giam/dung/tran/san), GTGD, khoi ngoai rong tung san, basis VN30F1M - VN30.

Ghi parquet tai realtime-lab/data/<YYYY-MM-DD>/
  index_1m.parquet          nen 1 phut, dedup theo (symbol, t), cong don ca ngay
  stocks_<HHMM>.parquet     snapshot bang gia moi vong (co the xoa bot, giu ATC)
  stocks_latest.parquet     snapshot moi nhat (app doc file nay)
  market_summary.parquet    1 dong / san / vong poll (append) -> ve duong do rong, khoi ngoai trong phien

Chay:  python poll_realtime.py                     # lap 60 s trong gio giao dich, tu dung sau 15:05
       python poll_realtime.py --once              # 1 vong roi thoat (test bat ky luc nao)
       python poll_realtime.py --force --interval 30   # bo qua kiem tra gio
Thu vien: requests, pandas, pyarrow (da co trong requirements.txt cua hub).
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time

import pandas as pd
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
VN_TZ = dt.timezone(dt.timedelta(hours=7))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
H_PLAIN = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
H_SSI = {**H_PLAIN, "Referer": "https://iboard.ssi.com.vn/", "Origin": "https://iboard.ssi.com.vn"}
H_VCI = {**H_PLAIN, "Content-Type": "application/json", "Referer": "https://trading.vietcap.com.vn/"}

INDEX_SYMBOLS = ["VNINDEX", "VN30", "HNX", "HNX30", "UPCOM", "VNMID", "VNSML", "VN100", "VN30F1M", "VN30F2M"]
# ten ma o tung nguon (VNDirect/Entrade dung HNX, UPCOM; SSI dung HNXINDEX, UPCOM chua co du lieu 1 phut)
SSI_NAME = {"HNX": "HNXINDEX", "UPCOM": "UPCOMINDEX"}
EXCHANGES = ["hose", "hnx", "upcom"]
STOCK_COLS = {
    "stockSymbol": "symbol", "exchange": "exchange", "session": "session", "refPrice": "ref", "ceiling": "ceiling",
    "floor": "floor", "openPrice": "open", "highest": "high", "lowest": "low", "matchedPrice": "price",
    "matchedVolume": "last_vol", "priceChange": "change", "priceChangePercent": "change_pct",
    "nmTotalTradedQty": "volume", "nmTotalTradedValue": "value", "avgPrice": "avg_price",
    "best1Bid": "bid1", "best1BidVol": "bid1_vol", "best1Offer": "ask1", "best1OfferVol": "ask1_vol",
    "buyForeignQtty": "fr_buy_vol", "buyForeignValue": "fr_buy_val", "sellForeignQtty": "fr_sell_vol",
    "sellForeignValue": "fr_sell_val", "remainForeignQtty": "fr_room", "expectedLastUpdate": "last_update_ms",
    "stockType": "stock_type",
}


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(VN_TZ):%H:%M:%S}] {msg}", flush=True)


def now_vn() -> dt.datetime:
    return dt.datetime.now(VN_TZ)


def in_session(t: dt.datetime) -> bool:
    if t.weekday() >= 5:
        return False
    hm = t.hour * 60 + t.minute
    return 8 * 60 + 55 <= hm <= 15 * 60 + 5


# ----------------------------------------------------------------------------- 1. nen 1 phut chi so
def _bars_vnd(sym: str, frm: int, to: int) -> pd.DataFrame | None:
    r = requests.get("https://dchart-api.vndirect.com.vn/dchart/history",
                     params={"symbol": sym, "resolution": "1", "from": frm, "to": to}, headers=H_PLAIN, timeout=20)
    r.raise_for_status()
    return _bars_frame(r.json(), sym, "vndirect")


def _bars_entrade(sym: str, frm: int, to: int) -> pd.DataFrame | None:
    kind = "derivative" if sym.startswith("VN30F") else "index"
    r = requests.get(f"https://services.entrade.com.vn/chart-api/v2/ohlcs/{kind}",
                     params={"from": frm, "to": to, "symbol": sym, "resolution": "1"}, headers=H_PLAIN, timeout=20)
    r.raise_for_status()
    return _bars_frame(r.json(), sym, "entrade")


def _bars_ssi(sym: str, frm: int, to: int) -> pd.DataFrame | None:
    r = requests.get("https://iboard-api.ssi.com.vn/statistics/charts/history",
                     params={"resolution": "1", "symbol": SSI_NAME.get(sym, sym), "from": frm, "to": to},
                     headers=H_SSI, timeout=20)
    r.raise_for_status()
    return _bars_frame(r.json().get("data", {}), sym, "ssi")


def _bars_frame(j: dict, sym: str, source: str) -> pd.DataFrame | None:
    if not j or not j.get("t"):
        return None
    df = pd.DataFrame({k: j.get(k) for k in ("t", "o", "h", "l", "c", "v") if k in j})
    df.insert(0, "symbol", sym)
    df["source"] = source
    df["time"] = pd.to_datetime(df["t"], unit="s", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    return df


def fetch_index_bars(lookback_sec: int = 8 * 3600) -> pd.DataFrame:
    """Keo ca phien (8 h, ~25 KB/ma) de --once chay duoc ngoai gio; trong phien dedup theo (symbol, t)."""
    to = int(time.time()) + 60
    frm = to - lookback_sec
    out = []
    for sym in INDEX_SYMBOLS:
        for fn in (_bars_vnd, _bars_entrade, _bars_ssi):
            try:
                df = fn(sym, frm, to)
                if df is not None and len(df):
                    out.append(df)
                    break
            except Exception as e:  # noqa: BLE001
                log(f"  ! {fn.__name__}({sym}): {type(e).__name__}: {str(e)[:80]}")
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ----------------------------------------------------------------------------- 2. bang gia toan thi truong
def fetch_stocks_ssi() -> pd.DataFrame:
    rows = []
    for ex in EXCHANGES:
        r = requests.get(f"https://iboard-query.ssi.com.vn/stock/exchange/{ex}", headers=H_SSI, timeout=40)
        r.raise_for_status()
        j = r.json()
        rows += (j.get("data") if isinstance(j, dict) else j) or []
    df = pd.DataFrame(rows)
    keep = [c for c in STOCK_COLS if c in df.columns]
    df = df[keep].rename(columns=STOCK_COLS)
    df["source"] = "ssi"
    return df


def fetch_stocks_vci(symbols: list[str]) -> pd.DataFrame:
    """Fallback: Vietcap getList, moi lan toi da ~300 ma. Tra cung schema (thieu bid/ask sau, change tu tinh)."""
    rows = []
    board = {"HSX": "hose", "HNX": "hnx", "UPCOM": "upcom"}
    for i in range(0, len(symbols), 300):
        r = requests.post("https://trading.vietcap.com.vn/api/price/symbols/getList",
                          json={"symbols": symbols[i:i + 300]}, headers=H_VCI, timeout=40)
        r.raise_for_status()
        for it in r.json():
            li, mp, ba = it.get("listingInfo") or {}, it.get("matchPrice") or {}, it.get("bidAsk") or {}
            bids, asks = ba.get("bidPrices") or [{}], ba.get("askPrices") or [{}]
            price, ref = mp.get("matchPrice"), li.get("refPrice")
            rows.append({
                "symbol": li.get("symbol"), "exchange": board.get(li.get("board"), li.get("board")),
                "session": mp.get("session"), "ref": ref, "ceiling": li.get("ceiling"), "floor": li.get("floor"),
                "open": mp.get("openPrice"), "high": mp.get("highest"), "low": mp.get("lowest"), "price": price,
                "last_vol": mp.get("matchVol"), "change": (price - ref) if price and ref else None,
                "change_pct": (price / ref - 1) * 100 if price and ref else None,
                "volume": mp.get("accumulatedVolume"), "value": (mp.get("accumulatedValue") or 0) * 1e6,
                "avg_price": mp.get("avgMatchPrice"), "bid1": bids[0].get("price"), "bid1_vol": bids[0].get("volume"),
                "ask1": asks[0].get("price"), "ask1_vol": asks[0].get("volume"),
                "fr_buy_vol": mp.get("foreignBuyVolume"), "fr_buy_val": mp.get("foreignBuyValue"),
                "fr_sell_vol": mp.get("foreignSellVolume"), "fr_sell_val": mp.get("foreignSellValue"),
                "fr_room": mp.get("currentRoom"), "last_update_ms": None, "stock_type": li.get("stockType"),
                "source": "vci",
            })
    return pd.DataFrame(rows)


def fetch_stocks(symbol_cache: str) -> pd.DataFrame:
    try:
        df = fetch_stocks_ssi()
        if len(df) > 100:
            pd.Series(sorted(df["symbol"].dropna().unique())).to_csv(symbol_cache, index=False, header=False)
            return df
        log(f"  ! SSI tra {len(df)} ma -> fallback Vietcap")
    except Exception as e:  # noqa: BLE001
        log(f"  ! SSI iBoard: {type(e).__name__}: {str(e)[:80]} -> fallback Vietcap")
    syms = []
    if os.path.exists(symbol_cache):
        syms = pd.read_csv(symbol_cache, header=None)[0].dropna().astype(str).tolist()
    if not syms:
        raise RuntimeError("Khong co danh sach ma de goi Vietcap (chua co symbols.txt)")
    return fetch_stocks_vci(syms)


# ----------------------------------------------------------------------------- 3. tong hop
def summarize(stocks: pd.DataFrame, bars: pd.DataFrame, ts: dt.datetime) -> pd.DataFrame:
    st = stocks
    if "stock_type" in stocks.columns:                      # chi co phieu thuong (bo CW, ETF, trai phieu)
        st = stocks[stocks["stock_type"].isin(["s", "STOCK"]) | stocks["stock_type"].isna()]
    rows = []
    for ex, g in st.groupby("exchange"):
        ch = pd.to_numeric(g["change"], errors="coerce")
        price = pd.to_numeric(g["price"], errors="coerce")
        rows.append({
            "time": ts.replace(tzinfo=None), "exchange": ex, "n": int(len(g)),
            "advances": int((ch > 0).sum()), "declines": int((ch < 0).sum()),
            "unchanged": int(((ch == 0) & price.notna()).sum()),
            "ceiling": int((price == pd.to_numeric(g["ceiling"], errors="coerce")).sum()),
            "floor": int((price == pd.to_numeric(g["floor"], errors="coerce")).sum()),
            "value": float(pd.to_numeric(g["value"], errors="coerce").sum()),
            "fr_buy_val": float(pd.to_numeric(g["fr_buy_val"], errors="coerce").sum()),
            "fr_sell_val": float(pd.to_numeric(g["fr_sell_val"], errors="coerce").sum()),
        })
    df = pd.DataFrame(rows)
    if len(df):
        df["fr_net_val"] = df["fr_buy_val"] - df["fr_sell_val"]
        df["basis_vn30f1m"] = float("nan")
    if len(bars) and len(df):
        last = bars.sort_values("t").groupby("symbol")["c"].last()
        if "VN30F1M" in last.index and "VN30" in last.index:
            df["basis_vn30f1m"] = float(last["VN30F1M"] - last["VN30"])
    return df


def merge_parquet(new: pd.DataFrame, path: str, keys: list[str] | None) -> pd.DataFrame:
    if os.path.exists(path):
        new = pd.concat([pd.read_parquet(path), new], ignore_index=True)
    if keys:
        new = new.drop_duplicates(subset=keys, keep="last")
    new.to_parquet(path, index=False)
    return new


def poll_once(day_dir: str) -> None:
    ts = now_vn()
    t0 = time.time()
    bars = fetch_index_bars()
    stocks = fetch_stocks(os.path.join(HERE, "symbols.txt"))
    stocks["snapshot_time"] = ts.replace(tzinfo=None)
    summ = summarize(stocks, bars, ts)
    os.makedirs(day_dir, exist_ok=True)
    if len(bars):
        bars = merge_parquet(bars, os.path.join(day_dir, "index_1m.parquet"), ["symbol", "t"])
    stocks.to_parquet(os.path.join(day_dir, f"stocks_{ts:%H%M}.parquet"), index=False)
    stocks.to_parquet(os.path.join(day_dir, "stocks_latest.parquet"), index=False)
    if len(summ):
        merge_parquet(summ, os.path.join(day_dir, "market_summary.parquet"), None)
    msg = ""
    if len(bars):
        last = bars.sort_values("t").groupby("symbol")["c"].last()
        msg += f"VNINDEX {last.get('VNINDEX', '?')} VN30F1M {last.get('VN30F1M', '?')}"
    if len(summ) and (summ["exchange"] == "hose").any():
        h = summ[summ["exchange"] == "hose"].iloc[0]
        msg += (f" | basis {h['basis_vn30f1m']:+.1f} | HOSE tang/giam {h['advances']}/{h['declines']}"
                f" KN rong {h['fr_net_val'] / 1e9:+.0f} ty")
    log(f"OK {len(bars)} nen, {len(stocks)} ma, {time.time() - t0:.1f}s  {msg}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--force", action="store_true", help="bo qua kiem tra gio giao dich")
    a = ap.parse_args()
    while True:
        t = now_vn()
        day_dir = os.path.join(DATA, t.strftime("%Y-%m-%d"))
        if a.once or a.force or in_session(t):
            try:
                poll_once(day_dir)
            except Exception as e:  # noqa: BLE001
                log(f"X vong poll loi: {type(e).__name__}: {e}")
            if a.once:
                return
        elif t.hour * 60 + t.minute > 15 * 60 + 5 or t.weekday() >= 5:
            log("Het gio giao dich -> thoat")
            return
        else:
            log("Chua den gio (08:55) -> cho")
        time.sleep(max(5, a.interval - (time.time() % a.interval)))


if __name__ == "__main__":
    main()
