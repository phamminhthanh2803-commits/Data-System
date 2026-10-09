# -*- coding: utf-8 -*-
r"""
data_src.py - LOP NGUON LIVE-FIRST cho Market Data App (09/10/2026, PV2: "data nao live duoc thi keo live,
khong doi pull tai pipeline").

Voi du lieu ma nguon REST cong khai cung cap duoc CA LICH SU, app keo thang tu nguon do, cache parquet cuc bo
(cache\src\), moi lan mo app cap nhat TANG DAN trong THREAD NEN (khong chan render), hom nay (trong phien) van
do data_live.with_live overlay. Pipeline chi con cho thu khong live duoc (vi mo, VSDC, trai phieu, tu doanh theo ma, khu vuc...).

Nguon (khong can key, header User-Agent Mozilla, 0,3-1 s/request):
  Entrade/DNSE  services.entrade.com.vn/chart-api/v2/ohlcs/{index|stock|derivative}  -> nen ngay o,h,l,c,v (CHUA dieu chinh,
                chi khoi luong khop lenh). VNINDEX tu 2000; VN30/HNX/UPCOM/HNX30 tu 05/2020; ma tu 2012; VN30F1M tu 2018.
  VNDirect finfo api-finfo.vndirect.com.vn/v4/  vnmarket_prices (OHLC + accumulatedVal GTGD chi so tu 08/2017),
                stock_prices (theo NGAY ca san: open/high/low/close/basicPrice/nmVolume/ptVolume/nmValue/ptValue -> lap ngay thieu,
                3 request/ngay), foreigns (khoi ngoai theo chi so tu 08/2018 + theo ma theo ngay), proprietary_trading
                (tu doanh theo chi so tu 05/2022), ratios (P/E P/B P/S co tuc von hoa thi truong + 55 nganh ICB).
  EOD bo thu    realtime-lab\data\<ngay>\stocks_latest.parquet / index_latest.parquet (snapshot cuoi phien) - du phong khi VNDirect loi.

File cache (long-format, parquet, ghi tmp roi os.replace):
  index_daily.parquet        date, index_code (VNINDEX VN30 HNXINDEX UPCOM HNX30 VN30F1M), open high low close volume value(trieu VND) src
  stock_daily.parquet        symbol, date, open high low close (DONG), volume, value (VND), ref (gia tham chieu, chi dong vnd/eod), src
  flows_daily.parquet        schema flows-master (date,index_code,flow_type,buy_val...): VNINDEX/VN30/HNXINDEX/UPCOM x foreign/prop
  foreign_stocks_tail.parquet  khoi ngoai theo ma (code,date,floor,buyVal,sellVal,netVal,...) cac ngay sau pipeline
  valuation_daily.parquet    code,date,ratio,value (VNINDEX/HNX/UPCOM/VN30 x 5 ratio)
  sectors_tail.parquet       code,date,ratio,value (55 nganh ICB) cac ngay sau pipeline
  status.json                trang thai tung dataset (nguon, ngay cuoi, so dong, cap nhat luc, loi, tien do keo nen)

Chinh sach gop (datalib.load / datalib.tv): nguon live-first la CHINH (thay the hang cung ngay cua pipeline, vi pipeline hay
dinh hang "do phien"); giai doan nguon thieu (VN30 truoc 05/2020, ma truoc 2012...) noi lich su pipeline phia truoc; nguon loi /
offline -> fallback pipeline + ghi loi vao status. Ham source_status() tra bang cho chip "Nguon du lieu" va trang Kho du lieu.

Gia Entrade CHUA DIEU CHINH (kiem chung 09/10/2026: VNM/FPT/HPG/MWG ty le tv/entrade buoc thang dung ngay GDKHQ) -> datalib
tinh he so dieu chinh tu tv-history (pipeline, gia dieu chinh TradingView) cho phan qua khu; sau ngay cuoi tv-history, phat hien
su kien quyen bang gia tham chieu (ref != close hom truoc, HOSE/HNX) de dieu chinh tiep.

Module nay KHONG dung streamlit (thread nen goi duoc); cache st.cache_data nam o datalib.
"""
from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.normpath(os.environ.get("SRC_CACHE", os.path.join(APP_DIR, "cache", "src")))
os.makedirs(SRC_DIR, exist_ok=True)
RT_ROOT = os.path.normpath(os.environ.get("RT_ROOT", r"D:\market-data\realtime-lab"))
RT_DATA = os.path.join(RT_ROOT, "data")
SYMBOLS_TXT = os.path.join(RT_ROOT, "symbols.txt")
STATUS_JSON = os.path.join(SRC_DIR, "status.json")
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

ENTRADE = "https://services.entrade.com.vn/chart-api/v2/ohlcs/{kind}"
VND = "https://api-finfo.vndirect.com.vn/v4/"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
       "Accept": "application/json, text/plain, */*", "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8"}
PAGE = 1000
THREADS = 8
CLOSE_HM = (15, 15)           # sau 15:15 moi coi phien hom nay la DA DONG -> nhan hang hom nay vao lich su

# ma app -> (kind Entrade, symbol Entrade) ; ma app -> code VNDirect vnmarket_prices / foreigns / ratios
ENT_IDX = {"VNINDEX": ("index", "VNINDEX"), "VN30": ("index", "VN30"), "HNXINDEX": ("index", "HNX"),
           "UPCOM": ("index", "UPCOM"), "HNX30": ("index", "HNX30"), "VN30F1M": ("derivative", "VN30F1M")}
