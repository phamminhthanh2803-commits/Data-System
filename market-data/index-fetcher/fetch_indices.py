# -*- coding: utf-8 -*-
"""
fetch_indices.py — Keo du lieu giao dich DAILY (OHLCV + gia tri giao dich) cua cac chi so thi truong
vao 1 file master CSV (long-format).

Nguon (cot `source` trong indices.csv):
  - yahoo   : chi so toan cau qua yfinance. Co adj_close. KHONG co gia tri giao dich (value).
  - vnstock : chi so VN, hit thang endpoint VCI gap-chart -> co accumulatedValue (trieu VND).
  - tencent : TQ (sh000001, sz399001, sh000300) + HK (hkHSI, hkHSCEI, hkHSTECH) qua newfqkline cua Tencent
              -> co amount (don vi van / 10^4 CNY|HKD). Lich su ve 1990 (SH) / 1997 (HSI).
  - twse    : Dai Loan, TWSE FMTQIK theo THANG (JSON) -> co 成交金額 (TWD) + 成交股數. Lich su ve 1999.
  - naver   : Han Quoc (KOSPI, KOSDAQ), bang HTML finance.naver.com sise_index_day -> 거래대금 (trieu KRW). Ve 1990.
  - set     : Thai Lan (SET, mai), API set.or.th chart-quotation 5Y -> value (THB). Can cookie Incapsula
              tu trang HTML truoc (curl_cffi impersonate chrome). Toi da 5 nam.
  - idx     : Indonesia (COMPOSITE, LQ45), idx.co.id GetIndexSummary THEO TUNG NGAY (Cloudflare -> curl_cffi).
              Lich su tu 2020.
  - bursa   : Malaysia. Gia chi so tu yahoo (^KLSE) + KL/GTGD TOAN THI TRUONG tu PDF "Daily Scoreboard"
              cua bursamalaysia.com (Main + ACE + LEAP, ca khop lenh lan Direct Business). PDF chi co tu ~giua 2024.
  - jpx     : Nhat. Gia chi so tu yahoo (^N225) + GTGD TOAN TSE (Prime+Standard+Growth, ca ToSTNeT) tu PDF
              "est-set" hang ngay cua jpx.co.jp. Trang JPX chi giu ~3 thang PDF -> phai chay deu de boi chuoi.

Danh sach chi so doc tu indices.csv (cot: index_code,index_name,source,symbol,currency).

Cach chay:
  python fetch_indices.py                 # incremental: keo tu (max_date cua TUNG ma - buffer) den hom nay, merge + dedup
  python fetch_indices.py --full          # keo lai FULL lich su, dung lai file master
  python fetch_indices.py --only A,B      # chi keo cac index_code liet ke (ket hop --full de backfill ma moi)

Output: indices-master.csv, long-format, 1 dong = 1 (date, index_code).
  Cot: date, index_code, index_name, source, open, high, low, close, adj_close, volume, value, currency, value_usd
  value     = gia tri giao dich, don vi TRIEU dong tien ban dia (cot currency).
  value_usd = value quy ve TRIEU USD theo ty gia ngay (yfinance XXX=X, cache fx-master.csv, ffill ngay nghi).
  volume    = so co phieu (da quy ve co phieu: TQ 手x100, Han 천주x1000, Malaysia '000x1000). HK khong co volume.
Dedup theo (date, index_code), giu ban ghi moi nhat. File luon sap xep theo (index_code, date).
"""
import os
import re
import io
import sys
import time
import logging
from datetime import datetime, timedelta

import pandas as pd

# --- Windows console: ep UTF-8 de tranh loi cp1252 khi in banner vnstock / chu Han-Han-Thai ---
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
logging.disable(logging.CRITICAL)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # D:\market-data
from mdlib import log, cffi_session as _cffi_session, safe_to_csv  # noqa: E402  (gop 14/09/2026)
CONFIG_PATH = os.path.join(HERE, "indices.csv")
MASTER_PATH = os.path.join(HERE, "indices-master.csv")
FX_PATH = os.path.join(HERE, "fx-master.csv")

FULL_START = "1990-01-01"   # moc keo full lich su
BUFFER_DAYS = 7             # incremental: lui lai vai ngay de tu va gap / bar chua chot

# Moc som nhat ma nguon co du lieu (tranh spam request vo ich khi --full)
SOURCE_FLOOR = {
    "idx": "2020-01-01",      # GetIndexSummary rong truoc 2020
    "bursa": "2024-01-01",    # scoreboard PDF 404 truoc ~giua 2024
    "twse": "1999-01-01",     # FMTQIK bat dau 1999-01
}

