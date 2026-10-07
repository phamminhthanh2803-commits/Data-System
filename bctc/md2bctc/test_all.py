# -*- coding: utf-8 -*-
"""Chạy md2bctc trên mọi file .md, in báo cáo consistency (KHÔNG ghi master)."""
import os
import glob
import sys
import io
from collections import Counter

import md2bctc as m

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

FOLDER = r"D:\bctc\pdf-detector\downloads\SSI"


def process(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    ticker = m._guess_ticker(path)
    meta, fmt0, recs, notes = m.process_file(text, ticker, "")
    fmt = {"TT334/2016": "NEW", "TT96/2008": "OLD", "BC-ATTC (TT226)": "CAR"}.get(fmt0, fmt0)

    # quality
    def q(r, st=""):
        return m.row_quality(r.get("value"), r.get("chi_tieu", ""), r.get("flag", ""), st)[0]
    dirty = sum(1 for r in recs if q(r, r.get("statement", "")) == "dirty")
    ndirty = sum(1 for r in notes if q(r) == "dirty")

    # balance check (dùng hàm chung)
    checks = ["OK" if ok else "LECH" for _lbl, _ta, _le, ok in m.balance_check(recs)]
    bal = "/".join(checks)

    c = Counter(r.get("statement") for r in recs)
    counts = " ".join("%s=%d" % (k[:3], v) for k, v in sorted(c.items()))
    return {
        "file": os.path.basename(path)[:8], "fmt": fmt,
        "year": meta["fiscal_year"] or "?", "ky": meta["period_label"],
        "cons": meta["consolidated"], "nrec": len(recs), "nnote": len(notes),
        "dirty": dirty, "ndirty": ndirty, "bal": bal, "counts": counts,
    }


def main():
    files = sorted(glob.glob(os.path.join(FOLDER, "*.md")))
    print("%-8s %-3s %-5s %-3s %-2s %5s %5s %5s %5s %-7s %s" %
          ("FILE", "FMT", "YEAR", "KY", "C", "REC", "DIRTY", "NOTE", "NDIRT", "BAL", "COUNTS"))
    print("-" * 120)
    rows = []
    for p in files:
        try:
            r = process(p)
            rows.append(r)
            print("%-8s %-3s %-5s %-3s %-2s %5d %5d %5d %5d %-7s %s" %
                  (r["file"], r["fmt"], r["year"], r["ky"], r["cons"],
                   r["nrec"], r["dirty"], r["nnote"], r["ndirty"], r["bal"] or "-", r["counts"]))
        except Exception as e:
            print("%-8s ERROR: %s" % (os.path.basename(p)[:8], e))
    print("-" * 120)
    # Cảnh báo bất thường
    print("\n== ANOMALIES ==")
    n_zero = n_lech = n_explode = n_ok = 0
    for r in rows:
        warns = []
        if r["nrec"] == 0 and r["fmt"] != "CAR":
            warns.append("0 rows"); n_zero += 1
        if "LECH" in (r["bal"] or ""):
            warns.append("balance LECH (loi OCR?)"); n_lech += 1
        if r["year"] == "?":
            warns.append("no year")
        # explosion: 1 báo cáo có số dòng phi lý (income/balance > 250)
        if any(("inc=" in p or "bal=" in p) and int(p.split("=")[1]) > 250
               for p in r["counts"].split()):
            warns.append("explosion (OCR nat)"); n_explode += 1
        if warns:
            print("  %s [%s %s %s]: %s" % (r["file"], r["fmt"], r["year"], r["ky"], ", ".join(warns)))
        elif r["nrec"] > 0:
            n_ok += 1
    print("\n== TONG KET: %d file | OK=%d | LECH=%d | explosion=%d | 0-rows=%d =="
          % (len(rows), n_ok, n_lech, n_explode, n_zero))


if __name__ == "__main__":
    main()
