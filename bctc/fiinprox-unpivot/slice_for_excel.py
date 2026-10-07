# -*- coding: utf-8 -*-
r"""
slice_for_excel.py
------------------
Cắt file long khổng lồ (fiinprox_facts_all.csv ~GB) thành file Excel GỌN, mở được ngay.

Vì Excel chỉ chứa ~1.048.576 dòng nên không mở nổi file 4.6 triệu dòng. Script này
lọc theo mã (và tần suất Q/Y), rồi PIVOT về dạng WIDE (chỉ tiêu × kỳ) — đúng kiểu
bảng FiinProX gốc nhưng đã sạch — xuất .xlsx, mỗi báo cáo (BS/IS/CF/NOTE) 1 sheet.

Dùng:
    python slice_for_excel.py --ticker HCM
    python slice_for_excel.py --ticker HCM --freq Y
    python slice_for_excel.py --ticker "Alpha Securities" --freq Q
    python slice_for_excel.py --ticker HCM --long      # giữ dạng long thay vì wide
    python slice_for_excel.py --ticker HCM --src "D:\\...\\fiinprox_facts_all.csv"

Mặc định đọc output\fiinprox_facts_all.csv cạnh script, xuất ra output\excel\<MÃ>_<Q|Y>.xlsx
"""
import os
import csv
import argparse

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = os.path.join(HERE, "output", "fiinprox_facts_all.csv")
STMT_ORDER = ["BS", "IS", "CF", "NOTE", "CAR"]


def read_ticker(src, ticker, freq):
    """Đọc theo chunk, chỉ giữ dòng đúng mã + tần suất (nhẹ RAM)."""
    tkr = ticker.strip().upper()
    keep = []
    for chunk in pd.read_csv(src, chunksize=200_000, dtype=str):
        m = (chunk["ticker"].str.upper() == tkr)
        if freq:
            m &= (chunk["freq"] == freq)
        if m.any():
            keep.append(chunk[m])
    if not keep:
        return pd.DataFrame()
    df = pd.concat(keep, ignore_index=True)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["row_order"] = pd.to_numeric(df["row_order"], errors="coerce")
    return df


def order_periods(cols):
    """Sắp cột kỳ tăng dần: Q1/2012 < Q2/2012 ... ; 2008 < 2009 ..."""
    def key(c):
        c = str(c)
        if "/" in c and c[0].upper() == "Q":
            q, y = c[1:].split("/")
            return (int(y), int(q))
        try:
            return (int(c), 0)
        except ValueError:
            return (9999, 0)
    return sorted(cols, key=key)


def to_wide(df):
    """Mỗi statement_code -> 1 bảng wide (chỉ tiêu × kỳ), giữ thứ tự gốc.

    Pivot theo (row_order, parent, metric) để KHÔNG gộp nhầm chỉ tiêu trùng tên
    (vd 'Khối lượng Cổ phiếu' của CTCK và của NĐT).
    """
    df = df.copy()
    df["row_order"] = pd.to_numeric(df["row_order"], errors="coerce")
    if "parent" not in df.columns:
        df["parent"] = ""
    df["parent"] = df["parent"].fillna("")
    out = {}
    for sc in [s for s in STMT_ORDER if s in set(df["statement_code"])]:
        sub = df[df["statement_code"] == sc]
        cols = order_periods(sub["period"].unique())
        piv = (sub.pivot_table(index=["row_order", "parent", "metric"], columns="period",
                               values="value", aggfunc="first")
                  .reindex(columns=cols).sort_index(level="row_order").reset_index())
        piv = piv.drop(columns="row_order").rename(
            columns={"parent": "Chỉ tiêu cha", "metric": "Chỉ tiêu"})
        out[sc] = piv
    return out


def main():
    ap = argparse.ArgumentParser(description="Cắt 1 mã ra Excel gọn (wide).")
    ap.add_argument("--ticker", required=True, help="Mã CK / tên (vd HCM, 'Alpha Securities')")
    ap.add_argument("--freq", default="Q", choices=["Q", "Y", ""], help="Q=quý (mặc định), Y=năm, ''=cả hai")
    ap.add_argument("--long", action="store_true", help="Giữ dạng long thay vì pivot wide")
    ap.add_argument("--src", default=DEFAULT_SRC, help="File long nguồn")
    ap.add_argument("--outdir", default=os.path.join(HERE, "output", "excel"))
    args = ap.parse_args()

    if not os.path.isfile(args.src):
        raise SystemExit("Không thấy file nguồn: " + args.src)

    print("Đang lọc mã", args.ticker, "...")
    df = read_ticker(args.src, args.ticker, args.freq)
    if df.empty:
        raise SystemExit("Không có dữ liệu cho mã/tần suất này. Kiểm tra lại tên mã.")

    os.makedirs(args.outdir, exist_ok=True)
    tag = "".join(ch if ch.isalnum() else "_" for ch in args.ticker).strip("_")
    suffix = args.freq or "QY"
    out = os.path.join(args.outdir, f"{tag}_{suffix}.xlsx")

    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        if args.long:
            df.sort_values(["statement_code", "row_order", "period"]).to_excel(
                xw, sheet_name="long", index=False)
        else:
            for sc, piv in to_wide(df).items():
                piv.to_excel(xw, sheet_name=sc, index=False)  # sheet BS/IS/CF/NOTE
    print(f"Xong -> {out}  ({len(df):,} dòng, {df['period'].nunique()} kỳ)")


if __name__ == "__main__":
    main()