VND_IDX = {"VNINDEX": "VNINDEX", "VN30": "VN30", "HNXINDEX": "HNX", "UPCOM": "UPCOM", "HNX30": "HNX30"}
FLOW_CODES = {"VNINDEX": "VNINDEX", "VN30": "VN30", "HNXINDEX": "HNX", "UPCOM": "UPCOM"}
VAL_CODES = ["VNINDEX", "HNX", "UPCOM", "VN30"]
RATIOS = {"PRICE_TO_EARNINGS": "pe", "PRICE_TO_BOOK": "pb", "PRICE_TO_SALES": "ps",
          "DIVIDEND_YIELD": "div_yield", "MARKETCAP": "marketcap"}
FLOORS = ["HOSE", "HNX", "UPCOM"]
FLOW_COLS = ["date", "index_code", "flow_type", "buy_val", "sell_val", "net_val", "buy_vol", "sell_vol", "net_vol",
             "total_room", "current_room", "buy_val_pct", "sell_val_pct", "currency", "freq"]
FS_COLS = ["code", "date", "floor", "buyVal", "sellVal", "netVal", "buyVol", "sellVol", "netVol", "totalRoom", "currentRoom"]
# ICB VNDirect (group INDUSTRY) - chep tu market-valuation\sectors.py
NGANH = {
    "0500": "Dầu khí", "0530": "Sản xuất Dầu khí", "0570": "Thiết bị, Dịch vụ & Phân phối Dầu khí",
    "1300": "Hóa chất", "1350": "Hóa chất",
    "1700": "Tài nguyên Cơ bản", "1730": "Lâm nghiệp & Giấy", "1750": "Kim loại công nghiệp", "1770": "Khai khoáng",
    "2300": "Xây dựng & Vật liệu", "2350": "Xây dựng & Vật liệu",
    "2700": "Hàng & Dịch vụ Công nghiệp", "2720": "Hàng công nghiệp tổng hợp",
    "2730": "Điện tử & Thiết bị điện", "2750": "Chế tạo máy công nghiệp",
    "2770": "Vận tải", "2790": "Dịch vụ hỗ trợ",
    "3300": "Ô tô & Phụ tùng", "3350": "Ô tô & Phụ tùng",
    "3500": "Thực phẩm & Đồ uống", "3530": "Đồ uống", "3570": "Sản xuất thực phẩm",
    "3700": "Hàng cá nhân & Gia dụng", "3720": "Đồ gia dụng & Xây dựng nhà",
    "3740": "Hàng giải trí", "3760": "Hàng cá nhân", "3780": "Thuốc lá",
    "4500": "Y tế", "4530": "Thiết bị & Dịch vụ Y tế", "4570": "Dược phẩm & Công nghệ sinh học",
    "5300": "Bán lẻ", "5330": "Bán lẻ Thực phẩm & Thuốc", "5370": "Bán lẻ tổng hợp",
    "5500": "Truyền thông", "5550": "Truyền thông",
    "5700": "Du lịch & Giải trí", "5750": "Du lịch & Giải trí",
    "6500": "Viễn thông", "6530": "Viễn thông cố định", "6570": "Viễn thông di động",
    "7500": "Tiện ích (Điện, Nước, Khí đốt)", "7530": "Điện", "7570": "Nước & Khí đốt",
    "8300": "Ngân hàng", "8350": "Ngân hàng",
    "8500": "Bảo hiểm", "8530": "Bảo hiểm phi nhân thọ",
    "8600": "Bất động sản", "8630": "Đầu tư & Dịch vụ Bất động sản", "8670": "Quỹ đầu tư BĐS (REITs)",
    "8700": "Dịch vụ tài chính", "8770": "Dịch vụ tài chính",
    "9500": "Công nghệ", "9530": "Phần mềm & Dịch vụ máy tính", "9570": "Thiết bị & Phần cứng công nghệ",
}

DATASETS = {   # ten file parquet -> (ten hien thi, nguon, pipeline tuong ung (key REGISTRY))
    "index_daily": ("Chỉ số VN (OHLCV + GTGD)", "Entrade + VNDirect vnmarket_prices", "indices"),
    "stock_daily": ("Giá cổ phiếu VN (~1.500 mã)", "Entrade (nền) + VNDirect stock_prices (ngày thiếu)", "tv_history"),
    "flows_daily": ("Khối ngoại & tự doanh theo chỉ số", "VNDirect foreigns / proprietary_trading", "flows"),
    "foreign_stocks_tail": ("Khối ngoại theo mã (ngày sau pipeline)", "VNDirect foreigns type:STOCK", "flows"),
    "valuation_daily": ("Định giá thị trường VN (P/E, P/B…)", "VNDirect ratios", "valuation_wide"),
    "sectors_tail": ("Định giá 55 ngành ICB (ngày sau pipeline)", "VNDirect ratios (batch 55 mã)", "sectors_wide"),
}
_LOCK = threading.RLock()
_STATUS_LOCK = threading.Lock()
_BG = {"thread": None, "started": None}
_SESSION = None


# ------------------------------------------------------------------------------------------------ tien ich
def now_vn() -> datetime:
    return datetime.now(VN_TZ).replace(tzinfo=None)


def session_closed(t: datetime | None = None) -> bool:
    """Phien hom nay da dong (sau 15:15) hoac cuoi tuan -> hang 'hom nay' cua nguon REST la EOD, nhan vao lich su."""
    t = t or now_vn()
    return t.weekday() >= 5 or (t.hour, t.minute) >= CLOSE_HM


