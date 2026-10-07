# -*- coding: utf-8 -*-
"""Keo GIA GIAO DICH hang ngay cua trai phieu rieng le tren san HNX (cbonds).

Nguon: POST /thong-ke-thi-truong/danh-sach, bang thu 3 "Thong ke giao dich theo
ma trai phieu" (1 dong = 1 ma x 1 ngay: KL, GT, gia giao dich cuoi ngay).
- Moi ngay server tra DU ~2.300 ma dang ky giao dich (ke ca ma khong khop, gia 0)
  -> chi luu dong co KL > 0.
- Lich su co tu 19/07/2023 (ngay san TPDNRL mo cua). Giao dien chan 15 ngay
  nhung server KHONG chan -> backfill duoc toan bo.
- Gia la GIA THANH TOAN = gia gop (dirty, da gom lai don tich), don vi dong/trai
  phieu. gia_bq = GT/KL (binh quan gia quyen trong ngay, on dinh hon gia cuoi).

Usage:
  python scripts/pull_prices.py update                 # 20 ngay gan nhat, merge
  python scripts/pull_prices.py backfill [--from 2023-07-19] [--to YYYY-MM-DD]
Output: data/processed/bond_prices.csv (long: ngay ISO, ma_gd, kl, gt, gia_cuoi, gia_bq)
"""
import argparse
import csv
import html as H
import os
import re
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hnx_common import BASE, make_session, polite_sleep, write_file_safe

OUT = "data/processed/bond_prices.csv"
FIELDS = ["ngay", "ma_gd", "kl", "gt", "gia_cuoi", "gia_bq"]
PAGE = 20000          # server chap nhan page lon; ~5 MB / 13k dong
MARKET_OPEN = date(2023, 7, 19)


def clean(c):
    return H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip()


def num(s):
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def fetch(sess, token, d_from, d_to, page):
    """d_from/d_to dd/mm/yyyy. Tra ve (rows cua bang 2, tong so ban ghi)."""
    f, t = d_from, d_to
    key = "%s|%s||||%s|%s|%s|%s|%s" % (f, t, t[-4:], f, t, f, t)
    data = [("keySearch", key), ("arrCurrentPage[]", "1"), ("arrCurrentPage[]", str(page)),
            ("arrCurrentPage[]", "1"), ("arrNumberRecord[]", "10"),
            ("arrNumberRecord[]", str(PAGE)), ("arrNumberRecord[]", "10")]
    r = sess.post(BASE + "/thong-ke-thi-truong/danh-sach", data=data,
                  headers={"CP-TOKEN": token}, timeout=300)
    r.raise_for_status()
    if r.text.lstrip().startswith("{"):
        raise RuntimeError("API error: " + r.text[:200])
    tables = re.findall(r"<table.*?</table>", r.text, re.S)
    if len(tables) < 3:
        return [], 0
    tails = re.split(r"</table>", r.text)
    m = re.search(r"Tổng số\s*<b>([\d,\.]+)</b>", tails[3] if len(tails) > 3 else "")
    total = int(re.sub(r"[^\d]", "", m.group(1))) if m else 0
    body = re.search(r"<tbody[^>]*>(.*?)</tbody>", tables[2], re.S)
    rows = []
    if body:
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1), re.S):
            cells = [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(cells) < 6:
                continue
            kl = num(cells[3])
            if kl <= 0:
                continue
            gt, gia = num(cells[4]), num(cells[5])
            d = cells[1].split("/")
            rows.append({"ngay": "%s-%s-%s" % (d[2], d[1], d[0]), "ma_gd": cells[2].strip().upper(),
                         "kl": int(kl), "gt": int(gt), "gia_cuoi": int(gia),
                         "gia_bq": round(gt / kl, 2) if kl else 0})
    return rows, total


def pull_range(sess, token, d0, d1):
    """d0, d1: date -> list rows (chi dong co KL>0)."""
    f, t = d0.strftime("%d/%m/%Y"), d1.strftime("%d/%m/%Y")
    out, page = [], 1
    while True:
        rows, total = fetch(sess, token, f, t, page)
        out.extend(rows)
        print("  %s..%s p%d: %d dong co KL (tong ban ghi %d)" % (f, t, page, len(rows), total), flush=True)
        if page * PAGE >= total or not total:
            break
        page += 1
        polite_sleep()
    return out


def load_existing():
    if not os.path.exists(OUT):
        return []
    return list(csv.DictReader(open(OUT, encoding="utf-8-sig")))


def save(rows):
    rows.sort(key=lambda r: (r["ngay"], r["ma_gd"]))

    def _w(f):
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    if not write_file_safe(OUT, _w):
        sys.exit(2)


def merge(existing, new):
    d = {(r["ngay"], r["ma_gd"]): r for r in existing}
    added = 0
    for r in new:
        k = (r["ngay"], r["ma_gd"])
        if k not in d:
            added += 1
        d[k] = r
    return list(d.values()), added


def month_chunks(d0, d1):
    cur = d0
    while cur <= d1:
        nxt = (cur.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        yield cur, min(nxt, d1)
        cur = nxt + timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["update", "backfill"])
    ap.add_argument("--from", dest="d_from", default=MARKET_OPEN.isoformat())
    ap.add_argument("--to", dest="d_to", default=date.today().isoformat())
    ap.add_argument("--days", type=int, default=20, help="update: so ngay nhin lai")
    a = ap.parse_args()
    existing = load_existing()
    sess, token = make_session("/thong-ke-thi-truong")
    d1 = datetime.strptime(a.d_to, "%Y-%m-%d").date()
    if a.cmd == "update":
        d0 = d1 - timedelta(days=a.days)
        new = pull_range(sess, token, d0, d1)
        rows, added = merge(existing, new)
        save(rows)
        print("bond_prices: +%d dong moi (tong %d, ngay cuoi %s)" % (
            added, len(rows), max((r["ngay"] for r in rows), default="")))
        return
    d0 = datetime.strptime(a.d_from, "%Y-%m-%d").date()
    rows = existing
    for c0, c1 in month_chunks(d0, d1):
        try:
            new = pull_range(sess, token, c0, c1)
        except Exception as e:
            print("  LOI %s..%s: %s (bo qua thang nay)" % (c0, c1, e), flush=True)
            continue
        rows, added = merge(rows, new)
        save(rows)
        print("thang %s: +%d (tong %d)" % (c0.strftime("%Y-%m"), added, len(rows)), flush=True)
        polite_sleep()
    print("backfill xong: %d dong" % len(rows))


if __name__ == "__main__":
    main()
