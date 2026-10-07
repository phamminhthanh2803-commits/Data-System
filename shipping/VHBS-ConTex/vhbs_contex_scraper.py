#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VHSS ConTex charter-rate scraper (ban Python - kéo full 1 phát, dự phòng)
-------------------------------------------------------------------------
Kéo dữ liệu giá cước (container ship charter rates) từ trang
https://www.vhbs.de/index.php?id=79&L=1 và xuất ra CSV.

Dữ liệu nằm sẵn (inline) trong HTML dưới dạng `var json = '{...}'`.
Mỗi series là 1 loại tàu (theo sức chở TEU), giá trị = USD/ngày (charter rate).

Cách dùng:
    python vhbs_contex_scraper.py                 # -> vhbs_contex.csv
    python vhbs_contex_scraper.py -o giacuoc.csv  # đặt tên file output
    python vhbs_contex_scraper.py --url "..."     # đổi URL khác nếu cần

Không cần thư viện ngoài (chỉ dùng standard library).
"""

import argparse
import csv
import json
import re
import sys
import urllib.request

DEFAULT_URL = "https://www.vhbs.de/index.php?id=79&L=1"

TYPE_LABELS = {
    "c1100teu": "1100 TEU",
    "c1700teu": "1700 TEU",
    "c1800teu": "1800 TEU",
    "c2500teu": "2500 TEU",
    "c2700teu": "2700 TEU",
    "c3000teu": "3000 TEU",
    "c3500teu": "3500 TEU",
    "c4250teu": "4250 TEU",
    "c5700teu": "5700 TEU",
    "c6500teu": "6500 TEU",
    "overall":  "New ConTex",
}

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/148.0.0.0 Safari/537.36"),
    "referer": "https://www.vhbs.de/index.php?id=28&L=1",
}


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_series(html: str) -> dict:
    blocks = re.findall(r"var\s+json\s*=\s*'(\{.*?\})'\s*;", html, re.S)
    if not blocks:
        raise RuntimeError("Khong tim thay du lieu JSON trong trang. "
                           "Co the cau truc trang da thay doi.")
    merged: dict = {}
    for block in blocks:
        data = json.loads(block)
        for key, series in data.items():
            if key == "maximum" or not isinstance(series, dict):
                continue
            if key not in merged or len(series) > len(merged[key]):
                merged[key] = series
    return merged


def build_rows(merged: dict):
    keys = sorted(merged.keys(),
                  key=lambda k: (len(TYPE_LABELS.get(k, k)), k))
    all_dates = sorted({d for s in merged.values() for d in s})
    header = ["Date"] + [TYPE_LABELS.get(k, k) for k in keys]
    rows = []
    for d in all_dates:
        row = [d]
        for k in keys:
            v = merged[k].get(d, "")
            row.append("" if v in (0, None) else v)
        rows.append(row)
    return header, rows


def main():
    ap = argparse.ArgumentParser(description="Keo gia cuoc ConTex (VHSS) ve CSV")
    ap.add_argument("-o", "--output", default="vhbs_contex.csv",
                    help="File CSV xuat ra (mac dinh: vhbs_contex.csv)")
    ap.add_argument("--url", default=DEFAULT_URL, help="URL trang ConTex")
    args = ap.parse_args()

    print(f"Dang tai: {args.url}")
    html = fetch_html(args.url)
    merged = extract_series(html)
    header, rows = build_rows(merged)

    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

    types = ", ".join(header[1:])
    print(f"OK -> {args.output}")
    print(f"  So loai tau : {len(header) - 1} ({types})")
    print(f"  So dong (ngay): {len(rows)}")
    if rows:
        print(f"  Khoang ngay : {rows[0][0]}  ->  {rows[-1][0]}")
        print(f"  Don vi gia tri: USD/ngay (charter rate)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"LOI: {e}", file=sys.stderr)
        sys.exit(1)