def cutoff() -> pd.Timestamp:
    """Ngay cuoi duoc phep nhan vao lich su: hom nay neu phien da dong, khong thi hom qua (hom nay do with_live overlay)."""
    t = now_vn()
    d = pd.Timestamp(t.date())
    return d if session_closed(t) else d - pd.Timedelta(days=1)


def _sess() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update(HDR)
        _SESSION = s
    return _SESSION


def _get(url, params, tries=3, timeout=30):
    last = None
    for i in range(tries):
        try:
            r = _sess().get(url, params=params, timeout=timeout)
            if r.status_code == 400:            # Entrade: invalid symbol -> khong thu lai
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{url.split('/')[-1]}: {type(last).__name__}: {str(last)[:80]}")


def _vnd(endpoint, q, sort, size=PAGE, max_pages=50):
    """Keo phan trang 1 truy van finfo. Tra list dict."""
    rows, page = [], 1
    while page <= max_pages:
        j = _get(VND + endpoint, {"q": q, "size": size, "page": page, "sort": sort})
        data = (j or {}).get("data", []) or []
        rows.extend(data)
        if len(data) < size:
            break
        page += 1
        time.sleep(0.3)
    return rows


def _path(name):
    return os.path.join(SRC_DIR, f"{name}.parquet")


def mtime(name) -> float:
    try:
        return os.path.getmtime(_path(name))
    except OSError:
        return 0.0


def mtime_all() -> float:
    return sum(mtime(n) for n in DATASETS)


def read(name) -> pd.DataFrame:
    """Doc parquet cache (rong neu chua co / dang ghi loi)."""
    p = _path(name)
    if not os.path.exists(p):
        return pd.DataFrame()
    for i in range(3):
        try:
            return pd.read_parquet(p)
        except Exception:  # noqa: BLE001
            time.sleep(0.3 * (i + 1))
    return pd.DataFrame()


def _write(name, df: pd.DataFrame):
    """Ghi parquet (tmp + os.replace). KHONG ghi neu noi dung khong doi (cung shape + cung tong so 300 dong cuoi) de mtime
    khong doi -> cache st.cache_data cua app khong phai dung lai moi 30 phut."""
    p = _path(name)
    if os.path.exists(p):
        try:
            old = pd.read_parquet(p)
            if old.shape == df.shape and list(old.columns) == list(df.columns):
                a, b = old.tail(300).select_dtypes("number").sum(), df.tail(300).select_dtypes("number").sum()
                if np.allclose(a.fillna(0).values, b.fillna(0).values, rtol=1e-9):
                    return
        except Exception:  # noqa: BLE001
            pass
    tmp = p + ".tmp"
    with _LOCK:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, p)


# ---------------------------------------------------------------------------------------------- trang thai
def _status_read() -> dict:
    try:
        with open(STATUS_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _status_set(name, **kw):
    with _STATUS_LOCK:
        s = _status_read()
        d = s.get(name, {})
        d.update(kw)
        s[name] = d
        tmp = STATUS_JSON + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1, default=str)
        os.replace(tmp, STATUS_JSON)


def _done(name, df: pd.DataFrame, dcol="date", note=""):
    last = pd.to_datetime(df[dcol]).max() if len(df) else None
    _status_set(name, last=str(last.date()) if pd.notna(last) and last is not None else None, rows=int(len(df)),
                updated=now_vn().strftime("%Y-%m-%d %H:%M:%S"), error=None, note=note, phase="ok")


def _fail(name, e):
    _status_set(name, error=f"{type(e).__name__}: {str(e)[:160]}", phase="error",
                error_at=now_vn().strftime("%Y-%m-%d %H:%M:%S"))


def status() -> dict:
    return _status_read()


def source_status() -> pd.DataFrame:
    """Bang trang thai nguon live-first: dataset, nguon, ngay cuoi, so dong, cap nhat, tinh trang."""
    s = _status_read()
    rows = []
    for name, (ten, nguon, pk) in DATASETS.items():
        d = s.get(name, {})
        ph = d.get("phase")
        if ph == "base":
            tt = f"đang kéo nền {d.get('done', 0)}/{d.get('total', 0)}"
        elif ph == "error":
            tt = "LỖI → dùng pipeline"
        elif ph == "running":
            tt = "đang cập nhật"
        elif d.get("last"):
            tt = "OK (live-first)"
        else:
            tt = "chưa có → pipeline"
        rows.append({"Dataset": ten, "Nguồn": nguon, "Pipeline thay thế": pk, "Ngày cuối": d.get("last"),
                     "Số dòng": d.get("rows"), "Cập nhật lúc": d.get("updated"), "Tình trạng": tt,
                     "Lỗi": d.get("error") or "", "Ghi chú": d.get("note") or ""})
    return pd.DataFrame(rows)


def status_line() -> str:
    """1 dong ngan cho chip header."""
    s = _status_read()
    ok = [n for n in DATASETS if s.get(n, {}).get("phase") == "ok"]
    err = [n for n in DATASETS if s.get(n, {}).get("phase") == "error"]
    base = [n for n in DATASETS if s.get(n, {}).get("phase") == "base"]
    parts = [f"live-first {len(ok)}/{len(DATASETS)} bộ"]
    if base:
        d = s[base[0]]
        parts.append(f"đang kéo nền giá {d.get('done', 0)}/{d.get('total', 0)} mã")
    if err:
        parts.append(f"lỗi {len(err)} bộ (dùng pipeline)")
    last = max((s.get(n, {}).get("updated") or "" for n in DATASETS), default="")
    if last:
        parts.append(f"cập nhật {last[11:16]}")
    return " · ".join(parts)


