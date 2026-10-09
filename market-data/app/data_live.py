# -*- coding: utf-8 -*-
r"""
data_live.py - lop du lieu REAL-TIME cho trang Live: doc cac parquet ma bo thu DNSE (realtime-lab\dnse_stream.py)
xuat moi 5 giay vao D:\market-data\realtime-lab\data\<YYYY-MM-DD>\. App KHONG mo DuckDB (1 process ghi).

File doc:  index_latest · market_summary (lich su 5 s) · index_1m · rt_bars_1m · rt_latest · influence_latest · foreign_latest · stocks_latest (toan san)
Chiu duoc file dang ghi do: doc lai 3 lan, van loi -> tra ket qua cu trong session_state. Cache ngan (ttl=4 s) theo mtime.
Don vi: total_val (chi so) = TY dong; fr_buy_val/fr_sell_val/buy_val/sell_val (khoi ngoai) = DONG -> chia 1e9.
Khoi luong: rt_latest.total_vol/last_qty/bid*_qty, rt_bars_1m.volume, index_1m.volume, stocks_latest.total_vol deu la SO CO PHIEU
(dnse_stream.py nhan 10 tick/top_price luc parse tu 09/10/2026 13:12; truoc do rt_latest.total_vol & last_qty = 1/10).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

ROOT = os.path.normpath(os.environ.get("RT_ROOT", r"D:\market-data\realtime-lab"))
DATA = os.path.join(ROOT, "data")
LOGS = os.path.join(ROOT, "logs")
BAT = os.path.join(ROOT, "Chay-realtime.bat")
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
FILES = ["index_latest", "market_summary", "index_1m", "rt_bars_1m", "rt_latest", "influence_latest", "foreign_latest"]
TEN_IDX = {"VNINDEX": "VN-Index", "VN30": "VN30", "HNX": "HNX-Index", "HNX30": "HNX30", "UPCOM": "UPCoM", "VN100": "VN100",
           "VNXALLSHARE": "VNX Allshare", "VNDIVIDEND": "VN Dividend", "VNMITECH": "VNMidtech", "VN50GROWTH": "VN50 Growth",
           "VN30F1M": "VN30F1M", "VN30F2M": "VN30F2M"}
TOAN_TT = ["VNINDEX", "HNX", "UPCOM"]          # cong 3 san = toan thi truong
SESSION_START, SESSION_END = (8, 45), (15, 10)  # bo thu chay 08:45-15:10 T2-T6


def now_vn() -> datetime:
    return datetime.now(VN_TZ).replace(tzinfo=None)


def in_session(t: datetime | None = None) -> bool:
    t = t or now_vn()
    hm = t.hour * 60 + t.minute
    return t.weekday() < 5 and SESSION_START[0] * 60 + SESSION_START[1] <= hm <= SESSION_END[0] * 60 + SESSION_END[1]


def trang_thai_phien(t: datetime | None = None) -> str:
    """Mo ta ngan: 'Dang giao dich' / 'Nghi trua' / 'ATC' / 'Ngoai gio'."""
    t = t or now_vn()
    if not in_session(t):
        return "Ngoài giờ giao dịch"
    hm = t.hour * 60 + t.minute
    if hm < 9 * 60:
        return "Trước giờ mở cửa"
    if 11 * 60 + 30 <= hm < 13 * 60:
        return "Nghỉ trưa"
    if 14 * 60 + 30 <= hm < 14 * 60 + 45:
        return "ATC"
    if hm >= 15 * 60:
        return "Đã đóng cửa"
    return "Đang giao dịch"


# --------------------------------------------------------------------- NGAY CO DU LIEU
def days() -> list[str]:
    """Cac thu muc data\\YYYY-MM-DD co index_latest.parquet (schema moi), tang dan."""
    if not os.path.isdir(DATA):
        return []
    out = []
    for n in os.listdir(DATA):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", n) and os.path.exists(os.path.join(DATA, n, "index_latest.parquet")):
            out.append(n)
    return sorted(out)


def latest_day() -> str | None:
    d = days()
    return d[-1] if d else None


def _stat(path):
    try:
        s = os.stat(path)
        return s.st_mtime_ns, s.st_size
    except OSError:
        return None


@st.cache_data(ttl=4, show_spinner=False)
def _read_pq(path: str, mtime_ns: int, size: int) -> pd.DataFrame:
    return pd.read_parquet(path)


def read(day: str, name: str) -> pd.DataFrame:
    """Doc 1 parquet cua ngay; thu lai 3 lan (file dang ghi do), van loi -> ket qua cu trong session_state."""
    path = os.path.join(DATA, day, f"{name}.parquet")
    fb = st.session_state.setdefault("_live_fb", {})
    key = f"{day}/{name}"
    last_err = None
    for i in range(3):
        st_ = _stat(path)
        if st_ is None:
            return fb.get(key, pd.DataFrame())
        try:
            df = _read_pq(path, *st_)
            fb[key] = df
            return df
        except Exception as e:  # noqa: BLE001 - parquet dang ghi do / doc lech
            last_err = e
            time.sleep(0.25 * (i + 1))
    if key in fb:
        return fb[key]
    st.session_state["_live_err"] = f"{name}: {type(last_err).__name__}"
    return pd.DataFrame()


def load_day(day: str) -> dict[str, pd.DataFrame]:
    return {n: read(day, n) for n in FILES}


# --------------------------------------------------------------------- TONG HOP
def ts_max(d: dict) -> pd.Timestamp | None:
    ts = []
    for n in ("index_latest", "rt_latest", "foreign_latest"):
        df = d.get(n)
        if df is not None and len(df) and "ts_recv" in df:
            ts.append(pd.Timestamp(pd.to_datetime(df["ts_recv"]).max()).as_unit("ns"))
    return max(ts) if ts else None


def _val_ty(s: pd.Series) -> pd.Series:
    """Gia tri dong -> ty neu so lon (ticks: grossTradeAmount dong; chi so: da la ty)."""
    s = pd.to_numeric(s, errors="coerce")
    med = s.abs().median() if s.notna().any() else 0
    return s / 1e9 if med and med > 1e6 else s


def kpi(d: dict) -> dict:
    """So lieu cho KPI strip: tung chi so, VN30F1M + basis, GTGD toan TT, do rong, gio cap nhat."""
    il = d["index_latest"]
    out = {"idx": {}, "f1m": None, "basis": None, "gtgd": np.nan, "adv": 0, "dec": 0, "unch": 0, "ceil": 0, "floor": 0, "ts": None}
    if il is None or il.empty:
        return out
    il = il.set_index("index_name")
    for k in il.index:
        r = il.loc[k]
        out["idx"][k] = dict(value=r.get("value"), change=r.get("change"), pct=r.get("change_pct"), prior=r.get("prior"),
                             high=r.get("high"), low=r.get("low"), total_val=r.get("total_val"))
    tt = il.reindex(TOAN_TT)
    out["gtgd"] = float(pd.to_numeric(tt["total_val"], errors="coerce").sum())
    for c, k in (("advances", "adv"), ("declines", "dec"), ("unchanged", "unch"), ("ceiling", "ceil"), ("floor", "floor")):
        out[k] = int(pd.to_numeric(tt[c], errors="coerce").fillna(0).sum()) if c in tt else 0
    out["ts"] = pd.Timestamp(pd.to_datetime(il["ts_recv"]).max()).as_unit("ns")
    # VN30F1M: gia moi nhat tu rt_latest (price) hoac nen 1 phut cuoi
    f1m = None
    rl = d["rt_latest"]
    if rl is not None and len(rl) and "price" in rl and (rl.symbol == "VN30F1M").any():
        v = rl.loc[rl.symbol == "VN30F1M", "price"].iloc[-1]
        f1m = float(v) if pd.notna(v) else None
    if f1m is None:
        b = d["index_1m"]
        if b is not None and len(b) and (b.symbol == "VN30F1M").any():
            f1m = float(b[b.symbol == "VN30F1M"].sort_values("t")["close"].dropna().iloc[-1])
    out["f1m"] = f1m
    if "basis_vn30f1m" in il and pd.notna(il["basis_vn30f1m"].iloc[0]) and il["basis_vn30f1m"].iloc[0] is not None:
        try:
            out["basis"] = float(il["basis_vn30f1m"].iloc[0])
        except (TypeError, ValueError):
            out["basis"] = None
    if out["basis"] is None and f1m is not None and "VN30" in out["idx"] and pd.notna(out["idx"]["VN30"]["value"]):
        out["basis"] = f1m - float(out["idx"]["VN30"]["value"])
    return out


def series_5s(d: dict, idx: str = "VNINDEX", cols=("value", "total_val")) -> pd.DataFrame:
    """Lich su 5 s cua 1 chi so (market_summary) -> index ts_recv."""
    ms = d["market_summary"]
    if ms is None or ms.empty or "index_name" not in ms:
        return pd.DataFrame()
    m = ms[ms.index_name == idx].copy()
    if m.empty:
        return pd.DataFrame()
    m["ts_recv"] = pd.to_datetime(m["ts_recv"]).astype("datetime64[ns]")   # ep ns: tranh loi union index us/ns khi concat
    m = m.sort_values("ts_recv").drop_duplicates("ts_recv", keep="last").set_index("ts_recv")
    keep = [c for c in cols if c in m]
    return m[keep].apply(pd.to_numeric, errors="coerce")


def gtgd_toan_tt_5s(d: dict) -> pd.Series:
    """GTGD luy ke toan thi truong (ty) theo thoi gian = tong 3 san, resample 5 s."""
    parts = []
    for i in TOAN_TT:
        s = series_5s(d, i, ("total_val",))
        if not s.empty:
            parts.append(s["total_val"].resample("5s").last().ffill().rename(i))
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts, axis=1).ffill().sum(axis=1, min_count=1).rename("GTGD toàn TT")


def breadth_5s(d: dict, idx: str = "VNINDEX") -> pd.DataFrame:
    s = series_5s(d, idx, ("advances", "declines", "unchanged"))
    if s.empty:
        return s
    s = s.rename(columns={"advances": "Tăng", "declines": "Giảm", "unchanged": "Đứng giá"})
    tot = s.sum(axis=1).replace(0, np.nan)
    s["% tăng"] = s["Tăng"] / tot * 100
    return s


def bars(d: dict, sym: str, src: str = "index_1m") -> pd.DataFrame:
    b = d[src]
    if b is None or b.empty or "symbol" not in b:
        return pd.DataFrame()
    o = b[b.symbol == sym].copy()
    if o.empty:
        return o
    o["time"] = pd.to_datetime(o["time"]).astype("datetime64[ns]")
    o = o.sort_values("t").drop_duplicates("t", keep="last").set_index("time")[["open", "high", "low", "close", "volume"]]
    return o.apply(pd.to_numeric, errors="coerce")


def bar_symbols(d: dict, src: str = "rt_bars_1m") -> list[str]:
    b = d[src]
    return sorted(b.symbol.dropna().unique().tolist()) if b is not None and len(b) and "symbol" in b else []


@st.cache_data(ttl=600, show_spinner=False)
def avg_curve(prev_days: tuple, n: int = 20) -> pd.Series:
    """Duong binh quan GTGD luy ke toan TT theo moc gio (1 phut) cua toi da n phien truoc co market_summary.
    Tra Series index = time-of-day (Timedelta tu 00:00)."""
    curves = []
    for day in list(prev_days)[-n:]:
        try:
            ms = pd.read_parquet(os.path.join(DATA, day, "market_summary.parquet"))
        except Exception:  # noqa: BLE001
            continue
        if ms.empty or "index_name" not in ms:
            continue
        d = {"market_summary": ms}
        g = gtgd_toan_tt_5s(d)
        if g.empty:
            continue
        g = g.resample("1min").last().ffill()
        g.index = g.index - g.index.normalize()
        curves.append(g)
    if not curves:
        return pd.Series(dtype=float)
    return pd.concat(curves, axis=1).mean(axis=1).rename(f"BQ {len(curves)} phiên")


def foreign_table(d: dict) -> pd.DataFrame:
    """Khoi ngoai luy ke theo ma (ty): mua, ban, rong, room con; gop rt_latest (fr_*) + foreign_latest."""
    rows = {}
    fl = d["foreign_latest"]
    if fl is not None and len(fl) and "symbol" in fl:
        for _, r in fl.iterrows():
            b = r.get("total_buy_val") if pd.notna(r.get("total_buy_val", np.nan)) else r.get("buy_val")
            s = r.get("total_sell_val") if pd.notna(r.get("total_sell_val", np.nan)) else r.get("sell_val")
            rows[r.symbol] = dict(mua=b, ban=s, room=r.get("room_left"), ts=r.get("ts_recv"))
    rl = d["rt_latest"]
    if rl is not None and len(rl) and "fr_buy_val" in rl:
        for _, r in rl.iterrows():
            if pd.isna(r.get("fr_buy_val", np.nan)) and pd.isna(r.get("fr_sell_val", np.nan)):
                continue
            cur = rows.get(r.symbol)
            if cur is None or (pd.notna(r.get("ts_recv")) and pd.notna(cur.get("ts")) and pd.Timestamp(r.ts_recv) >= pd.Timestamp(cur["ts"])):
                rows[r.symbol] = dict(mua=r.get("fr_buy_val"), ban=r.get("fr_sell_val"), room=r.get("fr_room_left"), ts=r.get("ts_recv"))
    if not rows:
        return pd.DataFrame(columns=["Mua (tỷ)", "Bán (tỷ)", "Ròng (tỷ)", "Room còn (tr CP)"])
    t = pd.DataFrame.from_dict(rows, orient="index")
    t["Mua (tỷ)"] = pd.to_numeric(t["mua"], errors="coerce").fillna(0) / 1e9
    t["Bán (tỷ)"] = pd.to_numeric(t["ban"], errors="coerce").fillna(0) / 1e9
    t["Ròng (tỷ)"] = t["Mua (tỷ)"] - t["Bán (tỷ)"]
    t["Room còn (tr CP)"] = pd.to_numeric(t["room"], errors="coerce") / 1e6
    t.index.name = "Mã"
    return t[["Mua (tỷ)", "Bán (tỷ)", "Ròng (tỷ)", "Room còn (tr CP)"]].sort_values("Ròng (tỷ)", ascending=False)


def influence(d: dict, idx: str = "VNINDEX", n: int = 10):
    """(keo len, keo xuong) - Series influence (diem) top n moi chieu."""
    inf = d["influence_latest"]
    if inf is None or inf.empty or "index_name" not in inf:
        return pd.Series(dtype=float), pd.Series(dtype=float), None
    m = inf[inf.index_name == idx].dropna(subset=["influence"])
    if m.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float), None
    s = m.set_index("symbol")["influence"].astype(float)
    up = s[s > 0].sort_values(ascending=False).head(n)
    dn = s[s < 0].sort_values().head(n)
    ts = pd.to_datetime(m["ts_recv"]).max() if "ts_recv" in m else None
    return up, dn, ts


def influence_indices(d: dict) -> list[str]:
    inf = d["influence_latest"]
    if inf is None or inf.empty or "index_name" not in inf:
        return ["VNINDEX"]
    order = ["VNINDEX", "VN30", "HNX", "HNX30", "VN100"]
    have = set(inf.index_name.dropna().unique())
    return [i for i in order if i in have] + sorted(have - set(order))


@st.cache_data(ttl=3600, show_spinner=False)
def prior_close(symbols: tuple, before: str) -> pd.Series:
    """Gia dong cua phien truoc (tv-history, gia dieu chinh) -> tham chieu ±% cho bang gia khi feed chua co ref."""
    try:
        import datalib as dl
        tv = dl.tv()
        t = tv[(tv.symbol.isin(list(symbols))) & (tv.date < pd.Timestamp(before))]
        return t.sort_values("date").groupby("symbol", observed=True)["close"].last()
    except Exception:  # noqa: BLE001
        return pd.Series(dtype=float)


def board(d: dict, day: str) -> pd.DataFrame:
    """Bang gia ma theo doi (rt_latest) + khoi ngoai; ±% theo change_pct cua influence neu co, khong thi theo gia dong cua phien truoc."""
    rl = d["rt_latest"]
    if rl is None or rl.empty or "symbol" not in rl:
        return pd.DataFrame()
    t = rl.copy().drop_duplicates("symbol", keep="last").set_index("symbol")
    for c in ("price", "bid1", "ask1", "last_qty", "total_vol", "total_val", "high", "low", "open", "avg_price", "bid1_qty", "ask1_qty"):
        if c not in t:
            t[c] = np.nan
    t["total_val"] = _val_ty(t["total_val"])
    # tham chieu
    ref = pd.Series(np.nan, index=t.index, dtype=float)
    inf = d["influence_latest"]
    if inf is not None and len(inf) and "change_pct" in inf and inf["change_pct"].notna().any():
        cp = inf.dropna(subset=["change_pct"]).drop_duplicates("symbol", keep="last").set_index("symbol")["change_pct"]
        t["pct"] = cp.reindex(t.index)
    else:
        t["pct"] = np.nan
    stocks = tuple(s for s in t.index if not str(s).startswith("VN30F"))
    pc = prior_close(stocks, day)
    if len(pc) and pc.median() > 500:          # tv-history: dong; DNSE: nghin dong
        pc = pc / 1000.0
    ref.loc[pc.index.intersection(ref.index)] = pc.reindex(ref.index).dropna()
    mask = t["pct"].isna() & t["price"].notna() & ref.notna() & (ref > 0)
    t.loc[mask, "pct"] = (t.loc[mask, "price"] / ref[mask] - 1) * 100
    t["ref"] = ref
    fr = foreign_table(d)
    t = t.join(fr[["Ròng (tỷ)", "Room còn (tr CP)"]], how="left")
    t = t.rename(columns={"price": "Giá", "pct": "±%", "bid1": "Bid1", "ask1": "Ask1", "last_qty": "KL khớp cuối", "total_vol": "KL tổng",
                          "total_val": "GTGD (tỷ)", "Ròng (tỷ)": "KN ròng (tỷ)", "Room còn (tr CP)": "Room (tr CP)",
                          "high": "Cao", "low": "Thấp", "ref": "Tham chiếu"})
    cols = ["Giá", "±%", "Bid1", "Ask1", "KL khớp cuối", "KL tổng", "GTGD (tỷ)", "KN ròng (tỷ)", "Room (tr CP)", "Cao", "Thấp", "Tham chiếu"]
    t = t[cols].copy()
    t.index.name = "Mã"
    # phai sinh xuong cuoi
    t["_fut"] = [str(s).startswith("VN30F") for s in t.index]
    t = t.sort_values(["_fut", "±%"], ascending=[True, False], na_position="last").drop(columns="_fut")
    return t


# --------------------------------------------------------------------- TOAN SAN (stocks_latest, 09/10/2026 chieu)
EXCH_ORDER = ["HOSE", "HNX", "UPCOM"]


def _stocks_day(d: dict) -> pd.DataFrame:
    """stocks_latest cua ngay dang xem (gia DONG, total_vol CP, total_val/fr_* TY, src dnse|ssi, ts). Rong neu chua co."""
    s = d.get("stocks_latest")
    if s is None or s.empty or "symbol" not in s:
        return pd.DataFrame()
    s = s.drop_duplicates("symbol", keep="last").set_index("symbol")
    for c in ("ref", "ceiling", "floor", "price", "change", "change_pct", "total_vol", "total_val", "fr_buy_val", "fr_sell_val", "fr_net_val"):
        s[c] = pd.to_numeric(s[c], errors="coerce") if c in s else np.nan
    s["exchange"] = (s["exchange"] if "exchange" in s else pd.Series(index=s.index, dtype=object)).astype(str).str.upper()
    if "src" not in s:
        s["src"] = None
    if "ts" not in s:
        s["ts"] = pd.NaT
    return s


def board_all(d: dict, basket: str = "VN30", q: str = "", sort: str = "±%") -> pd.DataFrame:
    """Bang gia TOAN SAN tu stocks_latest (gia NGHIN dong nhu bang cu); bid/ask 1 chi cho ma co trong rt_latest (VN30).
    basket: VN30 | HOSE | HNX | UPCOM | Tất cả. q: loc ma (chua chuoi). sort: '±%' | 'GTGD' | 'KL'."""
    s = _stocks_day(d)
    if s.empty:
        return pd.DataFrame()
    if basket == "VN30":
        s = s[s.index.isin(vn30_symbols())]
    elif basket in EXCH_ORDER:
        s = s[s.exchange == basket]
    q = (q or "").strip().upper()
    if q:
        s = s[s.index.astype(str).str.contains(q, regex=False)]
    if s.empty:
        return pd.DataFrame()
    t = pd.DataFrame(index=s.index)
    t["_ex"] = s.exchange
    for src, dst in (("price", "Giá"), ("change_pct", "±%"), ("ceiling", "Trần"), ("floor", "Sàn"), ("ref", "TC")):
        t[dst] = s[src] / 1000.0 if dst != "±%" else s[src]
    rl = d.get("rt_latest")
    bid = ask = pd.Series(np.nan, index=t.index, dtype=float)
    if rl is not None and len(rl) and "symbol" in rl and "bid1" in rl:
        r = rl.drop_duplicates("symbol", keep="last").set_index("symbol")
        bid = pd.to_numeric(r["bid1"], errors="coerce").reindex(t.index)
        ask = pd.to_numeric(r["ask1"], errors="coerce").reindex(t.index)
    t["Bid1"], t["Ask1"] = bid, ask
    t["KL"] = s.total_vol
    t["GTGD (tỷ)"] = s.total_val
    t["KN ròng (tỷ)"] = s.fr_net_val
    t["Nguồn"] = np.where(s.src.astype(str) == "dnse", "● 5 s", "○ 1 phút")
    ts = pd.to_datetime(s.ts, errors="coerce")
    t["Giờ"] = ts.dt.strftime("%H:%M:%S").where(ts.notna(), None)
    key = {"±%": "±%", "GTGD": "GTGD (tỷ)", "KL": "KL"}.get(sort, "±%")
    t = t.sort_values(key, ascending=False, na_position="last")
    t.index.name = "Mã"
    return t


def foreign_all(d: dict) -> dict | None:
    """Khoi ngoai trong phien TOAN SAN tu stocks_latest (ty): rong/mua/ban toan TT, theo san, top mua/ban rong, bang theo ma."""
    s = _stocks_day(d)
    if s.empty:
        return None
    f = s[s.fr_buy_val.notna() | s.fr_sell_val.notna()].copy()
    if f.empty:
        return None
    f["mua"], f["ban"] = f.fr_buy_val.fillna(0), f.fr_sell_val.fillna(0)
    f["rong"] = f["mua"] - f["ban"]
    by_ex = f.groupby("exchange")[["mua", "ban", "rong"]].sum().reindex(EXCH_ORDER).dropna(how="all")
    net = f["rong"]
    tbl = f[["exchange", "mua", "ban", "rong"]].rename(columns={"exchange": "Sàn GD", "mua": "Mua (tỷ)", "ban": "Bán (tỷ)", "rong": "KN ròng (tỷ)"})
    tbl = tbl[(tbl["Mua (tỷ)"] != 0) | (tbl["Bán (tỷ)"] != 0)].sort_values("KN ròng (tỷ)", ascending=False)
    tbl.index.name = "Mã"
    ts = pd.to_datetime(f.ts, errors="coerce").max()
    return {"net": float(net.sum()), "mua": float(f["mua"].sum()), "ban": float(f["ban"].sum()), "n": int(len(tbl)),
            "by_ex": by_ex, "top_mua": net[net > 0].sort_values(ascending=False).head(10),
            "top_ban": net[net < 0].sort_values().head(10), "table": tbl, "ts": ts,
            "n_dnse": int((f.src.astype(str) == "dnse").sum())}


def market_scan(d: dict) -> dict | None:
    """'Toan san trong phien': so ma tang/giam/dung/tran/san theo san tu stocks_latest (doi chieu advances/declines cua
    index_latest), top 10 tang/giam % (GTGD >= 0,5 ty) va top 10 GTGD."""
    s = _stocks_day(d)
    if s.empty:
        return None
    has = s.price.notna() & s.ref.notna() & (s.ref > 0)
    x = s[has].copy()
    x["chg"] = x.price - x.ref
    x["tran"] = x.ceiling.notna() & (x.price >= x.ceiling - 1e-6)
    x["san"] = x.floor.notna() & (x.price <= x.floor + 1e-6)
    idx = {}
    il = d.get("index_latest")
    if il is not None and len(il) and "index_name" in il:
        i2 = il.drop_duplicates("index_name", keep="last").set_index("index_name")
        for ex, code in (("HOSE", "VNINDEX"), ("HNX", "HNX"), ("UPCOM", "UPCOM")):
            if code in i2.index:
                r = i2.loc[code]
                idx[ex] = (r.get("advances"), r.get("declines"), r.get("ceiling"), r.get("floor"))

    def _pair(a, b):
        return f"{int(a)}/{int(b)}" if a is not None and b is not None and pd.notna(a) and pd.notna(b) else "—"

    rows = []
    for ex in EXCH_ORDER:
        g = x[x.exchange == ex]
        a, dcl, c, f = idx.get(ex, (None, None, None, None))
        rows.append({"Sàn GD": EXCH_TEN.get(ex, ex), "Tăng": int((g.chg > 0).sum()), "Giảm": int((g.chg < 0).sum()),
                     "Đứng": int((g.chg == 0).sum()), "Kịch trần": int(g.tran.sum()), "Kịch sàn": int(g.san.sum()),
                     "Có giá": int(len(g)), "Niêm yết": int((s.exchange == ex).sum()),
                     "Chỉ số tăng/giảm": _pair(a, dcl), "Chỉ số trần/sàn": _pair(c, f)})
    tot = {"Sàn GD": "Toàn TT", **{k: int(sum(r[k] for r in rows)) for k in ("Tăng", "Giảm", "Đứng", "Kịch trần", "Kịch sàn", "Có giá", "Niêm yết")},
           "Chỉ số tăng/giảm": "—", "Chỉ số trần/sàn": "—"}
    summ = pd.DataFrame(rows + [tot]).set_index("Sàn GD")
    cols = ["exchange", "price", "change_pct", "total_val", "total_vol"]
    liq = x[x.total_val.fillna(0) >= 0.5]                 # loai ma chi khop vai chuc trieu
    top_up = liq.sort_values("change_pct", ascending=False).head(10)[cols]
    top_dn = liq.sort_values("change_pct").head(10)[cols]
    top_val = x.sort_values("total_val", ascending=False).head(10)[cols]
    return {"summary": summ, "top_up": top_up, "top_dn": top_dn, "top_val": top_val,
            "ts": pd.to_datetime(s.ts, errors="coerce").max(), "n_dnse": int((s.src.astype(str) == "dnse").sum()),
            "n_price": int(len(x))}


# --------------------------------------------------------------------- BO THU
def log_tail(n: int = 5) -> tuple[str | None, list[str]]:
    if not os.path.isdir(LOGS):
        return None, []
    fs = sorted(f for f in os.listdir(LOGS) if re.fullmatch(r"realtime_\d{8}\.log", f))
    if not fs:
        return None, []
    p = os.path.join(LOGS, fs[-1])
    try:
        with open(p, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 20000))
            txt = f.read().decode("utf-8", errors="replace")
        lines = [ln.rstrip() for ln in txt.splitlines() if ln.strip()]
        return p, [ln[:220] for ln in lines[-n:]]
    except OSError:
        return p, []


@st.cache_data(ttl=4, show_spinner=False)
def collector_pids(_tick: int = 0) -> list[int]:
    """PID cac tien trinh python dang chay dnse_stream.py (psutil; khong co -> PowerShell CIM)."""
    try:
        import psutil
        out = []
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                nm = (p.info.get("name") or "").lower()
                cl = " ".join(p.info.get("cmdline") or [])
                if nm.startswith("python") and "dnse_stream.py" in cl:
                    out.append(p.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return out
    except ImportError:
        if sys.platform != "win32":
            return []
        cmd = ["powershell", "-NoProfile", "-Command",
               "Get-CimInstance Win32_Process -Filter \"name like 'python%'\" | Where-Object {$_.CommandLine -like '*dnse_stream.py*'} | Select-Object -ExpandProperty ProcessId"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return [int(x) for x in r.stdout.split() if x.strip().isdigit()]
        except Exception:  # noqa: BLE001
            return []


def collector_running() -> bool:
    return bool(collector_pids())


def start_collector() -> str:
    if sys.platform != "win32":
        return "Chỉ bật được trên Windows (Chay-realtime.bat)."
    if not os.path.exists(BAT):
        return f"Không thấy {BAT}"
    if collector_pids():
        return "Bộ thu đang chạy rồi."
    try:
        subprocess.Popen(["cmd", "/c", "start", "", "/min", BAT], cwd=ROOT,
                         creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0))
        collector_pids.clear()
        return "Đã gửi lệnh bật bộ thu (cửa sổ thu nhỏ). Chờ ~10 s để có dữ liệu."
    except Exception as e:  # noqa: BLE001
        return f"Không bật được: {e}"


def stop_collector() -> str:
    pids = collector_pids()
    if not pids:
        return "Bộ thu không chạy."
    try:
        import psutil
        for pid in pids:
            try:
                psutil.Process(pid).terminate()
            except psutil.Error:
                pass
    except ImportError:
        for pid in pids:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    collector_pids.clear()
    return f"Đã tắt bộ thu (PID {', '.join(map(str, pids))})."


# --------------------------------------------------------------------- TOM TAT CHO TONG QUAN
def snapshot_today() -> dict | None:
    """KPI live gon cho Tong quan: chi khi co thu muc data cua HOM NAY."""
    today = now_vn().strftime("%Y-%m-%d")
    if today not in days():
        return None
    d = load_day(today)
    k = kpi(d)
    if not k["idx"]:
        return None
    k["day"] = today
    k["lag"] = (now_vn() - k["ts"].to_pydatetime()).total_seconds() if k["ts"] is not None else None
    return k


# =====================================================================================================================
# LIVE TOAN APP (09/10/2026, PV2: "tat ca cac chart va data live duoc thi live het, chi tai ve dung historical")
# Lop "overlay hom nay": moi dataset co the live co 1 ham tra ve HANG HOM NAY (dict cot -> gia tri) tinh tu cac parquet
# cua bo thu (stocks_latest = toan san ~1.500 ma, index_latest, index_1m). with_live(df, kind) ghep hang do vao lich su
# (thay the hang cung ngay neu co) va gan df.attrs["live"] de ui_genea ve dau tron rong + nhan "LIVE hh:mm:ss" va
# nut tai chi xuat lich su. Khong doc realtime.duckdb. Overlay tinh tu stocks_latest (<= 2.000 dong) < 300 ms, cache
# ttl 4 s theo mtime file.
# =====================================================================================================================
FILES = FILES + ["stocks_latest"]
IDX_MAP = {"VNINDEX": "VNINDEX", "VN30": "VN30", "HNXINDEX": "HNX", "UPCOM": "UPCOM"}     # ma app -> ma DNSE
EXCH_TEN = {"HOSE": "HOSE", "HNX": "HNX", "UPCOM": "UPCoM"}
LIVE_FREQ = {"5 s": 5, "15 s": 15, "60 s": 60}
LIVE_DEFAULT_FREQ = "15 s"


def today_ts() -> pd.Timestamp:
    return pd.Timestamp(now_vn().date())


def live_pref() -> tuple[bool, int]:
    """(bat?, tan suat s) tu session_state (header dat); mac dinh BAT trong gio 08:45-15:10 T2-T6, ngoai gio TAT."""
    on = st.session_state.get("live_on")
    if on is None:
        on = in_session()
    f = st.session_state.get("live_freq_all", LIVE_DEFAULT_FREQ)
    return bool(on), LIVE_FREQ.get(f, 15)


def _day_today() -> str | None:
    t = now_vn().strftime("%Y-%m-%d")
    return t if os.path.exists(os.path.join(DATA, t, "index_latest.parquet")) else None


def live_state() -> dict:
    """{'active': bool, 'ts': Timestamp|None, 'lag': s, 'day': str|None, 'reason': str} - active = cong tac bat + co du lieu
    HOM NAY + bo thu con phat (tre < 300 s trong gio)."""
    on, _ = live_pref()
    day = _day_today()
    out = {"active": False, "ts": None, "lag": None, "day": day, "reason": ""}
    if not on:
        out["reason"] = "tắt"
        return out
    if day is None:
        out["reason"] = "chưa có dữ liệu hôm nay"
        return out
    ts = None
    for n, col in (("index_latest", "ts_recv"), ("stocks_latest", "ts")):
        df = read(day, n)
        if df is not None and len(df) and col in df.columns:
            t = pd.to_datetime(df[col], errors="coerce").max()
            if pd.notna(t):
                ts = t if ts is None else max(ts, t)
    if ts is None:
        out["reason"] = "file trống"
        return out
    lag = (now_vn() - ts.to_pydatetime()).total_seconds()
    out.update(ts=ts, lag=lag)
    if in_session() and lag > 300:
        out["reason"] = f"bộ thu trễ {lag:,.0f} s"
        return out
    if not in_session() and lag > 1800:
        out["reason"] = "ngoài giờ"
        return out
    out["active"] = True
    return out


def stocks_today() -> pd.DataFrame:
    """stocks_latest.parquet hom nay (gia DONG, total_val / fr_* TY). Rong neu chua co."""
    day = _day_today()
    if day is None:
        return pd.DataFrame()
    d = read(day, "stocks_latest")
    if d is None or d.empty or "symbol" not in d:
        return pd.DataFrame()
    return d.drop_duplicates("symbol", keep="last").set_index("symbol")


def index_today() -> pd.DataFrame:
    day = _day_today()
    if day is None:
        return pd.DataFrame()
    d = read(day, "index_latest")
    if d is None or d.empty or "index_name" not in d:
        return pd.DataFrame()
    return d.drop_duplicates("index_name", keep="last").set_index("index_name")


def _idx_open(code_dnse: str):
    day = _day_today()
    if day is None:
        return np.nan
    b = read(day, "index_1m")
    if b is None or b.empty or "symbol" not in b:
        return np.nan
    o = b[b.symbol == code_dnse].sort_values("t")
    return float(o["open"].dropna().iloc[0]) if len(o) and o["open"].notna().any() else np.nan


# ------------------------------------------------------------------- OVERLAY: tung dataset
def ov_index_ohlc(df, code: str) -> dict | None:
    """Hang hom nay cho dx.index_ohlc(code): open/high/low/close/volume/value (ty)."""
    k = IDX_MAP.get(code)
    il = index_today()
    if k is None or il.empty or k not in il.index:
        return None
    r = il.loc[k]
    if pd.isna(r.get("value")):
        return None
    return {"open": _idx_open(k), "high": r.get("high"), "low": r.get("low"), "close": r.get("value"),
            "volume": r.get("total_vol"), "value": r.get("total_val")}


def ov_index_close(df, codes) -> dict | None:
    """Hang hom nay cho dx.index_close (cot = ten hien thi)."""
    import data_ext as dx
    il = index_today()
    if il.empty:
        return None
    out = {}
    for c in codes:
        k = IDX_MAP.get(c)
        if k and k in il.index and pd.notna(il.loc[k, "value"]):
            out[dx.VN_INDEX_TEN.get(c, c)] = float(il.loc[k, "value"])
    return out or None


def ov_world_close(df) -> dict | None:
    """Chi so the gioi (indices-master, cot = index_code hoac ten hien thi): chi chi so VN co live."""
    il = index_today()
    if il.empty:
        return None
    out = {}
    for c in df.columns:
        k = IDX_MAP.get(c) or {"VN-Index": "VNINDEX"}.get(c)
        if k and k in il.index and pd.notna(il.loc[k, "value"]):
            out[c] = float(il.loc[k, "value"])
    return out or None


def ov_turnover(df) -> dict | None:
    """Hang hom nay cho dl.turnover_df(): GTGD 3 san (ty) tu index_latest + MA20/50 tinh lai + VN-Index."""
    il = index_today()
    if il.empty or "VNINDEX" not in il.index:
        return None
    v = {EXCH_TEN[e]: float(il.loc[k, "total_val"]) for e, k in (("HOSE", "VNINDEX"), ("HNX", "HNX"), ("UPCOM", "UPCOM"))
         if k in il.index and pd.notna(il.loc[k, "total_val"])}
    if "HOSE" not in v:
        return None
    tot = sum(v.values())
    row = dict(v)
    row["Toàn thị trường"] = tot
    hist = df["Toàn thị trường"] if df is not None and "Toàn thị trường" in df else pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    hist = hist[hist.index < today_ts()]
    for w in (20, 50):
        s = pd.concat([hist.tail(w - 1), pd.Series([tot])])
        row[f"MA{w} toàn TT"] = float(s.mean()) if len(s) >= w else np.nan
    row["VN-Index"] = float(il.loc["VNINDEX", "value"])
    row["Nguồn"] = "LIVE DNSE"
    row["Phiên"] = "Đang giao dịch"
    return row


def _px_hist(n: int = 300) -> pd.DataFrame:
    import datalib as dl
    _, px, _ = dl.prices()
    return px[px.index < today_ts()].tail(n)


def _stocks_mt() -> int:
    day = _day_today()
    if day is None:
        return 0
    st_ = _stat(os.path.join(DATA, day, "stocks_latest.parquet"))
    return st_[0] if st_ else 0


@st.cache_data(ttl=4, show_spinner=False)
def _breadth_today(mt: int) -> dict | None:
    import datalib as dl
    s = stocks_today()
    if s.empty:
        return None
    px = _px_hist(300)
    m = dl.meta()
    cols = px.columns
    p_today = pd.to_numeric(s["price"], errors="coerce").reindex(cols)
    last = px.iloc[-1]
    p_eff = p_today.fillna(last)                      # ma chua khop hom nay -> gia dong cua truoc (nhu px ffill)
    ok_any = p_eff.notna()
    out = {}
    ch = pd.to_numeric(s["change"], errors="coerce").reindex(cols)
    has = p_today.notna() & ch.notna()
    adv, dec = int(((ch > 0) & has).sum()), int(((ch < 0) & has).sum())
    out.update({"Số mã tăng": adv, "Số mã giảm": dec, "Số mã đứng giá": int(((ch == 0) & has).sum()),
                "Số mã giao dịch": int(has.sum()), "% mã tăng": adv / (adv + dec) * 100 if adv + dec else np.nan,
                "Tăng - Giảm": adv - dec})
    exch = m.exchange.reindex(cols)
    px2 = pd.concat([px, p_eff.to_frame(today_ts()).T])
    for w in (20, 50, 100, 200, 300):
        tail = px2.tail(w)
        ma = tail.mean(axis=0).where(tail.notna().sum(axis=0) >= w)
        ok = ma.notna() & ok_any
        above, below = (p_eff > ma) & ok, (p_eff < ma) & ok
        out[f"% mã trên MA{w}"] = float(above.sum() / ok.sum() * 100) if ok.sum() else np.nan
        if w in (50, 200, 300):
            for ex in ("HOSE", "HNX", "UPCOM"):
                out[f"Dưới MA{w} - {ex}"] = int(below[exch == ex].sum())
            out[f"Dưới MA{w} - Toàn TT"] = int(below.sum())
            out[f"Số mã đủ dữ liệu MA{w}"] = int(ok.sum())
            out[f"% dưới MA{w}"] = float(below.sum() / ok.sum() * 100) if ok.sum() else np.nan
    return out


def ov_breadth(df) -> dict | None:
    return _breadth_today(_stocks_mt())


def ov_flows_vn(df) -> dict | None:
    """Hang hom nay cho dl.flows_vn(): KN rong theo san (ty) = tong fr_net_val stocks_latest; tu doanh KHONG live (NaN)."""
    s = stocks_today()
    if s.empty or "fr_net_val" not in s:
        return None
    g = s.groupby("exchange")["fr_net_val"].sum(min_count=1)
    if g.isna().all():
        return None
    row = {f"KN ròng {EXCH_TEN[e]}": float(g.get(e, np.nan)) for e in ("HOSE", "HNX", "UPCOM")}
    row["KN ròng toàn TT"] = float(np.nansum(list(row.values())))
    hist = df["KN ròng toàn TT"] if df is not None and "KN ròng toàn TT" in df else pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    hist = hist[hist.index < today_ts()]
    row["Luỹ kế KN toàn TT"] = float(hist.fillna(0).sum() + row["KN ròng toàn TT"])
    return row


def ov_net_flows(df) -> dict | None:
    r = ov_flows_vn(None)
    return {"Khối ngoại ròng": r["KN ròng toàn TT"], "Tự doanh ròng": np.nan} if r else None


def ov_flows_investor(df) -> dict | None:
    """GTGD theo NDT hom nay: khoi ngoai = (mua + ban)/2 (ty); tu doanh NaN; trong nuoc khac = tong - KN."""
    s = stocks_today()
    to = ov_turnover(None)
    if s.empty or not to:
        return None
    kn = float((s["fr_buy_val"].fillna(0) + s["fr_sell_val"].fillna(0)).sum() / 2)
    return {"Khối ngoại": kn, "Tự doanh": np.nan, "Trong nước khác": to["Toàn thị trường"] - kn}


def stock_foreign_today() -> pd.DataFrame:
    """Theo ma: Mua/Ban/Rong khoi ngoai hom nay (ty) + nhom nganh (pn hien hanh)."""
    import datalib as dl
    s = stocks_today()
    if s.empty or "fr_net_val" not in s:
        return pd.DataFrame()
    d = s[["exchange", "fr_buy_val", "fr_sell_val", "fr_net_val"]].dropna(subset=["fr_net_val"]).copy()
    d["nhom"] = d.index.map(dl.nganh_ma(dl.PN)).fillna("Chưa phân ngành")
    return d


def ov_stock_ohlc(df, code: str) -> dict | None:
    s = stocks_today()
    if s.empty or code not in s.index or pd.isna(s.loc[code, "price"]):
        return None
    r = s.loc[code]
    tv = r.get("total_val")
    return {"open": r.get("open"), "high": r.get("high"), "low": r.get("low"), "close": r.get("price"), "volume": r.get("total_vol"),
            "value_approx": (tv * 1e9) if pd.notna(tv) else np.nan}


def ov_stock_flows(df, code: str) -> dict | None:
    s = stocks_today()
    if s.empty or code not in s.index or pd.isna(s.loc[code, "fr_net_val"]):
        return None
    r = s.loc[code]
    return {"Khối ngoại ròng": r["fr_net_val"], "Khối ngoại mua": r.get("fr_buy_val"), "Khối ngoại bán": r.get("fr_sell_val"),
            "Tự doanh ròng": np.nan, "GTGD (tỷ)": r.get("total_val")}


# ---- von hoa & dinh gia: he so = tong(gia x so CP) / tong(tham chieu x so CP)
@st.cache_data(ttl=4, show_spinner=False)
def _cap_table(mt: int) -> pd.DataFrame:
    import datalib as dl
    s = stocks_today()
    if s.empty:
        return pd.DataFrame()
    m = dl.meta()
    t = s[["exchange", "price", "ref"]].copy()
    t["sh"] = m.total_shares_outstanding_fundamental.reindex(t.index)
    t["nhom"] = t.index.map(dl.nganh_ma(dl.PN))
    t = t[t.sh.notna() & t.price.notna() & t.ref.notna() & (t.ref > 0)]
    t["cap_now"], t["cap_ref"] = t.price * t.sh, t.ref * t.sh
    return t


def cap_ratio(symbols=None, exchange=None, nhom=None, exclude=()) -> float:
    """Von hoa hien tai / von hoa theo gia tham chieu cua 1 ro (NaN neu < 5 ma)."""
    t = _cap_table(_stocks_mt())
    if t.empty:
        return np.nan
    if symbols is not None:
        t = t[t.index.isin(list(symbols))]
    if exchange:
        t = t[t.exchange == exchange]
    if nhom:
        t = t[t.nhom == nhom]
    if exclude:
        t = t[~t.index.isin(list(exclude))]
    if len(t) < 5 or t.cap_ref.sum() <= 0:
        return np.nan
    return float(t.cap_now.sum() / t.cap_ref.sum())


_VN30: list | None = None


def vn30_symbols() -> list[str]:
    global _VN30
    if _VN30 is None:
        p = os.path.join(ROOT, "dnse_symbols.txt")
        try:
            syms = [ln.split("#")[0].strip().upper() for ln in open(p, encoding="utf-8-sig")]
            _VN30 = [s for s in syms if s and not s.startswith("VN30F")]
        except OSError:
            _VN30 = []
    return _VN30


VIN = ("VIC", "VHM", "VRE", "VPL")


def ratio_for_index(code: str, exclude_vin: bool = False) -> float:
    ex = VIN if exclude_vin else ()
    if code in ("VNINDEX", "VN-Index"):
        return cap_ratio(exchange="HOSE", exclude=ex)
    if code == "VN30":
        return cap_ratio(symbols=vn30_symbols(), exclude=ex)
    if code in ("HNX", "HNXINDEX", "HNX-Index"):
        return cap_ratio(exchange="HNX", exclude=ex)
    if code in ("UPCOM", "UPCoM"):
        return cap_ratio(exchange="UPCOM", exclude=ex)
    return np.nan


def ov_valuation(df, ratio_by_col: dict) -> dict | None:
    """P/E, P/B hom nay = gia tri cuoi x he so von hoa (ratio_by_col: cot -> he so). Cot NaN he so -> bo."""
    if df is None or df.empty:
        return None
    hist = df[df.index < today_ts()]
    if hist.empty:
        return None
    last = hist.ffill().iloc[-1]
    out = {}
    for c, r in ratio_by_col.items():
        if c in last.index and pd.notna(last[c]) and pd.notna(r):
            out[c] = float(last[c] * r)
    return out or None


def ov_sector_caps(df, pn) -> dict | None:
    """Hang hom nay cho chi so nganh rebase (dl.sector_caps[0]): gia tri cuoi x he so von hoa nganh (HOSE)."""
    import datalib as dl
    if df is None or df.empty:
        return None
    hist = df[df.index < today_ts()]
    if hist.empty:
        return None
    last = hist.iloc[-1]
    t = _cap_table(_stocks_mt())
    if t.empty:
        return None
    t = t[t.exchange == "HOSE"].copy()
    t["nhom"] = t.index.map(dl.nganh_ma(pn))
    out = {}
    for g in df.columns:
        sub = t if g == "Toàn HOSE" else t[t.nhom == g]
        if len(sub) >= 1 and sub.cap_ref.sum() > 0 and pd.notna(last[g]):
            out[g] = float(last[g] * sub.cap_now.sum() / sub.cap_ref.sum())
    return out or None


def px_with_today() -> pd.DataFrame:
    """Ma tran gia (ffill) + hang hom nay (gia khop, ma chua khop -> gia dong cua truoc) - cho hieu suat nganh/ma den hom nay."""
    import datalib as dl
    _, px, _ = dl.prices(since="2016-01-01")
    s = stocks_today()
    if s.empty:
        return px
    px = px[px.index < today_ts()]
    p = pd.to_numeric(s["price"], errors="coerce").reindex(px.columns).fillna(px.iloc[-1])
    return pd.concat([px, p.to_frame(today_ts()).T])


# kind lay tu snapshot SSI iBoard 60 s (khoi ngoai theo ma ngoai VN30, UPCOM) -> nhan "live 1 phut" (PV2: uu tien on dinh)
SRC_1M = {"flows_vn", "net_flows", "flows_investor", "stock_flows"}

OVERLAY = {
    "index_ohlc": ov_index_ohlc, "index_close": ov_index_close, "world_close": ov_world_close, "turnover": ov_turnover,
    "breadth": ov_breadth, "flows_vn": ov_flows_vn, "net_flows": ov_net_flows, "flows_investor": ov_flows_investor,
    "stock_ohlc": ov_stock_ohlc, "stock_flows": ov_stock_flows, "valuation": ov_valuation, "sector_caps": ov_sector_caps,
}


def with_live(df: pd.DataFrame, kind: str, **kw) -> pd.DataFrame:
    """Lich su + hang HOM NAY (thay the hang cung ngay neu co). Khong live duoc -> tra df nguyen (attrs khong co 'live')."""
    if df is None or not isinstance(df, pd.DataFrame) or not isinstance(df.index, pd.DatetimeIndex):
        return df
    stt = live_state()
    if not stt["active"]:
        return df
    try:
        row = OVERLAY[kind](df, **kw)
    except Exception as e:  # noqa: BLE001
        st.session_state["_live_err"] = f"{kind}: {type(e).__name__}: {str(e)[:120]}"
        return df
    if not row:
        return df
    today = today_ts()
    hist = df[df.index < today]
    new = pd.DataFrame([row], index=pd.DatetimeIndex([today], name=df.index.name))
    new = new.reindex(columns=df.columns)
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            new[c] = pd.to_numeric(new[c], errors="coerce")
    out = pd.concat([hist, new])
    out.index.name = df.index.name
    out.attrs = dict(df.attrs)
    out.attrs["live"] = {"ts": stt["ts"], "hist_end": hist.index.max() if len(hist) else None,
                         "src": "live 1 phút" if kind in SRC_1M else None}
    return out


def mark_live(df: pd.DataFrame, src: pd.DataFrame) -> pd.DataFrame:
    """Chep attrs['live'] tu src sang df (sau cac phep bien doi lam mat attrs: diff, rolling, resample...)."""
    if src is not None and hasattr(src, "attrs") and "live" in src.attrs and df is not None:
        df.attrs["live"] = src.attrs["live"]
    return df


# ------------------------------------------------------------------- bang / treemap tinh voi gia hom nay
def _live_ts_or_none():
    stt = live_state()
    return stt["ts"] if stt["active"] else None


@st.cache_data(ttl=4, show_spinner=False)
def _sector_returns_live(mt: int, pn: tuple, san: tuple) -> pd.DataFrame | None:
    import data_ext as dx
    px2 = px_with_today()
    if px2.index.max() != today_ts():
        return None
    return dx.sector_returns_from(px2, today_ts(), pn, san)


def sector_returns_live(pn, san=("HOSE",)):
    """(bang hieu suat nganh 1D...5Y tinh voi gia LIVE, gio) hoac (None, None) khi khong live."""
    ts = _live_ts_or_none()
    if ts is None:
        return None, None
    r = _sector_returns_live(_stocks_mt(), tuple(pn), tuple(san))
    return (r, ts) if r is not None else (None, None)


@st.cache_data(ttl=4, show_spinner=False)
def _stock_returns_live(mt: int, nhom: str, pn: tuple) -> pd.DataFrame | None:
    import data_ext as dx
    px2 = px_with_today()
    if px2.index.max() != today_ts():
        return None
    return dx.stock_returns_from(px2, nhom, today_ts(), pn)


def stock_returns_live(nhom, pn):
    ts = _live_ts_or_none()
    if ts is None:
        return None, None
    t = _stock_returns_live(_stocks_mt(), nhom, tuple(pn))
    return (t, ts) if t is not None else (None, None)


LIVE_1M = "live 1 phút"       # ghi canh nhan gio cho the dung nguon 60 s (treemap / KN theo nganh)


def treemap_add_today(d_hist: pd.DataFrame, pn) -> tuple[pd.DataFrame, object]:
    """Treemap khoi ngoai theo ma: cong them rong HOM NAY (stocks_latest) vao ky. Tra (bang, gio live | None)."""
    import datalib as dl
    ts = _live_ts_or_none()
    if ts is None:
        return d_hist, None
    s = stocks_today()
    if s.empty or "fr_net_val" not in s or s["fr_net_val"].notna().sum() == 0:
        return d_hist, None
    td = s["fr_net_val"].dropna()
    td = td[td != 0]
    nhom = dl.nganh_ma(pn)
    today = pd.DataFrame({"Mã": td.index, "Nhóm ngành": td.index.map(nhom).fillna("Chưa phân ngành"), "Ròng (tỷ)": td.values})
    base = d_hist[["Mã", "Nhóm ngành", "Ròng (tỷ)"]] if len(d_hist) else pd.DataFrame(columns=["Mã", "Nhóm ngành", "Ròng (tỷ)"])
    g = pd.concat([base, today]).groupby("Mã", as_index=False).agg({"Nhóm ngành": "first", "Ròng (tỷ)": "sum"})
    g = g[g["Ròng (tỷ)"].abs() > 0.05]
    g = g.reindex(g["Ròng (tỷ)"].abs().sort_values(ascending=False).index).head(250).reset_index(drop=True)
    return g, ts


def sector_flows_add_today(tong: pd.DataFrame, pn) -> tuple[pd.DataFrame, object]:
    """Khoi ngoai rong theo nganh (ca ky): cong them hom nay theo nhom. Tra (bang, gio live | None)."""
    import datalib as dl
    ts = _live_ts_or_none()
    if ts is None:
        return tong, None
    s = stocks_today()
    if s.empty or "fr_net_val" not in s or s["fr_net_val"].notna().sum() == 0:
        return tong, None
    d = s[["fr_buy_val", "fr_sell_val", "fr_net_val"]].dropna(subset=["fr_net_val"]).copy()
    d["nhom"] = d.index.map(dl.nganh_ma(pn)).fillna("Chưa phân ngành")
    g = d.groupby("nhom")[["fr_buy_val", "fr_sell_val", "fr_net_val"]].sum()
    out = tong.copy()
    for col, src in (("Mua (tỷ)", "fr_buy_val"), ("Bán (tỷ)", "fr_sell_val"), ("Ròng (tỷ)", "fr_net_val")):
        if col in out:
            add = g[src].reindex(out.index).fillna(0)
            out[col] = out[col].fillna(0) + add
    # nhom chi co hom nay
    for nh in g.index.difference(out.index):
        out.loc[nh, ["Mua (tỷ)", "Bán (tỷ)", "Ròng (tỷ)"]] = [g.loc[nh, "fr_buy_val"], g.loc[nh, "fr_sell_val"], g.loc[nh, "fr_net_val"]]
    return out.sort_values("Ròng (tỷ)", ascending=False).round(1), ts


def ratio_for_sector(name: str) -> float:
    """He so von hoa hom nay cua 1 nganh (ten ICB cap 2, khop ten voi nganh_ma((2, False)); khong khop -> NaN)."""
    import datalib as dl
    t = _cap_table(_stocks_mt())
    if t.empty:
        return np.nan
    nh = t.index.map(dl.nganh_ma((2, False)))
    sub = t[nh == name]
    if len(sub) < 3 or sub.cap_ref.sum() <= 0:
        return np.nan
    return float(sub.cap_now.sum() / sub.cap_ref.sum())


def ratio_for_stock(code: str) -> float:
    s = stocks_today()
    if s.empty or code not in s.index:
        return np.nan
    r = s.loc[code]
    if pd.isna(r.get("price")) or pd.isna(r.get("ref")) or not r.get("ref"):
        return np.nan
    return float(r["price"] / r["ref"])
