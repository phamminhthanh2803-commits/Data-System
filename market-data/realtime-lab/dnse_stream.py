# -*- coding: utf-8 -*-
r"""
dnse_stream.py — BO THU REAL-TIME TOAN BO BANG DNSE Open API V2 (quyet dinh PV2 08/10/2026: "tat ca chuyen ve DNSE").
Khong dung chung pipeline hien tai. Key doc tu dnse.env (PV2 tu dien) hoac bien moi truong; KHONG BAO GIO in key.

Giao thuc (theo developers.dnse.com.vn + github dnse-tech/openapi-sdk, da kiem chung 08/10 voi key that):
  wss://ws-openapi.dnse.com.vn/v1/stream?encoding=json
  auth      {"action":"auth","api_key","signature"=HMAC-SHA256(secret, "key:ts:nonce") hex,"timestamp":int,"nonce":STR}
  subscribe {"action":"subscribe","channels":[{"name":"tick.G1.json","symbols":[...]}]}   -> {"action":"subscribed"}
  ping/pong server ping moi 3 phut, phai pong trong 60 s; ket noi toi da 8 gio; 10 ket noi/user, 200 stream/ket noi.
  Thong diep du lieu nhan dang bang truong "T":
    mi market_index (5 s/lan: diem, thay doi, so ma tang/giam/dung/tran/san, KL/GTGD khop + thoa thuan)
    emi estimated_market_index.VN30 (nested "marketIndex")   ii market_index_influence (anh huong tung ma len chi so)
    t tick (lenh khop)  te tick_extra (+side, avgPrice)  q top_price (bid/offer 3 buoc HOSE, 10 HNX/UPCOM)
    b ohlc (nen dang chay)  bc ohlc_closed (nen da dong)  f foreign (khoi ngoai mua/ban + room theo ma)
    e expected_price (ATO/ATC)  sd security_definition (tran/san/TC, 08:00)  s session

Ket noi (moi ket noi 1 nhom kenh, tu reconnect + dang ky lai):
  [market]    market_index x 10 chi so, estimated_market_index.VN30, market_index_influence (VNINDEX/VN30/HNX/HNX30/VN100),
              ohlc.1 + ohlc_closed.1 cho chi so + phai sinh, session STO/STX/UPX/FIO
  [watch-N]   tick_extra.G1, top_price.G1, foreign.G1, ohlc.1, ohlc_closed.1, expected_price.G1 cho tung lo <= 16 ma
              cua dnse_symbols.txt (mac dinh VN30 + VN30F1M -> 2 ket noi). --foreign-universe VN100: them foreign.G1 cho VN100.
  [universe]  09/10/2026 "live toan san": tick_extra.G1 cho TOAN BO co phieu HOSE + HNX (+ UPCOM neu con cho) ngoai VN30,
              nhet vao cho trong cua cac ket noi tren roi mo them ket noi moi (uni-N) cho den khi het 10 ket noi.
              Server bao subscriptions_max = 100 stream/ket noi (auth_success) -> 10 x 100 = 1.000 stream la tran.
              Danh sach ma + gia tham chieu/tran/san + khoi ngoai toan san lay tu SSI iBoard (poll_realtime.fetch_stocks_ssi,
              1 request/san, moi 60 s, khong can key) vi REST /price/instruments cua DNSE khong ton tai (404).
              -> gia khop HOSE/HNX la tick DNSE (5 s), UPCOM + khoi ngoai ngoai VN30 la snapshot SSI (60 s).

Luu: data/realtime.duckdb (1 process ghi). Xuat parquet cho app moi 5 s vao data/<YYYY-MM-DD>/:
  index_latest.parquet   diem + do rong + GTGD tung chi so, basis VN30F1M
  rt_latest.parquet      gia/bid/ask/khoi ngoai moi nhat tung ma theo doi
  index_1m.parquet       nen 1 phut chi so + phai sinh (DNSE)     rt_bars_1m.parquet  nen 1 phut ma theo doi
  market_summary.parquet lich su 5 s cua market_index (ve duong do rong / GTGD / khoi ngoai VN30 trong phien)
  influence_latest.parquet  anh huong tung ma len chi so (gia, GTGD, KL cua MOI ma trong ro VNINDEX/HNX -> toan san)
  foreign_latest.parquet    khoi ngoai luy ke theo ma
  stocks_latest.parquet     TOAN SAN (~1.500 ma, moi 5 s): symbol, exchange (HOSE/HNX/UPCOM), ref, ceiling, floor, price, change,
                            change_pct, open, high, low, avg, total_vol (CP; DNSE phat /10 -> da x10), total_val (TY dong), fr_buy_val, fr_sell_val,
                            fr_net_val (TY dong), src (dnse|ssi), ts (gio nhan), ts_ssi (gio snapshot SSI).
                            GIA = DONG (nhu tv-history; DNSE phat nghin dong -> x1000). App dung lam "overlay hom nay".

Chay:
  python dnse_stream.py --check                      # kiem tra key
  python dnse_stream.py                              # 08:45-15:10 T2-T6, tu thoat
  python dnse_stream.py --force --duration 60        # thu ngoai gio
  python dnse_stream.py --force --duration 90 --db data/test.duckdb --out data/test   # thu SONG SONG bo thu that (DB + thu muc rieng)
  python dnse_stream.py --backfill                   # chi keo lai nen 1 phut hom nay qua REST roi thoat
  python dnse_stream.py --no-universe                # chi VN30 + chi so nhu truoc 09/10
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import hmac
import json
import os
import queue
import sys
import threading
import time

import duckdb
import pandas as pd
import pyarrow as pa

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DB_PATH = os.path.join(DATA, "realtime.duckdb")
ENV_FILE = os.path.join(HERE, "dnse.env")
SYM_FILE = os.path.join(HERE, "dnse_symbols.txt")
VN_TZ = dt.timezone(dt.timedelta(hours=7))
WS_URL = "wss://ws-openapi.dnse.com.vn/v1/stream?encoding=json"
REST_URL = "https://openapi.dnse.com.vn"

INDICES = ["VNINDEX", "VN30", "HNX", "HNX30", "UPCOM", "VN100", "VNXALLSHARE", "VNMITECH", "VN50GROWTH", "VNDIVIDEND"]
INFLUENCE = ["VNINDEX", "VN30", "HNX", "HNX30", "VN100"]
FUTURES = ["VN30F1M", "VN30F2M"]
WATCH_CHUNK = 16              # ma / ket noi watch (6 kenh x 16 = 96 stream, duoi muc subscriptions_max = 100 server bao)
STREAM_MAX = 100              # auth_success: rate_limit.subscriptions_max = 100 (tai lieu ghi 200 nhung server bao 100)
CONN_MAX = 10                 # 10 ket noi / user
UNIVERSE_EXCH = ("hose", "hnx", "upcom")   # thu tu uu tien khi het cho stream
UNIVERSE_INTERVAL = 60        # s, poll SSI iBoard toan san
MAX_RAW = 300

SCHEMA = {
    "market_index": "ts_recv TIMESTAMP, index_name VARCHAR, value DOUBLE, prior DOUBLE, high DOUBLE, low DOUBLE, "
                    "change DOUBLE, change_pct DOUBLE, advances INTEGER, declines INTEGER, unchanged INTEGER, "
                    "ceiling INTEGER, floor INTEGER, up_vol BIGINT, down_vol BIGINT, flat_vol BIGINT, "
                    "matched_val DOUBLE, matched_vol BIGINT, block_val DOUBLE, block_vol BIGINT, total_val DOUBLE, "
                    "total_vol BIGINT, session_id VARCHAR, time VARCHAR",
    "estimated_index": "ts_recv TIMESTAMP, index_name VARCHAR, value DOUBLE, change DOUBLE, change_pct DOUBLE, "
                       "advances INTEGER, declines INTEGER, unchanged INTEGER, total_val DOUBLE, total_vol BIGINT, time VARCHAR",
    "ticks": "ts_recv TIMESTAMP, symbol VARCHAR, board VARCHAR, price DOUBLE, qty BIGINT, side VARCHAR, avg_price DOUBLE, "
             "total_vol BIGINT, total_val DOUBLE, high DOUBLE, low DOUBLE, open DOUBLE, session_id VARCHAR, time VARCHAR",
    "quotes": "ts_recv TIMESTAMP, symbol VARCHAR, board VARCHAR, bid1 DOUBLE, bid1_qty BIGINT, bid2 DOUBLE, bid2_qty BIGINT, "
              "bid3 DOUBLE, bid3_qty BIGINT, ask1 DOUBLE, ask1_qty BIGINT, ask2 DOUBLE, ask2_qty BIGINT, ask3 DOUBLE, "
              "ask3_qty BIGINT, total_bid BIGINT, total_ask BIGINT, time VARCHAR",
    "bars_1m": "symbol VARCHAR, sym_type VARCHAR, t BIGINT, time TIMESTAMP, open DOUBLE, high DOUBLE, low DOUBLE, "
               "close DOUBLE, volume BIGINT, closed BOOLEAN, last_updated BIGINT, ts_recv TIMESTAMP",
    "foreign_flow": "ts_recv TIMESTAMP, symbol VARCHAR, board VARCHAR, buy_vol BIGINT, buy_val DOUBLE, sell_vol BIGINT, "
               "sell_val DOUBLE, total_buy_vol BIGINT, total_buy_val DOUBLE, total_sell_vol BIGINT, total_sell_val DOUBLE, "
               "room_limit BIGINT, room_left BIGINT, time VARCHAR",
    "influence": "ts_recv TIMESTAMP, index_name VARCHAR, symbol VARCHAR, influence DOUBLE, influence_pct DOUBLE, "
                 "proportion DOUBLE, change_pct DOUBLE, change DOUBLE, price DOUBLE, total_val DOUBLE, total_vol DOUBLE, time VARCHAR",
    "expected": "ts_recv TIMESTAMP, symbol VARCHAR, board VARCHAR, close_price DOUBLE, exp_price DOUBLE, exp_qty BIGINT, time VARCHAR",
    "secdef": "ts_recv TIMESTAMP, symbol VARCHAR, board VARCHAR, market VARCHAR, ref DOUBLE, ceiling DOUBLE, floor DOUBLE, "
              "status VARCHAR, time VARCHAR",
    "sessions": "ts_recv TIMESTAMP, market VARCHAR, board VARCHAR, event VARCHAR, session_id VARCHAR, prod_grp VARCHAR, time VARCHAR",
    "raw_log": "ts_recv TIMESTAMP, conn VARCHAR, msg VARCHAR",
    "events": "ts_recv TIMESTAMP, conn VARCHAR, msg VARCHAR",
}
KEYS = {"bars_1m": ["symbol", "t"], "influence": ["index_name", "symbol"], "secdef": ["symbol", "board"]}


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(VN_TZ):%H:%M:%S}] {msg}", flush=True)


def now_vn() -> dt.datetime:
    return dt.datetime.now(VN_TZ)


def naive_now() -> dt.datetime:
    return now_vn().replace(tzinfo=None)


def in_session(t: dt.datetime) -> bool:
    hm = t.hour * 60 + t.minute
    return t.weekday() < 5 and 8 * 60 + 45 <= hm <= 15 * 60 + 10


def _f(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    try:
        return None if v is None else int(float(v))
    except (TypeError, ValueError):
        return None


def _ts(v):
    """time cua DNSE: ISO string, epoch s/ms, hoac {Seconds,Nanos} -> chuoi; giu nguyen de khong mat thong tin."""
    if isinstance(v, dict):
        return str(v.get("Seconds", v.get("seconds")))
    return None if v is None else str(v)


# ----------------------------------------------------------------------------- key / symbols
def load_credentials() -> tuple[str, str] | None:
    key, sec = os.environ.get("DNSE_API_KEY", ""), os.environ.get("DNSE_API_SECRET", "")
    if not (key and sec) and os.path.exists(ENV_FILE):
        for ln in open(ENV_FILE, encoding="utf-8-sig"):
            ln = ln.strip()
            if "=" in ln and not ln.startswith("#"):
                k, _, v = ln.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k == "DNSE_API_KEY":
                    key = v
                elif k == "DNSE_API_SECRET":
                    sec = v
    return (key, sec) if key and sec else None


def auth_message(api_key: str, api_secret: str) -> dict:
    ts = int(time.time())
    nonce = str(int(time.time() * 1_000_000))            # server doi CHUOI
    sig = hmac.new(api_secret.encode(), f"{api_key}:{ts}:{nonce}".encode(), hashlib.sha256).hexdigest()
    return {"action": "auth", "api_key": api_key, "signature": sig, "timestamp": ts, "nonce": nonce}


def load_symbols(path: str) -> list[str]:
    if os.path.exists(path):
        syms = [ln.split("#")[0].strip().upper() for ln in open(path, encoding="utf-8-sig")]
        return [s for s in syms if s]
    return ["VNM", "HPG", "VIC", "FPT", "VN30F1M"]


# ----------------------------------------------------------------------------- REST (HMAC qua goi pip `dnse`)
def rest_client(key: str, sec: str):
    from dnse import DnseClient
    return DnseClient(api_key=key, api_secret=sec)


def rest_get(client, path: str, params: dict | None = None):
    headers = client._request_headers("GET", path)
    r = client._send("GET", path, headers=headers, params=params or {})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} {path}: {r.text[:200]}")
    return r.json()


def index_constituents(client, index_name: str) -> list[str]:
    """GET /price/instruments?indexName=VN100 -> danh sach ma trong ro (phan trang)."""
    out, page = [], 1
    while True:
        j = rest_get(client, "/price/instruments", {"indexName": index_name, "limit": 500, "page": page})
        items = j if isinstance(j, list) else (j.get("data") or j.get("instruments") or j.get("items") or [])
        out += [it.get("symbol") for it in items if isinstance(it, dict) and it.get("symbol")]
        if len(items) < 500:
            break
        page += 1
    return sorted(set(out))


def backfill_bars(client, store: "Store", symbols: list[str], sym_type: str, day: dt.date) -> int:
    """GET /price/ohlc?type=INDEX|STOCK|DERIVATIVE&symbol&resolution=1&from&to -> bars_1m (closed=True)."""
    frm = int(dt.datetime.combine(day, dt.time(8, 30), VN_TZ).timestamp())
    to = int(dt.datetime.combine(day, dt.time(15, 30), VN_TZ).timestamp())
    n = 0
    for sym in symbols:
        try:
            j = rest_get(client, "/price/ohlc", {"type": sym_type, "symbol": sym, "resolution": "1", "from": frm, "to": to})
            d = j.get("data", j) if isinstance(j, dict) else j
            if isinstance(d, dict) and "t" in d:                      # dang TradingView {t,o,h,l,c,v}
                rows = [{"t": d["t"][k], "open": d["o"][k], "high": d["h"][k], "low": d["l"][k], "close": d["c"][k],
                         "volume": d["v"][k]} for k in range(len(d["t"]))]
            elif isinstance(d, list):
                rows = [{"t": r.get("time", r.get("t")), "open": r.get("open"), "high": r.get("high"), "low": r.get("low"),
                         "close": r.get("close"), "volume": r.get("volume")} for r in d if isinstance(r, dict)]
            else:
                rows = []
            for r in rows:
                t = _i(r["t"])
                if t is None:
                    continue
                if t > 1e12:
                    t //= 1000
                store.put("bars_1m", {"symbol": sym, "sym_type": sym_type, "t": t,
                                      "time": dt.datetime.fromtimestamp(t, VN_TZ).replace(tzinfo=None),
                                      "open": _f(r["open"]), "high": _f(r["high"]), "low": _f(r["low"]), "close": _f(r["close"]),
                                      "volume": _i(r["volume"]), "closed": True, "last_updated": None, "ts_recv": naive_now()})
                n += 1
        except Exception as e:  # noqa: BLE001
            log(f"  ! backfill {sym_type} {sym}: {type(e).__name__}: {str(e)[:120]}")
    return n


# ----------------------------------------------------------------------------- DuckDB
class Store:
    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.con = duckdb.connect(path)
        # 09/10/2026: sap "Fatal Python error: PyEval_SaveThread ... GIL released" sau ~1 gio (DuckDB quet DataFrame pandas
        # bang luong nen roi goi nguoc Python). Chua: DuckDB 1 luong + dua du lieu vao qua Arrow (khong goi nguoc Python).
        self.con.execute("SET threads TO 1")
        for tbl, cols in SCHEMA.items():
            self.con.execute(f"CREATE TABLE IF NOT EXISTS {tbl} ({cols})")
        self.q: queue.Queue = queue.Queue()
        self.latest: dict[str, dict] = {}           # symbol -> gia/bid/ask/khoi ngoai moi nhat
        self.index_latest: dict[str, dict] = {}     # index -> market_index moi nhat
        self.universe: dict[str, dict] = {}         # symbol -> snapshot SSI iBoard toan san (ref/tran/san/gia/KN), 60 s
        self.universe_ts: dt.datetime | None = None
        self.secdef: dict[str, dict] = {}           # symbol -> ref/ceiling/floor tu kenh security_definition (nghin dong)
        self.lock = threading.Lock()
        self.raw_left = MAX_RAW

    def put(self, tbl: str, row: dict) -> None:
        self.q.put((tbl, row))

    def flush(self) -> int:
        batches: dict[str, list[dict]] = {}
        while True:
            try:
                tbl, row = self.q.get_nowait()
            except queue.Empty:
                break
            batches.setdefault(tbl, []).append(row)
        n = 0
        with self.lock:
            for tbl, rows in batches.items():
                df = pd.DataFrame(rows)
                keys = KEYS.get(tbl)
                if keys:
                    df = df.drop_duplicates(subset=keys, keep="last")
                self.con.register("df_new", pa.Table.from_pandas(df, preserve_index=False))
                if keys:
                    cond = " AND ".join(f"{tbl}.{k} = df_new.{k}" for k in keys)
                    self.con.execute(f"DELETE FROM {tbl} USING df_new WHERE {cond}")
                cols = ", ".join(df.columns)
                self.con.execute(f"INSERT INTO {tbl} ({cols}) SELECT {cols} FROM df_new")
                self.con.unregister("df_new")
                n += len(df)
        return n

    def _copy(self, sql: str, path: str) -> None:
        self.con.execute(f"COPY ({sql}) TO '{path.replace(os.sep, '/')}' (FORMAT PARQUET)")

    def export(self, day_dir: str) -> None:
        os.makedirs(day_dir, exist_ok=True)
        today = now_vn().strftime("%Y-%m-%d")
        with self.lock:
            if self.latest:
                pd.DataFrame(list(self.latest.values())).to_parquet(os.path.join(day_dir, "rt_latest.parquet"), index=False)
            if self.index_latest:
                rows = list(self.index_latest.values())
                vn30 = self.index_latest.get("VN30", {}).get("value")
                f1m = self.latest.get("VN30F1M", {}).get("price")
                for r in rows:
                    r["basis_vn30f1m"] = (f1m - vn30) if (vn30 and f1m) else None
                pd.DataFrame(rows).to_parquet(os.path.join(day_dir, "index_latest.parquet"), index=False)
            self._copy(f"SELECT * FROM bars_1m WHERE sym_type IN ('INDEX','DERIVATIVE') AND CAST(time AS DATE) = DATE '{today}' "
                       "ORDER BY symbol, t", os.path.join(day_dir, "index_1m.parquet"))
            self._copy(f"SELECT * FROM bars_1m WHERE sym_type = 'STOCK' AND CAST(time AS DATE) = DATE '{today}' ORDER BY symbol, t",
                       os.path.join(day_dir, "rt_bars_1m.parquet"))
            self._copy(f"SELECT * FROM market_index WHERE CAST(ts_recv AS DATE) = DATE '{today}' ORDER BY ts_recv",
                       os.path.join(day_dir, "market_summary.parquet"))
            self._copy("SELECT * FROM influence ORDER BY index_name, influence DESC", os.path.join(day_dir, "influence_latest.parquet"))
            self._copy(f"SELECT * FROM foreign_flow WHERE CAST(ts_recv AS DATE) = DATE '{today}' QUALIFY row_number() OVER "
                       "(PARTITION BY symbol ORDER BY ts_recv DESC) = 1", os.path.join(day_dir, "foreign_latest.parquet"))
            sl = self.stocks_latest_frame()
        if sl is not None and len(sl):
            # ghi file tam roi doi ten: app doc moi 5 s, tranh doc trung luc ghi do
            p = os.path.join(day_dir, "stocks_latest.parquet")
            sl.to_parquet(p + ".tmp", index=False)
            os.replace(p + ".tmp", p)

    def stocks_latest_frame(self) -> pd.DataFrame | None:
        """Bang gia TOAN SAN = snapshot SSI (nen, 60 s) + tick DNSE (gia/KL/GTGD/cao/thap/avg, 5 s) + khoi ngoai DNSE (VN30).
        Don vi: gia DONG, total_val / fr_* TY dong. Goi trong lock."""
        if not self.universe and not self.latest:
            return None
        rows: dict[str, dict] = {}
        for sym, u in self.universe.items():
            rows[sym] = dict(u)
        skip = set(INDICES) | set(FUTURES)
        for sym, l in list(self.latest.items()):          # list(): thread WS dang them ma moi
            if sym in skip or str(sym).startswith("VN30F"):
                continue
            r = rows.get(sym)
            if r is None:
                r = rows[sym] = {"symbol": sym, "exchange": None, "ref": None, "ceiling": None, "floor": None, "price": None,
                                 "open": None, "high": None, "low": None, "avg": None, "total_vol": None, "total_val": None,
                                 "fr_buy_val": None, "fr_sell_val": None, "src": None, "ts": None, "ts_ssi": None}
            ts_d, ts_s = l.get("ts_recv"), r.get("ts_ssi")
            newer = ts_s is None or ts_d is None or ts_d >= ts_s
            if l.get("price") is not None and newer:
                r.update(price=l["price"] * 1000.0, src="dnse", ts=ts_d)
                for k_src, k_dst in (("open", "open"), ("high", "high"), ("low", "low"), ("avg_price", "avg")):
                    if l.get(k_src) is not None:
                        r[k_dst] = l[k_src] * 1000.0
                if l.get("total_vol") is not None:
                    # DNSE totalVolumeTraded = so CP / 10 (doi chieu SSI + GTGD/gia BQ 13:02 09/10: ti le dung 10,000 ca 3 san)
                    r["total_vol"] = l["total_vol"] * 10
                if l.get("total_val") is not None:
                    v = float(l["total_val"])
                    r["total_val"] = v / 1e9 if v > 1e5 else v          # grossTradeAmount: dong -> ty
            if l.get("fr_buy_val") is not None or l.get("fr_sell_val") is not None:   # foreign.G1 (VN30) luy ke -> ty
                if newer or r.get("fr_buy_val") is None:
                    r["fr_buy_val"] = (l.get("fr_buy_val") or 0) / 1e9
                    r["fr_sell_val"] = (l.get("fr_sell_val") or 0) / 1e9
            if r.get("ref") is None and sym in self.secdef and self.secdef[sym].get("ref"):
                sd = self.secdef[sym]
                r["ref"], r["ceiling"], r["floor"] = sd["ref"] * 1000.0, (sd.get("ceiling") or 0) * 1000.0 or None, (sd.get("floor") or 0) * 1000.0 or None
        df = pd.DataFrame(list(rows.values()))
        for c in ("ref", "ceiling", "floor", "price", "open", "high", "low", "avg", "total_vol", "total_val", "fr_buy_val", "fr_sell_val"):
            if c not in df:
                df[c] = None
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["change"] = df["price"] - df["ref"]
        df["change_pct"] = df["change"] / df["ref"].where(df["ref"] > 0) * 100
        df["fr_net_val"] = df["fr_buy_val"] - df["fr_sell_val"]
        cols = ["symbol", "exchange", "ref", "ceiling", "floor", "price", "change", "change_pct", "open", "high", "low", "avg",
                "total_vol", "total_val", "fr_buy_val", "fr_sell_val", "fr_net_val", "src", "ts", "ts_ssi"]
        for c in cols:
            if c not in df:
                df[c] = None
        df = df[cols]
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        df["ts_ssi"] = pd.to_datetime(df["ts_ssi"], errors="coerce")
        return df.sort_values("symbol").reset_index(drop=True)

    def counts(self) -> dict[str, int]:
        with self.lock:
            return {t: self.con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in SCHEMA if t != "events"}


# ----------------------------------------------------------------------------- xu ly thong diep -> bang
def handle(store: Store, conn: str, m: dict) -> None:
    T = m.get("T")
    ts = naive_now()
    if store.raw_left > 0:
        store.raw_left -= 1
        store.put("raw_log", {"ts_recv": ts, "conn": conn, "msg": json.dumps(m, ensure_ascii=False)[:3000]})
        if store.raw_left > MAX_RAW - 12:
            log(f"[{conn}] T={T}: {json.dumps(m, ensure_ascii=False)[:220]}")
    if T == "mi":
        row = {"ts_recv": ts, "index_name": m.get("indexName"), "value": _f(m.get("valueIndexes")),
               "prior": _f(m.get("priorValueIndexes")), "high": _f(m.get("highestValueIndexes")),
               "low": _f(m.get("lowestValueIndexes")), "change": _f(m.get("changedValue")), "change_pct": _f(m.get("changedRatio")),
               "advances": _i(m.get("fluctuationUpIssueCount")), "declines": _i(m.get("fluctuationDownIssueCount")),
               "unchanged": _i(m.get("fluctuationSteadinessIssueCount")), "ceiling": _i(m.get("fluctuationUpperLimitIssueCount")),
               "floor": _i(m.get("fluctuationLowerLimitIssueCount")), "up_vol": _i(m.get("fluctuationUpIssueVolume")),
               "down_vol": _i(m.get("fluctuationDownIssueVolume")), "flat_vol": _i(m.get("fluctuationSteadinessIssueVolume")),
               "matched_val": _f(m.get("contauctAccTrdVal")), "matched_vol": _i(m.get("contauctAccTrdVol")),
               "block_val": _f(m.get("blkTrdAccTrdVal")), "block_vol": _i(m.get("blkTrdAccTrdVol")),
               "total_val": _f(m.get("grossTradeAmount")), "total_vol": _i(m.get("totalVolumeTraded")),
               "session_id": _ts(m.get("tradingSessionId")), "time": _ts(m.get("transactTime"))}
        store.put("market_index", row)
        if row["index_name"]:
            store.index_latest[row["index_name"]] = dict(row)
    elif T == "emi":
        d = m.get("marketIndex") or m
        store.put("estimated_index", {"ts_recv": ts, "index_name": d.get("indexName"), "value": _f(d.get("valueIndexes")),
                                      "change": _f(d.get("changedValue")), "change_pct": _f(d.get("changedRatio")),
                                      "advances": _i(d.get("fluctuationUpIssueCount")), "declines": _i(d.get("fluctuationDownIssueCount")),
                                      "unchanged": _i(d.get("fluctuationSteadinessIssueCount")), "total_val": _f(d.get("grossTradeAmount")),
                                      "total_vol": _i(d.get("totalVolumeTraded")), "time": _ts(d.get("time"))})
    elif T in ("t", "te"):
        sym = m.get("symbol")
        row = {"ts_recv": ts, "symbol": sym, "board": m.get("boardId"), "price": _f(m.get("matchPrice")),
               "qty": _i(m.get("matchQtty")), "side": _ts(m.get("side")), "avg_price": _f(m.get("avgPrice")),
               "total_vol": _i(m.get("totalVolumeTraded")), "total_val": _f(m.get("grossTradeAmount")),
               "high": _f(m.get("highestPrice")), "low": _f(m.get("lowestPrice")), "open": _f(m.get("openPrice")),
               "session_id": _ts(m.get("tradingSessionId")), "time": _ts(m.get("time"))}
        store.put("ticks", row)
        if sym:
            store.latest.setdefault(sym, {"symbol": sym}).update(
                price=row["price"], last_qty=row["qty"], side=row["side"], avg_price=row["avg_price"], total_vol=row["total_vol"],
                total_val=row["total_val"], high=row["high"], low=row["low"], open=row["open"], last_time=row["time"], ts_recv=ts)
    elif T == "q":
        sym = m.get("symbol")
        bids, asks = (m.get("bid") or []), (m.get("offer") or [])
        lv = lambda arr, k, f: f(arr[k].get("price" if f is _f else "qtty")) if len(arr) > k else None  # noqa: E731
        row = {"ts_recv": ts, "symbol": sym, "board": m.get("boardId"),
               "bid1": lv(bids, 0, _f), "bid1_qty": lv(bids, 0, _i), "bid2": lv(bids, 1, _f), "bid2_qty": lv(bids, 1, _i),
               "bid3": lv(bids, 2, _f), "bid3_qty": lv(bids, 2, _i), "ask1": lv(asks, 0, _f), "ask1_qty": lv(asks, 0, _i),
               "ask2": lv(asks, 1, _f), "ask2_qty": lv(asks, 1, _i), "ask3": lv(asks, 2, _f), "ask3_qty": lv(asks, 2, _i),
               "total_bid": _i(m.get("totalBidQtty")), "total_ask": _i(m.get("totalOfferQtty")), "time": _ts(m.get("time"))}
        store.put("quotes", row)
        if sym:
            store.latest.setdefault(sym, {"symbol": sym}).update(bid1=row["bid1"], bid1_qty=row["bid1_qty"], ask1=row["ask1"],
                                                                 ask1_qty=row["ask1_qty"], ts_recv=ts)
    elif T in ("b", "bc"):
        sym = m.get("symbol") or m.get("symbolType")
        t = _i(m.get("time"))
        if sym and t is not None:
            if t > 1e12:
                t //= 1000
            store.put("bars_1m", {"symbol": sym, "sym_type": m.get("type") or ("DERIVATIVE" if sym.startswith("VN30F") else "STOCK"),
                                  "t": t, "time": dt.datetime.fromtimestamp(t, VN_TZ).replace(tzinfo=None), "open": _f(m.get("open")),
                                  "high": _f(m.get("high")), "low": _f(m.get("low")), "close": _f(m.get("close")),
                                  "volume": _i(m.get("volume")), "closed": T == "bc", "last_updated": _i(m.get("lastUpdated")),
                                  "ts_recv": ts})
            if sym in INDICES or sym in FUTURES:
                store.latest.setdefault(sym, {"symbol": sym}).update(price=_f(m.get("close")), ts_recv=ts)
    elif T == "f":
        sym = m.get("symbol")
        row = {"ts_recv": ts, "symbol": sym, "board": m.get("boardId"), "buy_vol": _i(m.get("buyVolume")),
               "buy_val": _f(m.get("buyTradedAmount")), "sell_vol": _i(m.get("sellVolume")), "sell_val": _f(m.get("sellTradedAmount")),
               "total_buy_vol": _i(m.get("totalBuyVolume")), "total_buy_val": _f(m.get("totalBuyTradedAmount")),
               "total_sell_vol": _i(m.get("totalSellVolume")), "total_sell_val": _f(m.get("totalSellTradedAmount")),
               "room_limit": _i(m.get("foreignerOrderLimitQuantity")), "room_left": _i(m.get("foreignerBuyPossibleQuantity")),
               "time": _ts(m.get("transactTime"))}
        store.put("foreign_flow", row)
        if sym:
            store.latest.setdefault(sym, {"symbol": sym}).update(fr_buy_val=row["total_buy_val"], fr_sell_val=row["total_sell_val"],
                                                                 fr_buy_vol=row["total_buy_vol"], fr_sell_vol=row["total_sell_vol"],
                                                                 fr_room_left=row["room_left"], ts_recv=ts)
    elif T == "ii":
        idx = m.get("index_name") or m.get("indexName")
        for it in (m.get("Data") or m.get("data") or []):
            store.put("influence", {"ts_recv": ts, "index_name": idx, "symbol": it.get("symbol"), "influence": _f(it.get("influence")),
                                    "influence_pct": _f(it.get("influenceRatio")), "proportion": _f(it.get("proportion")),
                                    "change_pct": _f(it.get("changeRatio")), "change": _f(it.get("changeValue")),
                                    "price": _f(it.get("price")), "total_val": _f(it.get("grossTradeAmount")),
                                    "total_vol": _f(it.get("totalVolumeTraded")), "time": _ts(it.get("time"))})
    elif T == "e":
        store.put("expected", {"ts_recv": ts, "symbol": m.get("symbol"), "board": m.get("boardId"), "close_price": _f(m.get("closePrice")),
                               "exp_price": _f(m.get("expectedTradePrice")), "exp_qty": _i(m.get("expectedTradeQuantity")),
                               "time": _ts(m.get("time"))})
    elif T == "sd":
        row = {"ts_recv": ts, "symbol": m.get("symbol"), "board": m.get("boardId"), "market": _ts(m.get("marketId")),
               "ref": _f(m.get("basicPrice")), "ceiling": _f(m.get("ceilingPrice")), "floor": _f(m.get("floorPrice")),
               "status": _ts(m.get("securityStatus")), "time": _ts(m.get("time"))}
        store.put("secdef", row)
        if row["symbol"] and row["ref"]:
            store.secdef[row["symbol"]] = row
    elif T == "s":
        store.put("sessions", {"ts_recv": ts, "market": _ts(m.get("marketId")), "board": m.get("boardId"), "event": _ts(m.get("eventId")),
                               "session_id": _ts(m.get("tradingSessionId")), "prod_grp": m.get("tscProdGrpId"),
                               "time": _ts(m.get("sendingTime") or m.get("time"))})


# ----------------------------------------------------------------------------- WebSocket client (1 ket noi)
class Conn:
    def __init__(self, name: str, channels: list[dict], key: str, sec: str, store: Store) -> None:
        self.name, self.channels, self.key, self.sec, self.store = name, channels, key, sec, store
        self.n_msg = 0
        self.stop = asyncio.Event()

    async def run(self) -> None:
        import websockets
        attempt = 0
        while not self.stop.is_set():
            try:
                async with websockets.connect(WS_URL, ssl=True, open_timeout=20, ping_interval=None, max_queue=2048) as ws:
                    hello = json.loads(await asyncio.wait_for(ws.recv(), 15))
                    await ws.send(json.dumps(auth_message(self.key, self.sec)))
                    resp = json.loads(await asyncio.wait_for(ws.recv(), 15))
                    if resp.get("action") != "auth_success":
                        raise RuntimeError(f"auth: {resp}")
                    await ws.send(json.dumps({"action": "subscribe", "channels": self.channels}))
                    log(f"[{self.name}] ket noi {hello.get('session_id')} | {len(self.channels)} kenh, "
                        f"{sum(max(1, len(c['symbols'])) for c in self.channels)} stream")
                    attempt = 0
                    t_conn = time.time()
                    while not self.stop.is_set():
                        if time.time() - t_conn > 7.5 * 3600:            # server cat sau 8 h -> chu dong noi lai
                            log(f"[{self.name}] 7,5 gio -> noi lai")
                            break
                        try:
                            raw = await asyncio.wait_for(ws.recv(), 5)
                        except asyncio.TimeoutError:
                            continue
                        m = json.loads(raw)
                        act = m.get("action")
                        if act == "ping":
                            await ws.send(json.dumps({"action": "pong", "timestamp": m.get("timestamp")}))
                        elif act in ("subscribed", "unsubscribed", "pong"):
                            if act == "subscribed":
                                self.store.put("events", {"ts_recv": naive_now(), "conn": self.name, "msg": raw[:500]})
                        elif act == "error":
                            log(f"[{self.name}] LOI server: {raw[:300]}")
                            self.store.put("events", {"ts_recv": naive_now(), "conn": self.name, "msg": raw[:500]})
                        elif "T" in m:
                            self.n_msg += 1
                            handle(self.store, self.name, m)
                        else:
                            self.store.put("events", {"ts_recv": naive_now(), "conn": self.name, "msg": raw[:500]})
            except Exception as e:  # noqa: BLE001
                if self.stop.is_set():
                    break
                attempt += 1
                delay = min(60, 2 ** min(attempt, 6))
                log(f"[{self.name}] mat ket noi ({type(e).__name__}: {str(e)[:100]}) -> thu lai sau {delay}s")
                await asyncio.sleep(delay)


def n_streams(channels: list[dict]) -> int:
    return sum(max(1, len(c["symbols"])) for c in channels)


# ----------------------------------------------------------------------------- SSI iBoard toan san (khong can key)
def universe_snapshot() -> tuple[pd.DataFrame, dt.datetime]:
    """1 request/san SSI iBoard -> DataFrame toan san (co phieu thuong), gia DONG, GTGD/KN DONG. Dung poll_realtime.fetch_stocks_ssi."""
    sys.path.insert(0, HERE)
    import poll_realtime as pr
    df = pr.fetch_stocks_ssi()
    ts = naive_now()
    if "stock_type" in df.columns:
        df = df[df["stock_type"].isin(["s", "STOCK"]) | df["stock_type"].isna()]
    df = df[df["symbol"].notna()].copy()
    df["exchange"] = df["exchange"].astype(str).str.upper()
    return df, ts


def universe_rows(df: pd.DataFrame, ts: dt.datetime) -> dict[str, dict]:
    """DataFrame SSI -> {symbol: row chuan stocks_latest} (gia dong, GTGD/KN ty)."""
    out = {}
    g = lambda r, k: (None if (k not in r or pd.isna(r[k])) else float(r[k]))  # noqa: E731
    for r in df.to_dict("records"):
        sym = str(r["symbol"]).upper()
        price = g(r, "price")
        val = g(r, "value")
        fb, fs = g(r, "fr_buy_val"), g(r, "fr_sell_val")
        out[sym] = {"symbol": sym, "exchange": r.get("exchange"), "ref": g(r, "ref"), "ceiling": g(r, "ceiling"), "floor": g(r, "floor"),
                    "price": price if price else None, "open": g(r, "open") or None, "high": g(r, "high") or None,
                    "low": g(r, "low") or None, "avg": g(r, "avg_price") or None, "total_vol": g(r, "volume"),
                    "total_val": (val / 1e9) if val is not None else None,
                    "fr_buy_val": (fb / 1e9) if fb is not None else None, "fr_sell_val": (fs / 1e9) if fs is not None else None,
                    "src": "ssi", "ts": ts, "ts_ssi": ts}
    return out


def universe_symbols(df: pd.DataFrame, exclude: set[str]) -> list[str]:
    """Thu tu dang ky tick DNSE: HOSE -> HNX -> UPCOM, trong san theo GTGD giam dan (phien truoc neu moi mo cua) roi ABC."""
    d = df[~df["symbol"].isin(exclude)].copy()
    d["_ex"] = d["exchange"].str.lower().map({e: i for i, e in enumerate(UNIVERSE_EXCH)}).fillna(9)
    d["_val"] = -pd.to_numeric(d.get("value"), errors="coerce").fillna(0)
    d = d.sort_values(["_ex", "_val", "symbol"])
    return d["symbol"].astype(str).str.upper().tolist()


def universe_loop(store: "Store", stop_evt: threading.Event, interval: int = UNIVERSE_INTERVAL) -> None:
    """Thread: moi `interval` s poll SSI toan san -> store.universe (nen cho stocks_latest: ref/tran/san, UPCOM, khoi ngoai)."""
    fails = 0
    while not stop_evt.is_set():
        t0 = time.time()
        try:
            df, ts = universe_snapshot()
            rows = universe_rows(df, ts)
            with store.lock:
                store.universe = rows
                store.universe_ts = ts
            if fails:
                log(f"[universe] SSI OK tro lai ({len(rows)} ma)")
            fails = 0
        except Exception as e:  # noqa: BLE001
            fails += 1
            if fails <= 3 or fails % 10 == 0:
                log(f"[universe] ! SSI iBoard loi lan {fails}: {type(e).__name__}: {str(e)[:120]}")
        wait = max(5.0, interval - (time.time() - t0))
        stop_evt.wait(wait)


def build_channels(symbols: list[str], foreign_extra: list[str], universe: list[str] | None = None) -> dict[str, list[dict]]:
    """Chia kenh theo ket noi. Tra {ten_ket_noi: [channel dict]}.
    universe: ma them tick_extra.G1 (toan san) -> nhet vao cho trong (<= STREAM_MAX/ket noi) roi mo ket noi uni-N toi CONN_MAX."""
    idx_syms = INDICES + FUTURES
    market = [{"name": f"market_index.{i}.json", "symbols": []} for i in INDICES]
    market += [{"name": "estimated_market_index.VN30.json", "symbols": []}]
    market += [{"name": f"market_index_influence.{i}.1.json", "symbols": []} for i in INFLUENCE]
    market += [{"name": "ohlc.1.json", "symbols": idx_syms}, {"name": "ohlc_closed.1.json", "symbols": idx_syms}]
    market += [{"name": f"session.{g}.G1.json", "symbols": []} for g in ("STO", "STX", "UPX", "FIO")]   # tier thuong: khong wildcard
    conns = {"market": market}
    for k in range(0, len(symbols), WATCH_CHUNK):
        chunk = symbols[k:k + WATCH_CHUNK]
        conns[f"watch-{k // WATCH_CHUNK + 1}"] = [
            {"name": "tick_extra.G1.json", "symbols": chunk}, {"name": "top_price.G1.json", "symbols": chunk},
            {"name": "foreign.G1.json", "symbols": chunk}, {"name": "ohlc.1.json", "symbols": chunk},
            {"name": "ohlc_closed.1.json", "symbols": chunk}, {"name": "expected_price.G1.json", "symbols": chunk},
        ]
    extra = [s for s in foreign_extra if s not in symbols]
    for k in range(0, len(extra), STREAM_MAX - 10):
        conns[f"foreign-{k // (STREAM_MAX - 10) + 1}"] = [{"name": "foreign.G1.json", "symbols": extra[k:k + STREAM_MAX - 10]}]
    uni = [s for s in (universe or []) if s not in symbols]
    if uni:
        # 1) lap cho trong cac ket noi da co
        for name, ch in list(conns.items()):
            free = STREAM_MAX - n_streams(ch)
            if free > 0 and uni:
                take, uni = uni[:free], uni[free:]
                ch.append({"name": "tick_extra.G1.json", "symbols": take})
        # 2) mo ket noi moi toi tran CONN_MAX
        k = 1
        while uni and len(conns) < CONN_MAX:
            take, uni = uni[:STREAM_MAX], uni[STREAM_MAX:]
            conns[f"uni-{k}"] = [{"name": "tick_extra.G1.json", "symbols": take}]
            k += 1
        if uni:
            log(f"[universe] het cho stream: {len(uni)} ma chi co snapshot SSI 60 s (vd {', '.join(uni[:5])} ...)")
    return conns


async def run_all(conns: dict[str, list[dict]], key: str, sec: str, store: Store, stop_evt: threading.Event) -> None:
    objs = [Conn(n, ch, key, sec, store) for n, ch in conns.items()]
    tasks = [asyncio.create_task(o.run()) for o in objs]
    while not stop_evt.is_set():
        await asyncio.sleep(1)
    for o in objs:
        o.stop.set()
    for t in tasks:
        t.cancel()
    store.conn_stats = {o.name: o.n_msg for o in objs}


async def check_credentials(key: str, sec: str) -> bool:
    import websockets
    try:
        async with websockets.connect(WS_URL, ssl=True, open_timeout=15) as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), 10))
            log(f"server: {hello.get('action')} session={hello.get('session_id')}")
            await ws.send(json.dumps(auth_message(key, sec)))
            resp = json.loads(await asyncio.wait_for(ws.recv(), 10))
            ok = resp.get("action") == "auth_success"
            log(("XAC THUC OK: " if ok else "XAC THUC THAT BAI: ") + json.dumps(resp)[:200])
            return ok
    except Exception as e:  # noqa: BLE001
        log(f"LOI ket noi: {type(e).__name__}: {str(e)[:200]}")
        return False


# ----------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--backfill", action="store_true", help="chi keo lai nen 1 phut hom nay qua REST roi thoat")
    ap.add_argument("--no-backfill", action="store_true", help="khong keo lai nen khi khoi dong")
    ap.add_argument("--symbols", default=SYM_FILE)
    ap.add_argument("--foreign-universe", default="", help="ten ro (vd VN100) de them kenh khoi ngoai cho ca ro")
    ap.add_argument("--duration", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--db", default=os.environ.get("DNSE_DB", DB_PATH), help="duong dan DuckDB (test: data/test.duckdb)")
    ap.add_argument("--out", default=os.environ.get("DNSE_OUT", DATA), help="thu muc goc xuat parquet (test: data/test)")
    ap.add_argument("--no-universe", action="store_true", help="khong dang ky tick toan san + khong poll SSI")
    ap.add_argument("--universe-interval", type=int, default=UNIVERSE_INTERVAL)
    a = ap.parse_args()

    cred = load_credentials()
    if not cred:
        log("CHUA CO KEY: dien DNSE_API_KEY / DNSE_API_SECRET vao dnse.env (xem dnse.env.example)")
        sys.exit(2)
    key, sec = cred
    if a.check:
        sys.exit(0 if asyncio.run(check_credentials(key, sec)) else 1)
    if not (a.force or a.duration or a.backfill or in_session(now_vn())):
        log("Ngoai gio giao dich (08:45-15:10, T2-T6) -> thoat. --force de chay thu.")
        return

    symbols = load_symbols(a.symbols)
    store = Store(os.path.abspath(a.db))
    day = now_vn().date()
    day_dir = os.path.join(os.path.abspath(a.out), day.strftime("%Y-%m-%d"))
    client = rest_client(key, sec)
    if a.db != DB_PATH or a.out != DATA:
        log(f"DB {a.db} | xuat {day_dir}")

    if not a.no_backfill:
        n = backfill_bars(client, store, INDICES, "INDEX", day) + backfill_bars(client, store, FUTURES, "DERIVATIVE", day)
        n += backfill_bars(client, store, [s for s in symbols if not s.startswith("VN30F")], "STOCK", day)
        log(f"backfill REST: {n} nen 1 phut ({store.flush()} dong ghi)")
        if a.backfill:
            store.export(day_dir)
            store.con.close()
            return

    foreign_extra: list[str] = []
    if a.foreign_universe:
        try:
            foreign_extra = index_constituents(client, a.foreign_universe)
            log(f"ro {a.foreign_universe}: {len(foreign_extra)} ma -> them kenh khoi ngoai")
        except Exception as e:  # noqa: BLE001
            log(f"  ! khong lay duoc ro {a.foreign_universe}: {e}")

    stop_evt = threading.Event()
    universe: list[str] = []
    th_uni = None
    if not a.no_universe:
        try:                                     # snapshot dau: danh sach ma toan san + ref/tran/san (SSI, khong can key)
            udf, uts = universe_snapshot()
            with store.lock:
                store.universe, store.universe_ts = universe_rows(udf, uts), uts
            universe = universe_symbols(udf, set(symbols))
            ex_cnt = udf["exchange"].str.upper().value_counts().to_dict()
            log(f"[universe] SSI iBoard: {len(udf)} ma {ex_cnt} -> dang ky tick DNSE cho {len(universe)} ma ngoai watch")
        except Exception as e:  # noqa: BLE001
            log(f"[universe] ! khong lay duoc snapshot SSI ({type(e).__name__}: {str(e)[:120]}) -> dung danh sach symbols.txt")
            try:
                universe = [s for s in load_symbols(os.path.join(HERE, "symbols.txt")) if s not in symbols]
            except Exception:  # noqa: BLE001
                universe = []
        th_uni = threading.Thread(target=universe_loop, args=(store, stop_evt, a.universe_interval), daemon=True)
        th_uni.start()

    conns = build_channels(symbols, foreign_extra, universe)
    log(f"{len(conns)} ket noi, {sum(n_streams(ch) for ch in conns.values())} stream: " +
        ", ".join(f"{n} ({n_streams(ch)})" for n, ch in conns.items()))
    th = threading.Thread(target=lambda: asyncio.run(run_all(conns, key, sec, store, stop_evt)), daemon=True)
    th.start()

    t0, last_export, last_log = time.time(), 0.0, 0.0
    try:
        while True:
            time.sleep(1)
            store.flush()
            if time.time() - last_export >= 5:
                try:
                    store.export(day_dir)
                except Exception as e:  # noqa: BLE001
                    log(f"  ! export: {type(e).__name__}: {str(e)[:120]}")
                last_export = time.time()
            if time.time() - last_log >= 60:
                vni = store.index_latest.get("VNINDEX", {})
                with store.lock:
                    n_px = sum(1 for v in store.latest.values() if v.get("price") is not None)
                    n_uni = len(store.universe)
                log(f"{store.counts()} | VNINDEX {vni.get('value')} tang/giam {vni.get('advances')}/{vni.get('declines')} "
                    f"| tick DNSE co gia: {n_px} ma | SSI toan san: {n_uni} ma")
                last_log = time.time()
            if a.duration and time.time() - t0 >= a.duration:
                break
            if not (a.force or a.duration) and not in_session(now_vn()):
                log("Het gio giao dich -> dung")
                break
    except KeyboardInterrupt:
        log("Dung theo yeu cau")
    finally:
        stop_evt.set()
        th.join(timeout=5)
        store.flush()
        store.export(day_dir)
        log(f"Ket thuc. {store.counts()} | thong diep/ket noi: {getattr(store, 'conn_stats', {})}")
        store.con.close()


if __name__ == "__main__":
    main()