def is_live_first(name) -> bool:
    """Co cache dung duoc (da keo xong it nhat 1 lan) - khong phu thuoc dang 'running'."""
    return bool(_status_read().get(name, {}).get("last")) and os.path.exists(_path(name))


# ================================================================================================ ENTRADE
def entrade(kind, symbol, start: pd.Timestamp | None = None, end: pd.Timestamp | None = None, resolution="1D") -> pd.DataFrame:
    """Nen ngay Entrade -> DataFrame(date, open, high, low, close, volume). Rong neu symbol khong hop le."""
    frm = int(pd.Timestamp(start or "2000-01-01").timestamp())
    to = int((pd.Timestamp(end) + pd.Timedelta(days=1)).timestamp()) if end is not None else int(time.time())
    j = _get(ENTRADE.format(kind=kind), {"from": frm, "to": to, "symbol": symbol, "resolution": resolution})
    if not j or not j.get("t"):
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    d = pd.DataFrame({"t": j["t"], "open": j["o"], "high": j["h"], "low": j["l"], "close": j["c"], "volume": j["v"]})
    d["date"] = pd.to_datetime(d.t, unit="s", utc=True).dt.tz_convert(VN_TZ).dt.normalize().dt.tz_localize(None)
    d = d.drop(columns="t").drop_duplicates("date", keep="last")
    for c in ("open", "high", "low", "close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d[["date", "open", "high", "low", "close", "volume"]]


# ============================================================================================ 1. INDEX DAILY
def _vnd_index(code_vnd, start):
    q = f"code:{code_vnd}" + (f"~date:gte:{start:%Y-%m-%d}" if start is not None else "")
    rows = _vnd("vnmarket_prices", q, "date:asc")
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    out = pd.DataFrame({"date": pd.to_datetime(d["date"]), "open": d.get("open"), "high": d.get("high"), "low": d.get("low"),
                        "close": d.get("close"), "volume": d.get("accumulatedVol"),
                        "value": pd.to_numeric(d.get("accumulatedVal"), errors="coerce") / 1e6})   # VND -> trieu (nhu indices-master)
    return out


def update_index_daily(full=False) -> pd.DataFrame:
    name = "index_daily"
    old = pd.DataFrame() if full else read(name)
    cut = cutoff()
    parts = []
    for code, (kind, sym) in ENT_IDX.items():
        last = old[old.index_code == code].date.max() if len(old) and (old.index_code == code).any() else None
        start = (last - pd.Timedelta(days=7)) if last is not None and pd.notna(last) else None
        e = entrade(kind, sym, start)
        v = _vnd_index(VND_IDX[code], start) if code in VND_IDX else pd.DataFrame()
        if e.empty and v.empty:
            continue
        if not v.empty:
            m = e.merge(v, on="date", how="outer", suffixes=("", "_v")).sort_values("date")
            for c in ("open", "high", "low", "close", "volume"):
                m[c] = m[c].fillna(m[f"{c}_v"])
            in_e, in_v = m.date.isin(e.date), m["close_v"].notna()
            m["src"] = np.select([in_e & in_v, in_e], ["ent+vnd", "ent"], "vnd")
            m = m[["date", "open", "high", "low", "close", "volume", "value", "src"]]
        else:
            m = e.assign(value=np.nan, src="ent")
        m["index_code"] = code
        parts.append(m)
    if not parts:
        raise RuntimeError("Entrade/VNDirect không trả dữ liệu chỉ số")
    new = pd.concat(parts, ignore_index=True)
    new = new[new.date <= cut]
    df = pd.concat([old, new], ignore_index=True) if len(old) else new
    df = (df.drop_duplicates(["index_code", "date"], keep="last").sort_values(["index_code", "date"]).reset_index(drop=True))
    df = df[["date", "index_code", "open", "high", "low", "close", "volume", "value", "src"]]
    _write(name, df)
    _done(name, df, note="OHLCV Entrade, GTGD VNDirect (triệu VND)")
    return df


# ============================================================================================ 2. STOCK DAILY
STOCK_COLS = ["symbol", "date", "open", "high", "low", "close", "volume", "value", "ref", "src"]


def symbols_all() -> list[str]:
    syms = []
    if os.path.exists(SYMBOLS_TXT):
        syms = [ln.strip().upper() for ln in open(SYMBOLS_TXT, encoding="utf-8-sig") if ln.strip()]
    # them ma dang co trong stocks_latest hom nay (ma moi niem yet)
    try:
        days = sorted(n for n in os.listdir(RT_DATA) if os.path.exists(os.path.join(RT_DATA, n, "stocks_latest.parquet")))
        if days:
            s = pd.read_parquet(os.path.join(RT_DATA, days[-1], "stocks_latest.parquet"), columns=["symbol"])
            syms += s.symbol.dropna().astype(str).str.upper().tolist()
    except Exception:  # noqa: BLE001
        pass
    return sorted(set(syms))


def _ent_stock(sym, start=None):
    d = entrade("stock", sym, start)
    if d.empty:
        return d
    for c in ("open", "high", "low", "close"):
        d[c] = d[c] * 1000.0                                 # nghin dong -> dong (nhu tv-history)
    d["value"] = d.close * d.volume                          # xap xi (Entrade khong co GTGD)
    d["ref"] = np.nan
    d["src"] = "ent"
    d["symbol"] = sym
    return d[STOCK_COLS]


def _pull_stock_base(symbols, old: pd.DataFrame) -> pd.DataFrame:
    """Keo nen toan bo lich su tung ma bang ThreadPool; luu tam moi 200 ma (tiep tuc duoc neu dung giua chung)."""
    name = "stock_daily"
    have = set(old.symbol.unique()) if len(old) else set()
    todo = [s for s in symbols if s not in have]
    total, done = len(todo), 0
    _status_set(name, phase="base", done=0, total=total, started=now_vn().strftime("%Y-%m-%d %H:%M:%S"))
    parts = [old] if len(old) else []
    buf, errs = [], 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=THREADS) as ex:
        futs = {ex.submit(_ent_stock, s): s for s in todo}
        for f in as_completed(futs):
            done += 1
            try:
                d = f.result()
                if len(d):
                    buf.append(d)
            except Exception:  # noqa: BLE001
                errs += 1
            if done % 25 == 0 or done == total:
                _status_set(name, done=done, total=total, errors=errs, elapsed=round(time.time() - t0))
            if len(buf) >= 200:
                parts.append(pd.concat(buf, ignore_index=True))
                buf = []
                _write(name, pd.concat(parts, ignore_index=True))
    if buf:
        parts.append(pd.concat(buf, ignore_index=True))
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=STOCK_COLS)
    _status_set(name, base_seconds=round(time.time() - t0), base_symbols=total, base_errors=errs)
    return df


