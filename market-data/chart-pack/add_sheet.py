# -*- coding: utf-8 -*-
r"""
add_sheet.py - THEM sheet du lieu vao Chart_Pack_TTCK.xlsx ma KHONG dung toi
cac sheet/chart user da chinh sua.

Dung Excel COM (pywin32) chu khong dung openpyxl: openpyxl load->save co the lam
hong chart/dinh dang do user tu ve. COM mo dung file Excel dang co, chi them sheet
moi (hoac ghi de dung sheet do neu da ton tai) roi luu lai.

Chay:  python add_sheet.py            # them 06_GTGD_ThiTruong + 06b_GTGD_KhuVuc
       python add_sheet.py --months 24
"""
import argparse
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data"))
IDXD = os.path.join(BASE, "index-fetcher")
XLSX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Chart_Pack_TTCK.xlsx")


def build_gtgd(months: int):
    """GTGD thi truong VN theo ngay (ty VND) + GTGD khu vuc theo thang (trieu USD)."""
    idx = pd.read_csv(os.path.join(IDXD, "indices-master.csv"), dtype={"date": str})
    idx["date"] = pd.to_datetime(idx.date)

    vn = idx[idx.index_code.isin(["VNINDEX", "HNXINDEX", "UPCOM"])]
    val = vn.pivot_table(index="date", columns="index_code", values="value", aggfunc="last") / 1e3
    vol = vn.pivot_table(index="date", columns="index_code", values="volume", aggfunc="last") / 1e6
    val = val.rename(columns={"VNINDEX": "GTGD HOSE", "HNXINDEX": "GTGD HNX", "UPCOM": "GTGD UPCoM"})
    vol = vol.rename(columns={"VNINDEX": "KLGD HOSE (triệu CP)", "HNXINDEX": "KLGD HNX (triệu CP)",
                              "UPCOM": "KLGD UPCoM (triệu CP)"})

    END = val.dropna(subset=["GTGD HOSE"]).index.max()
    now = pd.Timestamp.now()
    if END.normalize() == now.normalize() and now.hour < 15:
        END = val.index[val.index < now.normalize()].max()   # bo phien dang chay
    START = END - pd.DateOffset(months=months)

    d = pd.concat([val[["GTGD HOSE", "GTGD HNX", "GTGD UPCoM"]],
                   vol[["KLGD HOSE (triệu CP)", "KLGD HNX (triệu CP)", "KLGD UPCoM (triệu CP)"]]], axis=1)
    d["GTGD toàn thị trường"] = d[["GTGD HOSE", "GTGD HNX", "GTGD UPCoM"]].sum(axis=1, min_count=1)
    d["MA20 GTGD toàn TT"] = d["GTGD toàn thị trường"].rolling(20).mean()
    d["MA50 GTGD toàn TT"] = d["GTGD toàn thị trường"].rolling(50).mean()
    d["VN-Index"] = idx[idx.index_code == "VNINDEX"].set_index("date").close.reindex(d.index).ffill()
    d = d.loc[START:END]
    d = d[["GTGD HOSE", "GTGD HNX", "GTGD UPCoM", "GTGD toàn thị trường",
           "MA20 GTGD toàn TT", "MA50 GTGD toàn TT",
           "KLGD HOSE (triệu CP)", "KLGD HNX (triệu CP)", "KLGD UPCoM (triệu CP)", "VN-Index"]]
    d.index.name = "Ngày"

    # --- GTGD khu vuc: binh quan phien theo thang, trieu USD (value_usd da co san)
    REG = {"VNINDEX": "Việt Nam (HOSE)", "KOSPI": "Hàn Quốc (KOSPI)", "TAIEX": "Đài Loan (TWSE)",
           "SET": "Thái Lan (SET)", "JCI": "Indonesia (IDX)", "FBMKLCI": "Malaysia (Bursa)",
           "SSEC": "Trung Quốc (Thượng Hải)", "SZSEC": "Trung Quốc (Thâm Quyến)",
           "HSI": "Hồng Kông (HSI)", "N225": "Nhật (Nikkei)"}
    r = idx[idx.index_code.isin(REG) & idx.value_usd.notna() & (idx.date >= START)].copy()
    r["ym"] = r.date.dt.to_period("M")
    m = r.pivot_table(index="ym", columns="index_code", values="value_usd", aggfunc="mean")
    m = m.rename(columns=REG).reindex(columns=[v for v in REG.values() if v in m.rename(columns=REG).columns])
    m.index = pd.Index([f"{p.month:02d}/{p.year}" for p in m.index], name="Tháng")
    return d.round(1), m.round(0), START, END


