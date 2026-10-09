# -*- coding: utf-8 -*-
r"""
data_live.py - lop du lieu REAL-TIME: doc cac parquet ma bo thu DNSE (realtime-lab\dnse_stream.py) xuat moi 5 giay vao
D:\market-data\realtime-lab\data\<YYYY-MM-DD>\ de OVERLAY hang hom nay len cac bieu do lich su (with_live, muc "LIVE TOAN APP" duoi)
+ trang thai bo thu (Kho du lieu: PID, log, Bat/Tat). App KHONG mo DuckDB (1 process ghi).
Trang Live rieng da BO (09/10/2026, PV2: "bo ca phan live di"); cac ham chi phuc vu trang do (kpi, series_5s, breadth_5s, bars,
avg_curve, board/board_all, influence, foreign_all, market_scan, snapshot_today...) da xoa - xem git truoc commit "app: bo han trang Live".

File doc:  index_latest · index_1m · stocks_latest (toan san ~1.500 ma)
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
SESSION_START, SESSION_END = (8, 45), (15, 10)  # bo thu chay 08:45-15:10 T2-T6


def now_vn() -> datetime:
    return datetime.now(VN_TZ).replace(tzinfo=None)


def in_session(t: datetime | None = None) -> bool:
    t = t or now_vn()
    hm = t.hour * 60 + t.minute
    return t.weekday() < 5 and SESSION_START[0] * 60 + SESSION_START[1] <= hm <= SESSION_END[0] * 60 + SESSION_END[1]


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
