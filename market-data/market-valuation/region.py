# -*- coding: utf-8 -*-
r"""
region.py — DINH GIA THI TRUONG KHU VUC (P/E, P/B, ty suat co tuc, von hoa) theo "form" cua fetch_valuation.py (VN),
gop vao valuation-region-master.csv (long) + valuation-region-wide.csv (wide + dan xuat).

Nguon theo code (cot source):
  SET, MAI, SET50, SET100   set      set.or.th /api/set/index/{x}/performance: pe, pbv, dividendYield, marketCap(THB), eps.
                                     CHI CO SNAPSHOT NGAY HIEN TAI -> freq D, chay hang ngay de boi chuoi.
  SSE_A                     sse      query.sse.com.cn commonQuery MRGK (PRODUCT_CODE 01 = co phieu A san chinh SH):
                                     AVG_PE_RATE, TOTAL_VALUE (ti CNY x1e8), NEGO_VALUE. CO LICH SU theo ngay (1 request/ngay).
  SSEC, SZSEC, CSI300       tencent  qt.gtimg.cn/q=sh000001,sz399001,sh000300: truong 39 = P/E chi so, 45 = tong von hoa (ti CNY).
                                     Snapshot -> freq D.
  JCI, LQ45                 idx      idx.co.id GetIndexSummary?date=: MarketCapital (IDR). Lich su tu 2020, 1 request/ngay.
  FBMKLCI                   bursa    PDF securities_equities_keyindicators_YYYYMMDD.pdf: bang ngay ~1 thang gan nhat, lay
                                     Market Capitalisation TOTAL (RM ti x1e9). Chi co PDF moi (URL cu 403/404) -> boi dan.
  TSE_PRIME, TSE_STD, TSE_GROWTH, TSE_ALL  jpx  perpbrYYYYMM.xlsx (PER/PBR binh quan gia quyen theo thi truong, Composite) +
                                     historical-jika.xlsx (von hoa cuoi thang, trieu JPY). freq M, date = cuoi thang.
  TAIEX                     twse     (giai doan 2) gop tu tung ma: BWIBBU_d (P/E, yield, P/B) x MI_QFIIS (so CP) x gia dong cua.
  KOSPI/KOSDAQ: KRX data.krx.co.kr bat dang nhap -> chua co. HSI: hsi.com.hk chi co PDF bao cao -> chua co.

Ratio dung ten VN: PRICE_TO_EARNINGS, PRICE_TO_BOOK, DIVIDEND_YIELD (%), MARKETCAP (tien ban dia tuyet doi), EPS (diem).
Chay:
  python region.py                 # incremental (moi code keo tu ngay cuoi - 7; snapshot chi lay hom nay)
  python region.py --full          # keo lai lich su (chi nguon co lich su: sse/idx/jpx)
  python region.py --only SET,SSE_A
"""
import argparse
import io
import os
import re
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # D:\market-data
from mdlib import log, cffi_session as _cffi_session, safe_to_csv  # noqa: E402  (gop 14/09/2026)
MASTER_CSV = os.path.join(BASE_DIR, "valuation-region-master.csv")
WIDE_CSV = os.path.join(BASE_DIR, "valuation-region-wide.csv")
INDEX_MASTER = os.path.join(os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data")), "index-fetcher", "indices-master.csv")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
FULL_START = "2020-01-01"
BUFFER_DAYS = 7
COLS = ["code", "date", "ratio", "value", "currency", "freq", "source"]

# code -> (source, symbol, currency, index_code trong indices-master de join close)
CODES = {
    "SET": ("set", "SET", "THB", "SET"),
    "MAI": ("set", "mai", "THB", "MAI"),
    "SET50": ("set", "SET50", "THB", None),
    "SET100": ("set", "SET100", "THB", None),
    "SSE_A": ("sse", "01", "CNY", "SSEC"),
    "SSEC": ("tencent", "sh000001", "CNY", "SSEC"),
    "SZSEC": ("tencent", "sz399001", "CNY", "SZSEC"),
    "CSI300": ("tencent", "sh000300", "CNY", "CSI300"),
    "JCI": ("idx", "COMPOSITE", "IDR", "JCI"),
    "LQ45": ("idx", "LQ45", "IDR", "LQ45"),
    "FBMKLCI": ("bursa", "", "MYR", "FBMKLCI"),
    "TSE_PRIME": ("jpx", "Prime", "JPY", None),
    "TSE_STD": ("jpx", "Standard", "JPY", None),
    "TSE_GROWTH": ("jpx", "Growth", "JPY", None),
    "TSE_ALL": ("jpx", "Total", "JPY", "N225"),
    "TAIEX": ("twse", "", "TWD", "TAIEX"),
}
SOURCE_FLOOR = {"twse": "2024-01-01"}     # gop tung ma nang (2 request + 6s/ngay) -> mac dinh lui 2024, muon xa hon thi --full
SNAPSHOT_SOURCES = {"set", "tencent", "bursa"}


def _num(s):
    s = str(s).replace(",", "").strip()
    return float(s) if s not in ("", "--", "-", "nan", "None", "－", "＊", "*") else float("nan")


def bdays(start, end):
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(start=start, end=end)]