def _vnd_day(day: pd.Timestamp) -> pd.DataFrame:
    """Toan bo ma 3 san cua 1 ngay tu VNDirect stock_prices (3 request). Rong neu ngay nghi."""
    rows = []
    for fl in FLOORS:
        rows += _vnd("stock_prices", f"date:{day:%Y-%m-%d}~floor:{fl}", "code:asc", max_pages=3)
    if not rows:
        return pd.DataFrame(columns=STOCK_COLS)
    d = pd.DataFrame(rows)
    if "type" in d:
        d = d[d["type"].astype(str).isin(["STOCK", "ETF", "FUND"])]
    nm_vol, pt_vol = pd.to_numeric(d.get("nmVolume"), errors="coerce").fillna(0), pd.to_numeric(d.get("ptVolume"), errors="coerce").fillna(0)
    nm_val, pt_val = pd.to_numeric(d.get("nmValue"), errors="coerce").fillna(0), pd.to_numeric(d.get("ptValue"), errors="coerce").fillna(0)
    # volume = KHOP LENH (nhu Entrade, de chuoi KL nhat quan); value = khop + thoa thuan (GTGD that)
    out = pd.DataFrame({"symbol": d.code.astype(str).str.upper(), "date": pd.to_datetime(d["date"]),
                        "open": pd.to_numeric(d.open, errors="coerce") * 1000, "high": pd.to_numeric(d.high, errors="coerce") * 1000,
                        "low": pd.to_numeric(d.low, errors="coerce") * 1000, "close": pd.to_numeric(d.close, errors="coerce") * 1000,
                        "volume": nm_vol, "value": nm_val + pt_val,
                        "ref": pd.to_numeric(d.get("basicPrice"), errors="coerce") * 1000, "src": "vnd"})
    out = out[out.close.notna() & (out.close > 0)]
    return out[STOCK_COLS]


def _eod_day(day: pd.Timestamp) -> pd.DataFrame:
    """Snapshot cuoi phien cua bo thu (stocks_latest) -> cung schema; rong neu khong co / ghi truoc 14:45."""
    p = os.path.join(RT_DATA, f"{day:%Y-%m-%d}", "stocks_latest.parquet")
    if not os.path.exists(p):
        return pd.DataFrame(columns=STOCK_COLS)
    s = pd.read_parquet(p)
    if s.empty or "price" not in s:
        return pd.DataFrame(columns=STOCK_COLS)
    ts = pd.to_datetime(s["ts"], errors="coerce").max() if "ts" in s else None
    if ts is None or pd.isna(ts) or (ts.hour, ts.minute) < (14, 45):
        return pd.DataFrame(columns=STOCK_COLS)
    s = s.drop_duplicates("symbol", keep="last")
    out = pd.DataFrame({"symbol": s.symbol.astype(str).str.upper(), "date": pd.Timestamp(day), "open": s.get("open"),
                        "high": s.get("high"), "low": s.get("low"), "close": s["price"], "volume": s.get("total_vol"),
                        "value": pd.to_numeric(s.get("total_val"), errors="coerce") * 1e9, "ref": s.get("ref"), "src": "eod"})
    out = out[pd.to_numeric(out.close, errors="coerce").notna() & (out.close > 0)]
    return out[STOCK_COLS]


