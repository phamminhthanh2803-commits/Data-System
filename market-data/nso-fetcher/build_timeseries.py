# -*- coding: utf-8 -*-
"""build_timeseries.py - dung file Excel phan tich chuoi thoi gian tu nso_master.csv (khong keo mang).

    python build_timeseries.py                       # tat ca bang -> nso_timeseries.xlsx
    python build_timeseries.py --tables V11.06,V03.01 --out cpi.xlsx
    python build_timeseries.py --db "Chỉ số giá" --freq M

Sheet "DANH MUC": 1 dong / sheet (db, table_id, title, dims, freq, n_series, first, last, updated).
Moi bang 1 sheet (ten = table_id, them _M/_A/_Q neu bang co nhieu tan suat): cot A = date, moi cot sau = 1 series
(nhan = dim1 | dim2 | dim3), dong 1 = tieu de bang, dong 2 = don vi (neu tach duoc), dong 3 = header.
Gia tri "So bo"/"Uoc tinh" khong danh dau trong sheet rong - xem cot status trong nso_master.csv.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from mdlib import log, setup_stdout                               # noqa: E402

MASTER = os.path.join(HERE, "nso_master.csv")
CATALOG = os.path.join(HERE, "nso_catalog.csv")
OUT = os.path.join(HERE, "nso_timeseries.xlsx")
MAX_COLS = 16000


def sheet_name(tid: str, suffix: str = "") -> str:
    name = re.sub(r'[\[\]:*?/\\]', "_", tid) + suffix
    return name[:31]


def build(tables=None, dbs=None, freq=None, out: str = OUT) -> str | None:
    if not os.path.exists(MASTER):
        log(f"X chua co {MASTER}")
        return None
    df = pd.read_csv(MASTER, dtype={"date": str, "status": str, "dim1": str, "dim2": str, "dim3": str, "unit": str},
                     encoding="utf-8-sig", keep_default_na=False)
    cat = pd.read_csv(CATALOG, dtype=str, encoding="utf-8-sig", keep_default_na=False) if os.path.exists(CATALOG) \
        else pd.DataFrame(columns=["db", "table_id", "title"])
    if dbs:
        keep = set(cat[cat["db"].isin(dbs)]["table_id"])
        df = df[df["table_id"].isin(keep)]
    if tables:
        df = df[df["table_id"].isin(tables)]
    if freq:
        df = df[df["freq"].isin(list(freq))]
    if df.empty:
        log("X khong co dong nao sau khi loc")
        return None
    df = df[df["date"] != ""]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["pos"] = pd.to_numeric(df.get("pos", 0), errors="coerce").fillna(0)
    label = df["dim1"].copy()
    for c in ("dim2", "dim3"):
        label = label.where(df[c] == "", label + " | " + df[c])
    df["label"] = label.where(label != "", "value")
    title_of = dict(zip(cat["table_id"], cat["title"]))
    rows_cat = []
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        pd.DataFrame().to_excel(xw, sheet_name="DANH MUC")        # giu cho sheet dau
        for tid, g in df.groupby("table_id", sort=True):
            freqs = sorted(g["freq"].unique())
            for fq in freqs:
                gg = g[g["freq"] == fq]
                wide = gg.pivot_table(index="date", columns="label", values="value", aggfunc="last", sort=True)
                order = gg.groupby("label")["pos"].min().sort_values().index
                wide = wide.reindex(columns=[c for c in order if c in wide.columns])
                if wide.shape[1] > MAX_COLS:
                    log(f"  ! {tid}: {wide.shape[1]} cot > {MAX_COLS}, bo qua")
                    continue
                units = gg.groupby("label")["unit"].first().reindex(wide.columns).fillna("")
                sn = sheet_name(tid, f"_{fq}" if len(freqs) > 1 else "")
                ws = xw.book.create_sheet(sn)
                ws["A1"] = f"{tid} - {title_of.get(tid, '')}"
                ws["A2"] = "Đơn vị"
                for j, u in enumerate(units.tolist(), start=2):
                    ws.cell(row=2, column=j, value=u)
                wide.to_excel(xw, sheet_name=sn, startrow=2, index_label="date")
                ws.freeze_panes = "B4"
                ws.column_dimensions["A"].width = 12
                rows_cat.append({"sheet": sn, "db": next(iter(cat[cat["table_id"] == tid]["db"]), ""),
                                 "table_id": tid, "title": title_of.get(tid, ""), "freq": fq,
                                 "n_series": wide.shape[1], "first": wide.index.min(), "last": wide.index.max(),
                                 "updated": gg["updated"].max()})
        c = pd.DataFrame(rows_cat)
        c.to_excel(xw, sheet_name="DANH MUC", index=False)
        ws = xw.book["DANH MUC"]
        ws.freeze_panes = "A2"
        for col, w in zip("ABCDEFGHI", (14, 34, 12, 90, 6, 9, 9, 9, 11)):
            ws.column_dimensions[col].width = w
    log(f"Da luu {out}: {len(rows_cat)} sheet, {int(c['n_series'].sum()):,} series")
    return out


def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", help="V11.01,V03.01 ...")
    ap.add_argument("--db", help='ten CSDL (cach nhau ";")')
    ap.add_argument("--freq", help="A, M, Q, X (ghep: AM)")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    tables = [t.strip().removesuffix(".px") for t in a.tables.split(",")] if a.tables else None
    dbs = [x.strip() for x in a.db.split(";")] if a.db else None
    return 0 if build(tables, dbs, a.freq, a.out) else 1


if __name__ == "__main__":
    sys.exit(main())
