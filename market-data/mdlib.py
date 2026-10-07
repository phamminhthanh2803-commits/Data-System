# -*- coding: utf-8 -*-
"""mdlib.py — THU VIEN DUNG CHUNG cho cum tool DU LIEU THI TRUONG & VI MO (D:\\market-data), gop 14/09/2026.

Truoc day moi tool (index-fetcher, market-valuation, macro-fetcher, transmission-fetcher) tu viet lai
log / session gia Chrome / ghi CSV an toan / merge-dedup. Nay 1 ban duy nhat o day; tool con import:

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # D:\\market-data
    from mdlib import log, cffi_session, new_session, get, safe_to_csv, merge_long, vn_number, vn_date

Noi dung:
  log(msg)                      in + flush, co gio (runner PowerShell grep theo noi dung, khong theo gio)
  setup_stdout()                ep UTF-8 cho console Windows
  cffi_session(impersonate)     curl_cffi Session gia Chrome (Cloudflare/Incapsula: SET, IDX, Bursa, SBV...)
  new_session(kind)             'browser' (curl_cffi xoay van tay) | 'api' (VNDirect/VCI) | 'plain' (FRED)
  get(session, url, ...)        GET co retry + backoff + phien moi moi lan thu; nhan ra "Request Rejected" cua WAF SBV
  vn_number / vn_date           so kieu SBV ("892,137,0") va ngay dd/mm/yyyy
  safe_to_csv(df, path)         Excel dang mo file -> thu lai, roi do ra <path>.pending.csv; tra True/False
  merge_long(new, path, keys)   gop long-format vao master: nuot lai pending, dedup theo keys keep last, sort
"""
from __future__ import annotations

import datetime as dt
import os
import random
import re
import sys
import time

import pandas as pd

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL = True
except ImportError:                                               # noqa: BLE001
    curl_requests = None
    HAS_CURL = False
import requests

HUB = os.path.dirname(os.path.abspath(__file__))
IMPERSONATE = ["chrome131", "chrome124", "chrome120", "firefox133", "safari17_0"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
BROWSER_PROFILES = [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
     '"Chromium";v="128", "Not;A=Brand";v="24"', '"Windows"', "vi-VN,vi;q=0.9,en-US;q=0.8"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
     '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"', '"Windows"', "vi,en-US;q=0.9,en;q=0.8"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
     '"Chromium";v="130", "Not?A_Brand";v="99"', '"macOS"', "vi-VN,vi;q=0.9,en;q=0.8"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
     None, None, "vi,vi-VN;q=0.9,en-US;q=0.7"),
]
BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1",
}
API_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Content-Type": "application/json",
}


def log(msg) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def setup_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                             # noqa: BLE001
        pass


def cffi_session(impersonate: str = "chrome"):
    """curl_cffi Session bat tay TLS nhu Chrome that (Cloudflare/Incapsula/F5 doi chieu JA3 voi User-Agent)."""
    if not HAS_CURL:
        raise ImportError("can curl_cffi: python -m pip install --user curl_cffi")
    return curl_requests.Session(impersonate=impersonate)


def new_session(kind: str = "browser"):
    """browser: sbv.gov.vn va cac site co WAF (curl_cffi, xoay van tay moi phien)
    api    : VNDirect / VCI (403 neu thieu User-Agent)   plain: FRED, Vietcombank (timeout neu UA trinh duyet)."""
    if kind == "browser" and HAS_CURL:
        s = curl_requests.Session(impersonate=random.choice(IMPERSONATE))
        s.headers.update({"Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"})   # KHONG de UA cua minh len
        s._kind = "browser"
        return s
    s = requests.Session()
    s._kind = kind
    if kind == "browser":
        h = dict(BROWSER_HEADERS)
        ua, ch, plat, lang = random.choice(BROWSER_PROFILES)
        h["User-Agent"], h["Accept-Language"] = ua, lang
        if ch:
            h["sec-ch-ua"], h["sec-ch-ua-platform"] = ch, plat
        else:
            for k in ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"):
                h.pop(k, None)
        s.headers.update(h)
    elif kind == "api":
        s.headers.update(API_HEADERS)
    return s