def rec(code, date, ratio, value, cur, freq, source):
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    if v != v:
        return None
    return {"code": code, "date": date, "ratio": ratio, "value": v, "currency": cur, "freq": freq, "source": source}


# =====================================================================================
SET_HTML = "https://www.set.or.th/en/market/index/set/overview"
_set_sess = None


def fetch_set(code, sym, cur, start, end):
    global _set_sess
    if _set_sess is None:
        _set_sess = _cffi_session()
        _set_sess.get(SET_HTML, timeout=40)
    r = _set_sess.get(f"https://www.set.or.th/api/set/index/{sym}/performance", params={"lang": "en"},
                      headers={"Referer": SET_HTML, "Accept": "application/json"}, timeout=40)
    if r.status_code != 200 or not r.text.lstrip().startswith("{"):
        raise RuntimeError(f"SET {r.status_code}")
    j = r.json()
    d = (j.get("date") or "")[:10]
    out = [rec(code, d, "PRICE_TO_EARNINGS", j.get("pe"), cur, "D", "set"),
           rec(code, d, "PRICE_TO_BOOK", j.get("pbv"), cur, "D", "set"),
           rec(code, d, "DIVIDEND_YIELD", j.get("dividendYield"), cur, "D", "set"),
           rec(code, d, "MARKETCAP", j.get("marketCap"), cur, "D", "set"),
           rec(code, d, "EPS", j.get("eps"), cur, "D", "set")]
    return [x for x in out if x]


def fetch_sse(code, prod, cur, start, end):
    url = "https://query.sse.com.cn/commonQuery.do"
    h = {"User-Agent": UA, "Referer": "https://www.sse.com.cn/"}
    out = []
    for d in bdays(start, end):
        for attempt in range(3):
            try:
                r = requests.get(url, params={"sqlId": "COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C", "PRODUCT_CODE": prod,
                                              "type": "inParams", "SEARCH_DATE": d, "_": "1"}, headers=h, timeout=30)
                res = r.json().get("result", [])
                for x in res:
                    if x.get("PRODUCT_CODE") != prod:
                        continue
                    out += [rec(code, d, "PRICE_TO_EARNINGS", _num(x.get("AVG_PE_RATE")), cur, "D", "sse"),
                            rec(code, d, "MARKETCAP", _num(x.get("TOTAL_VALUE")) * 1e8, cur, "D", "sse"),
                            rec(code, d, "MARKETCAP_FLOAT", _num(x.get("NEGO_VALUE")) * 1e8, cur, "D", "sse")]
                break
            except Exception:
                time.sleep(3)
        time.sleep(0.4)
    return [x for x in out if x]


def fetch_tencent(code, sym, cur, start, end):
    r = requests.get("https://qt.gtimg.cn/q=" + sym, headers={"User-Agent": UA}, timeout=30)
    txt = r.content.decode("gbk", "ignore")
    f = txt.split("~")
    if len(f) < 46:
        return []
    d = f[30][:8]
    d = f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else datetime.now().strftime("%Y-%m-%d")
    out = [rec(code, d, "PRICE_TO_EARNINGS", _num(f[39]), cur, "D", "tencent"),
           rec(code, d, "MARKETCAP", _num(f[45]) * 1e8, cur, "D", "tencent"),
           rec(code, d, "MARKETCAP_FLOAT", _num(f[44]) * 1e8, cur, "D", "tencent")]
    return [x for x in out if x and x["value"] > 0]


def fetch_idx(code, sym, cur, start, end):
    url = "https://www.idx.co.id/primary/TradingSummary/GetIndexSummary"
    sess = _cffi_session()
    out, fails = [], 0
    for d in bdays(start, end):
        ok = False
        for attempt in range(4):
            try:
                r = sess.get(url, params={"date": d.replace("-", ""), "length": 9999, "start": 0}, timeout=40)
                if r.status_code == 200 and r.text.lstrip().startswith("{"):
                    for x in r.json().get("data", []):
                        if x.get("IndexCode") == sym:
                            out.append(rec(code, d, "MARKETCAP", x.get("MarketCapital"), cur, "D", "idx"))
                    ok = True
                    break
                time.sleep(2 + 2 * attempt)
                sess = _cffi_session()
            except Exception:
                time.sleep(2 + 2 * attempt)
                sess = _cffi_session()
        if not ok:
            fails += 1
            if fails > 30:
                break
        else:
            fails = 0
        time.sleep(0.4)
    return [x for x in out if x]


