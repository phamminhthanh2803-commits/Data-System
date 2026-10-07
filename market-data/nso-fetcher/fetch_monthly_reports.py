# -*- coding: utf-8 -*-
"""fetch_monthly_reports.py - tai file Excel "Bieu so lieu" dinh kem Bao cao tinh hinh KT-XH hang thang cua NSO
(nguon so lieu THANG: IIP, san pham CN, DN dang ky, von dau tu NSNN, FDI, tong muc ban le, XK/NK theo mat hang,
CPI, van tai, khach quoc te...) ve thu muc monthly-reports\ de doi chieu / tu bo so vao file phan tich.

    python fetch_monthly_reports.py               # tu 2024 den nay, bo qua file da co
    python fetch_monthly_reports.py --since 2020  # lui ve 2020 (bai cu hon ~2023 dang nam o gso.gov.vn da chet)

Danh sach: https://www.nso.gov.vn/bao-cao-tinh-hinh-kinh-te-xa-hoi-hang-thang/?paged=N
Ten file: monthly-reports\YYYY-MM_<ten goc>.xlsx ; chi muc: monthly_reports_index.csv (month, title, post_url, file).
Thang bao cao suy tu tieu de ("thang Tam va 8 thang nam 2026" -> 2026-08; "quy III va 9 thang" -> 2026-09),
khong doc duoc thi lay thang dang bai - 1. Bo cuc sheet doi theo thang nen tool KHONG tu parse - chi tai ve.
"""
from __future__ import annotations

import argparse
import html as H
import os
import re
import sys
import time

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from mdlib import log, new_session, safe_to_csv, setup_stdout     # noqa: E402

LIST = "https://www.nso.gov.vn/bao-cao-tinh-hinh-kinh-te-xa-hoi-hang-thang/"
OUT = os.path.join(HERE, "monthly-reports")
INDEX = os.path.join(HERE, "monthly_reports_index.csv")
VN_M = {"một": 1, "giêng": 1, "hai": 2, "ba": 3, "tư": 4, "bốn": 4, "năm": 5, "sáu": 6, "bảy": 7, "tám": 8,
        "chín": 9, "mười": 10, "mười một": 11, "mười hai": 12}
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}


def infer_month(title: str, url: str) -> str:
    t = title.lower().replace("–", "-")
    y = re.search(r"năm\s*(20\d{2})", t)
    um = re.search(r"/(20\d{2})/(\d{2})/", url)
    year = y.group(1) if y else (um.group(1) if um else "")
    q = re.search(r"quý\s*(iv|iii|ii|i|[1-4])\b", t)
    if q:
        n = ROMAN.get(q.group(1), q.group(1))
        return f"{year}-{3 * int(n):02d}"
    m = re.search(r"tháng\s+(mười hai|mười một|mười|một|giêng|hai|ba|tư|bốn|năm|sáu|bảy|tám|chín|\d{1,2})(?!\s*(?:20\d{2}|đầu))", t)
    if m and year:
        n = VN_M.get(m.group(1)) or int(m.group(1))
        return f"{year}-{int(n):02d}"
    if um:
        yy, mm = int(um.group(1)), int(um.group(2)) - 1
        if mm == 0:
            yy, mm = yy - 1, 12
        return f"{yy}-{mm:02d}"
    return ""


def main() -> int:
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=2024, help="nam cu nhat can tai")
    ap.add_argument("--max-pages", type=int, default=40)
    ap.add_argument("--no-parse", action="store_true", help="khong chay parse_monthly_reports sau khi tai")
    a = ap.parse_args()
    sys.path.insert(0, HERE)
    os.makedirs(OUT, exist_ok=True)
    s = new_session("browser")
    idx = pd.read_csv(INDEX, dtype=str, encoding="utf-8-sig") if os.path.exists(INDEX) else \
        pd.DataFrame(columns=["month", "title", "post_url", "file"])
    have = set(idx["post_url"])
    log(f"=== Bao cao KT-XH thang NSO: tai tu {a.since}, da co {len(have)} bai ===")
    posts, stop = [], False
    for p in range(1, a.max_pages + 1):
        try:
            r = s.get(LIST + (f"?paged={p}" if p > 1 else ""), timeout=60)
        except Exception as e:                                    # noqa: BLE001
            log(f"  ! trang {p}: {e}")
            break
        if r.status_code != 200:
            break
        found = 0
        for h, t in re.findall(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r.text, re.S):
            # slug doi theo thoi ky: bao-cao-tinh-hinh-kinh-te-xa-hoi-... / bc-tinh-hinh-... / tinh-hinh-kinh-te-xa-hoi-...
            # (bai cu 2000-2019 duoc dang lai nam 2019-2020 nen thu muc /YYYY/MM/ trong URL KHONG phai ky bao cao)
            if "tinh-hinh-kinh-te-xa-hoi" not in h or "?paged" in h or h.rstrip("/") == LIST.rstrip("/") \
                    or not re.search(r"/20\d\d/\d\d/", h):
                continue
            t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", H.unescape(t))).strip()
            t = re.split(r"\s*Ngày đăng", t)[0].strip()
            if not t or any(h == x[0] for x in posts):
                continue
            found += 1
            mon = infer_month(t, h)
            if mon and int(mon[:4]) < a.since:
                stop = True
                continue
            posts.append((h, t, mon))
        if stop or (not found and p > 3):
            break
        time.sleep(0.5)
    log(f"Tim thay {len(posts)} bai tu {a.since}")
    new = []
    for h, t, mon in posts:
        if h in have:
            continue
        try:
            r = s.get(h, timeout=60)
        except Exception as e:                                    # noqa: BLE001
            log(f"  ! {mon}: {e}")
            continue
        files = []
        for fh, ft in re.findall(r'<a[^>]*href="([^"]*\.xlsx?)"[^>]*>(.*?)</a>', r.text, re.S | re.I):
            fh = H.unescape(fh)
            if fh in [f[0] for f in files]:
                continue
            files.append((fh, re.sub(r"<[^>]+>", "", ft).strip()))
        if not files:
            log(f"  - {mon} {t[:60]}: khong co file Excel")
            new.append({"month": mon, "title": t, "post_url": h, "file": ""})
            continue
        for fh, ft in files:
            base = os.path.basename(fh.split("?")[0])
            dest = os.path.join(OUT, f"{mon}_{base}" if mon else base)
            if os.path.exists(dest):
                new.append({"month": mon, "title": t, "post_url": h, "file": os.path.basename(dest)})
                continue
            try:
                fr = s.get(fh, timeout=180)
                if fr.status_code == 200 and len(fr.content) > 2000:
                    with open(dest, "wb") as f:
                        f.write(fr.content)
                    log(f"  Da luu {os.path.basename(dest)} ({len(fr.content) // 1024} KB) <- {ft[:50]}")
                    new.append({"month": mon, "title": t, "post_url": h, "file": os.path.basename(dest)})
                else:
                    log(f"  X {mon}: HTTP {fr.status_code} {fh[-60:]}")
            except Exception as e:                                # noqa: BLE001
                log(f"  X {mon}: {e}")
        time.sleep(0.5)
    if new:
        idx = pd.concat([idx, pd.DataFrame(new)], ignore_index=True).drop_duplicates(["post_url", "file"], keep="last")
        idx = idx.sort_values("month", ascending=False).reset_index(drop=True)
        safe_to_csv(idx, INDEX)
    log(f"Tong: {len(new)} bai moi, chi muc {len(idx)} dong -> {OUT}")
    if not a.no_parse:
        import parse_monthly_reports
        parse_monthly_reports.main_parse()
    log("=== XONG ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