COLUMNS = ["date", "index_code", "index_name", "source", "open", "high",
           "low", "close", "adj_close", "volume", "value", "currency", "value_usd"]
NUM_COLS = ["open", "high", "low", "close", "adj_close", "volume", "value", "value_usd"]
DATA_COLS = ["date", "open", "high", "low", "close", "adj_close", "volume", "value"]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

VCI_URL = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
VCI_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Referer": "https://trading.vietcap.com.vn/",
}


def empty_frame():
    return pd.DataFrame(columns=DATA_COLS)


def load_config():
    if not os.path.exists(CONFIG_PATH):
        log(f"[LOI] Khong thay file cau hinh: {CONFIG_PATH}")
        sys.exit(1)
    cfg = pd.read_csv(CONFIG_PATH, dtype=str).fillna("")
    cfg = cfg[cfg["index_code"].str.strip() != ""]
    if "currency" not in cfg.columns:
        cfg["currency"] = ""
    return cfg.to_dict("records")


def bdays(start, end):
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(start=start, end=end)]


def _num(s):
    s = str(s).replace(",", "").strip()
    return float(s) if s not in ("", "--", "-", "nan", "None") else float("nan")


# =====================================================================================
# 1. YAHOO
# =====================================================================================
def fetch_yahoo(symbol, start, end):
    import yfinance as yf
    df = yf.download(symbol, start=start, end=end, interval="1d",
                     auto_adjust=False, progress=False, threads=False)
    if df is None or len(df) == 0:
        return empty_frame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    out = pd.DataFrame({
        "date": pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d"),
        "open": df.get("Open"),
        "high": df.get("High"),
        "low": df.get("Low"),
        "close": df.get("Close"),
        "adj_close": df.get("Adj Close", df.get("Close")),
        "volume": df.get("Volume"),
        "value": float("nan"),              # yahoo khong cung cap turnover cho chi so
    })
    # yahoo tra volume = 0 cho hau het chi so chau A -> coi nhu khong co
    vol = pd.to_numeric(out["volume"], errors="coerce")
    out.loc[vol <= 0, "volume"] = float("nan")
    return out