def get(session, url: str, *, tries: int = 4, wait: int = 6, referer: str | None = None,
        timeout: int = 40, binary: bool = False, fresh_session: bool = True):
    """GET co retry + backoff. Tra text (hoac bytes) hay None. WAF SBV tra 'Request Rejected' voi HTTP 200 -> coi la loi."""
    hdr = {"Referer": referer} if referer else {}
    kind = getattr(session, "_kind", None) or (
        "browser" if session.headers.get("Sec-Fetch-Mode") else ("api" if session.headers.get("Content-Type") else "plain"))
    for i in range(1, tries + 1):
        if i > 1 and fresh_session:
            session = new_session(kind)
        try:
            r = session.get(url, headers=hdr, timeout=timeout)
            body = r.content
            if r.status_code == 200 and b"Request Rejected" not in body[:600]:
                return body if binary else r.text
            reason = "WAF chan" if b"Request Rejected" in body[:600] else f"HTTP {r.status_code}"
        except Exception as e:                                    # noqa: BLE001
            reason = f"{type(e).__name__}: {e}"
        if i < tries:
            log(f"  ! {reason} -> thu lai {i}/{tries - 1} sau {wait * i}s: {url[:80]}")
            time.sleep(wait * i)
    log(f"  X BO QUA (khong lay duoc): {url[:110]}")
    return None


_NUM_RE = re.compile(r"^-?[\d.,]+$")


def vn_number(txt) -> float | None:
    """"892,137,0" -> 892137.0 | "4,62" -> 4.62 | "3,000%" -> 3.0 | "1.234,5" -> 1234.5 (dau phay cuoi = thap phan)."""
    if txt is None:
        return None
    s = str(txt).strip().replace("%", "").replace("\xa0", " ")
    s = re.sub(r"\(\*+\)", "", s).strip().replace(" ", "")
    if not s or not _NUM_RE.match(s):
        return None
    neg = s.startswith("-")
    s = s.lstrip("-").replace(".", "")
    if "," in s:
        head, _, tail = s.rpartition(",")
        s = (head.replace(",", "") or "0") + "." + tail
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def vn_date(txt) -> str | None:
    """dd/mm/yyyy (hoac d-m-yyyy) trong chuoi -> 'YYYY-MM-DD'."""
    if not txt:
        return None
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", str(txt))
    if not m:
        return None
    d, mth, y = (int(x) for x in m.groups())
    try:
        return dt.date(y, mth, d).isoformat()
    except ValueError:
        return None


def pending_path(path: str) -> str:
    return path + ".pending.csv"


def safe_to_csv(df: pd.DataFrame, path: str, *, tries: int = 3, wait: int = 5, **kw) -> bool:
    """Ghi CSV utf-8-sig. File dang mo trong Excel -> thu lai, roi do ra <path>.pending.csv (khong mat du lieu);
    lan sau merge_long / load_with_pending tu nuot lai. Tra True neu ghi dung path."""
    for i in range(1, tries + 1):
        try:
            df.to_csv(path, index=False, encoding="utf-8-sig", **kw)
            return True
        except PermissionError:
            if i < tries:
                log(f"  ! {os.path.basename(path)} dang bi khoa (mo trong Excel?) - thu lai sau {wait}s")
                time.sleep(wait)
    pend = pending_path(path)
    df.to_csv(pend, index=False, encoding="utf-8-sig", **kw)
    log(f"  X KHONG GHI DUOC {os.path.basename(path)} (dang mo trong Excel). Da luu tam {os.path.basename(pend)} - "
        "dong Excel roi chay lai la tu gop.")
    return False


def load_with_pending(path: str, dtype=None) -> pd.DataFrame | None:
    """Doc master + file pending (neu co) roi xoa pending. None neu chua co master."""
    if not os.path.exists(path):
        return None
    dtype = dtype or {"date": str}
    df = pd.read_csv(path, dtype=dtype, encoding="utf-8-sig")
    pend = pending_path(path)
    if os.path.exists(pend):
        try:
            p = pd.read_csv(pend, dtype=dtype, encoding="utf-8-sig")
            df = pd.concat([df, p], ignore_index=True)
            os.remove(pend)
            log(f"  Da nuot lai {len(p)} dong tu file pending")
        except Exception:                                         # noqa: BLE001
            pass
    return df


def merge_long(new_rows, path: str, keys, cols=None, sort=None, dropna_keys=True) -> pd.DataFrame:
    """Gop du lieu moi vao master long-format: nuot pending, ep du cot, dedup theo keys keep last, sort, ghi an toan."""
    new = new_rows if isinstance(new_rows, pd.DataFrame) else pd.DataFrame(new_rows, columns=cols)
    cols = list(cols or new.columns)
    keys = list(keys)
    old = load_with_pending(path, dtype={c: str for c in keys if c == "date"} or None)
    parts = []
    if old is not None and len(old):
        for c in cols:
            if c not in old.columns:
                old[c] = pd.NA
        parts.append(old[cols])
    if len(new):
        for c in cols:
            if c not in new.columns:
                new[c] = pd.NA
        parts.append(new[cols])
    if not parts:
        return pd.DataFrame(columns=cols)
    df = pd.concat(parts, ignore_index=True)
    if dropna_keys:
        df = df.dropna(subset=keys)
    df = df.drop_duplicates(subset=keys, keep="last")
    df = df.sort_values(sort or keys).reset_index(drop=True)
    safe_to_csv(df, path)
    return df
