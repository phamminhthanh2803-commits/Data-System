# -*- coding: utf-8 -*-
r"""
data_live.py - lop du lieu REAL-TIME cho trang Live: doc cac parquet ma bo thu DNSE (realtime-lab\dnse_stream.py)
xuat moi 5 giay vao D:\market-data\realtime-lab\data\<YYYY-MM-DD>\. App KHONG mo DuckDB (1 process ghi).

File doc:  index_latest · market_summary (lich su 5 s) · index_1m · rt_bars_1m · rt_latest · influence_latest · foreign_latest
Chiu duoc file dang ghi do: doc lai 3 lan, van loi -> tra ket qua cu trong session_state. Cache ngan (ttl=4 s) theo mtime.
Don vi: total_val (chi so) = TY dong; fr_buy_val/fr_sell_val/buy_val/sell_val (khoi ngoai) = DONG -> chia 1e9.
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