BURSA_KI = "https://www.bursamalaysia.com/misc/missftp/securities/securities_equities_keyindicators_{d}.pdf"


def fetch_bursa(code, sym, cur, start, end):
    """PDF Key Indicators: moi dong ngay = dd/mm/yyyy + 3 chi so + 7 KL + 7 GT + 7 von hoa (MM AM ETF SW LN LP TOTAL)."""
    import pypdf
    sess = _cffi_session()
    pdf = None
    for back in range(0, 10):
        d = (pd.Timestamp(end) - pd.Timedelta(days=back))
        if d.weekday() >= 5:
            continue
        r = sess.get(BURSA_KI.format(d=d.strftime("%Y%m%d")), timeout=40)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            pdf = r.content
            break
        if r.status_code == 403:                      # Cloudflare challenge -> doi session, thu lai ngay do
            time.sleep(3)
            sess = _cffi_session()
            r = sess.get(BURSA_KI.format(d=d.strftime("%Y%m%d")), timeout=40)
            if r.status_code == 200 and r.content[:4] == b"%PDF":
                pdf = r.content
                break
    if pdf is None:
        return []
    txt = " ".join((p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(pdf)).pages[:3]).replace("\n", " ")
    out = []
    for m in re.finditer(r"(\d{2})/(\d{2})/(\d{4})((?:\s+[\d,]+\.\d+){24})", txt):
        d = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        nums = [_num(x) for x in m.group(4).split()]
        out.append(rec(code, d, "MARKETCAP", nums[23] * 1e9, cur, "D", "bursa"))     # TOTAL market cap (RM bn)
    return [x for x in out if x and x["date"] >= start]


JPX_PER = "https://www.jpx.co.jp/markets/statistics-equities/misc/04.html"
JPX_JIKA = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001w3y-att/historical-jika.xlsx"
_jpx_cache = {}


def _jpx_load():
    """Tai 1 lan: tat ca perpbr*.xlsx dang list tren trang + historical-jika.xlsx."""
    if _jpx_cache:
        return _jpx_cache
    sess = _cffi_session()
    per = {}   # (ym, section) -> (pe, pb, earnings, netassets)
    r = sess.get(JPX_PER, timeout=40)
    links = sorted(set(re.findall(r'href="(/markets/statistics-equities/misc/[^"]*perpbr(\d{6})\.xlsx)"', r.text)))
    for href, ym in links:
        try:
            x = pd.read_excel(io.BytesIO(sess.get("https://www.jpx.co.jp" + href, timeout=60).content), header=None)
        except Exception as e:
            log(f"    [jpx] {ym}: {e}")
            continue
        for _, row in x.iterrows():
            if str(row[3]).strip() == "総合" and str(row[2]).strip() in ("Prime", "Standard", "Growth"):
                per[(f"{ym[:4]}-{ym[4:]}", str(row[2]).strip())] = (_num(row[10]), _num(row[11]), _num(row[12]), _num(row[13]))
        time.sleep(0.3)
    jika = {}
    try:
        x = pd.read_excel(io.BytesIO(sess.get(JPX_JIKA, timeout=60).content), sheet_name=0, header=None)
        for _, row in x.iterrows():
            if isinstance(row[0], (pd.Timestamp, datetime)):
                d = pd.Timestamp(row[0]).strftime("%Y-%m-%d")
                jika[d] = {"Prime": _num(row[1]) * 1e6, "Standard": _num(row[2]) * 1e6,
                           "Growth": _num(row[3]) * 1e6, "Total": _num(row[5]) * 1e6}
    except Exception as e:
        log(f"    [jpx] jika: {e}")
    _jpx_cache.update({"per": per, "jika": jika})
    return _jpx_cache


