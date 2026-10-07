# -*- coding: utf-8 -*-
r"""compare_sheet.py - sheet "So sánh mã" / "So sánh mã (năm)" + sheet trung gian "Calc_SoSanh" / "Calc_SoSanh_Nam" (16/09/2026).

Tra cứu SO SÁNH NHIỀU MÃ theo chuỗi thời gian: chọn 1 chỉ tiêu (G4, dropdown) + tối đa 12 mã (F8:F19, dropdown), cột = kỳ,
dòng TRUNG VỊ các mã đã chọn + dòng NGÀNH (từ Key ratios), biểu đồ đường bên dưới.
Cách tính: Calc_SoSanh = 12 KHỐI CÔNG TY giống hệt khối công ty của Key ratios (khối b ở dòng 36+110b .. 145+110b: mã lấy từ F8+b của
So sánh mã; dòng 91-145 = INDEX/MATCH vào Data_FS + SUM; dòng 38-64 = công thức tỷ lệ kr_formulas). Ô của "So sánh mã" chỉ còn
=INDEX(Calc_SoSanh!cột kỳ, dòng chỉ tiêu + 110·b) -> công thức ngắn, cùng một logic với Key ratios.
Danh mục chỉ tiêu chọn được (21 tỷ lệ + 55 số liệu gốc) = bảng tbl_ChiTieu trong Data_DM (cột H..O), Name dm_ct_q / dm_ct_y.

Gọi từ build_presentation.py ; chạy riêng để thêm/thay các sheet vào file đang có (file phải đã có Data_FS, Data_DM, Key ratios):
    python compare_sheet.py [--file <xlsx>] [--no-copy]
"""
import argparse, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_presentation import col_letter, com_retry, log, COL0, OUTX, copy_final, FS_COL0   # noqa: E402
import kr_formulas as KF                                                                      # noqa: E402

SHEET = {"Q": "So sánh mã", "Y": "So sánh mã (năm)"}
CALC = {"Q": "Calc_SoSanh", "Y": "Calc_SoSanh_Nam"}
KR_SHEET = {"Q": "Key ratios", "Y": "Key ratios (năm)"}
LIST_NAME = {"Q": "dm_ct_q", "Y": "dm_ct_y"}
N_SLOT, BLOCK = 12, 110
ROW_TITLE, ROW_METRIC, ROW_HDR, ROW0 = 2, 4, 7, 8
ROW_MED = ROW0 + N_SLOT                          # 20
ROW_IND = ROW_MED + 1                            # 21
ROW_CHART = ROW_IND + 2
# (dong Key ratios, dinh dang, dong nganh tuong ung o Key ratios)
RATIOS = [(38, "num", 6), (39, "num", 7), (40, "x", 8), (41, "x", 9), (42, "x", 10), (43, "pct", 11), (46, "pct", 14),
          (47, "pct", 15), (48, "pct", 16), (49, "pct", 17), (50, "pct", 18), (53, "pct", 21), (54, "pct", 22), (55, "pct", 23),
          (56, "pct", 24), (57, "pct", 25), (58, "pct", 26), (59, "pct", 28), (62, "pct", 31), (63, "pct", 32), (64, "pct", 33)]
DM_COL0 = 8                                      # Data_DM: tbl_ChiTieu tu cot H
DM_COLS = ["kr_row", "chi_tieu", "chi_tieu_nam", "loai", "stmt", "row_order", "dinh_dang", "dong_nganh"]
DEFAULT_TICKERS = ["SSI", "VND", "VCI", "HCM", "TCX", "VIX", "SHS", "MBS", "VPX", "VCBS", "LPS", "VCK"]
PURPLE, ORANGE, INPUT, GREY = 0xA03070, 0x00C0FF, 0xCCF2FF, 0xD9D9D9    # BGR