# =====================================================================================
# 2. VCI (VN)
# =====================================================================================
def fetch_vnstock(symbol, start, end):
    """Hit thang endpoint VCI de lay ca accumulatedValue (gia tri giao dich, trieu VND)."""
    import requests
    business_days = pd.bdate_range(start=start, end=end)
    count_back = len(business_days) + 5
    end_stamp = int((pd.Timestamp(end) + pd.Timedelta(days=1)).timestamp())
    payload = {"timeFrame": "ONE_DAY", "symbols": [symbol],
               "to": end_stamp, "countBack": count_back}
    r = requests.post(VCI_URL, json=payload, headers=VCI_HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    sd = data[0] if isinstance(data, list) and data else {}
    if not sd or not sd.get("c"):
        return empty_frame()
    dates = pd.to_datetime(pd.to_numeric(sd["t"]), unit="s", utc=True) \
              .tz_convert("Asia/Ho_Chi_Minh").strftime("%Y-%m-%d")
    out = pd.DataFrame({
        "date": dates,
        "open": sd["o"],
        "high": sd["h"],
        "low": sd["l"],
        "close": sd["c"],
        "adj_close": sd["c"],
        "volume": sd.get("v"),
        "value": sd.get("accumulatedValue"),
    })
    out = normalize_value_unit(out)
    out = out[out["date"] >= str(start)]
    return out


def normalize_value_unit(out):
    """VCI doi don vi accumulatedValue giua chung (truoc 2025-08-12: VND tuyet doi;
    tu 2025-08-12: TRIEU VND). Chuan hoa TAT CA ve TRIEU VND dua tren ty le value/volume
    (= gia TB/CP): neu ~ >100 la dang o don vi VND -> chia 1e6."""
    val = pd.to_numeric(out["value"], errors="coerce")
    vol = pd.to_numeric(out["volume"], errors="coerce")
    ratio = val / vol.where(vol > 0)
    mask = ratio > 100
    out.loc[mask, "value"] = val[mask] / 1_000_000.0
    return out


# =====================================================================================
# 3. TENCENT (TQ + HK)
# =====================================================================================
TENCENT_URL = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"


def fetch_tencent(symbol, start, end):
    """newfqkline: moi phan tu = [date, open, close, high, low, volume, {}, turnover_rate, amount(van), ...].
    Toi da ~640 dong/lan -> chia cua so 2 nam. amount don vi 10^4 (CNY hoac HKD) -> /100 ra trieu.
    Volume: sh/sz = 手 (x100 co phieu); hk: cot volume thuc ra la amount tuyet doi -> bo."""
    import requests
    rows = []
    cur = pd.Timestamp(start)
    endts = pd.Timestamp(end)
    while cur <= endts:
        nxt = min(cur + pd.DateOffset(years=2) - pd.Timedelta(days=1), endts)
        param = f"{symbol},day,{cur:%Y-%m-%d},{nxt:%Y-%m-%d},640,qfq"
        for attempt in range(3):
            try:
                r = requests.get(TENCENT_URL, params={"param": param},
                                 headers={"User-Agent": UA}, timeout=60)
                r.raise_for_status()
                d = r.json().get("data", {}).get(symbol, {})
                day = (d.get("day") or d.get("qfqday") or []) if isinstance(d, dict) else []
                rows.extend(day)
                break
            except Exception as e:
                if attempt == 2:
                    log(f"    [tencent] loi cua so {cur:%Y-%m-%d}: {repr(e)[:80]}")
                time.sleep(3)
        cur = nxt + pd.Timedelta(days=1)
        time.sleep(0.3)
    if not rows:
        return empty_frame()
    is_hk = symbol.lower().startswith("hk")
    recs = []
    for x in rows:
        try:
            amount = float(x[8]) if len(x) > 8 else float("nan")
        except Exception:
            amount = float("nan")
        vol = float("nan")
        if not is_hk:
            try:
                vol = float(x[5]) * 100.0          # 手 -> co phieu
            except Exception:
                pass
        recs.append({
            "date": x[0], "open": x[1], "close": x[2], "high": x[3], "low": x[4],
            "volume": vol,
            "value": amount / 100.0 if amount and amount > 0 else float("nan"),   # van -> trieu
        })
    out = pd.DataFrame(recs)
    out["adj_close"] = out["close"]
    out = out[(out["date"] >= str(start)) & (out["date"] <= str(end))]
    out = out.drop_duplicates(subset=["date"], keep="last")
    return out[DATA_COLS]


# =====================================================================================
# 4. TWSE (Dai Loan) — FMTQIK theo thang
# =====================================================================================
TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK"


def fetch_twse(symbol, start, end):
    """Moi request = 1 thang: [日期(ROC), 成交股數, 成交金額(TWD), 成交筆數, 加權指數, 漲跌點數].
    TWSE chan neu goi qua nhanh -> nghi 3s/thang."""
    import requests
    recs = []
    cur = pd.Timestamp(start).replace(day=1)
    endts = pd.Timestamp(end)
    while cur <= endts:
        for attempt in range(3):
            try:
                r = requests.get(TWSE_URL, params={"date": f"{cur:%Y%m%d}", "response": "json"},
                                 headers={"User-Agent": UA}, timeout=30)
                r.raise_for_status()
                j = r.json()
                for row in j.get("data", []) or []:
                    y, m, d = row[0].strip().split("/")
                    date = f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}"
                    recs.append({"date": date, "volume": _num(row[1]),
                                 "value": _num(row[2]) / 1e6, "close": _num(row[4])})
                break
            except Exception as e:
                if attempt == 2:
                    log(f"    [twse] loi thang {cur:%Y-%m}: {repr(e)[:80]}")
                time.sleep(10)
        cur = cur + pd.DateOffset(months=1)
        time.sleep(3)
    if not recs:
        return empty_frame()
    out = pd.DataFrame(recs)
    for c in ("open", "high", "low"):
        out[c] = float("nan")
    out["adj_close"] = out["close"]
    out = out[(out["date"] >= str(start)) & (out["date"] <= str(end))]
    return out[DATA_COLS]


# =====================================================================================
# 5. NAVER (Han Quoc) — bang HTML theo trang, 6 dong/trang
# =====================================================================================
NAVER_URL = "https://finance.naver.com/sise/sise_index_day.naver"


