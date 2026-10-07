# -*- coding: utf-8 -*-
r"""fetch_nso.py - keo TOAN BO bang so lieu kinh te tu PX-Web Cuc Thong ke (NSO) ve 1 file long-format
de lam phan tich chuoi thoi gian.

    python fetch_nso.py                      # 11 CSDL kinh te (pxweb.ECON_DBS), ~230 bang, ~8-10 phut
    python fetch_nso.py --db "Chỉ số giá"    # 1 CSDL (nhieu CSDL: cach nhau dau ;)  |  --db all = moi CSDL ke ca PLV*
    python fetch_nso.py --tables V11.01,V11.06,V03.01    # chi vai bang (khong can .px)
    python fetch_nso.py --list               # chi liet ke bang, khong keo
    python fetch_nso.py --no-excel           # khong dung lai nso_timeseries.xlsx

Output (cung thu muc):
  nso_master.csv     long: date,freq,table_id,series_id,dim1,dim2,dim3,unit,status,value,updated,source
                     date = YYYY (freq A) | YYYY-MM (M) | YYYY-Qn (Q) | chuoi goc nhu "1988-1990" (X)
                     status = "Sơ bộ" / "Ước tính" (nam chua chot) - nam sau NSO chot so thi dong duoc ghi de (khoa khong doi)
                     series_id = table_id|dim1|dim2|dim3 (nhan goc tieng Viet, da bo khoang trang thua)
  nso_catalog.csv    1 dong / bang: db, table_id, title, dims, time_dim, freq, n_series, n_rows, first, last, updated, fetched_at
  raw\<table>.json   JSON-stat goc (de doi chieu)
  nso_timeseries.xlsx  moi bang 1 sheet dang rong (date x series) - build_timeseries.py

Chay theo lich: buoc 'nso' thu Hai trong Market Data AM (Run-Market.ps1). Moi lan keo lai het vi NSO
sua so cu (so bo -> chinh thuc) va PX-Web khong cho biet ngay cap nhat tung bang.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                        # D:\market-data
sys.path.insert(0, HERE)
from mdlib import log, merge_long, safe_to_csv, setup_stdout      # noqa: E402
import pxweb                                                      # noqa: E402

MASTER = os.path.join(HERE, "nso_master.csv")
CATALOG = os.path.join(HERE, "nso_catalog.csv")
RAW = os.path.join(HERE, "raw")
CAT_COLS = ["db", "table_id", "title", "dims", "time_dim", "freq", "n_series", "n_rows", "first", "last",
            "updated", "fetched_at"]


def pick_dbs(s, arg: str | None) -> list[str]:
    if not arg:
        return list(pxweb.ECON_DBS)
    if arg.strip().lower() == "all":
        dbs = pxweb.list_databases(s)
        log(f"PX-Web co {len(dbs)} CSDL: {', '.join(dbs)}")
        return dbs
    return [x.strip() for x in arg.split(";") if x.strip()]


def main() -> int:
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help='ten CSDL (cach nhau ";") hoac "all"; mac dinh 11 CSDL kinh te')
    ap.add_argument("--tables", help="chi keo cac bang nay (V11.01,V03.01 ...)")
    ap.add_argument("--list", action="store_true", help="chi liet ke bang")
    ap.add_argument("--no-excel", action="store_true", help="khong dung nso_timeseries.xlsx")
    ap.add_argument("--sleep", type=float, default=0.8, help="nghi giua 2 bang (giay)")
    a = ap.parse_args()

    log("=== BAT DAU keo NSO PX-Web ===")
    s = pxweb.session()
    want = {t.strip().upper().removesuffix(".PX") for t in (a.tables or "").split(",") if t.strip()}
    tables = []
    for db in pick_dbs(s, a.db):
        tl = pxweb.list_tables(s, db)
        log(f"{db}: {len(tl)} bang")
        tables += tl
    if want:
        tables = [t for t in tables if t["table_id"].upper().removesuffix(".PX") in want]
        miss = want - {t["table_id"].upper().removesuffix(".PX") for t in tables}
        if miss:
            log(f"  ! khong thay bang: {', '.join(sorted(miss))}")
    if a.list:
        for t in tables:
            print(f"{t['db']:<40} {t['table_id']:<14} {t['title']}")
        log(f"Tong {len(tables)} bang")
        return 0
    if not tables:
        log("LOI: khong co bang nao de keo")
        return 1

    os.makedirs(RAW, exist_ok=True)
    rows, cat, fails = [], [], []
    t0 = time.time()
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    for i, t in enumerate(tables, 1):
        tid = t["table_id"].removesuffix(".px")
        d = pxweb.fetch_table(s, t["db"], t["folder"], t["table_id"])
        if d is None:
            fails.append(tid)
            continue
        try:
            with open(os.path.join(RAW, tid + ".json"), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            r, info = pxweb.parse_table(d, tid, t["title"])
        except Exception as e:                                    # noqa: BLE001
            log(f"  X {tid}: loi doc JSON-stat {type(e).__name__}: {e}")
            fails.append(tid)
            continue
        rows += r
        cat.append({"db": t["db"], "table_id": tid, "title": t["title"], **{k: info[k] for k in
                    ("dims", "time_dim", "freq", "n_series", "n_rows", "first", "last", "updated")},
                    "fetched_at": now})
        log(f"  [{i}/{len(tables)}] {tid}: {info['n_rows']} dong, {info['n_series']} series, "
            f"{info['freq']} {info['first']}..{info['last']} | {t['title'][:60]}")
        time.sleep(a.sleep)

    if not rows:
        log("LOI: khong keo duoc bang nao")
        return 1
    df = merge_long(rows, MASTER, keys=["table_id", "series_id", "date"], cols=pxweb.COLS,
                    sort=["table_id", "series_id", "date"])
    # catalog: thay dong cua cac bang vua keo, giu dong bang khac
    new_cat = pd.DataFrame(cat, columns=CAT_COLS)
    if os.path.exists(CATALOG):
        old = pd.read_csv(CATALOG, dtype=str, encoding="utf-8-sig")
        old = old[~old["table_id"].isin(new_cat["table_id"])]
        new_cat = pd.concat([old, new_cat], ignore_index=True)
    new_cat = new_cat.sort_values(["db", "table_id"]).reset_index(drop=True)
    safe_to_csv(new_cat, CATALOG)
    n_m = int((df["freq"] == "M").sum())
    log(f"Da luu {MASTER}: {len(df):,} dong, {df['series_id'].nunique():,} series, "
        f"{df['table_id'].nunique()} bang ({n_m:,} dong thang); catalog {len(new_cat)} bang")
    log(f"Tong: {len(tables) - len(fails)}/{len(tables)} bang OK, {len(rows):,} dong moi/cap nhat, "
        f"{(time.time() - t0) / 60:.1f} phut" + (f" | LOI: {', '.join(fails)}" if fails else ""))
    if not a.no_excel:
        import build_timeseries
        build_timeseries.build()
    log("=== XONG ===")
    return 0 if len(fails) < len(tables) else 1


if __name__ == "__main__":
    sys.exit(main())
