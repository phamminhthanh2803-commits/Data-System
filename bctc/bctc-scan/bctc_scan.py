# -*- coding: utf-8 -*-
r"""bctc_scan.py — QUÉT BÁO CÁO TÀI CHÍNH MỚI CÔNG BỐ của toàn bộ mã HOSE/HNX/UPCOM (13/10/2026).

3 nguồn chạy song song và GỘP: CafeF (FileBCTC.ashx theo từng mã) + Vietstock (data/GetDocument) + HOSE chính thức
(api.hsx.vn mediafiles/5/{secOrgId}, chỉ mã HOSE). Khảo sát nguồn + endpoint: NGUON.md. Kết quả long-format, 1 dòng = 1 BCTC:
    id, nguon, symbol, exchange, ten_dn, ky (2026Q3 | 2026H1 | 2025FY), loai (quy|soat_xet|kiem_toan|khac),
    pham_vi (hop_nhat|rieng|cong_ty_me|khong_ro), ngay_cong_bo, gio_dang, nam, quy, tieu_de, url_pdf, url_nguon, ngay_quet,
    nguon_khac (các nguồn khác cũng có file này, cách nhau dấu phẩy), url_pdf_khac (link PDF tương ứng, cách nhau dấu |)
    -> data\bctc_congbo.csv (UTF-8 BOM) + data\bctc_congbo_latest.parquet (bản đầy đủ)
GỘP theo khoá (symbol, ky, loai, pham_vi): giữ 1 dòng có ngay_cong_bo/gio_dang SỚM NHẤT (nguon + url_pdf + id của nguồn đó);
dữ liệu cũ trong CSV cũng gộp theo cùng quy tắc (khoá trùng -> giữ ngày sớm nhất, cập nhật nguon_khac).

    python bctc_scan.py                      # tăng dần: từ (ngày cuối trong CSV − 7) tới nay, tối đa --days 30, --source all
    python bctc_scan.py --full               # lần đầu / dựng lại: 400 ngày
    python bctc_scan.py --days 60 --symbols FPT,VNM
    python bctc_scan.py --source cafef       # 1 nguồn (cafef | vietstock | hose | both = cafef+vietstock | all)
    python bctc_scan.py --download           # tải PDF về pdf\<ma>\ (mặc định KHÔNG tải)
Danh sách mã: MD_ROOT\index-fetcher\raw\vn_screener_meta.csv (có sàn) + tên DN từ raw\vn_icb_vci.csv; thiếu -> realtime-lab\symbols.txt.
HOSE cần map mã -> secOrgId: data\hose_secorg.csv, tự bổ sung từ chi tiết tin CBTT (news/cate -> news/{id}.relatedId);
mã không map được (không có CBTT nào 400 ngày) ghi sec_org_id rỗng + ngay_kiem_tra, 30 ngày sau mới thử lại.
Lịch sự với nguồn: 6 luồng, nghỉ 0,05 s/request, 429/5xx chờ tăng dần, thử lại 4 lần. Nguồn lỗi liên tiếp (chặn IP, timeout)
-> tắt nguồn đó cho phần còn lại, các nguồn khác vẫn chạy. Log: logs\bctc_scan.log.
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
import unicodedata
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
SECORG_CSV = os.path.join(DATA, "hose_secorg.csv")
VN_TZ = dt.timezone(dt.timedelta(hours=7))
COLS = ["id", "nguon", "symbol", "exchange", "ten_dn", "ky", "loai", "pham_vi", "ngay_cong_bo", "gio_dang", "nam", "quy",
        "tieu_de", "url_pdf", "url_nguon", "ngay_quet", "nguon_khac", "url_pdf_khac"]
KEY = ["symbol", "ky", "loai", "pham_vi"]
SRC_ORDER = {"cafef": 0, "vietstock": 1, "hose": 2}

CAFEF = "https://cafef.vn/du-lieu/Ajax/PageNew/FileBCTC.ashx"
VS_DOC = "https://finance.vietstock.vn/data/GetDocument"
VS_PAGE = "https://finance.vietstock.vn/{sym}/tai-lieu.htm"
HSX_NEWS = "https://api.hsx.vn/n/api/v1/1/news/cate"
HSX_NEWS_ID = "https://api.hsx.vn/n/api/v1/1/news/{id}"
HSX_FILES = "https://api.hsx.vn/m/api/v1/1/mediafiles/5/{org}"
HSX_STATIC = "https://staticfile.hsx.vn/"
HSX_PAGE = "https://www.hsx.vn/vi/tin-tuc/tin-to-chuc-niem-yet"
HSX_HDR = {"Origin": "https://www.hsx.vn", "Referer": "https://www.hsx.vn/", "Accept": "application/json, text/plain, */*"}
SLEEP = 0.05
_TLS = threading.local()
_LOCK = threading.Lock()
STATS = {"req": 0, "retry": 0, "err": 0}
# sức khoẻ từng nguồn: >=12 mã lỗi liên tiếp mà chưa mã nào thành công -> tắt nguồn (chặn IP / timeout), nguồn khác vẫn chạy
SRC = {s: {"ok": 0, "err": 0, "down": False} for s in SRC_ORDER}

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


def _src_ok(src: str) -> None:
    with _LOCK:
        SRC[src]["ok"] += 1


def _src_fail(src: str) -> None:
    with _LOCK:
        SRC[src]["err"] += 1
        if not SRC[src]["down"] and SRC[src]["ok"] == 0 and SRC[src]["err"] >= 12:
            SRC[src]["down"] = True
            log.warning("! nguon %s: %d ma loi lien tiep, chua ma nao thanh cong -> TAT nguon nay (chan IP / timeout?)", src, SRC[src]["err"])


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


def unix_time(v):
    """Unix giây (HOSE createdDate) -> Timestamp giờ VN."""
    try:
        return pd.Timestamp(int(v), unit="s", tz="UTC").tz_convert(VN_TZ).tz_localize(None)
    except Exception:                                # noqa: BLE001
        return pd.NaT


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _ascii(s: str) -> str:
    """Bỏ dấu tiếng Việt + về chữ thường, gom khoảng trắng: 'Hợp Nhất Q2' -> 'hop nhat q2'."""
    s = unicodedata.normalize("NFD", str(s or "")).replace("đ", "d").replace("Đ", "D")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def pham_vi_of(name: str) -> str:
    n = _norm(name)
    if "hợp nhất" in n or "hop nhat" in n:
        return "hop_nhat"
    if "công ty mẹ" in n or "cong ty me" in n:
        return "cong_ty_me"
    if "riêng" in n or "rieng" in n:
        return "rieng"
    return "khong_ro"


def pham_vi_hose(file_name: str) -> str:
    """Phạm vi từ tên file HOSE: 'BCTC HN KT 2022', 'Bao Cao Tai Chinh Hop Nhat Q2', 'BCTC cty me SX ban nien', 'BCTC Rieng Q2'."""
    n = _ascii(re.sub(r"\.[a-z0-9]{2,4}$", "", str(file_name or ""), flags=re.I))
    n = re.sub(r"[_\-\.\(\)\[\],]+", " ", n)
    if re.search(r"hop ?nhat|\bhn\b|\bhopnhat\b", n):
        return "hop_nhat"
    if re.search(r"cong ?ty ?me|\bctm\b|\bcty ?me\b|\bme\b|\bc ?ty ?me\b", n):
        return "cong_ty_me"
    if re.search(r"\brieng\b|\briengle\b|\briêng\b", n):
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


def ky_hose(typ: str, tm: str, file_name: str = "") -> tuple[str, str]:
    """HOSE mediafiles: (type 'Quý', time '02.2026') -> ('2026Q2','quy'); ('Bán niên','2025') -> ('2025H1','soat_xet');
    ('Năm','2024') -> ('2024FY','kiem_toan'). Tên file 'giai trinh' / 'cong van' / 'thong bao' -> loai 'khac' (không phải BCTC)."""
    t = _ascii(typ)
    m = re.search(r"(\d{1,2})\s*[\./\-]\s*(20\d{2})", str(tm or ""))
    y = m.group(2) if m else (re.search(r"20\d{2}", str(tm or "")) or [""])[0]
    if "quy" in t:
        q = int(m.group(1)) if m else 0
        ky, loai = (f"{y}Q{q}", "quy") if 1 <= q <= 4 and y else ((f"{y}FY", "kiem_toan") if y else ("", "khac"))
    elif "ban nien" in t or "6 thang" in t:
        ky, loai = (f"{y}H1", "soat_xet") if y else ("", "khac")
    elif "nam" in t:
        ky, loai = (f"{y}FY", "kiem_toan") if y else ("", "khac")
    else:
        ky, loai = (y or ""), "khac"
    fn = _ascii(file_name)
    if re.search(r"giai ?trinh|cong ?van|thong ?bao|bao ?cao ?thuong ?nien|bctn", fn) and not re.search(r"bctc|bao ?cao ?tai ?chinh", fn):
        loai = "khac"
    return ky, loai


# ------------------------------------------------------------------------------------------------ nguồn CafeF
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


# ------------------------------------------------------------------------------------------------ nguồn Vietstock
_VS = {"tok": "", "cookies": None, "t": 0.0}


def _vs_token():
    """Token + cookie Vietstock dùng chung mọi luồng (làm mới sau 20 phút hoặc khi server trả HTML)."""
    with _LOCK:
        if _VS["cookies"] is None or time.time() - _VS["t"] > 1200:
            s = cr.Session(impersonate="chrome") if HAS_CURL else cr.Session()
            r = s.get(VS_PAGE.format(sym="FPT"), timeout=40)
            m = re.search(r'__RequestVerificationToken[^>]*?value=["\']?([A-Za-z0-9_\-]{20,})', r.text)
            ck = s.cookies.get_dict() if hasattr(s.cookies, "get_dict") else dict(s.cookies)
            _VS.update(tok=m.group(1) if m else "", cookies=ck, t=time.time())
            if not _VS["tok"]:
                _VS["cookies"] = None
                raise RuntimeError("Vietstock: không lấy được __RequestVerificationToken")
        return _VS["cookies"], _VS["tok"]


def vietstock_rows(sym: str, since: pd.Timestamp, meta: dict) -> list[dict]:
    ck, tok = _vs_token()
    s = _sess()
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": VS_PAGE.format(sym=sym)}
    out, page = [], 1
    while page <= 20:
        last = None
        for i in range(4):
            try:
                with _LOCK:
                    STATS["req"] += 1
                r = s.post(VS_DOC, data={"code": sym, "type": 1, "page": page, "pageSize": 50, "__RequestVerificationToken": tok},
                           headers=hdr, cookies=ck, timeout=40)
                if r.status_code in (429, 503) or r.status_code >= 500:
                    time.sleep(3.0 * (i + 1))
                    continue
                txt = r.text.strip()
                if not txt.startswith("["):
                    with _LOCK:
                        _VS["t"] = 0.0                # ép lấy token mới ở lần gọi sau
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


# ------------------------------------------------------------------------------------------------ nguồn HOSE
_SECORG_MISS: dict[str, str] = {}      # mã HOSE không tìm thấy CBTT nào trong 400 ngày -> ngày kiểm tra (thử lại sau 30 ngày)


def load_secorg() -> dict[str, int]:
    """data\\hose_secorg.csv (symbol, sec_org_id, ten, ngay_kiem_tra) -> {symbol: secOrgId}; dòng sec_org_id rỗng = chưa map được (ngày thử)."""
    _SECORG_MISS.clear()
    if not os.path.exists(SECORG_CSV):
        return {}
    d = pd.read_csv(SECORG_CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    out = {}
    for s, o, nk in zip(d.get("symbol", []), d.get("sec_org_id", []), d.get("ngay_kiem_tra", [""] * len(d))):
        s, o = str(s).strip().upper(), str(o).strip()
        if s and o.isdigit():
            out[s] = int(o)
        elif s:
            _SECORG_MISS[s] = str(nk)
    return out


def save_secorg(m: dict[str, int], ten: dict[str, str]) -> None:
    rows = [{"symbol": s, "sec_org_id": o, "ten": ten.get(s, ""), "ngay_kiem_tra": ""} for s, o in sorted(m.items())]
    rows += [{"symbol": s, "sec_org_id": "", "ten": ten.get(s, ""), "ngay_kiem_tra": nk} for s, nk in sorted(_SECORG_MISS.items()) if s not in m]
    tmp = SECORG_CSV + ".tmp"
    pd.DataFrame(rows, columns=["symbol", "sec_org_id", "ten", "ngay_kiem_tra"]).to_csv(tmp, index=False, encoding="utf-8-sig")
    os.replace(tmp, SECORG_CSV)


def _hsx_news_page(page: int, d0: dt.date, d1: dt.date, size: int = 100) -> tuple[list, int]:
    r = _get(HSX_NEWS, {"pageIndex": page, "pageSize": size, "startDate": d0.isoformat(), "endDate": d1.isoformat(),
                        "aliasCate": "tin-tuc/tin-to-chuc-niem-yet"}, HSX_HDR)
    j = r.json()
    data = (j.get("data") or {}) if isinstance(j, dict) else {}
    return data.get("list") or [], int((data.get("paging") or {}).get("totalPages") or 0)


def hose_build_map(missing: list[str], today: pd.Timestamp, threads: int, secorg: dict[str, int], ten: dict[str, str]) -> int:
    """Bổ sung map mã -> secOrgId cho các mã HOSE còn thiếu: quét tin CBTT (news/cate, 100 tin/trang, cửa sổ lùi dần
    0–30 / 30–90 / 90–200 / 200–400 ngày), lấy mã từ tiền tố tiêu đề 'XXX: …', rồi gọi chi tiết news/{id} 1 lần/mã lấy relatedId.
    Trả số mã map được thêm. Lỗi mạng -> ném RuntimeError (HOSE bị tắt ở main)."""
    need = set(missing)
    news_id: dict[str, int] = {}
    rx = re.compile(r"^\s*([A-Z0-9]{3})\s*:")
    t0 = time.time()
    for w0, w1 in ((0, 30), (30, 90), (90, 200), (200, 400)):
        if not need:
            break
        d1, d0 = (today - pd.Timedelta(days=w0)).date(), (today - pd.Timedelta(days=w1)).date()
        lst, total = _hsx_news_page(1, d0, d1)
        pages = [lst]
        page = 2
        with cf.ThreadPoolExecutor(max_workers=max(1, threads)) as ex:
            while True:
                for x in pages:
                    for it in x:
                        m = rx.match(str(it.get("title") or ""))
                        if m and m.group(1) in need and m.group(1) not in news_id:
                            news_id[m.group(1)] = int(it.get("id"))
                            need.discard(m.group(1))
                if not need or page > total:
                    break
                chunk = list(range(page, min(page + max(1, threads), total + 1)))
                pages = [p[0] for p in ex.map(lambda pg: _hsx_news_page(pg, d0, d1), chunk)]
                page = chunk[-1] + 1
        log.info("-> HOSE map: cua so %d-%d ngay, %d trang tin, con thieu %d ma, %.0fs", w0, w1, total, len(need), time.time() - t0)

    def detail(item):
        sym, nid = item
        try:
            j = _get(HSX_NEWS_ID.format(id=nid), None, HSX_HDR).json()
            d = (j.get("data") or {}) if isinstance(j, dict) else {}
            code, rid = str(d.get("code") or "").upper(), d.get("relatedId")
            return sym, (int(rid) if rid and code == sym else None), str(d.get("relatedName") or "")
        except Exception as e:                       # noqa: BLE001
            return sym, None, f"ERR {e}"

    added, errs = 0, 0
    with cf.ThreadPoolExecutor(max_workers=max(1, threads)) as ex:
        for sym, rid, nm in ex.map(detail, list(news_id.items())):
            if rid:
                secorg[sym] = rid
                if nm and not nm.startswith("ERR") and not ten.get(sym):
                    ten[sym] = nm
                added += 1
            elif nm.startswith("ERR"):
                errs += 1
    if news_id and errs >= len(news_id) and errs >= 5:
        raise RuntimeError(f"HOSE news detail loi {errs}/{len(news_id)}")
    for s in need:                                   # không có CBTT nào trong 400 ngày -> ghi nhớ, 30 ngày sau mới quét lại
        _SECORG_MISS[s] = f"{today:%Y-%m-%d}"
    if added or need:
        save_secorg(secorg, ten)
    log.info("-> HOSE map: them %d ma (%d loi chi tiet), tong %d ma co secOrgId, con thieu %d: %s", added, errs, len(secorg), len(need),
             ",".join(sorted(need)[:15]) + ("…" if len(need) > 15 else ""))
    return added


def hose_rows(sym: str, org: int, since: pd.Timestamp, meta: dict) -> list[dict]:
    """File BCTC chính thức của 1 DN HOSE: mediafiles/5/{secOrgId}, 50 file/trang, sắp theo createdDate giảm dần."""
    out, page = [], 1
    while page <= 20:
        j = _get(HSX_FILES.format(org=org), {"pageIndex": page, "pageSize": 50, "year": 0}, HSX_HDR).json()
        data = (j.get("data") or {}) if isinstance(j, dict) else {}
        lst = data.get("list") or []
        if not lst:
            break
        stop = False
        for x in lst:
            ts = unix_time(x.get("createdDate"))
            if pd.isna(ts):
                continue
            if ts < since:
                stop = True
                continue
            fn = str(x.get("fileName") or "").strip()
            fp = str(x.get("filePath") or "").lstrip("~").lstrip("/")
            doc = (re.search(r"UploadDocuments/(\d+)/", fp) or [None, ""])[1]
            ky, loai = ky_hose(str(x.get("type") or ""), str(x.get("time") or ""), fn)
            url = HSX_STATIC + urllib.parse.quote(fp, safe="/") if fp else ""
            out.append({"id": f"hose:{doc}:{fn}"[:200], "nguon": "hose", "symbol": sym, "exchange": meta.get("exchange") or "HOSE",
                        "ten_dn": meta.get("ten", ""), "ky": ky, "loai": loai, "pham_vi": pham_vi_hose(fn),
                        "ngay_cong_bo": ts.normalize(), "gio_dang": f"{ts:%H:%M}", "nam": ky[:4] if ky else None,
                        "quy": (ky[5:] if len(ky) > 4 else ""), "tieu_de": f"{x.get('type') or ''} {x.get('time') or ''} · {fn}".strip(" ·"),
                        "url_pdf": url, "url_nguon": HSX_PAGE})
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


# ------------------------------------------------------------------------------------------------ gộp + lưu
def read_old() -> pd.DataFrame:
    if not os.path.exists(CSV):
        return pd.DataFrame(columns=COLS)
    d = pd.read_csv(CSV, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    for c in COLS:
        if c not in d.columns:
            d[c] = ""
    d["ngay_cong_bo"] = pd.to_datetime(d["ngay_cong_bo"], errors="coerce")
    return d[COLS]


def _explode_old(old: pd.DataFrame) -> pd.DataFrame:
    """Dòng đã gộp (có nguon_khac) -> từng mục theo nguồn: mục chính giữ ngày; mục nguồn khác ngày NaT (không biết, coi là muộn hơn)."""
    if old.empty:
        return old
    base = old.copy()
    extra = []
    for r in base[base["nguon_khac"].astype(str).str.strip() != ""].itertuples(index=False):
        srcs = [s.strip() for s in str(r.nguon_khac).split(",") if s.strip()]
        urls = [u.strip() for u in str(r.url_pdf_khac).split("|")]
        for i, s in enumerate(srcs):
            x = r._asdict()
            x.update(nguon=s, id=f"{s}:?", url_pdf=(urls[i] if i < len(urls) else ""), ngay_cong_bo=pd.NaT, gio_dang="",
                     nguon_khac="", url_pdf_khac="", url_nguon="")
            extra.append(x)
    base["nguon_khac"] = ""
    base["url_pdf_khac"] = ""
    return pd.concat([base, pd.DataFrame(extra, columns=COLS)], ignore_index=True) if extra else base


def merge_sources(entries: pd.DataFrame) -> pd.DataFrame:
    """Gộp các mục (1 dòng = 1 file của 1 nguồn) theo khoá (symbol, ky, loai, pham_vi): giữ mục có ngày+giờ SỚM NHẤT làm dòng chính
    (nguon, id, url_pdf, tieu_de của nguồn đó); các nguồn còn lại -> nguon_khac (dấu phẩy) + url_pdf_khac (dấu |).
    pham_vi 'rieng' và 'cong_ty_me' coi là một (HOSE đặt tên file "Rieng", CafeF/Vietstock ghi "Công ty mẹ"); nhãn ra = cong_ty_me
    nếu có nguồn ghi vậy. Khoá có ky rỗng -> không gộp (dùng id làm khoá). Trùng trong cùng nguồn (CafeF đăng 2 lần) -> giữ bản sớm nhất."""
    if entries.empty:
        return pd.DataFrame(columns=COLS)
    d = entries.copy()
    for c in COLS:
        if c not in d.columns:
            d[c] = ""
    d["ngay_cong_bo"] = pd.to_datetime(d["ngay_cong_bo"], errors="coerce")
    for c in ("symbol", "ky", "loai", "pham_vi", "nguon", "gio_dang", "url_pdf", "ngay_quet"):
        d[c] = d[c].fillna("").astype(str)
    pv = d["pham_vi"].replace({"cong_ty_me": "rieng"})            # "riêng" (HOSE) ≡ "công ty mẹ" (CafeF/Vietstock): cùng 1 báo cáo
    d["_k"] = d["symbol"] + "|" + d["ky"].where(d["ky"] != "", d["id"]) + "|" + d["loai"] + "|" + pv
    d["_so"] = d["nguon"].map(SRC_ORDER).fillna(9)
    d["_na"] = d["ngay_cong_bo"].isna()
    d["_url"] = d["url_pdf"] == ""
    d = d.sort_values(["_k", "_na", "ngay_cong_bo", "gio_dang", "_url", "_so"], kind="stable")
    d = d.drop_duplicates(["_k", "nguon"], keep="first")           # 1 mục / nguồn / khoá: sớm nhất
    d = d.sort_values(["_k", "_na", "ngay_cong_bo", "gio_dang", "_so"], kind="stable")
    main = d.drop_duplicates("_k", keep="first").set_index("_k")
    rest = d[d.duplicated("_k", keep="first")].sort_values(["_k", "_so"], kind="stable")
    me = d[d["pham_vi"] == "cong_ty_me"]["_k"].unique()            # nhãn thống nhất: có nguồn ghi "công ty mẹ" -> cong_ty_me
    main.loc[main.index.isin(me) & (main["pham_vi"] == "rieng"), "pham_vi"] = "cong_ty_me"
    if len(rest):
        g = rest.groupby("_k")
        main["nguon_khac"] = g["nguon"].agg(",".join).reindex(main.index).fillna("")
        main["url_pdf_khac"] = g["url_pdf"].agg("|".join).reindex(main.index).fillna("")
        nq = g["ngay_quet"].max().reindex(main.index).fillna("").astype(str)
        main["ngay_quet"] = main["ngay_quet"].astype(str).where(main["ngay_quet"].astype(str) >= nq, nq)
    else:
        main["nguon_khac"] = ""
        main["url_pdf_khac"] = ""
    return main.reset_index(drop=True)[COLS]


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
    ap = argparse.ArgumentParser(description="Quét BCTC mới công bố toàn thị trường (CafeF + Vietstock + HOSE, gộp ngày sớm nhất).")
    ap.add_argument("--full", action="store_true", help="lần đầu: 400 ngày, không dùng mốc tăng dần")
    ap.add_argument("--days", type=int, default=30, help="số ngày gần nhất (mặc định 30; --full = 400)")
    ap.add_argument("--symbols", default="", help="chỉ các mã này, cách nhau bởi dấu phẩy")
    ap.add_argument("--source", choices=["cafef", "vietstock", "hose", "both", "all"], default="all",
                    help="all = CafeF + Vietstock + HOSE (mặc định); both = CafeF + Vietstock")
    ap.add_argument("--download", action="store_true", help="tải PDF về pdf\\<ma>\\")
    ap.add_argument("--threads", type=int, default=6)
    a = ap.parse_args(argv)
    srcs = {"cafef": ["cafef"], "vietstock": ["vietstock"], "hose": ["hose"], "both": ["cafef", "vietstock"],
            "all": ["cafef", "vietstock", "hose"]}[a.source]

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
             "FULL" if a.full else "tang dan", "+".join(srcs), since.date(), (today - since).days, len(uni), years, a.threads, HAS_CURL, len(old))
    t0 = time.time()

    # ---- HOSE: map mã -> secOrgId (file data\hose_secorg.csv, bổ sung mã thiếu từ tin CBTT)
    secorg: dict[str, int] = {}
    if "hose" in srcs:
        try:
            secorg = load_secorg()
            ten = {s: m.get("ten", "") for s, m in uni.items()}
            han = f"{today - pd.Timedelta(days=30):%Y-%m-%d}"
            missing = [s for s, m in uni.items() if m.get("exchange") == "HOSE" and s not in secorg and _SECORG_MISS.get(s, "") < han]
            if missing:
                hose_build_map(missing, today, a.threads, secorg, ten)
            if not any(s in secorg for s in uni):
                raise RuntimeError("khong co ma HOSE nao co secOrgId")
        except Exception as e:                       # noqa: BLE001
            log.warning("! HOSE map secOrgId loi: %s -> bo qua nguon HOSE lan nay", e)
            SRC["hose"]["down"] = True
    if "vietstock" in srcs:
        try:
            _vs_token()
        except Exception as e:                       # noqa: BLE001
            log.warning("! Vietstock token loi: %s -> bo qua nguon Vietstock lan nay", e)
            SRC["vietstock"]["down"] = True

    rows, errs = [], []

    def run_src(src, fn):
        if SRC[src]["down"]:
            return None, None
        try:
            got = fn()
            _src_ok(src)
            return got, None
        except Exception as e:                       # noqa: BLE001
            _src_fail(src)
            return None, f"{src}: {e}"

    def work(sym):
        meta = uni[sym]
        got, es = [], []
        for src in srcs:
            if src == "cafef":
                r, e = run_src(src, lambda: cafef_rows(sym, years, since, meta))
                if e and "vietstock" not in srcs:       # --source cafef: CafeF lỗi -> dự phòng Vietstock như cũ
                    r, e2 = run_src("vietstock", lambda: vietstock_rows(sym, since, meta))
                    es += [f"{sym} {e}"] + ([f"{sym} {e2}"] if e2 else [])
                    got += r or []
                    continue
            elif src == "vietstock":
                r, e = run_src(src, lambda: vietstock_rows(sym, since, meta))
            else:
                org = secorg.get(sym)
                if not org:
                    continue
                r, e = run_src(src, lambda: hose_rows(sym, org, since, meta))
            got += r or []
            if e:
                es.append(f"{sym} {e}")
        return sym, got, es

    done = 0
    with cf.ThreadPoolExecutor(max_workers=max(1, a.threads)) as ex:
        for sym, got, es in ex.map(work, list(uni)):
            rows += got
            errs += es
            done += 1
            if done % 200 == 0:
                log.info("-> %d/%d ma, %d muc, %.0fs", done, len(uni), len(rows), time.time() - t0)
    for e in errs[:20]:
        log.warning("! %s", e)
    if len(errs) > 20:
        log.warning("! ... tong %d luot ma/nguon loi", len(errs))

    new = pd.DataFrame(rows, columns=COLS[:-2]) if rows else pd.DataFrame(columns=COLS[:-2])
    new["ngay_quet"] = f"{today:%Y-%m-%d}"
    new["nguon_khac"] = ""
    new["url_pdf_khac"] = ""
    if len(new):
        for src in srcs:
            t = new[new["nguon"] == src]
            log.info("Tong nguon %s: %d file, %d DN, %d ma OK / %d loi%s", src, len(t), t["symbol"].nunique(), SRC[src]["ok"], SRC[src]["err"],
                     " (DA TAT)" if SRC[src]["down"] else "")
    # ---- gộp: mục mới + mục cũ (đã gộp -> tách lại theo nguồn), khoá trùng -> ngày sớm nhất
    old_x = _explode_old(old) if len(old) else old
    old_keys = set(zip(old["symbol"], old["ky"], old["loai"], old["pham_vi"])) if len(old) else set()
    entries = pd.concat([old_x, new], ignore_index=True) if len(old_x) else new
    all_df = merge_sources(entries)
    all_df["ngay_cong_bo"] = pd.to_datetime(all_df["ngay_cong_bo"], errors="coerce")
    all_df = all_df.dropna(subset=["ngay_cong_bo"])
    save(all_df)
    n_dn = new["symbol"].nunique() if len(new) else 0
    merged_new = merge_sources(new) if len(new) else new
    them = merged_new[[k not in old_keys for k in zip(merged_new["symbol"], merged_new["ky"], merged_new["loai"], merged_new["pham_vi"])]] \
        if len(merged_new) else merged_new
    log.info("Tong: %d muc tu %d nguon -> %d BCTC trong cua so (%d DN), %d BCTC MOI so voi CSV; %d request, %d retry, %d luot loi; %.0fs",
             len(new), len(srcs), len(merged_new), n_dn, len(them), STATS["req"], STATS["retry"], len(errs), time.time() - t0)
    if len(merged_new):
        ng = merged_new["nguon"].value_counts()
        som = merged_new[(merged_new["nguon"] != "cafef") & merged_new["nguon_khac"].str.contains("cafef")]
        chi = merged_new[(merged_new["nguon"] != "cafef") & ~merged_new["nguon_khac"].str.contains("cafef")]
        log.info("Tong nguon som nhat: %s | %d BCTC CafeF co ngay som hon nho nguon khac | %d BCTC CafeF KHONG co",
                 "; ".join(f"{k}={v}" for k, v in ng.items()), len(som), len(chi))
        ky = merged_new.groupby("ky")["symbol"].nunique().sort_index(ascending=False).head(8)
        log.info("Tong theo ky (so DN): %s", "; ".join(f"{k}={v}" for k, v in ky.items()))
        lo = merged_new.groupby(["loai", "pham_vi"]).size()
        log.info("Tong theo loai/pham vi: %s", "; ".join(f"{k[0]}/{k[1]}={v}" for k, v in lo.items()))
    log.info("Da luu %s (%d dong) + %s", CSV, len(all_df), os.path.basename(PQ))
    if a.download and len(them):
        n = download_pdfs(them)
        log.info("Da luu %d PDF vao %s", n, PDF_DIR)
    alive = [s for s in srcs if not SRC[s]["down"] and SRC[s]["ok"] > 0]
    if len(uni) and not alive:
        log.error("LOI: khong nguon nao chay duoc (%s) - nguon co the chan", ", ".join(f"{s}: {SRC[s]['err']} loi" for s in srcs))
        return 2
    for s in srcs:
        if SRC[s]["down"] or (SRC[s]["ok"] + SRC[s]["err"] and SRC[s]["err"] > (SRC[s]["ok"] + SRC[s]["err"]) * 0.5):
            log.warning("! nguon %s: %d OK / %d loi - ket qua lan nay thieu nguon nay", s, SRC[s]["ok"], SRC[s]["err"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