def update_stock_daily(full=False) -> pd.DataFrame:
    """Lan dau: keo nen Entrade toan bo ma (ThreadPool 8). Sau do: moi ngay thieu -> VNDirect theo ngay (3 request), loi -> EOD bo thu."""
    name = "stock_daily"
    old = pd.DataFrame(columns=STOCK_COLS) if full else read(name)
    syms = symbols_all()
    if not syms:
        raise RuntimeError("Không có danh sách mã (realtime-lab\\symbols.txt)")
    if len(old) == 0 or len(set(syms) - set(old.symbol.unique())) > 50:   # chua co nen hoac nhieu ma moi
        old = _pull_stock_base(syms, old)
    cut = cutoff()
    last = old.date.max() if len(old) else None
    if last is None or pd.isna(last):
        raise RuntimeError("Kéo nền Entrade không có dữ liệu")
    _status_set(name, phase="running")
    parts, notes = [old], []
    # cac ngay thieu sau ngay cuoi (toi da 40 ngay lam viec; xa hon thi keo lai Entrade tung ma)
    # + 14 ngay gan nhat chua co ban VNDirect (hang Entrade khong co gia tham chieu `ref` -> khong phat hien duoc su kien quyen)
    days = [d for d in pd.bdate_range(last + pd.Timedelta(days=1), cut)]
    have_vnd = set(old[old.src == "vnd"].date.unique()) if len(old) else set()
    recent = [d for d in pd.bdate_range(cut - pd.Timedelta(days=14), min(last, cut)) if d not in have_vnd and d <= cut]
    days = sorted(set(days) | set(recent))
    if len(days) > 40:
        notes.append(f"thiếu {len(days)} ngày → kéo lại Entrade từng mã")
        old = old[old.date <= last]
        tail = []
        with ThreadPoolExecutor(max_workers=THREADS) as ex:
            for d in ex.map(lambda s: _ent_stock(s, last - pd.Timedelta(days=3)), syms):
                if len(d):
                    tail.append(d)
        parts += tail
        days = []
    for d in days:
        try:
            x = _vnd_day(d)
        except Exception as e:  # noqa: BLE001
            notes.append(f"VNDirect {d:%d/%m} lỗi ({type(e).__name__})")
            x = pd.DataFrame(columns=STOCK_COLS)
        if x.empty:
            x = _eod_day(d)
            if len(x):
                notes.append(f"{d:%d/%m}: EOD bộ thu")
        if len(x):
            parts.append(x)
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df.date)
    df = df[df.date <= cut]
    df = df.drop_duplicates(["symbol", "date"], keep="last").sort_values(["symbol", "date"]).reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume", "value", "ref"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    df["symbol"] = df.symbol.astype(str)
    df["src"] = df.src.astype(str)
    _write(name, df)
    _done(name, df, note="; ".join(notes) if notes else "giá chưa điều chỉnh, KL khớp lệnh (Entrade) / khớp + thoả thuận (VNDirect)")
    return df


# ============================================================================================ 3. FLOWS (chi so)
def _row(date, index_code, flow_type, **kw):
    r = {c: None for c in FLOW_COLS}
    r.update(date=date, index_code=index_code, flow_type=flow_type, currency="VND", freq="D")
    r.update(kw)
    return r


def update_flows_daily(full=False) -> pd.DataFrame:
    name = "flows_daily"
    old = pd.DataFrame() if full else read(name)
    cut = cutoff()
    rows = []
    for code, vcode in FLOW_CODES.items():
        for ft, ep, dcol in (("foreign", "foreigns", "tradingDate"), ("prop", "proprietary_trading", "date")):
            last = None
            if len(old):
                sub = old[(old.index_code == code) & (old.flow_type == ft)]
                last = sub.date.max() if len(sub) else None
            q = f"code:{vcode}" + (f"~{dcol}:gte:{(last - pd.Timedelta(days=7)):%Y-%m-%d}" if last is not None and pd.notna(last) else "")
            for r in _vnd(ep, q, f"{dcol}:asc"):
                if ft == "foreign":
                    rows.append(_row(r[dcol], code, ft, buy_val=r.get("buyVal"), sell_val=r.get("sellVal"), net_val=r.get("netVal"),
                                     buy_vol=r.get("buyVol"), sell_vol=r.get("sellVol"), net_vol=r.get("netVol"),
                                     total_room=r.get("totalRoom"), current_room=r.get("currentRoom")))
                else:
                    rows.append(_row(r[dcol], code, ft, buy_val=r.get("buyingVal"), sell_val=r.get("sellingVal"), net_val=r.get("netVal"),
                                     buy_vol=r.get("buyingVol"), sell_vol=r.get("sellingVol"), net_vol=r.get("netVol"),
                                     buy_val_pct=r.get("buyingValPct"), sell_val_pct=r.get("sellingValPct")))
    new = pd.DataFrame(rows, columns=FLOW_COLS)
    if new.empty and old.empty:
        raise RuntimeError("VNDirect foreigns không trả dữ liệu")
    new["date"] = pd.to_datetime(new["date"].astype(str).str[:10])
    new = new[new.date <= cut]
    df = pd.concat([old, new], ignore_index=True) if len(old) else new
    df = df.drop_duplicates(["date", "index_code", "flow_type"], keep="last").sort_values(["index_code", "flow_type", "date"]).reset_index(drop=True)
    for c in FLOW_COLS[3:13]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    _write(name, df[FLOW_COLS])
    _done(name, df, note="khối ngoại từ 08/2018, tự doanh từ 05/2022 (T+1)")
    return df