def fetch_naver(symbol, start, end):
    """Cot: 날짜, 체결가, 전일비, 등락률, 거래량(천주), 거래대금(백만). Doc tu trang 1 lui dan
    den khi gap ngay < start. 거래대금 da la TRIEU KRW; 거래량 x1000 ra co phieu."""
    import requests
    recs = []
    seen = set()
    page = 1
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA})
    err_streak = 0
    while True:
        try:
            r = sess.get(NAVER_URL, params={"code": symbol, "page": page}, timeout=30)
            r.encoding = "euc-kr"
            t = pd.read_html(io.StringIO(r.text))[0].dropna(how="all")
            err_streak = 0
        except Exception as e:
            err_streak += 1
            log(f"    [naver] loi trang {page}: {repr(e)[:80]}")
            if err_streak > 5:
                break
            time.sleep(5)
            continue
        if t.empty:
            break
        t.columns = ["date", "close", "chg", "pct", "vol_k", "val_mn"][:len(t.columns)]
        min_date = None
        new_rows = 0
        for _, row in t.iterrows():
            ds = str(row["date"]).strip()
            if not re.match(r"\d{4}\.\d{2}\.\d{2}", ds):
                continue
            date = ds.replace(".", "-")
            min_date = date if min_date is None else min(min_date, date)
            if date in seen:
                continue
            seen.add(date)
            new_rows += 1
            recs.append({"date": date, "close": pd.to_numeric(row["close"], errors="coerce"),
                         "volume": pd.to_numeric(row.get("vol_k"), errors="coerce") * 1000.0,
                         "value": pd.to_numeric(row.get("val_mn"), errors="coerce")})
        # trang qua cuoi thi Naver lap lai trang cuoi -> new_rows == 0 -> dung
        if min_date is None or min_date < str(start) or new_rows == 0:
            break
        page += 1
        if page > 3000:
            break
        time.sleep(0.15)
    if not recs:
        return empty_frame()
    out = pd.DataFrame(recs)
    for c in ("open", "high", "low"):
        out[c] = float("nan")
    out["adj_close"] = out["close"]
    out = out[(out["date"] >= str(start)) & (out["date"] <= str(end))]
    return out[DATA_COLS]


# =====================================================================================
# 6. SET (Thai Lan) — can cookie Incapsula tu trang HTML, roi goi API
# =====================================================================================
SET_HTML = "https://www.set.or.th/en/market/index/set/overview"


def fetch_set(symbol, start, end):
    """chart-quotation period=5Y: quotations[{datetime, price, volume, value(THB)}]. 10Y/MAX bi 400."""
    s = _cffi_session()
    s.get(SET_HTML, timeout=40)
    url = f"https://www.set.or.th/api/set/index/{symbol}/chart-quotation"
    r = s.get(url, params={"period": "5Y", "accumulated": "false"},
              headers={"Referer": SET_HTML, "Accept": "application/json"}, timeout=40)
    if r.status_code != 200 or not r.text.lstrip().startswith("{"):
        raise RuntimeError(f"SET API {r.status_code}: {r.text[:80]!r}")
    q = r.json().get("quotations") or []
    if not q:
        return empty_frame()
    out = pd.DataFrame({
        "date": [x["datetime"][:10] for x in q],
        "close": [x.get("price") for x in q],
        "volume": [x.get("volume") for x in q],
        "value": [(x.get("value") or float("nan")) / 1e6 for x in q],
    })
    for c in ("open", "high", "low"):
        out[c] = float("nan")
    out["adj_close"] = out["close"]
    out = out[(out["date"] >= str(start)) & (out["date"] <= str(end))]
    return out[DATA_COLS]


# =====================================================================================
# 7. IDX (Indonesia) — 1 request / ngay, Cloudflare
# =====================================================================================
IDX_URL = "https://www.idx.co.id/primary/TradingSummary/GetIndexSummary"


def fetch_idx(symbol, start, end):
    """GetIndexSummary?date=YYYYMMDD -> data[{IndexCode, Previous, Highest, Lowest, Close, Volume, Value(IDR)}].
    Cloudflare thinh thoang tra 'Just a moment' -> doi session moi + retry."""
    sess = _cffi_session()
    recs = []
    fails = 0
    for d in bdays(start, end):
        ok = False
        for attempt in range(4):
            try:
                r = sess.get(IDX_URL, params={"date": d.replace("-", ""), "length": 9999, "start": 0},
                             timeout=40)
                if r.status_code == 200 and r.text.lstrip().startswith("{"):
                    rows = [x for x in r.json().get("data", []) if x.get("IndexCode") == symbol]
                    if rows:
                        x = rows[0]
                        recs.append({"date": d, "high": x.get("Highest"),
                                     "low": x.get("Lowest"), "close": x.get("Close"),
                                     "volume": x.get("Volume"),
                                     "value": (x.get("Value") or float("nan")) / 1e6})
                    ok = True
                    break
                time.sleep(2 + 2 * attempt)
                sess = _cffi_session()
            except Exception:
                time.sleep(2 + 2 * attempt)
                sess = _cffi_session()
        if not ok:
            fails += 1
            log(f"    [idx] bo ngay {d} (Cloudflare/loi mang)")
            if fails > 30:
                log("    [idx] qua nhieu loi lien tiep -> dung nguon nay, giu phan da keo")
                break
        else:
            fails = 0
        time.sleep(0.4)
    if not recs:
        return empty_frame()
    out = pd.DataFrame(recs)
    out["open"] = float("nan")        # IDX chi co 'Previous' (dong cua hom truoc), khong co open
    out["adj_close"] = out["close"]
    return out[DATA_COLS]


