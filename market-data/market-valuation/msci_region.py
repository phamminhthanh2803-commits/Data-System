# -*- coding: utf-8 -*-
r"""
msci_region.py — Dinh gia chi so MSCI theo NUOC tu factsheet PDF cong khai cua MSCI (thang), gom ca P/E FORWARD
(I/B/E/S consensus) — nguon forward duy nhat mien phi, cung mot phuong phap cho moi nuoc.

URL: https://www.msci.com/documents/10199/255599/msci-<country>-index.pdf (cap nhat cuoi thang, ~5 ngay sau).
Trang 1 co bang "FUNDAMENTALS (MMM DD, YYYY)": Div Yld (%) | P/E | P/E Fwd | P/BV — 4 so dau la chi so nuoc,
2 bo 4 so sau la chi so tham chieu (MSCI EM / ACWI...). Vietnam: P/E Fwd = "na" (frontier, it coverage).
LUU Y: MSCI country index = large + mid cap (~85% von hoa), KHONG phai toan san -> P/E khac tv_region/VNDirect.

Ghi vao valuation-region-master.csv: code MSCI_<CC>, ratio PRICE_TO_EARNINGS / PE_FORWARD / PRICE_TO_BOOK /
DIVIDEND_YIELD, currency USD, freq M, date = ngay "as of" trong factsheet, source msci.
Chay: python msci_region.py   (12 PDF, ~30s; goi trong Run-Region-Daily.ps1 — moi thang chi them 1 dong/nuoc)
"""
import io
import os
import re
import sys
import time

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # D:\market-data
from mdlib import log, cffi_session as _cffi_session, safe_to_csv  # noqa: E402  (gop 14/09/2026)
import region as R

SLUGS = {"VN": "msci-vietnam-index", "TH": "msci-thailand-index", "KR": "msci-korea-index", "TW": "msci-taiwan-index",
         "ID": "msci-indonesia-index", "MY": "msci-malaysia-index", "PH": "msci-philippines-index",
         "HK": "msci-hong-kong-index", "CN": "msci-china-index", "JP": "msci-japan-index", "SG": "msci-singapore-index",
         "IN": "msci-india-index-net"}   # india: ten file khac (msci-india-index.pdf 404)
URL = "https://www.msci.com/documents/10199/255599/{slug}.pdf"
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def parse(pdf_bytes):
    import pypdf
    t = " ".join((p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages[:2]).replace("\n", " ")
    m = re.search(r"FUNDAMENTALS\s*\(([A-Z]{3}) (\d{1,2}), (\d{4})\)\s*Div Yld \(%\)\s*P/E\s*P/E Fwd\s*P/BV\s*"
                  r"([\d.]+|na)\s+([\d.]+|na)\s+([\d.]+|na)\s+([\d.]+|na)", t)
    if not m:
        raise ValueError("khong thay bang FUNDAMENTALS")
    d = f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
    num = lambda s: float(s) if s != "na" else None
    return d, {"DIVIDEND_YIELD": num(m.group(4)), "PRICE_TO_EARNINGS": num(m.group(5)),
               "PE_FORWARD": num(m.group(6)), "PRICE_TO_BOOK": num(m.group(7))}


def main():
    from curl_cffi import requests
    recs = []
    for cc, slug in SLUGS.items():
        try:
            r = requests.get(URL.format(slug=slug), impersonate="chrome", timeout=60)
            if r.status_code != 200 or r.content[:4] != b"%PDF":
                log(f"  MSCI_{cc:3} [LOI] HTTP {r.status_code}")
                continue
            d, vals = parse(r.content)
            for k, v in vals.items():
                recs.append(R.rec(f"MSCI_{cc}", d, k, v, "USD", "M", "msci"))
            log(f"  MSCI_{cc:3} {d}  P/E {vals['PRICE_TO_EARNINGS']}  fwd {vals['PE_FORWARD']}  P/B {vals['PRICE_TO_BOOK']}  yld {vals['DIVIDEND_YIELD']}")
        except Exception as e:
            log(f"  MSCI_{cc:3} [LOI] {repr(e)[:100]}")
        time.sleep(0.5)
    recs = [x for x in recs if x]
    if not recs:
        return
    new = pd.DataFrame(recs)
    old = pd.read_csv(R.MASTER_CSV, dtype={"date": str, "currency": str, "freq": str}) \
        if os.path.exists(R.MASTER_CSV) else pd.DataFrame(columns=R.COLS)
    master = pd.concat([old[R.COLS], new[R.COLS]], ignore_index=True) if not old.empty else new[R.COLS]
    master["value"] = pd.to_numeric(master["value"], errors="coerce")
    master = master.dropna(subset=["value"]).drop_duplicates(subset=["code", "date", "ratio"], keep="last")
    master = master.sort_values(["code", "ratio", "date"]).reset_index(drop=True)
    master.to_csv(R.MASTER_CSV, index=False, encoding="utf-8-sig")
    R.build_wide(master).to_csv(R.WIDE_CSV, index=False, encoding="utf-8-sig")
    log(f"-> master {len(master)} dong")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