# ============================================================================= 4. KHOI NGOAI THEO MA (ngay sau pipeline)
def update_foreign_stocks_tail(after: pd.Timestamp | None, full=False) -> pd.DataFrame:
    """Keo khoi ngoai theo ma cho cac ngay > `after` (ngay cuoi pipeline Vietcap/VNDirect). Giu toi da 60 ngay gan nhat."""
    name = "foreign_stocks_tail"
    old = pd.DataFrame() if full else read(name)
    cut = cutoff()
    start = (after + pd.Timedelta(days=1)) if after is not None and pd.notna(after) else cut - pd.Timedelta(days=10)
    if len(old):
        start = max(start, old.date.max() - pd.Timedelta(days=2))
    if start > cut:
        if len(old):
            _done(name, old, note="không có ngày mới")
        return old
    rows = _vnd("foreigns", f"type:STOCK~tradingDate:gte:{start:%Y-%m-%d}~tradingDate:lte:{cut:%Y-%m-%d}", "tradingDate:asc", max_pages=40)
    new = pd.DataFrame(rows)
    if new.empty:
        if len(old):
            _done(name, old, note="không có ngày mới")
            return old
        new = pd.DataFrame(columns=FS_COLS)
    else:
        new = new.rename(columns={"tradingDate": "date"})
        for c in FS_COLS:
            if c not in new:
                new[c] = np.nan
        new = new[FS_COLS]
        new["date"] = pd.to_datetime(new["date"].astype(str).str[:10])
    df = pd.concat([old, new], ignore_index=True) if len(old) else new
    df = df.drop_duplicates(["code", "date"], keep="last").sort_values(["date", "code"]).reset_index(drop=True)
    df = df[df.date >= cut - pd.Timedelta(days=90)]
    _write(name, df)
    _done(name, df, note="chỉ các ngày sau pipeline (Vietcap theo mã)")
    return df


# ============================================================================================ 5. VALUATION (VNDirect)
def _ratios(codes_csv, ratio_code, start, dcol="reportDate"):
    q = f"code:{codes_csv}~ratioCode:{ratio_code}" + (f"~{dcol}:gte:{start:%Y-%m-%d}" if start is not None else "")
    rows = _vnd("ratios", q, f"{dcol}:asc", max_pages=200)
    return [{"code": str(r.get("code")), "date": r.get("reportDate"), "ratio": ratio_code, "value": r.get("value")} for r in rows]


def update_valuation_daily(full=False) -> pd.DataFrame:
    name = "valuation_daily"
    old = pd.DataFrame() if full else read(name)
    cut = cutoff()
    rows = []
    for code in VAL_CODES:
        for rc in RATIOS:
            last = None
            if len(old):
                sub = old[(old.code == code) & (old.ratio == rc)]
                last = sub.date.max() if len(sub) else None
            rows += _ratios(code, rc, (last - pd.Timedelta(days=5)) if last is not None and pd.notna(last) else None)
    new = pd.DataFrame(rows, columns=["code", "date", "ratio", "value"])
    if new.empty and old.empty:
        raise RuntimeError("VNDirect ratios không trả dữ liệu")
    new["date"] = pd.to_datetime(new["date"].astype(str).str[:10])
    new = new[new.date <= cut]
    df = pd.concat([old, new], ignore_index=True) if len(old) else new
    df = df.drop_duplicates(["code", "date", "ratio"], keep="last").sort_values(["code", "ratio", "date"]).reset_index(drop=True)
    df["value"] = pd.to_numeric(df.value, errors="coerce")
    _write(name, df)
    _done(name, df, note="P/E P/B P/S cổ tức vốn hoá từ 12/2017")
    return df


def update_sectors_tail(after: pd.Timestamp | None, full=False) -> pd.DataFrame:
    """55 nganh ICB x 5 ratio cho cac ngay > `after` (ngay cuoi sectors-wide pipeline): 5 request batch."""
    name = "sectors_tail"
    old = pd.DataFrame() if full else read(name)
    cut = cutoff()
    start = (after - pd.Timedelta(days=3)) if after is not None and pd.notna(after) else cut - pd.Timedelta(days=30)
    if len(old):
        start = max(start, old.date.max() - pd.Timedelta(days=3))
    codes_csv = ",".join(NGANH)
    rows = []
    for rc in RATIOS:
        rows += _ratios(codes_csv, rc, start)
    new = pd.DataFrame(rows, columns=["code", "date", "ratio", "value"])
    if not new.empty:
        new["date"] = pd.to_datetime(new["date"].astype(str).str[:10])
        new = new[new.date <= cut]
    df = pd.concat([x for x in (old, new) if len(x)], ignore_index=True) if (len(old) or len(new)) else new
    if df.empty:
        _done(name, df, note="không có ngày mới")
        return df
    df = df.drop_duplicates(["code", "date", "ratio"], keep="last").sort_values(["code", "ratio", "date"]).reset_index(drop=True)
    df = df[df.date >= cut - pd.Timedelta(days=120)]
    df["value"] = pd.to_numeric(df.value, errors="coerce")
    _write(name, df)
    _done(name, df, note="chỉ các ngày sau pipeline sectors-wide")
    return df


def valuation_wide_from_long(long: pd.DataFrame, close: pd.DataFrame | None = None) -> pd.DataFrame:
    """code,date,ratio,value -> wide nhu valuation-wide.csv (ke ca cot suy ra + close/eps_index/bvps_index neu co gia chi so)."""
    if long.empty:
        return pd.DataFrame()
    w = long.pivot_table(index=["code", "date"], columns="ratio", values="value").reset_index()
    w.columns.name = None
    w = w.rename(columns=RATIOS)
    for c in RATIOS.values():
        if c not in w:
            w[c] = np.nan
    w["ln_ttm"] = w.marketcap / w.pe
    w["gtss"] = w.marketcap / w.pb
    w["doanh_thu_ttm"] = w.marketcap / w.ps
    w["co_tuc_ttm"] = w.div_yield * w.marketcap
    w["earnings_yield"] = 1 / w.pe
    w["roe_ttm"] = w.pb / w.pe
    if close is not None and len(close):
        c = close.copy()
        c["code"] = c.index_code.map({"VNINDEX": "VNINDEX", "HNXINDEX": "HNX", "UPCOM": "UPCOM", "VN30": "VN30"})
        c = c.dropna(subset=["code"])[["date", "code", "close"]].drop_duplicates(["date", "code"], keep="last")
        w = w.merge(c, on=["code", "date"], how="left")
    else:
        w["close"] = np.nan
    w["eps_index"] = w.close / w.pe
    w["bvps_index"] = w.close / w.pb
    return w.sort_values(["code", "date"]).reset_index(drop=True)