def _fmt(rg, bold=False, fill=None, color=None, size=10, halign=None):
    rg.Font.Name = "Calibri"; rg.Font.Size = size; rg.Font.Bold = bold
    if fill is not None:
        rg.Interior.Color = fill
    if color is not None:
        rg.Font.Color = color
    if halign is not None:
        rg.HorizontalAlignment = halign                 # -4152 right, -4108 center, -4131 left


def metric_items(kr_q):
    """Danh muc chi tieu: 21 ty le (nhan Q/nam tu kr_formulas hoac sheet) + 55 so lieu goc (nhan ngan cot F, dong 91-145 Key ratios)."""
    items, seen = [], set()
    for r, fmt, ind in RATIOS:
        lab_q = KF.LABELS.get(r) or str(kr_q.Cells(r, 6).Value or f"Dòng {r}").strip()
        lab_y = KF.LABELS_Y.get(r) or lab_q
        items.append([r, lab_q, lab_y, "Tỷ lệ", None, None, fmt, ind]); seen.add(lab_q)
    vals = [(80 + j, row[0]) for j, row in enumerate(kr_q.Range(kr_q.Cells(80, 6), kr_q.Cells(85, 6)).Value)] + \
           [(91 + j, row[0]) for j, row in enumerate(kr_q.Range(kr_q.Cells(91, 6), kr_q.Cells(145, 6)).Value)]
    for r, v in vals:
        lab = str(v or "").strip()
        if not lab:
            continue
        if lab in seen:
            lab = f"{lab} [{r}]"
        seen.add(lab)
        stmt, ro = KF.RAW_MAP.get(r, (None, None))
        items.append([r, lab, lab, "Số liệu gốc" if r in KF.RAW_MAP else "Dẫn xuất (tổng)", stmt, ro, "num", None])
    return items


def write_metric_table(wb, items):
    dm = wb.Worksheets("Data_DM")
    for j in range(1, dm.ListObjects.Count + 1):
        if dm.ListObjects(j).Name == "tbl_ChiTieu":
            dm.ListObjects(j).Delete(); break
    n = len(items); c0 = DM_COL0
    dm.Range(dm.Cells(1, c0), dm.Cells(300, c0 + len(DM_COLS) - 1)).ClearContents()
    dm.Range(dm.Cells(1, c0), dm.Cells(1, c0 + len(DM_COLS) - 1)).Value = [DM_COLS]
    dm.Range(dm.Cells(2, c0), dm.Cells(n + 1, c0 + len(DM_COLS) - 1)).Value = items
    lo = dm.ListObjects.Add(1, dm.Range(dm.Cells(1, c0), dm.Cells(n + 1, c0 + len(DM_COLS) - 1)), None, 1); lo.Name = "tbl_ChiTieu"; lo.TableStyle = "TableStyleLight1"
    for nm, j in (("dm_ct_row", 0), ("dm_ct_q", 1), ("dm_ct_y", 2), ("dm_ct_fmt", 6), ("dm_ct_ind", 7)):
        L = col_letter(c0 + j); wb.Names.Add(nm, f"=Data_DM!${L}$2:${L}${n + 1}")
    dm.Columns(c0 + 1).ColumnWidth = 44; dm.Columns(c0 + 2).ColumnWidth = 44
    return n


def _fresh_sheet(wb, name, after):
    """Xoa sheet cung ten (neu co) va tao sheet RONG sau `after`. Ca 2 sheet (So sanh + Calc) phai ton tai truoc khi ghi cong thuc
    tham chieu cheo, neu khong Excel bien '=<sheet chua co>!F8' thanh link ngoai."""
    for i in range(1, wb.Worksheets.Count + 1):
        if wb.Worksheets(i).Name == name:
            wb.Worksheets(i).Delete(); break
    ws = wb.Worksheets.Add(None, after); ws.Name = name
    return ws


