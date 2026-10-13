# -*- coding: utf-8 -*-
r"""bctc_scan.py — QUÉT BÁO CÁO TÀI CHÍNH MỚI CÔNG BỐ của toàn bộ mã HOSE/HNX/UPCOM (13/10/2026).

Nguồn chính CafeF (FileBCTC.ashx theo từng mã, ~1 phút toàn thị trường với 6 luồng), dự phòng Vietstock (data/GetDocument).
Khảo sát nguồn + endpoint: NGUON.md. Kết quả long-format, 1 dòng = 1 file BCTC:
    id, nguon, symbol, exchange, ten_dn, ky (2026Q3 | 2026H1 | 2025FY), loai (quy|soat_xet|kiem_toan|khac),
    pham_vi (hop_nhat|rieng|cong_ty_me|khong_ro), ngay_cong_bo, gio_dang, nam, quy, tieu_de, url_pdf, url_nguon, ngay_quet
    -> data\bctc_congbo.csv (UTF-8 BOM, append theo khoá id) + data\bctc_congbo_latest.parquet (bản đầy đủ)

    python bctc_scan.py                      # tăng dần: từ (ngày cuối trong CSV − 7) tới nay, tối đa --days 30
    python bctc_scan.py --full               # lần đầu: 400 ngày
    python bctc_scan.py --days 60 --symbols FPT,VNM
    python bctc_scan.py --source vietstock   # dự phòng (hoặc both)
    python bctc_scan.py --download           # tải PDF về pdf\<ma>\ (mặc định KHÔNG tải)
Danh sách mã: MD_ROOT\index-fetcher\raw\vn_screener_meta.csv (có sàn) + tên DN từ raw\vn_icb_vci.csv; thiếu -> realtime-lab\symbols.txt.
Lịch sự với nguồn: 6 luồng, nghỉ 0,05 s/request, 429/5xx chờ tăng dần, thử lại 4 lần. Log: logs\bctc_scan.log.
Dòng in ra khớp regex runner: "Che do|Tong|Da luu|LOI|-> |! ".
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import logging
import os
import re
import sys
import threading
import time
import urllib.parse

import pandas as pd

try:
    from curl_cffi import requests as cr
    HAS_CURL = True
except ImportError:                                  # pragma: no cover
    import requests as cr                            # type: ignore
    HAS_CURL = False

HERE = os.path.dirname(os.path.abspath(__file__))
MD_ROOT = os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data"))
DATA = os.path.join(HERE, "data")
PDF_DIR = os.path.join(HERE, "pdf")
LOG_DIR = os.path.join(HERE, "logs")
CSV = os.path.join(DATA, "bctc_congbo.csv")
PQ = os.path.join(DATA, "bctc_congbo_latest.parquet")
VN_TZ = dt.timezone(dt.timedelta(hours=7))
COLS = ["id", "nguon", "symbol", "exchange", "ten_dn", "ky", "loai", "pham_vi", "ngay_cong_bo", "gio_dang", "nam", "quy",
        "tieu_de", "url_pdf", "url_nguon", "ngay_quet"]

CAFEF = "https://cafef.vn/du-lieu/Ajax/PageNew/FileBCTC.ashx"
VS_DOC = "https://finance.vietstock.vn/data/GetDocument"
VS_PAGE = "https://finance.vietstock.vn/{sym}/tai-lieu.htm"
SLEEP = 0.05
_TLS = threading.local()
_LOCK = threading.Lock()
STATS = {"req": 0, "retry": 0, "err": 0}

for d in (DATA, LOG_DIR):
    os.makedirs(d, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.FileHandler(os.path.join(LOG_DIR, "bctc_scan.log"), encoding="utf-8"),
                              logging.StreamHandler(sys.stdout)])
log = logging.getLogger("bctc_scan")


# ------------------------------------------------------------------------------------------------ mạng
def _sess():
    """1 session curl_cffi (bắt tay TLS như Chrome) cho mỗi luồng."""
    s = getattr(_TLS, "s", None)
    if s is None:
        s = cr.Session(impersonate="chrome") if HAS_CURL else cr.Session()
        _TLS.s = s
    return s


def _get(url, params, headers, tries=4, post=False, **kw):
    """GET/POST với thử lại: 429/503/5xx hoặc lỗi mạng -> chờ 3·i giây. Trả Response hoặc ném RuntimeError."""
    last = None
    for i in range(tries):
        try:
            with _LOCK:
                STATS["req"] += 1
            s = _sess()
            r = (s.post(url, data=params, headers=headers, timeout=40, **kw) if post
                 else s.get(url, params=params, headers=headers, timeout=40, **kw))
            if r.status_code in (429, 503) or r.status_code >= 500:
                last = RuntimeError(f"HTTP {r.status_code}")
                with _LOCK:
                    STATS["retry"] += 1
                time.sleep(3.0 * (i + 1))
                continue
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            time.sleep(SLEEP)
            return r
        except Exception as e:                       # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{type(last).__name__}: {str(last)[:100]}")


# ------------------------------------------------------------------------------------------------ phân loại
def oid_time(oid: str):
    """Mongo ObjectId -> Timestamp giờ VN (4 byte đầu = Unix time). Không phải ObjectId -> NaT."""
    try:
        return pd.Timestamp(int(str(oid)[:8], 16), unit="s", tz="UTC").tz_convert(VN_TZ).tz_localize(None)
    except Exception:                                # noqa: BLE001
        return pd.NaT


def ms_date(v):
    """'/Date(1787371890290)/' -> Timestamp giờ VN."""
    try:
        ms = int(re.search(r"-?\d+", str(v)).group(0))
        return pd.Timestamp(ms, unit="ms", tz="UTC").tz_convert(VN_TZ).tz_localize(None)
    except Exception:                                # noqa: BLE001
        return pd.NaT


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def pham_vi_of(name: str) -> str:
    n = _norm(name)
    if "hợp nhất" in n or "hop nhat" in n:
        return "hop_nhat"
    if "công ty mẹ" in n or "cong ty me" in n:
        return "cong_ty_me"
    if "riêng" in n or "rieng" in n:
        return "rieng"
    return "khong_ro"


def loai_of(name: str, quarter=None) -> str:
    n = _norm(name)
    if "kiểm toán" in n or "kiem toan" in n:
        return "kiem_toan"
    if "soát xét" in n or "soat xet" in n:
        return "soat_xet"
    if quarter == 5 and ("năm" in n or "nam" in n):
        return "kiem_toan"                            # CafeF: Quarter 5 = cả năm; không ghi "kiểm toán" vẫn là BCTC năm
    if "quý" in n or "quy " in n or quarter in (1, 2, 3, 4):
        return "quy"
    if "6 tháng" in n or "bán niên" in n or "giữa niên độ" in n:
        return "soat_xet"
    return "khac"


def ky_cafef(name: str, quarter, year, loai: str) -> str:
    try:
        q, y = int(quarter), int(year)
    except Exception:                                # noqa: BLE001
        return ""
    n = _norm(name)
    if q == 5 or loai == "kiem_toan":
        return f"{y}FY"
    if q == 2 and (loai == "soat_xet" or "6 tháng" in n or "bán niên" in n):
        return f"{y}H1"
    if q in (1, 2, 3, 4):
        return f"{y}Q{q}"
    return str(y)


def ky_vietstock(title: str) -> tuple[str, str]:
    """'BCTC Hợp nhất Soát xét 6 tháng đầu năm 2026' -> ('2026H1', 'soat_xet'); 'BCTC quý 2 năm 2026' -> ('2026Q2', 'quy')."""
    n = _norm(title)
    loai = loai_of(title)
    m = re.search(r"quý\s*(\d)\D{0,12}(20\d{2})", n)
    if m:
        if m.group(1) == "2" and loai == "soat_xet":      # "Soát xét quý 2" = soát xét bán niên
            return f"{m.group(2)}H1", loai
        return f"{m.group(2)}Q{m.group(1)}", loai
    m = re.search(r"(?:6 tháng|bán niên|giữa niên độ)\D{0,20}(20\d{2})", n)
    if m:
        return f"{m.group(1)}H1", "soat_xet" if loai in ("khac", "quy") else loai
    m = re.search(r"(?:9 tháng)\D{0,20}(20\d{2})", n)
    if m:
        return f"{m.group(1)}Q3", loai
    m = re.search(r"năm\s*(20\d{2})", n)
    if m:
        return f"{m.group(1)}FY", "kiem_toan" if loai in ("khac", "quy") else loai
    m = re.search(r"(20\d{2})", n)
    return (m.group(1) if m else ""), loai


# ------------------------------------------------------------------------------------------------ nguồn
def cafef_rows(sym: str, years: list[int], since: pd.Timestamp, meta: dict) -> list[dict]:
    hdr = {"Referer": f"https://cafef.vn/du-lieu/hose/{sym.lower()}-tai-lieu.chn", "X-Requested-With": "XMLHttpRequest",
           "Accept": "application/json, text/javascript, */*; q=0.01"}
    out, seen = [], set()
    for y in years:
        r = _get(CAFEF, {"Symbol": sym.lower(), "Type": 1, "Year": y}, hdr)
        txt = r.text.strip()
        if not txt.startswith("{"):
            continue                                  # "symbol is empty" / HTML
        j = r.json()
        data = (j.get("Data") or []) if isinstance(j, dict) else []
        for x in data:
            oid = str(x.get("id") or "")
            if not oid or oid in seen:
                continue
            seen.add(oid)
            ts = oid_time(oid)
            if pd.isna(ts) or ts < since:
                continue
            name = str(x.get("Name") or "").strip()
            loai = loai_of(name, x.get("Quarter"))
            out.append({"id": f"cafef:{oid}", "nguon": "cafef", "symbol": sym, "exchange": meta.get("exchange", ""),
                        "ten_dn": meta.get("ten", ""), "ky": ky_cafef(name, x.get("Quarter"), x.get("Year"), loai),
                        "loai": loai, "pham_vi": pham_vi_of(name), "ngay_cong_bo": ts.normalize(), "gio_dang": f"{ts:%H:%M}",
                        "nam": x.get("Year"), "quy": x.get("Quarter"), "tieu_de": name, "url_pdf": str(x.get("Link") or ""),
                        "url_nguon": f"https://cafef.vn/du-lieu/hose/{sym.lower()}-tai-lieu.chn"})
    return out


_VS = {"tok": "", "sess": None, "t": 0.0}


def _vs_token():
    """Token + cookie Vietstock dùng chung (làm mới sau 20 phút)."""
    with _LOCK:
        if _VS["sess"] is None or time.time() - _VS["t"] > 1200:
            s = cr.Session(impersonate="chrome") if HAS_CURL else cr.Session()
            r = s.get(VS_PAGE.format(sym="FPT"), timeout=40)
            m = re.search(r'__RequestVerificationToken[^>]*?value=["\']?([A-Za-z0-9_\-]{20,})', r.text)
            _VS.update(tok=m.group(1) if m else "", sess=s, t=time.time())
            if not _VS["tok"]:
                raise RuntimeError("Vietstock: không lấy được __RequestVerificationToken")
        return _VS["sess"], _VS["tok"]


def vietstock_rows(sym: str, since: pd.Timestamp, meta: dict) -> list[dict]:
    s, tok = _vs_token()
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": VS_PAGE.format(sym=sym)}
    out, page = [], 1
    while page <= 20:
        last = None
        for i in range(4):
            try:
                with _LOCK:
                    STATS["req"] += 1
                r = s.post(VS_DOC, data={"code": sym, "type": 1, "page": page, "pageSize": 50, "__RequestVerificationToken": tok},
                           headers=hdr, timeout=40)
                if r.status_code in (429, 503) or r.status_code >= 500:
                    time.sleep(3.0 * (i + 1))
                    continue
                txt = r.text.strip()
                if not txt.startswith("["):
                    raise RuntimeError("Vietstock trả HTML (token/cookie hết hạn?)")
                lst = r.json()
                last = None
                break
            except Exception as e:                   # noqa: BLE001
                last = e
                time.sleep(1.5 * (i + 1))
        if last is not None:
            raise RuntimeError(str(last)[:100])
        time.sleep(SLEEP)
        if not lst:
            break
        stop = False
        for x in lst:
            ts = ms_date(x.get("LastUpdate"))
            if pd.isna(ts):
                continue
            if ts < since:
                stop = True
                continue
            title = str(x.get("FullName") or x.get("Title") or "").strip()
            ky, loai = ky_vietstock(title)
            url = str(x.get("Url") or "")
            ex = meta.get("exchange") or (re.search(r"/data/(HOSE|HNX|UPCOM)/", url) or [None, ""])[1]
            out.append({"id": f"vietstock:{x.get('FileInfoID')}", "nguon": "vietstock", "symbol": sym, "exchange": ex,
                        "ten_dn": meta.get("ten", ""), "ky": ky, "loai": loai, "pham_vi": pham_vi_of(title),
                        "ngay_cong_bo": ts.normalize(), "gio_dang": f"{ts:%H:%M}", "nam": ky[:4] if ky else None,
                        "quy": (ky[5:] if len(ky) > 4 else ""), "tieu_de": title, "url_pdf": url, "url_nguon": VS_PAGE.format(sym=sym)})
        if stop or len(lst) < 50:
            break
        page += 1
    return out


# ------------------------------------------------------------------------------------------------ danh sách mã
def universe(symbols: list[str] | None = None) -> dict[str, dict]:
    """{symbol: {exchange, ten}} từ vn_screener_meta.csv (sàn) + vn_icb_vci.csv (tên); không có file -> symbols.txt."""
    meta: dict[str, dict] = {}
    p = os.path.join(MD_ROOT, "index-fetcher", "raw", "vn_screener_meta.csv")
    if os.path.exists(p):
        m = pd.read_csv(p, usecols=["name", "exchange"]).dropna(subset=["name"])
        for n, ex in zip(m["name"], m["exchange"]):
            n = str(n).strip().upper()
            if re.fullmatch(r"[A-Z0-9]{3}", n):
                meta[n] = {"exchange": str(ex).upper() if pd.notna(ex) else "", "ten": ""}
    p = os.path.join(MD_ROOT, "index-fetcher", "raw", "vn_icb_vci.csv")
    if os.path.exists(p):
        icb = pd.read_csv(p, usecols=["code", "floor", "ten"]).dropna(subset=["code"])
        for c, fl, ten in zip(icb["code"], icb["floor"], icb["ten"]):
            c = str(c).strip().upper()
            if c in meta:
                meta[c]["ten"] = str(ten) if pd.notna(ten) else ""
            elif re.fullmatch(r"[A-Z0-9]{3}", c) and str(fl).upper() in ("HOSE", "HNX", "UPCOM"):
                meta[c] = {"exchange": str(fl).upper(), "ten": str(ten) if pd.notna(ten) else ""}
    if not meta:
        p = os.path.join(MD_ROOT, "realtime-lab", "symbols.txt")
        if os.path.exists(p):
            for ln in open(p, encoding="utf-8"):
                ln = ln.strip().upper()
                if re.fullmatch(r"[A-Z0-9]{3}", ln):
                    meta[ln] = {"exchange": "", "ten": ""}
    if symbols:
        return {s: meta.get(s, {"exchange": "", "ten": ""}) for s in symbols}
    return dict(sorted(meta.items()))


# ------------------------------------------------------------------------------------------------ lưu
def read_old() -> pd.DataFrame:
    if not os.path.exists(CSV):
        return pd.DataFrame(columns=COLS)
    d = pd.read_csv(CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    for c in COLS:
        if c not in d.columns:
            d[c] = ""
    d["ngay_cong_bo"] = pd.to_datetime(d["ngay_cong_bo"], errors="coerce")
    return d[COLS]


def save(all_df: pd.DataFrame) -> None:
    d = all_df.copy()
    d["ngay_cong_bo"] = pd.to_datetime(d["ngay_cong_bo"], errors="coerce")
    d = d.drop_duplicates("id", keep="last").sort_values(["ngay_cong_bo", "symbol", "id"], ascending=[False, True, True])
    out = d.copy()
    out["ngay_cong_bo"] = out["ngay_cong_bo"].dt.strftime("%Y-%m-%d")
    tmp = CSV + ".tmp"
    out[COLS].to_csv(tmp, index=False, encoding="utf-8-sig")
    os.replace(tmp, CSV)
    try:
        pq = d[COLS].copy()
        for c in ("nam", "quy"):
            pq[c] = pq[c].astype(str)
        pq.to_parquet(PQ, index=False)
    except Exception as e:                           # noqa: BLE001
        log.warning("! parquet: %s", e)


def download_pdfs(df: pd.DataFrame) -> int:
    n = 0
    for _, r in df.iterrows():
        url = str(r["url_pdf"] or "")
        if not url.startswith("http"):
            continue
        d = os.path.join(PDF_DIR, str(r["symbol"]))
        os.makedirs(d, exist_ok=True)
        base = urllib.parse.unquote(os.path.basename(urllib.parse.urlsplit(url).path)) or f"{r['id']}.pdf"
        base = re.sub(r'[\\/:*?"<>|]', "_", base)[:150]
        path = os.path.join(d, base)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            continue
        try:
            resp = _get(url, None, {"Referer": str(r["url_nguon"])})
            with open(path, "wb") as f:
                f.write(resp.content)
            n += 1
        except Exception as e:                       # noqa: BLE001
            log.warning("! tải %s %s: %s", r["symbol"], base[:40], e)
    return n


# ------------------------------------------------------------------------------------------------ chính
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Quét BCTC mới công bố toàn thị trường (CafeF / Vietstock).")
    ap.add_argument("--full", action="store_true", help="lần đầu: 400 ngày, không dùng mốc tăng dần")
    ap.add_argument("--days", type=int, default=30, help="số ngày gần nhất (mặc định 30; --full = 400)")
    ap.add_argument("--symbols", default="", help="chỉ các mã này, cách nhau bởi dấu phẩy")
    ap.add_argument("--source", choices=["cafef", "vietstock", "both"], default="cafef")
    ap.add_argument("--download", action="store_true", help="tải PDF về pdf\\<ma>\\")
    ap.add_argument("--threads", type=int, default=6)
    a = ap.parse_args(argv)

    today = pd.Timestamp(dt.datetime.now(VN_TZ).date())
    days = 400 if a.full else a.days
    since = today - pd.Timedelta(days=days)
    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()] or None
    old = read_old()
    if not a.full and not syms and len(old) and old["ngay_cong_bo"].notna().any():
        since = max(since, old["ngay_cong_bo"].max().normalize() - pd.Timedelta(days=7))
    uni = universe(syms)
    years = sorted({y for y in range(since.year - (1 if since.month <= 4 else 0), today.year + 1)})
    log.info("Che do: %s | nguon %s | tu %s (%d ngay) | %d ma | nam CafeF %s | %d luong | curl_cffi=%s | da co %d dong",
             "FULL" if a.full else "tang dan", a.source, since.date(), (today - since).days, len(uni), years, a.threads, HAS_CURL, len(old))

    rows, errs = [], []
    t0 = time.time()

    def work(sym):
        meta = uni[sym]
        got, e_c, e_v = [], None, None
        if a.source in ("cafef", "both"):
            try:
                got += cafef_rows(sym, years, since, meta)
            except Exception as e:                   # noqa: BLE001
                e_c = f"{sym} cafef: {e}"
        if a.source in ("vietstock", "both") or (a.source == "cafef" and e_c):
            try:
                got += vietstock_rows(sym, since, meta)
            except Exception as e:                   # noqa: BLE001
                e_v = f"{sym} vietstock: {e}"
        return sym, got, [x for x in (e_c, e_v) if x]

    done = 0
    with cf.ThreadPoolExecutor(max_workers=max(1, a.threads)) as ex:
        for sym, got, es in ex.map(work, list(uni)):
            rows += got
            errs += es
            done += 1
            if done % 200 == 0:
                log.info("-> %d/%d ma, %d dong, %.0fs", done, len(uni), len(rows), time.time() - t0)
    for e in errs[:20]:
        log.warning("! %s", e)
    if len(errs) > 20:
        log.warning("! ... tong %d ma loi", len(errs))

    new = pd.DataFrame(rows, columns=COLS[:-1]) if rows else pd.DataFrame(columns=COLS[:-1])
    new["ngay_quet"] = f"{today:%Y-%m-%d}"
    old_ids = set(old["id"]) if len(old) else set()
    them = new[~new["id"].isin(old_ids)]
    all_df = pd.concat([old, new], ignore_index=True) if len(old) else new
    save(all_df)
    n_dn = new["symbol"].nunique() if len(new) else 0
    log.info("Tong: %d dong trong cua so (%d DN), %d dong MOI so voi CSV; %d request, %d retry, %d ma loi; %.0fs",
             len(new), n_dn, len(them), STATS["req"], STATS["retry"], len(errs), time.time() - t0)
    if len(new):
        ky = new.groupby("ky")["symbol"].nunique().sort_index(ascending=False).head(8)
        log.info("Tong theo ky (so DN): %s", "; ".join(f"{k}={v}" for k, v in ky.items()))
        lo = new.groupby(["loai", "pham_vi"]).size()
        log.info("Tong theo loai/pham vi: %s", "; ".join(f"{k[0]}/{k[1]}={v}" for k, v in lo.items()))
    log.info("Da luu %s (%d dong) + %s", CSV, len(all_df.drop_duplicates('id')), os.path.basename(PQ))
    if a.download and len(them):
        n = download_pdfs(them)
        log.info("Da luu %d PDF vao %s", n, PDF_DIR)
    if len(uni) and len(errs) > len(uni) * 0.5:
        log.error("LOI: hon 50%% ma loi (%d/%d) - nguon co the chan", len(errs), len(uni))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
