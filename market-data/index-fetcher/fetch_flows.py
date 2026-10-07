# -*- coding: utf-8 -*-
r"""
fetch_flows.py — Keo DONG TIEN THEO NHOM NHA DAU TU (khoi ngoai, tu doanh, to chuc, ca nhan) cap THI TRUONG
vao 1 master CSV (long): flows-master.csv.

VIET NAM (VNDirect finfo, cong khai): khoi ngoai v4/foreigns (tu 2018-08), tu doanh v4/proprietary_trading (tu 2022-05).
  4 ro: VNINDEX, VN30, HNXINDEX(=HNX ben VNDirect), UPCOM.

KHU VUC (them 09/2026, cung schema, them cot currency + freq):
  index_code  source  chi tiet
  KOSPI/KOSDAQ naver  finance.naver.com/sise/investorDealTrendDay.naver (sosok=01/02): NET theo ngay cua
                      개인/외국인/기관 (don vi 억원 x1e8 KRW). Chi co net, khong co buy/sell. Lich su day du.
  TAIEX        twse   twse.com.tw/rwd/zh/fund/BFI82U?type=day: buy/sell/net cua 外資 (foreign = 外資及陸資 + 外資自營商),
                      自營商 (prop = tu doanh tu hanh + phong ho), 投信 (institution). TWD. 1 request/ngay, nghi 2s.
  SET/MAI      set    set.or.th /api/set/market/{SET|mai}/investor-type: buy/sell/net 4 nhom NGAY HIEN TAI (freq D,
                      phai chay hang ngay de boi) + /investor-type-chart?period=1Y: NET theo THANG 12 thang (freq M,
                      date = ngay 1 cua thang). Can cookie Incapsula (curl_cffi) nhu index-fetcher.
  JCI          idx    idx.co.id GetStockSummary?date=: cong ForeignBuy/ForeignSell (SO CO PHIEU) tung ma; gia tri =
                      so CP x VWAP ma (Value/Volume) -> *_val la XAP XI, *_vol chinh xac. IDR. 1 request/ngay (~1MB).
  FBMKLCI      bursa  bursamalaysia.com PDF trading_participation_investor_YYYYMMDD.pdf: THANG (freq M) buy/sell
                      value RM ty x1e9 cua Foreign (inst + retail), Local Institutional, Local Retail (+Nominees).
                      PDF cua thang M mo ta thang M-1. Chi co tu 10/2025.

flow_type: foreign | prop | institution | individual.  freq: D (ngay) | M (thang, date = YYYY-MM-01).
Don vi *_val: dong tien BAN DIA tuyet doi (cot currency): VND, KRW, TWD, THB, IDR, MYR. *_vol: so co phieu.

Chay:
  python fetch_flows.py                # incremental (moi (index_code, flow_type) keo tu ngay cuoi - buffer)
  python fetch_flows.py --full         # keo lai toan bo lich su (VN: API tu gioi han; khu vuc: tu REGION_FULL_START)
  python fetch_flows.py --only JCI,SET # chi keo cac index_code liet ke (ma chua co trong master -> tu keo full)
  python fetch_flows.py --vn-only / --region-only

Dedup theo (date, index_code, flow_type), giu ban ghi moi. Sap xep (index_code, flow_type, date).
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
MASTER = os.path.join(BASE_DIR, "flows-master.csv")

API_FOREIGN = "https://api-finfo.vndirect.com.vn/v4/foreigns"
API_PROP = "https://api-finfo.vndirect.com.vn/v4/proprietary_trading"
HDR = {"User-Agent": "Mozilla/5.0"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
PAGE = 1000
SLEEP = 0.5
FULL_START = "2010-01-01"
REGION_FULL_START = "2020-01-01"
BUFFER_DAYS = 7

# index_code noi bo (khop indices-master) -> code ben VNDirect
CODES = {"VNINDEX": "VNINDEX", "VN30": "VN30", "HNXINDEX": "HNX", "UPCOM": "UPCOM"}

# index_code -> (source, symbol, currency)
REGION = {
    "KOSPI": ("naver", "01", "KRW"),
    "KOSDAQ": ("naver", "02", "KRW"),
    "TAIEX": ("twse", "", "TWD"),
    "SET": ("set", "SET", "THB"),
    "MAI": ("set", "mai", "THB"),
    "JCI": ("idx", "", "IDR"),
    "FBMKLCI": ("bursa", "", "MYR"),
}
SOURCE_FLOOR = {"bursa": "2025-10-01", "idx": "2020-01-01", "set": "2021-01-01"}

COLS = ["date", "index_code", "flow_type", "buy_val", "sell_val", "net_val",
        "buy_vol", "sell_vol", "net_vol", "total_room", "current_room",
        "buy_val_pct", "sell_val_pct", "currency", "freq"]
NUM_COLS = COLS[3:13]


def _num(s):
    s = str(s).replace(",", "").strip()
    return float(s) if s not in ("", "--", "-", "nan", "None") else float("nan")


def bdays(start, end):
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(start=start, end=end)]


def row(date, index_code, flow_type, currency, freq="D", **kw):
    r = {"date": date, "index_code": index_code, "flow_type": flow_type,
         "buy_val": None, "sell_val": None, "net_val": None, "buy_vol": None, "sell_vol": None,
         "net_vol": None, "total_room": None, "current_room": None, "buy_val_pct": None,
         "sell_val_pct": None, "currency": currency, "freq": freq}
    r.update(kw)
    return r


# =====================================================================================
# VIET NAM (VNDirect)
# =====================================================================================
def _get(url, q, sort_field):
    """Keo phan trang 1 truy van finfo, tra list dict."""
    rows, page = [], 1
    while True:
        params = {"q": q, "size": PAGE, "page": page, "sort": f"{sort_field}:asc"}
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, headers=HDR, timeout=30)
                r.raise_for_status()
                data = r.json().get("data", [])
                break
            except Exception as e:
                if attempt == 2:
                    raise
                log(f"    [retry] {e}")
                time.sleep(3 * (attempt + 1))
        rows.extend(data)
        if len(data) < PAGE:
            break
        page += 1
        time.sleep(SLEEP)
    return rows


def fetch_foreign(code_vnd, index_code, from_date):
    q = f"code:{code_vnd}"
    if from_date:
        q += f"~tradingDate:gte:{from_date}"
    out = []
    for r in _get(API_FOREIGN, q, "tradingDate"):
        out.append(row(r["tradingDate"], index_code, "foreign", "VND",
                       buy_val=r.get("buyVal"), sell_val=r.get("sellVal"), net_val=r.get("netVal"),
                       buy_vol=r.get("buyVol"), sell_vol=r.get("sellVol"), net_vol=r.get("netVol"),
                       total_room=r.get("totalRoom"), current_room=r.get("currentRoom")))
    return out


def fetch_prop(code_vnd, index_code, from_date):
    q = f"code:{code_vnd}"
    if from_date:
        q += f"~date:gte:{from_date}"
    out = []
    for r in _get(API_PROP, q, "date"):
        out.append(row(r["date"], index_code, "prop", "VND",
                       buy_val=r.get("buyingVal"), sell_val=r.get("sellingVal"), net_val=r.get("netVal"),
                       buy_vol=r.get("buyingVol"), sell_vol=r.get("sellingVol"), net_vol=r.get("netVol"),
                       buy_val_pct=r.get("buyingValPct"), sell_val_pct=r.get("sellingValPct")))
    return out


# =====================================================================================
# KHU VUC
# =====================================================================================
def fetch_naver(sosok, index_code, cur, from_date, end):
    """investorDealTrendDay: cot 날짜, 개인, 외국인, 기관계 ... (억원). Lui trang den khi ngay < from_date."""
    url = "https://finance.naver.com/sise/investorDealTrendDay.naver"
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA})
    biz = end.replace("-", "")
    out, seen, page, errs = [], set(), 1, 0
    while page <= 3000:
        try:
            r = sess.get(url, params={"bizdate": biz, "sosok": sosok, "page": page}, timeout=30)
            r.encoding = "euc-kr"
            tabs = [t for t in pd.read_html(io.StringIO(r.text)) if t.shape[1] >= 4]
            t = tabs[0].dropna(how="all")
            errs = 0
        except Exception as e:
            errs += 1
            log(f"    [naver] loi trang {page}: {repr(e)[:80]}")
            if errs > 5:
                break
            time.sleep(5)
            continue
        t.columns = [c[1] if isinstance(c, tuple) else c for c in t.columns]
        t = t.iloc[:, :4]
        t.columns = ["date", "individual", "foreign", "institution"]
        t = t[t["date"].astype(str).str.match(r"\d\d\.\d\d\.\d\d")]
        new = 0
        min_d = None
        for _, x in t.iterrows():
            d = "20" + str(x["date"]).replace(".", "-")
            min_d = d if min_d is None else min(min_d, d)
            if d in seen:
                continue
            seen.add(d)
            new += 1
            for ft in ("foreign", "institution", "individual"):
                v = pd.to_numeric(x[ft], errors="coerce")
                if pd.notna(v):
                    out.append(row(d, index_code, ft, cur, net_val=float(v) * 1e8))
        if new == 0 or (min_d and min_d < from_date):
            break
        page += 1
        time.sleep(0.15)
    return [r for r in out if r["date"] >= from_date]


def fetch_twse(_, index_code, cur, from_date, end):
    """BFI82U type=day: [單位名稱, 買進金額, 賣出金額, 買賣差額] (TWD)."""
    url = "https://www.twse.com.tw/rwd/zh/fund/BFI82U"
    out = []
    for d in bdays(from_date, end):
        j = None
        for attempt in range(3):
            try:
                r = requests.get(url, params={"type": "day", "dayDate": d.replace("-", ""), "response": "json"},
                                 headers={"User-Agent": UA}, timeout=30)
                j = r.json()
                break
            except Exception:
                time.sleep(5)
        if j and j.get("stat") == "OK":
            agg = {}
            for name, b, s, n in j["data"]:
                if name.startswith("外資"):
                    ft = "foreign"
                elif name.startswith("自營商"):
                    ft = "prop"
                elif name.startswith("投信"):
                    ft = "institution"
                else:
                    continue
                a = agg.setdefault(ft, [0.0, 0.0])
                a[0] += _num(b)
                a[1] += _num(s)
            for ft, (b, s) in agg.items():
                out.append(row(d, index_code, ft, cur, buy_val=b, sell_val=s, net_val=b - s))
        time.sleep(2)
    return out


SET_HTML = "https://www.set.or.th/en/market/index/set/overview"
SET_TYPES = {"foreign": "foreign", "institution": "institution", "proprietary": "prop", "individual": "individual"}


def fetch_set(sym, index_code, cur, from_date, end):
    s = _cffi_session()
    s.get(SET_HTML, timeout=40)
    H = {"Referer": SET_HTML, "Accept": "application/json"}
    out = []
    # 1) ngay hien tai (buy/sell/net)
    r = s.get(f"https://www.set.or.th/api/set/market/{sym}/investor-type", params={"lang": "en"},
              headers=H, timeout=40)
    if r.status_code == 200 and r.text.lstrip().startswith("{"):
        j = r.json()
        d = (j.get("asOfDate") or "")[:10]
        if d and j.get("totalValue"):
            for inv in j.get("investors", []):
                ft = SET_TYPES.get(inv.get("type"))
                if ft:
                    out.append(row(d, index_code, ft, cur, buy_val=inv.get("buyValue"),
                                   sell_val=inv.get("sellValue"), net_val=inv.get("netValue")))
    # 2) thang (net) 12 thang gan nhat
    r = s.get(f"https://www.set.or.th/api/set/market/{sym}/investor-type-chart", params={"period": "1Y"},
              headers=H, timeout=40)
    if r.status_code == 200 and r.text.lstrip().startswith("["):
        for x in r.json():
            d = x["date"][:7] + "-01"
            for k, ft in SET_TYPES.items():
                if x.get(k) is not None:
                    out.append(row(d, index_code, ft, cur, "M", net_val=x[k]))
    return [x for x in out if x["date"] >= from_date[:7] + "-01"]


def fetch_idx(_, index_code, cur, from_date, end):
    url = "https://www.idx.co.id/primary/TradingSummary/GetStockSummary"
    sess = _cffi_session()
    out, fails = [], 0
    for d in bdays(from_date, end):
        ok = False
        for attempt in range(4):
            try:
                r = sess.get(url, params={"date": d.replace("-", ""), "length": 9999, "start": 0}, timeout=60)
                if r.status_code == 200 and r.text.lstrip().startswith("{"):
                    data = r.json().get("data", [])
                    if data:
                        fb = fs = bv = sv = 0.0
                        for x in data:
                            vol = x.get("Volume") or 0
                            val = x.get("Value") or 0
                            vwap = (val / vol) if vol else (x.get("Close") or 0)
                            b = x.get("ForeignBuy") or 0
                            s_ = x.get("ForeignSell") or 0
                            bv += b
                            sv += s_
                            fb += b * vwap
                            fs += s_ * vwap
                        out.append(row(d, index_code, "foreign", cur, buy_val=fb, sell_val=fs, net_val=fb - fs,
                                       buy_vol=bv, sell_vol=sv, net_vol=bv - sv))
                    ok = True
                    break
                time.sleep(2 + 2 * attempt)
                sess = _cffi_session()
            except Exception:
                time.sleep(2 + 2 * attempt)
                sess = _cffi_session()
        if not ok:
            fails += 1
            log(f"    [idx] bo ngay {d}")
            if fails > 30:
                break
        else:
            fails = 0
        time.sleep(0.4)
    return out


BURSA_PDF = "https://www.bursamalaysia.com/misc/missftp/securities/securities_equities_trading_participation_investor_{d}.pdf"
BURSA_LABELS = ("Foreign Institutional", "Local Institutional", "Foreign Retail", "Local Retail", "Local Nominees")
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July",
                                      "August", "September", "October", "November", "December"], 1)}


def _bursa_parse(pdf_bytes):
    """Tra (yyyy-mm-01, {label: (buy_bn, sell_bn)}) tu bieu do 'buy value / sell value' (RM billion)."""
    import pypdf
    t = pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text() or ""
    mm = re.search(r"For (\w+) (\d{4})", t)
    if not mm:
        raise ValueError("khong thay thang")
    d = f"{mm.group(2)}-{MONTHS[mm.group(1)]:02d}-01"
    i = t.find("RM (billion)")
    j = t.find("buy value")
    nums = [float(x) for x in re.findall(r"\d+\.\d+", t[i:j])]
    labels = re.findall("|".join(BURSA_LABELS), t[:i])
    k = len(nums) // 2
    labs = labels[-k:]
    if k == 0 or len(labs) != k or len(nums) < 2 * k:
        raise ValueError("bieu do khong khop")
    return d, {lab: (nums[n], nums[k + n]) for n, lab in enumerate(labs)}


def fetch_bursa(_, index_code, cur, from_date, end):
    sess = _cffi_session()
    out = []
    cur_m = pd.Timestamp(from_date).to_period("M") + 1      # PDF thang M mo ta thang M-1
    end_m = pd.Timestamp(end).to_period("M")
    while cur_m <= end_m:
        for day in range(3, 15):
            ds = f"{cur_m.year}{cur_m.month:02d}{day:02d}"
            try:
                r = sess.get(BURSA_PDF.format(d=ds), timeout=40)
            except Exception:
                continue
            if r.status_code != 200 or r.content[:4] != b"%PDF":
                continue
            try:
                d, vals = _bursa_parse(r.content)
            except Exception as e:
                log(f"    [bursa] {ds}: {e}")
                break
            grp = {"foreign": ["Foreign Institutional", "Foreign Retail"],
                   "institution": ["Local Institutional"],
                   "individual": ["Local Retail", "Local Nominees"]}
            for ft, labs in grp.items():
                b = sum(vals[l][0] for l in labs if l in vals) * 1e9
                s_ = sum(vals[l][1] for l in labs if l in vals) * 1e9
                out.append(row(d, index_code, ft, cur, "M", buy_val=b, sell_val=s_, net_val=b - s_))
            break
        cur_m += 1
        time.sleep(0.3)
    # NGAY HIEN TAI (them 09/2026): trang market_statistic/securities nhung san JSON `data_vis_data`
    # -> daily_trade_participation = {as_of: "10 September 2026", data: [{title, buy_val, sell_val, net (RM mil)}]}.
    # Chi co 1 ngay/lan -> freq D boi dan (Cloudflare thinh thoang 403 -> thu lai voi session moi).
    try:
        out += _bursa_daily(index_code, cur)
    except Exception as e:
        log(f"    [bursa] daily: {repr(e)[:80]}")
    return out


BURSA_STAT_PAGE = "https://www.bursamalaysia.com/market_information/market_statistic/securities"


def _bursa_daily(index_code, cur):
    import json
    html = None
    for attempt in range(4):
        r = _cffi_session().get(BURSA_STAT_PAGE, timeout=60)
        if r.status_code == 200 and "data_vis_data" in r.text:
            html = r.text
            break
        time.sleep(3 + 3 * attempt)
    if html is None:
        return []
    m = re.search(r"data_vis_data\s*=\s*(\{.*?\});\s*\n", html, flags=re.S)
    if not m:
        return []
    j = json.loads(m.group(1))
    p = j.get("daily_trade_participation") or {}
    d = pd.to_datetime(p.get("as_of", ""), format="%d %B %Y", errors="coerce")
    if pd.isna(d):
        return []
    ds = d.strftime("%Y-%m-%d")
    grp = {"foreign": ["Foreign Institution", "Foreign Retail"], "institution": ["Local Institution"],
           "individual": ["Retail", "Local Retail", "Local Nominees"]}
    vals = {x.get("title", ""): (_num(x.get("buy_val")), _num(x.get("sell_val"))) for x in p.get("data", [])}
    out = []
    for ft, labs in grp.items():
        hit = [l for l in labs if l in vals]
        if not hit:
            continue
        b = sum(vals[l][0] for l in hit) * 1e6
        s_ = sum(vals[l][1] for l in hit) * 1e6
        out.append(row(ds, index_code, ft, cur, "D", buy_val=b, sell_val=s_, net_val=b - s_))
    return out


REGION_FETCH = {"naver": fetch_naver, "twse": fetch_twse, "set": fetch_set, "idx": fetch_idx, "bursa": fetch_bursa}


# =====================================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="Keo lai toan bo lich su")
    ap.add_argument("--only", default="", help="Chi keo cac index_code (phay)")
    ap.add_argument("--vn-only", action="store_true")
    ap.add_argument("--region-only", action="store_true")
    args = ap.parse_args()
    only = {c.strip().upper() for c in args.only.split(",") if c.strip()}

    old = None
    if os.path.exists(MASTER):
        old = pd.read_csv(MASTER, dtype={"date": str, "currency": str, "freq": str})
        for c in COLS:
            if c not in old.columns:
                old[c] = float("nan") if c in NUM_COLS else ""
        old["currency"] = old["currency"].fillna("").replace("nan", "")
        old["freq"] = old["freq"].fillna("").replace("nan", "")
        old.loc[old["index_code"].isin(CODES) & (old["currency"] == ""), "currency"] = "VND"
        old.loc[old["freq"] == "", "freq"] = "D"

    full = args.full or old is None or old.empty
    today = datetime.now().strftime("%Y-%m-%d")
    log(f"=== Che do: {'FULL' if full else 'INCREMENTAL'} | den {today}"
        + (f" | only={sorted(only)}" if only else "") + " ===")

    def from_for(index_code, flow_type=None, default=None):
        if full or old is None or old.empty:
            return default
        sub = old[old["index_code"] == index_code]
        if flow_type:
            sub = sub[sub["flow_type"] == flow_type]
        if sub.empty:
            return default
        return (pd.to_datetime(sub["date"]).max() - timedelta(days=BUFFER_DAYS)).strftime("%Y-%m-%d")

    frames = []
    # ---- VN ----
    if not args.region_only:
        for index_code, code_vnd in CODES.items():
            if only and index_code not in only:
                continue
            for flow_type, fn in (("foreign", fetch_foreign), ("prop", fetch_prop)):
                from_date = from_for(index_code, flow_type, None)
                try:
                    got = fn(code_vnd, index_code, from_date)
                    log(f"  {index_code:9} {flow_type:8} tu {from_date or 'dau'} -> {len(got)} dong")
                    if got:
                        frames.append(pd.DataFrame(got))
                except Exception as e:
                    log(f"  {index_code:9} {flow_type:8} [LOI] {repr(e)[:120]}")
                time.sleep(SLEEP)
    # ---- KHU VUC ----
    if not args.vn_only:
        for index_code, (src, sym, cur) in REGION.items():
            if only and index_code not in only:
                continue
            from_date = from_for(index_code, None, REGION_FULL_START) or REGION_FULL_START
            floor = SOURCE_FLOOR.get(src)
            if floor and from_date < floor:
                from_date = floor
            t0 = time.time()
            try:
                got = REGION_FETCH[src](sym, index_code, cur, from_date, today)
                log(f"  {index_code:9} {src:8} tu {from_date} -> {len(got)} dong [{time.time() - t0:.0f}s]")
                if got:
                    frames.append(pd.DataFrame(got))
            except Exception as e:
                log(f"  {index_code:9} {src:8} [LOI] {repr(e)[:140]}")

    if not frames:
        log("Khong keo duoc dong nao. Giu nguyen master.")
        return

    for f in frames:
        for c in NUM_COLS:
            f[c] = pd.to_numeric(f[c], errors="coerce")
    new = pd.concat(frames, ignore_index=True)
    if old is not None and not old.empty:
        for c in NUM_COLS:
            old[c] = pd.to_numeric(old[c], errors="coerce")
        if args.full and only:
            old = old[~old["index_code"].isin(only)]
        elif args.full and not only:
            old = old.iloc[0:0]
        combined = pd.concat([old[COLS], new[COLS]], ignore_index=True)
    else:
        combined = new[COLS]

    before = len(combined)
    combined = combined.drop_duplicates(subset=["date", "index_code", "flow_type"], keep="last")
    combined = combined.dropna(subset=["date"])
    combined = combined.sort_values(["index_code", "flow_type", "date"]).reset_index(drop=True)

    old_n = 0 if old is None else len(old)
    log(f"--- Tong dong: {len(combined)} (truoc {old_n}, +{len(combined) - old_n}, bo {before - len(combined)} trung) ---")
    for i in range(3):
        try:
            combined.to_csv(MASTER, index=False, encoding="utf-8-sig")
            break
        except PermissionError:
            time.sleep(5)
    else:
        combined.to_csv(MASTER.replace(".csv", ".pending.csv"), index=False, encoding="utf-8-sig")
        log("  [!] master dang bi khoa -> ghi pending")
    log(f"Da luu: {MASTER}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