# =====================================================================================
# 8. BURSA (Malaysia) — gia tu yahoo + KL/GTGD toan thi truong tu PDF Daily Scoreboard
# =====================================================================================
BURSA_PDF = "https://www.bursamalaysia.com/misc/missftp/securities/securities_equities_daily_scoreboard_{d}.pdf"
BURSA_EQUITY_SECTIONS = ("Main Market", "Ace Market", "Leap Market")


def _bursa_nums(text, label):
    """Chuoi so lien tiep ngay sau `label`; neu chuoi co dang A A B B ... (chu dam in 2 lop) thi lay 1 ban."""
    m = re.search(label + r"((?:\s+[\d,]+)+)", text)
    if not m:
        return None
    toks = m.group(1).split()
    if len(toks) % 2 == 0 and len(toks) >= 4 and toks[0::2] == toks[1::2]:
        toks = toks[0::2]
    return [_num(x) for x in toks]


def _bursa_parse(pdf_bytes):
    """Tra (volume_shares, value_rm_mn) = tong Main+ACE+LEAP, ca khop lenh (Market Transaction) lan Direct Business.
    Text cac trang noi lai vi dong 'Direct Business' cua Main Market hay bi day sang trang sau."""
    import pypdf
    p = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    txt = ""
    for pg in p.pages[:12]:
        # mot so PDF (vd 08/07/2026) co 2 lop chu chong len nhau -> pypdf tra MOI DONG 2 LAN (A A B B C C).
        # KHONG duoc gop moi dong trung lien tiep (bang co nhieu dong "0" that) -> chi khi >=80% cap (2i,2i+1) trung
        # thi lay dong chan.
        # (layout 08/07/2026: chi dong TIEU DE bi lap, dong so thi khong) -> gop dong trung lien tiep CO CHU, giu dong so.
        lines = []
        for ln in (pg.extract_text() or "").split("\n"):
            if lines and lines[-1] == ln and re.search(r"[A-Za-z]", ln):
                continue
            lines.append(ln)
        t = " ".join(lines)
        if "Daily Stock Transaction" in t:
            break
        txt += " " + t
    parts = re.split(r"\s(?=\d\.\s+(?:Main Market|Structured Warrant|Ace Market|Loans|Exchange Traded|Leap Market)\b)", txt)
    vol = val = 0.0
    found = 0
    for part in parts:
        m = re.match(r"\s*\d\.\s+([A-Za-z ]+?)\s+Volume", part)
        if not m or m.group(1).strip() not in BURSA_EQUITY_SECTIONS:
            continue
        # Lay CHUOI SO ngay sau nhan; token dau = khoi luong ('000), token cuoi = gia tri (RM '000).
        # Layout thuong: Total ... V r f n t Val (6 so); Direct Business V 0 0 0 0 Val (6) hoac V Val (2).
        # Layout 08/07/2026 (chu dam in 2 lop): moi so lap 2 lan "V V r r f f ..." -> _bursa_nums() tu khu lap.
        tv = _bursa_nums(part, r"Total\s+Market\s+Transaction")
        if not tv:
            continue
        found += 1
        vol += tv[0] * 1000.0
        val += tv[-1] / 1000.0
        tail = part[part.find("Total"):]
        dv = _bursa_nums(tail, r"Direct\s+Business")
        if dv:
            vol += dv[0] * 1000.0
            val += dv[-1] / 1000.0
    if found == 0:
        raise ValueError("khong tim thay section Main/ACE/LEAP")
    return vol, val


def _merge_px_liq(px, recs):
    liq = pd.DataFrame(recs) if recs else pd.DataFrame(columns=["date", "volume", "value"])
    px = px.drop(columns=["volume", "value"])
    out = px.merge(liq, on="date", how="outer").sort_values("date")
    out["adj_close"] = out["adj_close"].fillna(out["close"])
    return out[DATA_COLS]


