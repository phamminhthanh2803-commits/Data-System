# -*- coding: utf-8 -*-
"""vhbs_pull.py — ban Python cua Update-VhbsContex.ps1 (07/10/2026), de cung 1 code chay tren Windows lan Linux/cloud.

Keo gia thue tau container VHBS/VHSS ConTex (USD/ngay) tu HTML (inline  var json = '{...}'), MERGE cac date MOI
vao vhbs_contex.csv canh script. Idempotent: chay nhieu lan chi them ngay chua co. Gia tri 0 trong nguon = khong
cong bo -> de trong. ps1 goc giu nguyen; cach merge/dedup/ghi file y het:
  - header/thu tu cot lay theo FILE CU (neu co); date la khoa, dong cu khong bi sua
  - ghi lai toan bo, sap theo ngay, UTF-8 BOM + CRLF (Excel)
  - log vhbs_contex.log: "yyyy-mm-dd HH:MM:SS  START/DONE/ERROR ..."
    python vhbs_pull.py [--csv path] [--log path] [--url url]
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://www.vhbs.de/index.php?id=79&L=1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.vhbs.de/index.php?id=28&L=1",
    "User-Agent": UA,
}
# key trong JSON -> nhan cot (giu thu tu nay)
TYPE_LABELS = {
    "c1100teu": "1100 TEU", "c1700teu": "1700 TEU", "c1800teu": "1800 TEU",
    "c2500teu": "2500 TEU", "c2700teu": "2700 TEU", "c3000teu": "3000 TEU",
    "c3500teu": "3500 TEU", "c4250teu": "4250 TEU", "c5700teu": "5700 TEU",
    "c6500teu": "6500 TEU", "overall": "New ConTex",
}
LABEL_TO_KEY = {v: k for k, v in TYPE_LABELS.items()}


class Log:
    def __init__(self, path):
        self.path = path

    def __call__(self, msg):
        line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:                                         # noqa: BLE001
            pass
        print(line, flush=True)


def fmt(v):
    """[string]$val cua PowerShell: 6389.0 -> '6389', 10212.5 -> '10212.5'."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(HERE, "vhbs_contex.csv"))
    ap.add_argument("--log", default=os.path.join(HERE, "vhbs_contex.log"))
    ap.add_argument("--url", default=URL)
    a = ap.parse_args(argv)
    log = Log(a.log)
    try:
        log(f"START  tai {a.url}")
        # ---- 1. Tai HTML
        r = requests.get(a.url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        html = r.text
        # ---- 2. Trich cac block JSON
        blocks = re.findall(r"var\s+json\s*=\s*'(\{.*?\})'\s*;", html, re.S)
        if not blocks:
            raise RuntimeError("Khong tim thay du lieu JSON trong trang (cau truc co the da thay doi).")
        # ---- 3. Gop series, uu tien series dai nhat
        merged = {}                                               # key -> {date: value}
        for b in blocks:
            obj = json.loads(b)
            for key, series in obj.items():
                if key == "maximum" or not isinstance(series, dict) or not series:
                    continue
                if key not in merged or len(series) > len(merged[key]):
                    merged[key] = dict(series)
        # ---- 4. Thu tu cot
        ordered = [k for k in TYPE_LABELS if k in merged] + sorted(k for k in merged if k not in TYPE_LABELS)
        labels = [TYPE_LABELS.get(k, k) for k in ordered]
        header = ["Date"] + labels
        # ---- 5. Doc file cu (neu co), giu nguyen header/thu tu cot cua file
        existing = {}                                             # date -> [cells]
        if os.path.exists(a.csv):
            lines = open(a.csv, encoding="utf-8-sig").read().splitlines()
            if lines:
                header = lines[0].split(",")
                labels = header[1:]
                for ln in lines[1:]:
                    if not ln.strip():
                        continue
                    cells = ln.split(",")
                    existing[cells[0]] = cells
        # ---- 6. Them cac date MOI (chua co trong file)
        all_dates = {d for k in merged for d in merged[k]}
        added = 0
        for d in all_dates:
            if d in existing:
                continue
            row = [d]
            for label in labels:
                key = LABEL_TO_KEY.get(label)
                val = merged[key].get(d) if key and key in merged else None
                row.append("" if val is None or val == 0 else fmt(val))
            existing[d] = row
            added += 1
        # ---- 7. Ghi lai (sap xep theo ngay), UTF-8 BOM + CRLF cho Excel
        sorted_dates = sorted(existing)
        text = ",".join(header) + "\r\n" + "".join(",".join(existing[d]) + "\r\n" for d in sorted_dates)
        with open(a.csv, "wb") as f:
            f.write(text.encode("utf-8-sig"))
        latest = sorted_dates[-1] if sorted_dates else "(rong)"
        log(f"DONE   them {added} ngay moi | tong {len(sorted_dates)} ngay | moi nhat {latest} -> {a.csv}")
        return 0
    except Exception as e:                                        # noqa: BLE001
        log(f"ERROR  {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