def fetch_jpx(code, section, cur, start, end):
    c = _jpx_load()
    out = []
    for d, caps in c["jika"].items():
        if d >= start and section in caps:
            out.append(rec(code, d, "MARKETCAP", caps[section], cur, "M", "jpx"))
    # ngay von hoa cuoi thang cua jika (ngay giao dich cuoi, vd 2026-05-29) -> dung cung ngay cho PER/PBR de khop dong
    month_date = {d[:7]: d for d in c["jika"]}
    if section != "Total":
        for (ym, sec), (pe, pb, earn, na) in c["per"].items():
            if sec != section:
                continue
            d = month_date.get(ym) or (pd.Period(ym, freq="M").end_time).strftime("%Y-%m-%d")
            if d < start:
                continue
            out += [rec(code, d, "PRICE_TO_EARNINGS", pe, cur, "M", "jpx"),
                    rec(code, d, "PRICE_TO_BOOK", pb, cur, "M", "jpx"),
                    rec(code, d, "EARNINGS_TTM", earn, cur, "M", "jpx"),
                    rec(code, d, "BOOK_VALUE", na, cur, "M", "jpx")]
    return [x for x in out if x]


def fetch_twse(code, sym, cur, start, end):
    """Gop toan san TWSE tu tung ma: BWIBBU_d (P/E,殖利率, P/B, gia dong cua) x MI_QFIIS (發行股數).
    mcap_i = so CP x gia; P/E = sum mcap(pe>0) / sum(mcap/pe); P/B tuong tu; yield = binh quan gia quyen mcap.
    MARKETCAP = tong mcap TAT CA ma. 2 request/ngay, nghi 3s (TWSE chan neu goi nhanh)."""
    h = {"User-Agent": UA}
    out = []
    for d in bdays(start, end):
        ds = d.replace("-", "")
        try:
            r = requests.get("https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d",
                             params={"date": ds, "selectType": "ALL", "response": "json"}, headers=h, timeout=30).json()
            if r.get("stat") != "OK":
                time.sleep(3)
                continue
            bw = pd.DataFrame(r["data"], columns=r["fields"]).rename(columns={"證券代號": "code"})
            time.sleep(3)
            r = requests.get("https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS",
                             params={"date": ds, "selectType": "ALLBUT0999", "response": "json"}, headers=h, timeout=30).json()
            if r.get("stat") != "OK":
                time.sleep(3)
                continue
            q = pd.DataFrame(r["data"], columns=r["fields"]).rename(columns={"證券代號": "code"})
        except Exception as e:
            log(f"    [twse] {d}: {repr(e)[:80]}")
            time.sleep(5)
            continue
        m = bw.merge(q[["code", "發行股數"]], on="code", how="inner")
        m["mcap"] = m["發行股數"].map(_num) * m["收盤價"].map(_num)
        m["pe"] = m["本益比"].map(_num)
        m["pb"] = m["股價淨值比"].map(_num)
        m["yld"] = m["殖利率(%)"].map(_num)
        m = m[m["mcap"] > 0]
        if m.empty:
            continue
        tot = m["mcap"].sum()
        pe_m = m[m["pe"] > 0]
        pb_m = m[m["pb"] > 0]
        pe = pe_m["mcap"].sum() / (pe_m["mcap"] / pe_m["pe"]).sum() if len(pe_m) else float("nan")
        pb = pb_m["mcap"].sum() / (pb_m["mcap"] / pb_m["pb"]).sum() if len(pb_m) else float("nan")
        yld = (m["yld"].fillna(0) * m["mcap"]).sum() / tot
        out += [rec(code, d, "PRICE_TO_EARNINGS", pe, cur, "D", "twse"),
                rec(code, d, "PRICE_TO_BOOK", pb, cur, "D", "twse"),
                rec(code, d, "DIVIDEND_YIELD", yld, cur, "D", "twse"),
                rec(code, d, "MARKETCAP", tot, cur, "D", "twse"),
                rec(code, d, "PE_COVERAGE", pe_m["mcap"].sum() / tot, cur, "D", "twse")]
        time.sleep(3)
    return [x for x in out if x]


FETCH = {"set": fetch_set, "sse": fetch_sse, "tencent": fetch_tencent, "idx": fetch_idx,
         "bursa": fetch_bursa, "jpx": fetch_jpx, "twse": fetch_twse}