EPOCH = pd.Timestamp("1899-12-30")


def write_sheet(ws, df, index_label):
    """Ghi 1 DataFrame vao worksheet COM: 1 lan gan mang 2 chieu cho nhanh.

    Cot dau: ngay ghi bang SO SERIAL cua Excel (pywin32 doi datetime sang gio UTC
    -> lech 1 ngay), con nhan dang chu ("09/2026") phai dat NumberFormat "@" TRUOC
    khi ghi, neu khong Excel tu ep thanh ngay.
    """
    header = [index_label] + [str(c) for c in df.columns]
    is_date = isinstance(df.index, pd.DatetimeIndex)
    nrow = len(df)

    ws.Range(ws.Cells(1, 1), ws.Cells(1, len(header))).Value = [header]
    if nrow:
        ws.Range(ws.Cells(2, 1), ws.Cells(1 + nrow, 1)).NumberFormat = "dd/mm/yyyy" if is_date else "@"
    body = []
    for ix, row in zip(df.index, df.itertuples(index=False, name=None)):
        first = float((pd.Timestamp(ix).normalize() - EPOCH).days) if is_date else str(ix)
        body.append([first] + [None if (isinstance(v, float) and np.isnan(v)) else v for v in row])
    if body:
        ws.Range(ws.Cells(2, 1), ws.Cells(1 + len(body), len(header))).Value = body
    ws.Rows(1).Font.Bold = True
    ws.Rows(1).WrapText = True
    ws.Rows(1).RowHeight = 30
    ws.Range(ws.Cells(2, 2), ws.Cells(1 + len(body), len(header))).NumberFormat = "#,##0.0"
    ws.Columns.AutoFit()
    for c in range(1, len(header) + 1):
        if ws.Columns(c).ColumnWidth > 22:
            ws.Columns(c).ColumnWidth = 22
    ws.Activate()
    ws.Application.ActiveWindow.FreezePanes = False
    ws.Range("B2").Select()
    ws.Application.ActiveWindow.FreezePanes = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=12)
    args = ap.parse_args()

    daily, monthly, START, END = build_gtgd(args.months)
    print("Ky: %s -> %s | GTGD ngay %d dong, GTGD khu vuc %d thang"
          % (START.date(), END.date(), len(daily), len(monthly)))
    print("GTGD binh quan 20 phien gan nhat: {:,.0f} ty VND"
          .format(daily["GTGD toàn thị trường"].tail(20).mean()))

    bak = XLSX.replace(".xlsx", "_backup.xlsx")
    import shutil
    shutil.copy2(XLSX, bak)
    print("Backup ->", bak)

    import win32com.client as win32
    excel = win32.gencache.EnsureDispatch("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    wb = excel.Workbooks.Open(XLSX)
    try:
        ten = {"06_GTGD_ThiTruong": (daily, "Ngày"), "06b_GTGD_KhuVuc": (monthly, "Tháng")}
        for name, (df, lab) in ten.items():
            cu = None
            for ws in wb.Worksheets:
                if ws.Name == name:
                    cu = ws
                    break
            if cu is not None:          # da co -> xoa sach noi dung, giu nguyen vi tri
                cu.Cells.Clear()
                ws = cu
            else:
                ws = wb.Worksheets.Add(After=wb.Worksheets(wb.Worksheets.Count))
                ws.Name = name
            write_sheet(ws, df, lab)
            print("  da ghi %s: %d dong x %d cot" % (name, len(df), len(df.columns) + 1))
        wb.Worksheets(1).Activate()
        wb.Save()
    finally:
        wb.Close(SaveChanges=True)
        excel.Quit()
    print("XONG ->", XLSX)


if __name__ == "__main__":
    main()