def build_calc(wb, ws, freq, periods, fs_cols, kr_ws):
    """Calc sheet: 12 khoi cong ty (dong 36+off: ma ; 38-64+off: ty le ; 91-145+off: so lieu goc)."""
    name = CALC[freq]
    ncol = len(periods)
    ws.Cells(1, 6).Value = (f"SHEET TRUNG GIAN cho '{SHEET[freq]}': {N_SLOT} khối công ty giống khối công ty của Key ratios "
                            f"(khối b: dòng {36 + 0}+{BLOCK}·b .. {145}+{BLOCK}·b; mã = ô F{ROW0}+b của '{SHEET[freq]}'; dữ liệu gốc tra Data_FS). Không sửa tay.")
    _fmt(ws.Cells(1, 6), bold=True)
    ws.Cells(4, 6).Value = "Kỳ"; ws.Range(ws.Cells(4, COL0), ws.Cells(4, COL0 + ncol - 1)).Value = [list(periods)]
    _fmt(ws.Range(ws.Cells(4, 6), ws.Cells(4, COL0 + ncol - 1)), bold=True, fill=PURPLE, color=0xFFFFFF)
    lab_ratio = kr_ws.Range(kr_ws.Cells(37, 5), kr_ws.Cells(64, 6)).Value          # E,F dong 37-64
    lab_extra = kr_ws.Range(kr_ws.Cells(79, 5), kr_ws.Cells(85, 6)).Value          # E,F dong 79-84 (so lieu bo sung CIR)
    lab_raw = kr_ws.Range(kr_ws.Cells(88, 5), kr_ws.Cells(145, 6)).Value           # E,F dong 88-145
    for b in range(N_SLOT):
        off = b * BLOCK
        ws.Cells(36 + off, 6).Value = f"Mã #{b + 1} ▼"; ws.Cells(36 + off, 7).Formula = f"='{SHEET[freq]}'!$F${ROW0 + b}"
        _fmt(ws.Range(ws.Cells(36 + off, 6), ws.Cells(36 + off, 7)), bold=True, fill=ORANGE)
        ws.Range(ws.Cells(37 + off, 5), ws.Cells(64 + off, 6)).Value = lab_ratio
        ws.Range(ws.Cells(79 + off, 5), ws.Cells(85 + off, 6)).Value = lab_extra
        ws.Range(ws.Cells(88 + off, 5), ws.Cells(145 + off, 6)).Value = lab_raw
        KF.write_raw_block(ws, freq, periods, fs_cols, COL0, off, f"$G${36 + off}")
        KF.write(ws, freq, periods, None, COL0, company_only=True, off=off)
    ws.Columns(8).Hidden = True; ws.Columns(5).ColumnWidth = 3; ws.Columns(6).ColumnWidth = 30
    ws.Range(ws.Columns(COL0), ws.Columns(COL0 + ncol - 1)).NumberFormat = "#,##0.00;(#,##0.00);-"
    ws.Tab.Color = GREY
    return ws