def fetch_bursa(symbol, start, end):
    px = fetch_yahoo(symbol, start, end)
    sess = _cffi_session()
    recs = []
    for d in bdays(start, end):
        try:
            r = None
            for attempt in range(4):
                r = sess.get(BURSA_PDF.format(d=d.replace("-", "")), timeout=60)
                if r.status_code == 404:
                    break                                  # ngay nghi
                if r.status_code == 200 and r.content[:4] == b"%PDF":
                    break
                # Cloudflare "Just a moment" (403) thinh thoang -> doi session + cho roi thu lai
                time.sleep(3 + 3 * attempt)
                sess = _cffi_session()
            if r is None or r.status_code != 200 or r.content[:4] != b"%PDF":
                continue
            vol, val = _bursa_parse(r.content)
            if val > 0:                       # PDF ngay nghi/nua ngay co the toan 0 -> bo, khong ghi 0
                recs.append({"date": d, "volume": vol, "value": val})
        except Exception as e:
            log(f"    [bursa] {d}: {repr(e)[:80]}")
        time.sleep(0.3)
    return _merge_px_liq(px, recs)


# =====================================================================================
# 9. JPX (Nhat) — gia tu yahoo + GTGD toan TSE tu PDF est-set
# =====================================================================================
JPX_BASE = "https://www.jpx.co.jp"
JPX_INDEX = JPX_BASE + "/markets/statistics-equities/daily/index.html"
JPX_ARCH = JPX_BASE + "/markets/statistics-equities/daily/00-archives-{n:02d}.html"


def _jpx_list_pdfs(sess, start):
    """Gom link est-set_YYYYMMDD.pdf tu trang index + cac trang archive (moi trang ~1 thang)."""
    links = {}
    pages = [JPX_INDEX] + [JPX_ARCH.format(n=n) for n in range(1, 13)]
    for url in pages:
        try:
            r = sess.get(url, timeout=40)
        except Exception:
            break
        if r.status_code != 200:
            break
        found = re.findall(r'href="(/markets/statistics-equities/daily/[^"]*est-set_(\d{8})\.pdf)"', r.text)
        if not found:
            break
        oldest = None
        for href, ymd in found:
            date = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
            links[date] = JPX_BASE + href
            oldest = date if oldest is None else min(oldest, date)
        if oldest and oldest < str(start):
            break
        time.sleep(0.3)
    return links


_JPX_NUM = re.compile(r"^\d{1,3}(,\d{3})*$")


def _jpx_numbers(line):
    """pypdf hay tach 1 so thanh manh ('2,831,128,1 00', '2,873, 546,125') -> ghep lai cac manh
    cho den khi thanh so hop le dang 1,234,567. '－' (khong co) = 0."""
    toks = line.replace("－", "-").split()
    out = []
    buf = ""
    for t in toks:
        if t == "-":
            if buf:
                buf = ""
            out.append(0.0)
            continue
        if not re.fullmatch(r"[\d,]+", t):
            buf = ""
            continue
        cand = buf + t
        if _JPX_NUM.match(cand):
            out.append(_num(cand))
            buf = ""
        else:
            buf = cand
    return out


def _jpx_parse(pdf_bytes):
    """Trang 'Domestic Stock' theo gia tri (円): 3 dong 'Total' = Prime/Standard/Growth, sau do 1 dong
    khong nhan = tong toan bo. Cot thu 7 (index 6) = tong ca dau gia lan ToSTNeT trong ngay.
    Tra (volume_shares, value_jpy_mn)."""
    import pypdf
    p = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    vol_total = val_total = None
    for pg in p.pages[:6]:
        t = pg.extract_text() or ""
        if "Common" not in t or "Total" not in t:
            continue
        is_value = "円[" in t.split("Common")[0]
        totals = []
        grand = None
        for ln in t.splitlines():
            s = ln.strip()
            if s.startswith("Total"):
                nums = _jpx_numbers(s[5:])
                if len(nums) >= 7:
                    totals.append(nums)
            elif re.match(r"^[\d,]", s) and len(totals) >= 3 and grand is None:
                nums = _jpx_numbers(s)
                if len(nums) >= 7:
                    grand = nums
        if grand is None and len(totals) >= 3:
            grand = [sum(x[k] for x in totals[:3]) for k in range(7)]
        if grand is None:
            continue
        if is_value and val_total is None:
            val_total = grand[6] / 1e6
        elif not is_value and vol_total is None:
            vol_total = grand[6]
        if val_total is not None and vol_total is not None:
            break
    if val_total is None:
        raise ValueError("khong tim thay bang gia tri")
    return vol_total, val_total