# =====================================================================================
def build_wide(master):
    m = master.copy()
    m["value"] = pd.to_numeric(m["value"], errors="coerce")
    w = m.pivot_table(index=["code", "date"], columns="ratio", values="value", aggfunc="last").reset_index()
    w.columns.name = None
    ren = {"PRICE_TO_EARNINGS": "pe", "PRICE_TO_BOOK": "pb", "DIVIDEND_YIELD": "div_yield", "MARKETCAP": "marketcap",
           "MARKETCAP_FLOAT": "marketcap_float", "EPS": "eps_src", "EARNINGS_TTM": "ln_src", "BOOK_VALUE": "bv_src"}
    w = w.rename(columns=ren)
    for c in ren.values():
        if c not in w.columns:
            w[c] = float("nan")
    meta = m.drop_duplicates(["code", "date"])[["code", "date", "currency", "freq"]]
    w = w.merge(meta, on=["code", "date"], how="left")
    w["ln_ttm"] = w["marketcap"] / w["pe"]
    w["gtss"] = w["marketcap"] / w["pb"]
    w.loc[w["ln_ttm"].isna() & w["ln_src"].notna(), "ln_ttm"] = w["ln_src"]
    w.loc[w["gtss"].isna() & w["bv_src"].notna(), "gtss"] = w["bv_src"]
    w["earnings_yield"] = 1.0 / w["pe"]
    w["roe_ttm"] = w["pb"] / w["pe"]
    # join close tu indices-master
    if os.path.exists(INDEX_MASTER):
        idx = pd.read_csv(INDEX_MASTER, usecols=["date", "index_code", "close"], dtype={"date": str})
        cmap = {c: v[3] for c, v in CODES.items() if v[3]}
        w["index_code"] = w["code"].map(cmap)
        w = w.merge(idx.rename(columns={"close": "close"}), on=["index_code", "date"], how="left").drop(columns=["index_code"])
        w["eps_index"] = w["close"] / w["pe"]
        w["bvps_index"] = w["close"] / w["pb"]
    cols = ["code", "date", "currency", "freq", "pe", "pb", "div_yield", "marketcap", "marketcap_float",
            "ln_ttm", "gtss", "earnings_yield", "roe_ttm", "close", "eps_index", "bvps_index", "eps_src"]
    cols = [c for c in cols if c in w.columns]
    return w[cols].sort_values(["code", "date"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = {c.strip().upper() for c in args.only.split(",") if c.strip()}
    # 07/10/2026 cloud: env REGION_SKIP=idx,bursa (ten nguon hoac code, khong phan biet hoa/thuong) -> bo qua nguon bi chan IP
    # nuoc ngoai (IDX + Bursa Cloudflare 403 tu GitHub Actions); 2 san nay keo o laptop: python region.py --only JCI,LQ45,FBMKLCI
    skip = {c.strip().lower() for c in os.environ.get("REGION_SKIP", "").split(",") if c.strip()}

    old = pd.read_csv(MASTER_CSV, dtype={"date": str, "currency": str, "freq": str}) \
        if os.path.exists(MASTER_CSV) else pd.DataFrame(columns=COLS)
    today = datetime.now().strftime("%Y-%m-%d")
    frames = []
    for code, (src, sym, cur, _) in CODES.items():
        if only and code not in only:
            continue
        if skip and (src.lower() in skip or code.lower() in skip):
            log(f"  {code:10} ({src:7}) bo qua (REGION_SKIP)")
            continue
        sub = old[old["code"] == code] if not old.empty else old
        if args.full or sub.empty:
            start = FULL_START
        else:
            start = (pd.to_datetime(sub["date"]).max() - timedelta(days=BUFFER_DAYS)).strftime("%Y-%m-%d")
        if src in SNAPSHOT_SOURCES:
            start = max(start, (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d"))
        if SOURCE_FLOOR.get(src) and start < SOURCE_FLOOR[src]:
            start = SOURCE_FLOOR[src]
        t0 = time.time()
        try:
            got = FETCH[src](code, sym, cur, start, today)
            log(f"  {code:10} ({src:7}) tu {start} -> {len(got)} gia tri [{time.time() - t0:.0f}s]")
            if got:
                frames.append(pd.DataFrame(got))
        except Exception as e:
            log(f"  {code:10} ({src:7}) [LOI] {repr(e)[:140]}")
    if not frames:
        log("Khong co du lieu moi.")
        return
    new = pd.concat(frames, ignore_index=True)
    if not old.empty and args.full and only:
        old = old[~old["code"].isin(only)]
    elif not old.empty and args.full:
        old = old.iloc[0:0]
    master = pd.concat([old[COLS], new[COLS]], ignore_index=True) if not old.empty else new[COLS]
    master["value"] = pd.to_numeric(master["value"], errors="coerce")
    master = master.dropna(subset=["value", "date"])
    master = master.drop_duplicates(subset=["code", "date", "ratio"], keep="last")
    master = master.sort_values(["code", "ratio", "date"]).reset_index(drop=True)
    master.to_csv(MASTER_CSV, index=False, encoding="utf-8-sig")
    log(f"-> {MASTER_CSV}: {len(master)} dong (truoc {len(old)})")
    wide = build_wide(master)
    wide.to_csv(WIDE_CSV, index=False, encoding="utf-8-sig")
    log(f"-> {WIDE_CSV}: {len(wide)} dong ({wide['date'].min()} den {wide['date'].max()})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