def build_one(wb, ws, freq, periods, tickers_avail, n_items):
    name, calc, krn = SHEET[freq], CALC[freq], KR_SHEET[freq]
    ncol = len(periods); c_last = COL0 + ncol - 1; L0, L1 = col_letter(COL0), col_letter(c_last)
    Q = f"'{name}'!"
    ws.Cells.Font.Name = "Calibri"; ws.Cells.Font.Size = 10
    # ---- tieu de + chon chi tieu
    ws.Cells(ROW_TITLE, 6).Value = ("SO SÁNH NHIỀU MÃ THEO THỜI GIAN" + (" – theo quý" if freq == "Q" else " – theo năm")
                                    + f": chọn chỉ tiêu ở G4, tối đa {N_SLOT} mã ở cột F; Trung vị = median các mã đã chọn; Ngành = Key ratios; tính trong sheet {calc}")
    _fmt(ws.Cells(ROW_TITLE, 6), bold=True, size=12)
    ws.Cells(ROW_METRIC, 6).Value = "Chỉ tiêu ▼"; _fmt(ws.Cells(ROW_METRIC, 6), bold=True, fill=PURPLE, color=0xFFFFFF)
    g4 = ws.Cells(ROW_METRIC, 7); g4.Value = (KF.LABELS if freq == "Q" else KF.LABELS_Y)[48]      # mac dinh ROE
    _fmt(g4, bold=True, fill=ORANGE, halign=-4131)
    g4.Validation.Delete(); g4.Validation.Add(3, 1, 1, f"={LIST_NAME[freq]}")
    ws.Range(ws.Cells(ROW_METRIC, 8), ws.Cells(ROW_METRIC, 18)).Interior.Color = ORANGE   # KHONG merge o dropdown: chu tran sang H..R (o trong)
    lst = LIST_NAME[freq]
    ws.Cells(ROW_METRIC, 3).Formula = f'=IFERROR(INDEX(dm_ct_row,MATCH($G${ROW_METRIC},{lst},0)),"")'          # dong Key ratios cua chi tieu
    ws.Cells(ROW_METRIC, 5).Formula = f'=IFERROR(INDEX(dm_ct_fmt,MATCH($G${ROW_METRIC},{lst},0)),"num")'       # dinh dang
    ws.Cells(ROW_METRIC + 1, 4).Formula = f'=IFERROR(1/(1/INDEX(dm_ct_ind,MATCH($G${ROW_METRIC},{lst},0))),"")'   # dong nganh ("" neu khong co)
    ws.Cells(ROW_METRIC + 1, 3).Value = "dòng KR / dòng ngành / định dạng (ẩn)"
    ws.Cells(ROW_METRIC + 1, 6).Formula = f'=IF($D${ROW_METRIC + 1}="","(chỉ tiêu này không có dòng ngành)","")'
    ws.Cells(ROW_METRIC + 1, 6).Font.Italic = True; ws.Cells(ROW_METRIC + 1, 6).Font.Color = 0x808080
    # ---- header
    ws.Cells(ROW_HDR, 6).Value = "Mã CK ▼"; ws.Cells(ROW_HDR, 7).Value = "Mới nhất"
    ws.Range(ws.Cells(ROW_HDR, COL0), ws.Cells(ROW_HDR, c_last)).Value = [list(periods)]
    _fmt(ws.Range(ws.Cells(ROW_HDR, 6), ws.Cells(ROW_HDR, c_last)), bold=True, fill=PURPLE, color=0xFFFFFF)
    ws.Range(ws.Cells(ROW_HDR, 7), ws.Cells(ROW_HDR, c_last)).HorizontalAlignment = -4152
    # ---- slot: =INDEX(Calc!cot ky, dong chi tieu + 110*b)
    defaults = [t for t in DEFAULT_TICKERS if t in tickers_avail][:N_SLOT]
    for s in range(N_SLOT):
        r = ROW0 + s
        f = ws.Cells(r, 6); f.Value = defaults[s] if s < len(defaults) else None
        _fmt(f, bold=True, fill=INPUT, halign=-4108)
        f.Validation.Delete(); f.Validation.Add(3, 1, 1, "=dm_ma_list")
        ws.Range(ws.Cells(r, COL0), ws.Cells(r, c_last)).Formula = [[
            f'=IF(OR($F{r}="",$C${ROW_METRIC}=""),"",IFERROR(IF(INDEX({calc}!{col_letter(COL0 + k)}:{col_letter(COL0 + k)},$C${ROW_METRIC}+{s * BLOCK})="","",'
            f'INDEX({calc}!{col_letter(COL0 + k)}:{col_letter(COL0 + k)},$C${ROW_METRIC}+{s * BLOCK})),""))'
            for k in range(ncol)]]
        ws.Cells(r, 7).Formula = f'=IFERROR(LOOKUP(2,1/({L0}{r}:{L1}{r}<>""),{L0}{r}:{L1}{r}),"")'
    # ---- trung vi + nganh
    ws.Cells(ROW_MED, 6).Value = "Trung vị các mã đã chọn"
    ws.Range(ws.Cells(ROW_MED, COL0), ws.Cells(ROW_MED, c_last)).Formula = [[
        f'=IFERROR(MEDIAN({col_letter(COL0 + k)}{ROW0}:{col_letter(COL0 + k)}{ROW0 + N_SLOT - 1}),"")' for k in range(ncol)]]
    ws.Cells(ROW_IND, 6).Value = f"Ngành ({krn})"
    ws.Range(ws.Cells(ROW_IND, COL0), ws.Cells(ROW_IND, c_last)).Formula = [[
        f'=IF($D${ROW_METRIC + 1}="","",IFERROR(INDEX(\'{krn}\'!{col_letter(COL0 + k)}:{col_letter(COL0 + k)},$D${ROW_METRIC + 1}),""))' for k in range(ncol)]]
    for r in (ROW_MED, ROW_IND):
        ws.Cells(r, 7).Formula = f'=IFERROR(LOOKUP(2,1/({L0}{r}:{L1}{r}<>""),{L0}{r}:{L1}{r}),"")'
        rg = ws.Range(ws.Cells(r, 6), ws.Cells(r, c_last)); rg.Font.Bold = True; rg.Interior.Color = GREY
    ws.Range(ws.Cells(ROW_MED, 6), ws.Cells(ROW_MED, c_last)).Borders(8).LineStyle = 1       # xlEdgeTop
    # ---- dinh dang so theo loai chi tieu (conditional format doi NumberFormat; General de truc Y bieu do khong bi "0")
    val = ws.Range(ws.Cells(ROW0, 7), ws.Cells(ROW_IND, c_last))
    val.NumberFormat = "General"
    val.FormatConditions.Delete()
    fc = val.FormatConditions.Add(Type=2, Formula1=f'=$E${ROW_METRIC}="pct"'); fc.NumberFormat = "0.0%"
    fc = val.FormatConditions.Add(Type=2, Formula1=f'=$E${ROW_METRIC}="x"'); fc.NumberFormat = '0.00"x"'
    fc = val.FormatConditions.Add(Type=2, Formula1=f'=$E${ROW_METRIC}="num"'); fc.NumberFormat = "#,##0;(#,##0);-"
    # ---- bo cuc
    ws.Columns(1).ColumnWidth = 2.7
    for c in (2, 3, 4, 5):
        ws.Columns(c).ColumnWidth = 3
    ws.Range(ws.Columns(3), ws.Columns(5)).EntireColumn.Hidden = True
    ws.Columns(6).ColumnWidth = 24.9; ws.Columns(7).ColumnWidth = 11; ws.Columns(8).ColumnWidth = 2
    ws.Range(ws.Columns(COL0), ws.Columns(c_last)).ColumnWidth = 9 if freq == "Q" else 10
    ws.Activate(); ws.Application.ActiveWindow.DisplayGridlines = False
    ws.Application.ActiveWindow.FreezePanes = False
    ws.Cells(ROW0, COL0).Select(); ws.Application.ActiveWindow.FreezePanes = True
    # ---- bieu do duong: 12 ma + trung vi + nganh
    top = ws.Cells(ROW_CHART, 6).Top; left = ws.Cells(ROW_CHART, 6).Left
    sh = ws.Shapes.AddChart2(227, 4, left, top, 980, 340); ch = sh.Chart          # xlLine
    sh.Placement = 3                                                  # xlFreeFloating: khong co/gian khi an cot (an cot cu = zoom chart)
    while ch.SeriesCollection().Count:
        ch.SeriesCollection(1).Delete()
    for r in list(range(ROW0, ROW0 + N_SLOT)) + [ROW_MED, ROW_IND]:
        s = ch.SeriesCollection().NewSeries()
        s.Name = f"={Q}$F${r}"; s.Values = f"={Q}${L0}${r}:${L1}${r}"; s.XValues = f"={Q}${L0}${ROW_HDR}:${L1}${ROW_HDR}"
        if r == ROW_MED:
            s.Format.Line.DashStyle = 4; s.Format.Line.ForeColor.RGB = 0x404040; s.Format.Line.Weight = 2.25   # msoLineDash
        elif r == ROW_IND:
            s.Format.Line.ForeColor.RGB = 0x000000; s.Format.Line.Weight = 3
    ch.HasTitle = True
    try:
        ch.ChartTitle.Formula = f"={Q}$G${ROW_METRIC}"
    except Exception:                                                # noqa: BLE001
        ch.ChartTitle.Text = "So sánh mã"
    ch.HasLegend = True; ch.Legend.Position = -4107                   # xlLegendPositionBottom
    ch.DisplayBlanksAs = 1                                            # xlNotPlotted
    ws.Range("A1").Select()
    return ws