def fetch_jpx(symbol, start, end):
    px = fetch_yahoo(symbol, start, end)
    sess = _cffi_session()
    links = _jpx_list_pdfs(sess, start)
    recs = []
    for d in sorted(links):
        if d < str(start) or d > str(end):
            continue
        try:
            r = sess.get(links[d], timeout=90)
            if r.status_code != 200 or r.content[:4] != b"%PDF":
                continue
            vol, val = _jpx_parse(r.content)
            recs.append({"date": d, "volume": vol, "value": val})
        except Exception as e:
            log(f"    [jpx] {d}: {repr(e)[:80]}")
        time.sleep(0.5)
    return _merge_px_liq(px, recs)


# =====================================================================================
# FX: ty gia XXX=X (so don vi ban dia / 1 USD) tu yfinance, cache fx-master.csv
# =====================================================================================
def update_fx(currencies, start):
    import yfinance as yf
    old = pd.read_csv(FX_PATH, dtype={"date": str}) if os.path.exists(FX_PATH) else \
        pd.DataFrame(columns=["date", "currency", "rate"])
    frames = [old] if not old.empty else []      # tranh FutureWarning concat voi frame rong
    for cur in sorted(set(c for c in currencies if isinstance(c, str) and c and c != "USD")):
        s = start
        if not old.empty and (old["currency"] == cur).any():
            mx = pd.to_datetime(old.loc[old["currency"] == cur, "date"]).max()
            s = (mx - timedelta(days=BUFFER_DAYS)).strftime("%Y-%m-%d")
        try:
            df = yf.download(f"{cur}=X", start=s, interval="1d", auto_adjust=False,
                             progress=False, threads=False)
            if df is None or df.empty:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.reset_index()
            frames.append(pd.DataFrame({"date": pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d"),
                                        "currency": cur, "rate": df["Close"].values}))
        except Exception as e:
            log(f"  [fx] {cur}: {repr(e)[:80]}")
    fx = pd.concat(frames, ignore_index=True)
    fx["rate"] = pd.to_numeric(fx["rate"], errors="coerce")
    fx = fx.dropna(subset=["rate"]).drop_duplicates(subset=["date", "currency"], keep="last")
    fx = fx.sort_values(["currency", "date"]).reset_index(drop=True)
    safe_to_csv(fx, FX_PATH)
    return fx


def apply_value_usd(df, fx):
    """value_usd = value / rate(ngay), rate ffill theo ngay trong tung currency."""
    df = df.copy()
    df["value_usd"] = float("nan")
    if fx is None or fx.empty:
        return df
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    for cur, grp in df.groupby("currency"):
        if not isinstance(cur, str) or not cur:
            continue
        if cur == "USD":
            df.loc[grp.index, "value_usd"] = grp["value"]
            continue
        rates = fx[fx["currency"] == cur].set_index("date")["rate"].sort_index()
        if rates.empty:
            continue
        idx = pd.Index(sorted(set(rates.index) | set(grp["date"])))
        r = rates.reindex(idx).ffill()
        df.loc[grp.index, "value_usd"] = grp["value"].values / r.reindex(grp["date"]).values
    return df


# =====================================================================================
FETCHERS = {
    "yahoo": fetch_yahoo,
    "vnstock": fetch_vnstock,
    "tencent": fetch_tencent,
    "twse": fetch_twse,
    "naver": fetch_naver,
    "set": fetch_set,
    "idx": fetch_idx,
    "bursa": fetch_bursa,
    "jpx": fetch_jpx,
}


def fetch_one(rec, start, end):
    src = rec["source"].strip().lower()
    sym = rec["symbol"].strip()
    fn = FETCHERS.get(src)
    if fn is None:
        log(f"  [BO QUA] source khong ho tro: {src} ({rec['index_code']})")
        return None
    floor = SOURCE_FLOOR.get(src)
    if floor and str(start) < floor:
        start = floor
    df = fn(sym, start, end)
    if df is None or len(df) == 0:
        return None
    df = df.copy()
    df.insert(1, "index_code", rec["index_code"])
    df.insert(2, "index_name", rec["index_name"])
    df.insert(3, "source", src)
    df["currency"] = rec.get("currency", "") or ""
    df["value_usd"] = float("nan")
    return df[COLUMNS]


def load_master():
    if not os.path.exists(MASTER_PATH):
        return None
    old = pd.read_csv(MASTER_PATH, dtype={"date": str, "currency": str})
    pend = MASTER_PATH.replace(".csv", ".pending.csv")
    if os.path.exists(pend):
        try:
            p = pd.read_csv(pend, dtype={"date": str, "currency": str})
            old = pd.concat([old, p], ignore_index=True)
            os.remove(pend)
            log(f"  Da nuot lai {len(p)} dong tu file pending")
        except Exception:
            pass
    return old


