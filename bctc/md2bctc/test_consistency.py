# -*- coding: utf-8 -*-
"""
Test consistency CHÉO: số 'đầu năm' (prior) của BCTC năm N phải = số 'cuối năm'
(current) của BCTC năm N-1, khớp theo statement+ma_so. Tỷ lệ khớp cao = trích nhất quán.
Cũng kiểm tra nội bộ: Tiền (CĐKT) vs Tiền cuối kỳ (LCTT).
"""
import os
import glob
import sys
import io
from collections import defaultdict

import md2bctc as m

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
FOLDER = r"D:\bctc\pdf-detector\downloads\SSI"


def load_all():
    """Trả về {(cons, period_label, year): (n, file, idx, endcash)} chọn file nhiều dòng nhất."""
    best = {}
    for p in sorted(glob.glob(os.path.join(FOLDER, "*.md"))):
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        meta, fmt, recs, notes = m.process_file(text, m._guess_ticker(p) or "SSI", "")
        if not recs or not meta["fiscal_year"]:
            continue
        key = (meta["consolidated"], meta["period_label"], meta["fiscal_year"])
        if key not in best or len(recs) > best[key][0]:
            idx = {}
            endcash = bscash = None
            for r in recs:
                if r.get("ma_so"):
                    idx[(r["statement"], r["ma_so"], r["period"])] = r["value"]
                ct = m.strip_accents(r.get("chi_tieu", "")).lower()
                if (r.get("statement") == "cash_flow" and r.get("period") == "current"
                        and "tien" in ct and "cuoi" in ct and "dau" not in ct):
                    endcash = r["value"]
                # Tiền trên CĐKT: nhãn 'tiền và ... tương đương tiền' (mã 110 ở TT95, 111 ở TT334)
                if (r.get("statement") == "balance_sheet" and r.get("period") == "current"
                        and bscash is None and "tuong duong tien" in ct):
                    bscash = r["value"]
            best[key] = (len(recs), os.path.basename(p)[:8], idx, endcash, bscash)
    return best


def yoy_check(best):
    print("== YoY: prior(N) vs current(N-1) tren balance_sheet (cons=Y, FY) ==")
    years = sorted(int(y) for (c, pl, y) in best if c == "Y" and pl == "FY")
    for y in years:
        if (y - 1) not in [int(yy) for (c, pl, yy) in best if c == "Y" and pl == "FY"]:
            continue
        cur = best[("Y", "FY", str(y))][2]      # năm N: lấy prior
        prev = best[("Y", "FY", str(y - 1))][2]  # năm N-1: lấy current
        match = mismatch = only = 0
        samples = []
        for (st, ma, per), v in cur.items():
            if st != "balance_sheet" or per != "prior":
                continue
            pv = prev.get((st, ma, "current"))
            if pv is None:
                only += 1
            elif pv == v:
                match += 1
            else:
                mismatch += 1
                if len(samples) < 3:
                    samples.append("ma %s: %s vs %s" % (ma, v, pv))
        tot = match + mismatch
        rate = (100.0 * match / tot) if tot else 0
        print("  %d<-%d: khop %d/%d (%.0f%%) | chi 1 ben:%d %s"
              % (y, y - 1, match, tot, rate, only,
                 ("| " + "; ".join(samples)) if samples else ""))


def cash_check(best):
    print("\n== Noi bo: Tien (CDKT) vs Tien cuoi ky (LCTT) — khop theo NHAN ==")
    n_ok = n_lech = 0
    for (c, pl, y), (n, fn, idx, endcash, bscash) in sorted(best.items()):
        bs = bscash
        if bs is not None and endcash is not None:
            ok = bs == endcash
            n_ok += ok
            n_lech += (not ok)
            if not ok:
                print("  LECH %s %s %s [%s]: BS=%s CF=%s" % (c, pl, y, fn, bs, endcash))
    print("  -> OK=%d | LECH=%d" % (n_ok, n_lech))


def formula_check():
    print("\n== Cong thuc nhung trong nhan ('100=110+130'...) — do chinh xac ==")
    tot_ok = tot_fail = 0
    worst = []
    for p in sorted(glob.glob(os.path.join(FOLDER, "*.md"))):
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        meta, fmt, recs, notes = m.process_file(text, m._guess_ticker(p) or "SSI", "")
        if not recs:
            continue
        v = m.verify_formulas(recs)
        tot_ok += v["ok"]
        tot_fail += v["fail"]
        if v["fail"]:
            worst.append((v["fail"], v["ok"], os.path.basename(p)[:8],
                          meta["fiscal_year"], meta["period_label"], v["fails"][:2]))
    tot = tot_ok + tot_fail
    print("  Tong cong thuc khop: %d/%d (%.1f%%)" % (tot_ok, tot, 100.0 * tot_ok / tot if tot else 0))
    worst.sort(reverse=True)
    print("  Top file nhieu cong thuc LECH (chi ra o sai):")
    for nf, no, fn, y, pl, samples in worst[:8]:
        s = "; ".join("ma %s[%s]: trich=%s vs CT=%s" % (ma, per[:4], tv, cv)
                      for st, per, ma, tv, cv in samples)
        print("    %s %s %s: fail=%d ok=%d | %s" % (fn, y, pl, nf, no, s))


def main():
    best = load_all()
    print("Da load %d ky bao cao\n" % len(best))
    yoy_check(best)
    cash_check(best)
    formula_check()


if __name__ == "__main__":
    main()