def build(wb, per_q, per_y, fs_cols):
    dm = wb.Worksheets("Data_DM")
    n = dm.Cells(dm.Rows.Count, 1).End(-4162).Row                     # xlUp
    tickers = {str(v[0]) for v in dm.Range(dm.Cells(2, 1), dm.Cells(n, 1)).Value}
    items = metric_items(wb.Worksheets(KR_SHEET["Q"]))
    n_items = com_retry(lambda: write_metric_table(wb, items))
    out = []
    for freq, per in (("Q", per_q), ("Y", per_y)):
        ws_ss = _fresh_sheet(wb, SHEET[freq], wb.Worksheets(KR_SHEET[freq]))          # tao ca 2 sheet rong TRUOC roi moi ghi cong thuc
        ws_c = _fresh_sheet(wb, CALC[freq], wb.Worksheets(wb.Worksheets.Count))
        com_retry(lambda: build_calc(wb, ws_c, freq, per, fs_cols, wb.Worksheets(KR_SHEET[freq])))
        ws = com_retry(lambda: build_one(wb, ws_ss, freq, per, tickers, n_items))
        log(f"  {ws.Name}: {n_items} chỉ tiêu, {N_SLOT} slot mã, {len(per)} kỳ; {CALC[freq]}: {N_SLOT} khối × (55 gốc + 21 tỷ lệ) × {len(per)} kỳ"); out.append(ws)
    for freq in ("Q", "Y"):                                           # Calc dat truoc Data_FS
        wb.Worksheets(CALC[freq]).Move(wb.Worksheets("Data_FS"))
    wb.Worksheets("DASHBOARD").Activate()
    return out