def sectors_wide_from_long(long: pd.DataFrame) -> pd.DataFrame:
    if long.empty:
        return pd.DataFrame()
    w = long.pivot_table(index=["code", "date"], columns="ratio", values="value").reset_index()
    w.columns.name = None
    w = w.rename(columns=RATIOS)
    for c in RATIOS.values():
        if c not in w:
            w[c] = np.nan
    w["code"] = w.code.astype(str).str.zfill(4)
    w["ten_nganh"] = w.code.map(NGANH)
    w["cap_icb"] = np.where(w.code.str.endswith("00"), 2, 3)
    w["ln_ttm"] = w.marketcap / w.pe
    w["gtss"] = w.marketcap / w.pb
    w["doanh_thu_ttm"] = w.marketcap / w.ps
    w["co_tuc_ttm"] = w.div_yield * w.marketcap
    w["roe_ttm"] = w.pb / w.pe
    return w[["code", "ten_nganh", "cap_icb", "date", "div_yield", "marketcap", "pb", "pe", "ps", "ln_ttm", "gtss",
              "doanh_thu_ttm", "co_tuc_ttm", "roe_ttm"]].sort_values(["code", "date"]).reset_index(drop=True)


# ============================================================================================ CAP NHAT TONG
def pipeline_ends() -> dict:
    """Ngay cuoi cua cac file pipeline lien quan (de keo phan duoi): doc nhanh cot date."""
    out = {}
    try:
        base = os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data"))   # nhu datalib.BASE (khong import datalib: streamlit)
        f = os.path.join(base, "market-valuation", "sectors-wide.csv")
        if os.path.exists(f):
            out["sectors"] = pd.to_datetime(pd.read_csv(f, usecols=["date"]).date).max()
        import glob
        fs = glob.glob(os.path.join(base, "index-fetcher", "raw", "vn_foreign_stocks_20*.csv"))
        pq = os.path.join(base, "index-fetcher", "raw", "vn_foreign_stocks_vci.parquet")
        ds = []
        if os.path.exists(pq):
            ds.append(pd.to_datetime(pd.read_parquet(pq, columns=["date"]).date).max())
        for f in fs:
            ds.append(pd.to_datetime(pd.read_csv(f, usecols=["date"]).date).max())
        if ds:
            out["foreign_stocks"] = max(ds)
    except Exception:  # noqa: BLE001
        pass
    return out


def refresh_all(full=False, only=None) -> dict:
    """Cap nhat tang dan tat ca dataset (tuan tu, moi dataset try/except rieng). Tra {name: 'ok'|'loi: ...'}."""
    res = {}
    ends = pipeline_ends()
    steps = [
        ("index_daily", lambda: update_index_daily(full)),
        ("flows_daily", lambda: update_flows_daily(full)),
        ("valuation_daily", lambda: update_valuation_daily(full)),
        ("sectors_tail", lambda: update_sectors_tail(ends.get("sectors"), full)),
        ("foreign_stocks_tail", lambda: update_foreign_stocks_tail(ends.get("foreign_stocks"), full)),
        ("stock_daily", lambda: update_stock_daily(full)),      # nang nhat de cuoi
    ]
    for name, fn in steps:
        if only and name not in only:
            continue
        t0 = time.time()
        try:
            _status_set(name, phase="running")
            fn()
            _status_set(name, seconds=round(time.time() - t0, 1))
            res[name] = "ok"
        except Exception as e:  # noqa: BLE001
            _fail(name, e)
            res[name] = f"lỗi: {e}"
    _status_set("_run", last=now_vn().strftime("%Y-%m-%d %H:%M:%S"), result=res)
    return res


def _bg_loop(interval=1800):
    while True:
        try:
            refresh_all()
        except Exception as e:  # noqa: BLE001
            _status_set("_run", error=str(e)[:200])
        time.sleep(interval)


def start_background(interval=1800) -> bool:
    """Chay cap nhat tang dan trong thread nen (1 lan/tien trinh), lap lai moi `interval` giay. Tra True neu vua khoi dong."""
    with _LOCK:
        t = _BG.get("thread")
        if t is not None and t.is_alive():
            return False
        th = threading.Thread(target=_bg_loop, args=(interval,), name="data_src_bg", daemon=True)
        th.start()
        _BG["thread"], _BG["started"] = th, now_vn()
        return True


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Cap nhat cache nguon live-first (chay tay / test)")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--only", help="vd index_daily,flows_daily")
    a = ap.parse_args()
    t0 = time.time()
    r = refresh_all(a.full, a.only.split(",") if a.only else None)
    print(json.dumps(r, ensure_ascii=False, indent=1), f"{time.time() - t0:.0f}s")
    print(source_status().to_string())
