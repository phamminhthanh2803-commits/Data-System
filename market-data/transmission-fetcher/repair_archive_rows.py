# -*- coding: utf-8 -*-
"""Doc lai toan bo cac ban da tai ve trong sbv_cache/ bang bo parser HIEN TAI.

Vi sao can: hai loi cua parser cu da lam hong mot phan du lieu archive.
  1. `pick()` chi quet 3 dong dau moi bang -> truot het cac ban 2023-2024 vi chung co
     them dong tieu de va dong don vi truoc dong ten cot. Nhung ban do bi ghi la "rong".
  2. SBV danh so khong nhat quan: ban 2022-2024 kieu My ("2,140,824.1"), ban khac kieu
     Viet ("2.039.967,8"). Doc nham quy uoc bien LDR 83,16% thanh 8316 - sai ma van co
     ve la mot con so that, nen khong the phat hien bang mat.

Cach chay:
    python repair_archive_rows.py            # doc lai tu cache, chua ghi vao master
    python repair_archive_rows.py --merge    # doc lai xong gop luon vao master

Ban nao KHONG co trong cache ma dang giu gia tri phi ly thi bi xoa khoi state de lan
backfill sau tai lai - khong doan, khong nhan he so.
"""
from __future__ import annotations

import argparse
import json

import backfill_sbv_archive as B
from common import MASTER, log, merge_master, setup_stdout

# nguong tinh tao: LDR/SFL/CAR la phan tram hai chu so, ra ngoai khoang nay la doc sai
SANE = {"ldr": (30.0, 130.0), "sfl": (5.0, 60.0), "car": (5.0, 40.0)}


def implausible(rows):
    for x in rows:
        for pre, (lo, hi) in SANE.items():
            if x["series_id"].startswith(pre) and not lo <= x["value"] <= hi:
                return True
    return False


def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge", action="store_true", help="gop vao master sau khi doc lai")
    args = ap.parse_args()

    st = json.load(open(B.STATE, encoding="utf-8"))
    ent, rows = st["entries"], st["rows"]
    reparsed = gained = lost = dropped = 0

    for url in list(rows):
        e = ent.get(url)
        if not e:
            continue
        html = B._cached(url)
        if html is None:
            if implausible(rows[url]):
                del rows[url]
                dropped += 1
            continue
        new = B.read_tables(B.tables(html), e["kind"], e["date"])
        before = len(rows[url])
        if implausible(new):
            log("  ! %s %s van phi ly sau khi doc lai - bo qua" % (e["kind"], e["date"]))
            continue
        rows[url] = new
        reparsed += 1
        if len(new) > before:
            gained += 1
        elif len(new) < before:
            lost += 1

    json.dump(st, open(B.STATE, "w", encoding="utf-8"), ensure_ascii=False)
    log("Doc lai %d ban tu cache: %d ban nhieu chi tieu hon, %d ban it hon." %
        (reparsed, gained, lost))
    if dropped:
        log("Xoa %d ban co so phi ly ma khong co cache - lan backfill sau se tai lai."
            % dropped)

    allrows = [r for rs in rows.values() for r in rs]
    bad = sum(implausible([x]) for x in allrows)
    log("Tong %d chi tieu trong state, %d gia tri con phi ly." % (len(allrows), bad))

    if args.merge and allrows:
        df = merge_master(allrows, MASTER)
        log("Da gop vao master: %d dong, %d series." % (len(df), df["series_id"].nunique()))


if __name__ == "__main__":
    main()