def _periods(ws):
    vals = ws.Range(ws.Cells(4, COL0), ws.Cells(4, 200)).Value[0]
    out = []
    for v in vals:
        if v is None:
            break
        out.append(str(int(v)) if isinstance(v, float) else str(v))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=OUTX); ap.add_argument("--no-copy", action="store_true")
    a = ap.parse_args()
    import win32com.client as win32
    t0 = time.time()
    xl = win32.DispatchEx("Excel.Application"); xl.Visible = False; xl.DisplayAlerts = False; xl.ScreenUpdating = False
    try:
        wb = xl.Workbooks.Open(os.path.abspath(a.file), UpdateLinks=0)
        xl.Calculation = -4135; xl.EnableEvents = False
        fsw = wb.Worksheets("Data_FS"); hdr = fsw.Range(fsw.Cells(1, FS_COL0), fsw.Cells(1, 300)).Value[0]
        fs_cols = {str(v): FS_COL0 + i for i, v in enumerate(hdr) if v is not None}
        per_q, per_y = _periods(wb.Worksheets(KR_SHEET["Q"])), _periods(wb.Worksheets(KR_SHEET["Y"]))
        build(wb, per_q, per_y, fs_cols)
        xl.Calculation = -4105; xl.CalculateFull()
        wb.Save(); wb.Close(False)
        log(f"-> {a.file} [{time.time() - t0:.0f}s]")
    finally:
        try:
            xl.Quit()
        except Exception:                                            # noqa: BLE001
            pass
    if not a.no_copy and os.path.abspath(a.file) == os.path.abspath(OUTX):
        try:
            copy_final(OUTX)
        except Exception as e:                                       # noqa: BLE001
            log(f"  ! KHONG chep duoc sang OneDrive ({e}) - file dang mo?")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