def main():
    args = sys.argv[1:]
    full = "--full" in args
    only = None
    if "--only" in args:
        i = args.index("--only")
        if i + 1 < len(args):
            only = {c.strip().upper() for c in args[i + 1].split(",") if c.strip()}
    config = load_config()
    if only:
        config = [c for c in config if c["index_code"].upper() in only]
        missing = only - {c["index_code"].upper() for c in config}
        if missing:
            log(f"[!] --only: khong thay trong indices.csv: {sorted(missing)}")

    old = load_master()
    if old is not None:
        for c in COLUMNS:
            if c not in old.columns:
                old[c] = float("nan") if c in NUM_COLS else ""

    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")  # yfinance end exclusive
    today = datetime.now().strftime("%Y-%m-%d")

    def start_for(code):
        """Incremental theo TUNG ma: ma chua co trong master -> keo full."""
        if full or old is None or old.empty:
            return FULL_START
        sub = old.loc[old["index_code"] == code, "date"]
        if sub.empty:
            return FULL_START
        mx = pd.to_datetime(sub).max()
        return (mx - timedelta(days=BUFFER_DAYS)).strftime("%Y-%m-%d")

    mode = "FULL" if full else "INCREMENTAL"
    log(f"=== Che do: {mode} | den {today} | {len(config)} chi so"
        + (f" | only={sorted(only)}" if only else "") + " ===")

    frames = []
    for rec in config:
        code = rec["index_code"]
        start = start_for(code)
        t0 = time.time()
        try:
            df = fetch_one(rec, start, end)
            n = 0 if df is None else len(df)
            log(f"  {code:10} ({rec['source']:7}) tu {start} -> {n} dong [{time.time() - t0:.0f}s]")
            if df is not None and n:
                frames.append(df)
        except Exception as e:
            log(f"  {code:10} [LOI] {repr(e)[:140]}")

    if not frames:
        log("Khong keo duoc du lieu moi nao. Giu nguyen file master.")
        return

    for f in frames:
        for c in NUM_COLS:
            f[c] = pd.to_numeric(f[c], errors="coerce")
    new = pd.concat(frames, ignore_index=True)

    if old is not None and not old.empty:
        for c in NUM_COLS:
            old[c] = pd.to_numeric(old[c], errors="coerce")
        is_derived = old["source"].astype(str).str.startswith("derived")
        if full and not only:
            # dung lai tu dau nhung GIU cac chi so phai sinh do tool khac ghi vao (source derived-*)
            combined = pd.concat([old[is_derived][COLUMNS], new], ignore_index=True)
        elif full and only:
            # backfill lai 1 so ma: bo han ban cu cua CHINH cac ma do (vd doi source yahoo -> tencent)
            keep = old[is_derived | ~old["index_code"].str.upper().isin(only)]
            combined = pd.concat([keep[COLUMNS], new], ignore_index=True)
        else:
            combined = pd.concat([old[COLUMNS], new], ignore_index=True)
    else:
        combined = new

    # currency cho dong cu chua co (schema cu): lay tu indices.csv
    cur_map = {c["index_code"]: (c.get("currency") or "") for c in load_config()}
    combined["currency"] = combined["currency"].fillna("").astype(str)
    mask = combined["currency"].str.strip().isin(["", "nan"])
    combined.loc[mask, "currency"] = combined.loc[mask, "index_code"].map(cur_map).fillna("")

    before = len(combined)
    combined = combined.drop_duplicates(subset=["date", "index_code"], keep="last")
    combined = combined.dropna(subset=["date"])
    combined = combined.sort_values(["index_code", "date"]).reset_index(drop=True)

    # FX + value_usd (tinh lai cho toan bo master de ty gia moi/ffill nhat quan)
    try:
        fx = update_fx(combined["currency"].unique().tolist(), FULL_START)
        combined = apply_value_usd(combined, fx)
    except Exception as e:
        log(f"  [fx] bo qua value_usd: {repr(e)[:100]}")

    old_n = 0 if old is None else len(old)
    added = len(combined) - old_n
    log(f"--- Tong dong: {len(combined)} (truoc {old_n}, +{added} moi/cap nhat, bo {before - len(combined)} trung) ---")
    safe_to_csv(combined[COLUMNS], MASTER_PATH)
    log(f"Da luu: {MASTER_PATH}")


if __name__ == "__main__":
    main()
