# -*- coding: utf-8 -*-
"""Giai ma bang THONG KE / CAR cua sbv.gov.vn tu HTML DAN TAY -> master.

Dung khi WAF chan script: anh mo trang bang trinh duyet thuong, Inspect -> Copy element
cai <tbody> (hoac ca <table>), dan vao MOT file text, moi ban mot khoi. Tool nay khong
gui request nao - chi doc file tren dia.

Dinh dang file  paste/paste.txt  (ma hoa UTF-8):

    ## 28/02/2026
    <tbody> ... </tbody>

    ## 31/01/2026 car
    <tbody> ... </tbody>

- Dong `## dd/mm/yyyy` la NGAY cua ban (lay tu tieu de "Den thoi diem dd/mm/yyyy").
  Chu `car` phia sau la tuy chon; khong ghi thi tool tu doan theo so cot:
  7 cot = bang chi tieu co ban (LDR/SFL), 4 cot = bang ty le an toan von (CAR).
- Dan bao nhieu khoi cung duoc, lap lai ngay cu cung duoc (dedup keep-last).
- Co the dat nhieu file trong paste/, tool doc het *.txt va *.html.

    python paste_sbv.py            # doc paste/, in ra bang kiem tra, gop vao master
    python paste_sbv.py --dry      # chi in, khong ghi

Ket qua ghi vao transmission-master.csv va sbv_paste_state.json (de backfill_sbv_archive
biet ban nao da co, khong tai lai). Sau do chay: python fetch_all.py --build
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import sys

from bs4 import BeautifulSoup

from backfill_sbv_archive import PARSER, _norm
from common import MASTER, log, merge_master, setup_stdout

ROOT = os.path.dirname(os.path.abspath(__file__))
PASTE_DIR = os.path.join(ROOT, "paste")
PASTE_STATE = os.path.join(ROOT, "sbv_paste_state.json")

HEAD = re.compile(r"^\s*##\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*(\w+)?\s*$", re.M)


def _rows_from_html(html: str) -> list[list[str]]:
    """<tbody>/<table>/bat ky -> [[cell, ...], ...]. Bo dong rong."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if cells:
            out.append(cells)
    return out


def _guess_kind(rows) -> str | None:
    """7 cot = chi tieu co ban; 4 cot co dong 'Nhom ...' = CAR."""
    widths = [len(r) for r in rows]
    if any(w >= 7 for w in widths):
        return "chi_tieu"
    if any(w >= 4 for w in widths) and any(_norm(r[0]).startswith("nhom") for r in rows):
        return "car"
    return None


def parse_blocks(text: str, src: str):
    """-> [(date, kind, rows, warn)]"""
    heads = list(HEAD.finditer(text))
    if not heads:
        return [(None, None, [], "khong thay dong '## dd/mm/yyyy' nao trong %s" % src)]
    out = []
    for i, m in enumerate(heads):
        d, mo, y, kind = m.group(1), m.group(2), m.group(3), (m.group(4) or "").lower()
        date = "%s-%02d-%02d" % (y, int(mo), int(d))
        body = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        rows = _rows_from_html(body)
        warn = ""
        if not rows:
            warn = "khong co dong <tr> nao"
        elif kind not in ("car", "chi_tieu"):
            kind = _guess_kind(rows) or ""
            if not kind:
                warn = "khong doan duoc loai bang (can 7 cot hoac 4 cot co dong 'Nhom')"
        out.append((date, kind, rows, warn))
    return out


def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="chi in, khong ghi")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(PASTE_DIR, "*.txt"))
                   + glob.glob(os.path.join(PASTE_DIR, "*.html")))
    if not files:
        os.makedirs(PASTE_DIR, exist_ok=True)
        log("Chua co file nao trong %s - tao file paste.txt roi dan vao." % PASTE_DIR)
        return

    allrows, done, bad = [], {}, 0
    for f in files:
        text = open(f, encoding="utf-8-sig").read()
        for date, kind, rows, warn in parse_blocks(text, os.path.basename(f)):
            if warn:
                log("  ! %s %s: %s" % (os.path.basename(f), date or "", warn))
                bad += 1
                continue
            fn = PARSER[kind][0]
            recs = fn(rows, date)
            for r in recs:
                r["source"] = "SBV (dan tay)"
            key = "%s|%s" % (kind, date)
            done[key] = dict(kind=kind, date=date, file=os.path.basename(f),
                             n=len(recs), at=dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
            allrows += recs
            vals = ", ".join("%s=%g" % (r["series_id"], r["value"]) for r in recs)
            log("  %-8s %s -> %2d chi tieu: %s" % (kind, date, len(recs), vals))

    log("Tong: %d khoi hop le, %d khoi loi, %d dong chi tieu" % (len(done), bad, len(allrows)))
    if args.dry or not allrows:
        return

    st = {}
    if os.path.exists(PASTE_STATE):
        st = json.load(open(PASTE_STATE, encoding="utf-8"))
    st.update(done)
    json.dump(st, open(PASTE_STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    df = merge_master(allrows, MASTER)
    log("Da gop vao master: %d dong, %d series. Chay tiep: python fetch_all.py --build"
        % (len(df), df["series_id"].nunique()))


if __name__ == "__main__":
    main()
