# -*- coding: utf-8 -*-
r"""build_presentation.py — FILE NGÀNH DUY NHẤT IB&Brokerage_Nganh.xlsx dựng TRONG EXCEL (COM)
=> sheet trình bày giữ 100% layout/format/biểu đồ (DASHBOARD, Key ratios, Key ratios (năm), So sánh mã, So sánh mã (năm), FS Industry,
   Drivers, Market Share, Số TK mở mới) + 2 sheet DATA trung gian phục vụ lookup/dropdown (Data_FS, Data_DM) + 2 sheet CALC trung gian
   (Calc_SoSanh, Calc_SoSanh_Nam) + 4 bảng thị trường theo ngày (Data_DinhGia, Data_DinhGia_Ma, Data_NPAT, Data_TK).
Ra: excel_feed\logic\IB&Brokerage_Nganh.xlsx (bản làm việc) -> chép sang OneDrive excel_feed\IB&Brokerage_Nganh.xlsx (file duy nhất giao).

 1. Mở workbook gốc (read-only) -> copy các sheet trình bày sang workbook mới (Sheets.Copy giữ định dạng + chart + tham chiếu nội bộ).
 2. FS Industry, Drivers: đóng băng thành GIÁ TRỊ rồi đổ giá trị pipeline (logic\cells_values.csv, tính bởi build_workbook_logic.py).
 3. Data_FS (tbl_FS) = TOÀN BỘ item BS/IS/CF/NOTE của 87 mã + dòng ALL, theo quý, key = ticker|stmt|row_order (excel_feed\data_fs.csv,
    build_data_fs.py); Data_DM = tbl_Ma (danh mục mã, Name dm_ma_list) + tbl_ChiTieu (danh mục chỉ tiêu tra cứu, compare_sheet.py).
 4. Key ratios: khối ngành (4–33) = CÔNG THỨC tham chiếu FS Industry (kr_formulas.py); dòng 149–174 = giá trị ngành;
    khối công ty: dòng 91–145 = INDEX/MATCH vào Data_FS (cột C/D = báo cáo/row_order, cột H ẩn = vị trí dòng) + dòng tổng SUM,
    dòng 38–64 = công thức tỷ lệ theo định nghĩa PV2. G36 dropdown mã. "Key ratios (năm)": dòng chảy = tổng 4 quý, số dư = Q4.
 5. So sánh mã / (năm) + Calc_SoSanh / _Nam: compare_sheet.py (12 khối công ty giống Key ratios -> bảng so sánh chỉ INDEX 1 dòng).
 6. Số TK mở mới: Table2 ghi đè bằng VSDC tự động; 4 bảng thị trường theo ngày (update_nganh_daily.py ghi đè hàng ngày).
 7. Phá link ngoài còn sót, tính lại, lưu xlsx vào excel_feed\logic\. KHÔNG ghi đè file OneDrive đã có (24/09/2026) trừ khi --replace-final.
Chạy: python build_presentation.py [--wb <workbook gốc>] [--no-data] [--no-copy]   (gọi tự động cuối build_workbook_logic.py)
"""
import argparse, os, sys, time
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "excel_feed", "logic")
OUTX = os.path.join(OUT, "IB&Brokerage_Nganh.xlsx")
FINAL = os.path.join(os.path.expanduser("~"), "OneDrive - Cong ty co phan Dau tu PV2", "excel_feed", "IB&Brokerage_Nganh.xlsx")
VSDC_T2 = os.path.join(os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data")), "vsdc-accounts", "vsdc_tk_ndt_table2.csv")
VSDC_LONG = os.path.join(os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data")), "vsdc-accounts", "vsdc_tk_ndt.csv")
FEED = os.path.join(HERE, "excel_feed")
DATA_FS_CSV = os.path.join(FEED, "data_fs.csv")
DATA_DM_CSV = os.path.join(FEED, "data_dm_ma.csv")
DATA_SHEETS = [   # bang thi truong theo ngay (sheet, ten bang, file csv, cot ngay) - update_nganh_daily.py ghi de hang ngay
    ("Data_DinhGia",    "tbl_DinhGia",    os.path.join(HERE, "valuation_nganh_ck_daily.csv"),  ["date"]),
    ("Data_DinhGia_Ma", "tbl_DinhGia_Ma", os.path.join(HERE, "valuation_ck_stocks_daily.csv"), ["date"]),
    ("Data_NPAT",       "tbl_NPAT",       os.path.join(HERE, "npat_nganh_ck_quarterly.csv"),   ["qend"]),
    ("Data_TK",         "tbl_TK",         VSDC_LONG,                                          ["date", "ngay_bao_cao"]),
]
EPOCH = pd.Timestamp("1899-12-30")
SHEETS = ["DASHBOARD", "FS Industry", "Key ratios", "Drivers", "Market Share", "Số TK mở mới"]   # 2 sheet nguon Drivers copy nguyen (gia tri, bang, pivot)
COL0, NCOL_T = 9, 42
COMPANY_ROWS = list(range(37, 65)) + list(range(91, 146))
INDUSTRY_ROWS = list(range(149, 166))                  # chi dong so lieu goc nganh (thuyet minh) = gia tri; ty le nganh 6-33 = CONG THUC (kr_formulas.py)
PEER_ROWS = list(range(69, 79))                        # khoi peer cu (69-78) de trong; 79-84 = so lieu bo sung CIR chuan bank (kr_formulas.EXTRA_LABELS)
FS_COL0 = 6                                            # data_fs.csv: 5 cot dau (key, ticker, stmt, row_order, label) roi den cac quy


def log(m):
    print(m, flush=True)


def col_letter(c):
    s = ""
    while c:
        c, r = divmod(c - 1, 26); s = chr(65 + r) + s
    return s


def com_retry(fn, tries=60, wait=3):
    """Excel dang ban (vd. vua dong file 68 MB) -> COM tra 'Call was rejected by callee' -> thu lai."""
    import pywintypes
    for i in range(tries):
        try:
            return fn()
        except pywintypes.com_error as e:
            if e.args[0] in (-2147418111, -2147417846) and i < tries - 1:
                time.sleep(wait); continue
            raise


def freeze(ws):
    def _f():
        ur = ws.UsedRange; ur.Value = ur.Value
    com_retry(_f)


def put_values(ws, cells):
    """cells: DataFrame(row, col, value) -> ghi theo từng dòng (1 lệnh COM / dòng)."""
    for r, g in cells.groupby("row"):
        g = g.sort_values("col")
        c0, c1 = int(g.col.min()), int(g.col.max())
        cur = ws.Range(ws.Cells(r, c0), ws.Cells(r, c1)).Value
        cur = list(cur[0]) if isinstance(cur, tuple) else [cur]
        for c, v in zip(g.col, g.value):
            cur[int(c) - c0] = float(v)
        ws.Range(ws.Cells(r, c0), ws.Cells(r, c1)).Value = [cur]


def copy_final(src, replace=False):
    """KHONG ghi de file giao OneDrive (24/09/2026, PV2: chi duoc THEM du lieu, khong dung lai + chep file moi de len).
    File OneDrive da co -> chi bao, giu nguyen; ket qua dung lai nam o src (excel_feed/logic/). Hang ngay dung update_nganh_daily.py (append).
    replace=True (co --replace-final, user yeu cau ro): sao luu ban OneDrive vao excel_feed/_backup/ roi thay nguyen tu (os.replace)."""
    import shutil
    if os.path.exists(FINAL) and not replace:
        log(f"  (KHONG ghi de {FINAL} - ban dung lai o {src}; thay file giao chi khi chay kem --replace-final)")
        return False
    os.makedirs(os.path.dirname(FINAL), exist_ok=True)
    if os.path.exists(FINAL):
        bk = os.path.join(FEED, "_backup"); os.makedirs(bk, exist_ok=True)
        dst = os.path.join(bk, time.strftime("Nganh_OneDrive_truoc-replace_%Y%m%d_%H%M%S.xlsx"))
        shutil.copy2(FINAL, dst); log(f"  sao luu ban OneDrive -> {dst}")
    tmp = FINAL + ".tmp"
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, FINAL)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    log(f"-> {FINAL}")
    return True


def to_serial(sr):
    d = pd.to_datetime(sr, errors="coerce")
    return (d - EPOCH).dt.days.astype("float").where(d.notna(), None)


def sheet_by_name(wb, name):
    for i in range(1, wb.Worksheets.Count + 1):
        if wb.Worksheets(i).Name == name:
            return wb.Worksheets(i)
    return None


def periods_from_data_fs():
    """Danh sach quy trong data_fs.csv + {nhan quy: so cot Data_FS}."""
    hdr = pd.read_csv(DATA_FS_CSV, encoding="utf-8-sig", nrows=0).columns.tolist()
    per = hdr[FS_COL0 - 1:]
    return per, {p: FS_COL0 + i for i, p in enumerate(per)}


def write_table(wb, name, tbl, csv_path, date_cols, chunk=20000):
    """CSV -> sheet moi + bang Excel (ListObject) de PivotTable / lookup. Ghi theo khoi 20k dong (1 lenh COM / khoi)."""
    if not os.path.exists(csv_path):
        log(f"  ! thieu {csv_path} -> bo qua sheet {name}"); return
    df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype={c: str for c in ("period", "stmt")})
    for c in date_cols:
        if c in df.columns:
            df[c] = to_serial(df[c])
    cols = [str(c) for c in df.columns]
    vals = df.astype(object).where(pd.notna(df), None).values.tolist()
    ws = sheet_by_name(wb, name)
    if ws is not None:
        ws.Delete()
    ws = wb.Worksheets.Add(None, wb.Worksheets(wb.Worksheets.Count)); ws.Name = name
    ws.Range(ws.Cells(1, 1), ws.Cells(1, len(cols))).Value = [cols]
    for i in range(0, len(vals), chunk):
        part = vals[i:i + chunk]
        ws.Range(ws.Cells(2 + i, 1), ws.Cells(1 + i + len(part), len(cols))).Value = part
    for c in date_cols:
        if c in cols:
            j = cols.index(c) + 1
            ws.Range(ws.Cells(2, j), ws.Cells(len(vals) + 1, j)).NumberFormat = "yyyy-mm-dd"
    lo = ws.ListObjects.Add(1, ws.Range(ws.Cells(1, 1), ws.Cells(len(vals) + 1, len(cols))), None, 1)   # xlSrcRange, header
    lo.Name = tbl; lo.TableStyle = "TableStyleLight1"
    log(f"  {name}: {len(vals):,} dong x {len(cols)} cot -> bang {tbl}")
    return ws


def write_data_dm(wb):
    """Data_DM: tbl_Ma (A:E) = danh muc ma -> Name dm_ma_list (dropdown). tbl_ChiTieu (tu cot H) do compare_sheet.py ghi."""
    dm = pd.read_csv(DATA_DM_CSV, encoding="utf-8-sig")
    ws = sheet_by_name(wb, "Data_DM")
    if ws is not None:
        ws.Delete()
    ws = wb.Worksheets.Add(None, wb.Worksheets(wb.Worksheets.Count)); ws.Name = "Data_DM"
    cols = list(dm.columns); n = len(dm)
    ws.Range(ws.Cells(1, 1), ws.Cells(1, len(cols))).Value = [cols]
    ws.Range(ws.Cells(2, 1), ws.Cells(n + 1, len(cols))).Value = dm.astype(object).where(pd.notna(dm), None).values.tolist()
    lo = ws.ListObjects.Add(1, ws.Range(ws.Cells(1, 1), ws.Cells(n + 1, len(cols))), None, 1); lo.Name = "tbl_Ma"; lo.TableStyle = "TableStyleLight1"
    wb.Names.Add("dm_ma_list", f"=Data_DM!$A$2:$A${n + 1}")
    ws.Columns(2).ColumnWidth = 40
    log(f"  Data_DM: tbl_Ma {n} ma (dm_ma_list)")
    return sorted(dm.ticker.astype(str))


def write_ms_lists(wb):
    """Data_DM cot Q/R: danh sach DUY NHAT cong ty + san trong tbl_MarketShare -> Name dm_ms_company / dm_ms_market (dropdown Drivers)."""
    ms = wb.Worksheets("Market Share"); lo = ms.ListObjects("tbl_MarketShare")
    body = lo.DataBodyRange.Value
    comp = sorted({str(r[0]).strip() for r in body if r[0]}); mkt = sorted({str(r[1]).strip() for r in body if r[1]})
    dm = wb.Worksheets("Data_DM")
    dm.Range(dm.Cells(1, 17), dm.Cells(2000, 18)).ClearContents()
    dm.Cells(1, 17).Value = "ms_company"; dm.Cells(1, 18).Value = "ms_market"
    dm.Range(dm.Cells(2, 17), dm.Cells(len(comp) + 1, 17)).Value = [[c] for c in comp]
    dm.Range(dm.Cells(2, 18), dm.Cells(len(mkt) + 1, 18)).Value = [[m] for m in mkt]
    wb.Names.Add("dm_ms_company", f"=Data_DM!$Q$2:$Q${len(comp) + 1}"); wb.Names.Add("dm_ms_market", f"=Data_DM!$R$2:$R${len(mkt) + 1}")
    return len(comp), len(mkt)


def restore_drivers(wb, fs_cols):
    """Drivers: tra lai CONG THUC cho 3 khoi co dropdown (bi dong bang thanh gia tri khi copy):
       - Thi phan (12-22): XLOOKUP tbl_MarketShare theo cong ty F12:F22 + san G12 ; dropdown = danh sach duy nhat (Data_DM Q/R)
       - Tai khoan (39-51): SUMIFS/MAXIFS vao Table2 (VSDC cap nhat hang thang tu chay vao)
       - Nguon von (54-62): G55 trong = nganh (FS Industry dong 43/53/54) ; G55 = ma -> tra Data_FS (BS 8 / 142 / 145)
       Thanh khoan (28-35): GIA TRI tu pipeline index-fetcher (drivers_extra.write_gtgd, thay link SharePoint)."""
    ws = wb.Worksheets("Drivers")
    cols = [c for c in range(COL0, COL0 + NCOL_T) if ws.Cells(8, c).Value]
    T2 = "Table2"
    n = 0
    for c in cols:
        L, Lp = col_letter(c), col_letter(c - 1); p = str(ws.Cells(8, c).Value)
        for r in range(12, 23):
            if ws.Cells(r, 6).Value:
                ws.Cells(r, c).Formula2 = (f'=IFNA(XLOOKUP($F{r}&"|"&$G$12&"|"&{L}$8,tbl_MarketShare[company]&"|"&tbl_MarketShare[market]&"|"&tbl_MarketShare[period],'
                                           f'tbl_MarketShare[market-share]),NA())'); n += 1        # NA: bieu do thi phan bo qua ky khong co so (khong ve 0)
        ws.Cells(39, c).Formula = f"={L}$8"; ws.Cells(54, c).Formula = f"={L}$8"
        g = f'COUNTIF({T2}[Time],{L}$39)=0'
        last = f'MAXIFS({T2}[Date],{T2}[Time],{L}$39)'; last_p = f'MAXIFS({T2}[Date],{T2}[Time],{Lp}$39)'
        ws.Cells(40, c).Formula2 = f'=IF({g},"",SUMIFS({T2}[Cá nhân mở thêm  (TK)],{T2}[Time],{L}$39))'
        ws.Cells(41, c).Formula2 = f'=IF({g},"",SUMIFS({T2}[Tổ chức mở thêm (TK)],{T2}[Time],{L}$39))'
        first = c == cols[0]                                          # cot dau: khong co ky truoc -> "" (dong chenh lech)
        for r, col in ((43, "Cá nhân NN"), (44, "Tổ chức NN")):
            ws.Cells(r, c).Formula2 = '=""' if first else (f'=IF({g},"",SUMIFS({T2}[{col}],{T2}[Time],{L}$39,{T2}[Date],{last})'
                                                            f'-SUMIFS({T2}[{col}],{T2}[Date],{last_p}))')
        for r, col in ((47, "Cá nhân"), (48, "Tổ chức"), (50, "Cá nhân NN"), (51, "Tổ chức NN")):
            ws.Cells(r, c).Formula2 = f'=IF({g},"",SUMIFS({T2}[{col}],{T2}[Time],{L}$39,{T2}[Date],{last}))'
        n += 10
        fc = fs_cols.get(p)
        ind = lambda row: f"INDEX('FS Industry'!$U${row}:$BN${row},MATCH({L}$8,'FS Industry'!$U$4:$BN$4,0))"
        if fc is None:
            co = lambda ro: '""'
        else:
            D = col_letter(fc)
            co = lambda ro: f'INDEX(Data_FS!{D}:{D},MATCH($G$55&"|BS|{ro}",Data_FS!$A:$A,0))'
        ws.Cells(55, c).Formula = f'=IF($G$55="",IFERROR({ind(43)}/(2*{ind(53)}),""),IFERROR({co(8)}/(2*{co(142)}),""))'
        ws.Cells(57, c).Formula = f'=IF($G$55="",IFERROR({ind(53)},""),IFERROR({co(142)},""))'
        ws.Cells(58, c).Formula = f'=IF($G$55="",IFERROR({ind(54)},""),IFERROR({co(145)},""))'
        ws.Cells(59, c).Formula = f'=IFERROR({L}57-{L}58,"")'
        ws.Cells(61, c).Formula = '=""' if first else f'=IFERROR({L}58-{Lp}58,"")'
        ws.Cells(62, c).Formula = '=""' if first else f'=IFERROR({L}59-{Lp}59,"")'
        n += 6
    fc = ws.Range(ws.Cells(12, cols[0]), ws.Cells(22, cols[-1])).FormatConditions.Add(Type=16)   # #N/A thi phan -> chu trang (an)
    fc.Font.Color = 0xFFFFFF
    for addr, lst in (("F12:F22", "dm_ms_company"), ("G12", "dm_ms_market"), ("G55", "dm_ma_list")):
        rg = ws.Range(addr); rg.Validation.Delete(); rg.Validation.Add(3, 1, 1, f"={lst}")
    ws.Range("G55").Value = None
    ws.Range("G56").Value = "(trống = toàn ngành; chọn mã để xem room margin / VCSH / vốn góp của mã)"; ws.Range("G56").Font.Italic = True; ws.Range("G56").Font.Size = 8
    log(f"  Drivers: khôi phục {n:,} ô công thức (thị phần XLOOKUP, tài khoản SUMIFS Table2, nguồn vốn G55 → Data_FS); dropdown F12:F22/G12/G55")
    return n


def unmerge_dropdowns(wb):
    """O dropdown KHONG duoc merge (yeu cau 17/09/2026): G4 cua 2 sheet So sanh (chu tran sang H..R)."""
    for sn in ("So sánh mã", "So sánh mã (năm)"):
        ws = sheet_by_name(wb, sn)
        if ws is None:
            continue
        g4 = ws.Range("G4")
        if g4.MergeCells:
            g4.MergeArea.UnMerge()
        ws.Range("H4:R4").Interior.Color = 0x00C0FF


def update_table2(wb):
    """Sheet 'Số TK mở mới': ghi de Table2 (Date..Tổng) bang du lieu VSDC tu dong, keo cong thuc cot tinh, refresh pivot."""
    if not os.path.exists(VSDC_T2):
        log("  ! khong co vsdc_tk_ndt_table2.csv -> giu Table2 cu"); return
    ws = wb.Worksheets("Số TK mở mới")
    lo = ws.ListObjects("Table2")
    hr, c0, ncol = lo.HeaderRowRange.Row, lo.Range.Column, lo.Range.Columns.Count
    n_old = lo.DataBodyRange.Rows.Count
    t2 = pd.read_csv(VSDC_T2, encoding="utf-8-sig")
    first = str(ws.Cells(hr + 1, c0).Value)[:10]                   # giu moc dau cua workbook (2016-01)
    t2 = t2[pd.to_datetime(t2.Date) >= pd.Timestamp(first)].sort_values("Date").reset_index(drop=True)
    n = len(t2)
    f_first = ws.Range(ws.Cells(hr + 1, c0 + 6), ws.Cells(hr + 1, c0 + ncol - 1)).FormulaR1C1
    f_next = ws.Range(ws.Cells(hr + 2, c0 + 6), ws.Cells(hr + 2, c0 + ncol - 1)).FormulaR1C1
    if n > n_old:
        lo.Resize(ws.Range(ws.Cells(hr, c0), ws.Cells(hr + n, c0 + ncol - 1)))
    b = t2.iloc[:, :6].copy(); b["Date"] = to_serial(b["Date"])
    body = [[float(v) for v in row] for row in b.values.tolist()]
    ws.Range(ws.Cells(hr + 1, c0), ws.Cells(hr + n, c0 + 5)).Value = body
    for j in range(ncol - 6):                                        # gan TUNG CHUOI R1C1 cho ca cot (gan mang -> Excel doi offset 2 lan, sai dong)
        ws.Cells(hr + 1, c0 + 6 + j).FormulaR1C1 = f_first[0][j]
        ws.Range(ws.Cells(hr + 2, c0 + 6 + j), ws.Cells(hr + n, c0 + 6 + j)).FormulaR1C1 = f_next[0][j]
    ws.Range(ws.Cells(hr + 1, c0), ws.Cells(hr + n, c0)).NumberFormat = "dd/mm/yyyy"
    ws.Range(ws.Cells(hr + 1, c0 + 1), ws.Cells(hr + n, c0 + 7)).NumberFormat = "#,##0"
    ws.Calculate()                                                   # dang che do tinh tay: tinh cot Nam/Quy/Time truoc khi refresh pivot
    npv = 0
    for i in range(1, ws.PivotTables().Count + 1):
        pt = ws.PivotTables(i)
        try:                                                         # pivot copy theo van tro Table2 cua FILE GOC -> tro ve Table2 file nay
            pt.ChangePivotCache(wb.PivotCaches().Create(1, f"'{ws.Name}'!{lo.Range.Address}"))   # xlDatabase; Address la property (goi ham -> 'str' not callable)
            pt.RefreshTable(); npv += 1
        except Exception as e:                                       # noqa: BLE001
            log(f"  (pivot So TK #{i}) {e}")
    log(f"  Số TK mở mới: Table2 {n_old} -> {n} thang tu VSDC (den {t2.Date.iloc[-1]}), refresh {npv} pivot")


def fill_key_ratios(ws, periods, ind_cells, freq, fs_hdr, fs_cols):
    import kr_formulas as KF
    ncol = len(periods)
    for k in range(NCOL_T):
        c = COL0 + k
        if k < ncol:
            p = periods[k]
            ws.Cells(4, c).Value = p; ws.Cells(36, c).Value = p
            ws.Cells(89, c).Value = int(p[-4:]); ws.Cells(90, c).Value = int(p[1]) if p.startswith("Q") else 4
        else:
            for r0, r1 in ((4, 33), (36, 64), (88, 174)):
                ws.Range(ws.Cells(r0, c), ws.Cells(r1, c)).ClearContents()
    ws.Range(ws.Cells(5, COL0), ws.Cells(33, COL0 + ncol - 1)).ClearContents()      # ty le nganh: bo gia tri cu, ghi cong thuc
    if ind_cells is not None and len(ind_cells):
        put_values(ws, ind_cells)                                                     # 149-165 thuyet minh nganh + 167-174 IS nganh (gia tri)
    for r, lab, *_ in KF.IND_IS_ROWS + KF.IND_DER_ROWS:
        ws.Cells(r, 6).Value = lab
    ws.Cells(166, 6).Value = "DỮ LIỆU GỐC NGÀNH – IS lãi/lỗ từng loại tài sản (tổng toàn bộ mã), nguồn yield ngành dòng 21–24; 175–177: CIR chuẩn bank"
    ws.Range(ws.Cells(69, 5), ws.Cells(85, 6)).ClearContents()                       # nhan khoi peer cu
    for r, (note, lab) in KF.EXTRA_LABELS.items():
        ws.Cells(r, 5).Value = note or None; ws.Cells(r, 6).Value = lab
    ws.Cells(79, 6).Font.Bold = True
    ws.Cells(88, 3).Value = "BC"; ws.Cells(88, 4).Value = "dòng"
    ws.Range(ws.Cells(91, COL0), ws.Cells(145, COL0 + NCOL_T - 1)).ClearContents()
    n_raw = KF.write_raw_block(ws, freq, periods, fs_cols, COL0, 0, "$G$36")        # 91-145: INDEX/MATCH vao Data_FS + SUM
    for r in KF.RATIO_ROWS_CO:
        ws.Cells(r, 8).ClearContents()
    n_ind, n_co = KF.write(ws, freq, periods, fs_hdr, COL0)                          # TY LE = CONG THUC theo dinh nghia da chot
    log(f"  {ws.Name}: so lieu goc {n_raw:,} o (Data_FS), cong thuc ty le nganh {n_ind:,} o, cong ty {n_co:,} o")
    for r in PEER_ROWS:
        ws.Range(ws.Cells(r, COL0), ws.Cells(r, COL0 + NCOL_T - 1)).ClearContents()
    ws.Cells(68, 6).Value = "Khối so sánh peer đã bỏ: dùng sheet 'So sánh mã' (nhiều mã × 1 chỉ tiêu theo thời gian)."


def patch_drivers(no_copy, replace=False):
    import win32com.client as win32
    _, fs_cols = periods_from_data_fs()
    t0 = time.time()
    xl = win32.DispatchEx("Excel.Application"); xl.Visible = False; xl.DisplayAlerts = False; xl.ScreenUpdating = False
    try:
        wb = xl.Workbooks.Open(os.path.abspath(OUTX), UpdateLinks=0)
        xl.Calculation = -4135; xl.EnableEvents = False
        com_retry(lambda: write_ms_lists(wb)); com_retry(lambda: restore_drivers(wb, fs_cols)); unmerge_dropdowns(wb)
        xl.Calculation = -4105; xl.CalculateFull()
        wb.Save(); wb.Close(False)
        log(f"-> {OUTX} [{time.time() - t0:.0f}s]")
    finally:
        try:
            xl.Quit()
        except Exception:                                            # noqa: BLE001
            pass
    if not no_copy:
        copy_final(OUTX, replace)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wb", default=None)
    ap.add_argument("--no-data", action="store_true", help="bo qua 4 bang thi truong theo ngay (chay nhanh de thu)")
    ap.add_argument("--no-copy", action="store_true", help="khong chep sang OneDrive")
    ap.add_argument("--replace-final", action="store_true", help="THAY file giao OneDrive bang ban dung lai (sao luu truoc); mac dinh KHONG ghi de")
    ap.add_argument("--patch-drivers", action="store_true", help="chi va file dang co: Drivers cong thuc + dropdown, bo merge G4 So sanh (khong dung lai)")
    a = ap.parse_args()
    if a.patch_drivers:
        return patch_drivers(a.no_copy, a.replace_final)
    wbp = a.wb or next(p for p in [os.path.join(os.path.expanduser("~"), "Downloads", "IB&Brokerage_Genea_2Q26.xlsx"),
                                    os.path.join(os.path.expanduser("~"), "OneDrive - Cong ty co phan Dau tu PV2", "IB&Brokerage_Genea_2Q26.xlsx")] if os.path.exists(p))
    if not os.path.exists(DATA_FS_CSV):
        log(f"LOI: chua co {DATA_FS_CSV} - chay build_data_fs.py truoc"); return 2
    cells = pd.read_csv(os.path.join(OUT, "cells_values.csv"), encoding="utf-8-sig")
    all_per, fs_cols = periods_from_data_fs()
    per_q = [p for p in all_per if int(p[-4:]) >= 2016][-NCOL_T:]                  # Key ratios: toi da 42 cot ky, tu 2016, cuon theo quy moi
    per_y = [str(y) for y in sorted({int(p[-4:]) for p in per_q}) if all(f"Q{q}-{y}" in all_per for q in (1, 2, 3, 4))]
    import kr_formulas as KF
    kr_ind = cells[(cells.sheet == "Key ratios") & (cells.row.isin(INDUSTRY_ROWS)) & (cells.col >= COL0) & (cells.col < COL0 + NCOL_T)]
    # bản năm: cột I.. = Q4 của từng năm -> map từ cột quý
    qcol = {p: COL0 + k for k, p in enumerate(per_q)}
    kr_ind_y = kr_ind[kr_ind.col.isin([qcol[f"Q4-{y}"] for y in per_y if f"Q4-{y}" in qcol])].copy()
    kr_ind_y["col"] = kr_ind_y.col.map({qcol[f"Q4-{y}"]: COL0 + i for i, y in enumerate(per_y) if f"Q4-{y}" in qcol})
    # dòng 167-174: IS ngành (lãi/lỗ từng loại TS, tổng mọi mã) từ fs_all_wide -> nguồn cho yield ngành (Q: quý; năm: tổng 4 quý)
    fsa = pd.read_csv(os.path.join(FEED, "fs_all_wide.csv"), encoding="utf-8-sig", dtype={"row_order": str})
    ind_is, ind_is_y = [], []
    for r, lab, ro, head in KF.IND_IS_ROWS:
        m = fsa[(fsa.row_order == str(ro)) & fsa.metric.str.startswith(head)]
        if len(m) != 1:
            log(f"  ! IS nganh dong {r}: {len(m)} dong khop '{head[:40]}' (ro {ro})"); continue
        rec = m.iloc[0]
        for k, p in enumerate(per_q):
            c = f"{p[-4:]}Q{p[1]}"
            if c in fsa.columns and pd.notna(rec[c]):
                ind_is.append((r, COL0 + k, float(rec[c])))
        for k, y in enumerate(per_y):
            cols = [f"{y}Q{q}" for q in (1, 2, 3, 4)]
            if all(c in fsa.columns and pd.notna(rec[c]) for c in cols):
                ind_is_y.append((r, COL0 + k, float(sum(rec[c] for c in cols))))
    # dòng 175-177: số liệu ngành cho CIR chuẩn bank, lấy từ dòng ALL của data_fs.csv (DER 1/2, IS 31)
    dfs_all = pd.read_csv(DATA_FS_CSV, encoding="utf-8-sig", dtype={"stmt": str})
    dfs_all = dfs_all[dfs_all.ticker == "ALL"].set_index(["stmt", "row_order"])
    for r, lab, stmt, ro in KF.IND_DER_ROWS:
        if (stmt, ro) not in dfs_all.index:
            log(f"  ! nganh dong {r}: khong co ALL|{stmt}|{ro} trong data_fs"); continue
        rec = dfs_all.loc[(stmt, ro)]
        for k, p in enumerate(per_q):
            if p in rec.index and pd.notna(rec[p]):
                ind_is.append((r, COL0 + k, float(rec[p])))
        for k, y in enumerate(per_y):
            cols = [f"Q{q}-{y}" for q in (1, 2, 3, 4)]
            if r in KF.IND_BAL_ROWS:                                   # so du: nam = Q4
                if cols[3] in rec.index and pd.notna(rec[cols[3]]):
                    ind_is_y.append((r, COL0 + k, float(rec[cols[3]])))
            elif all(c in rec.index and pd.notna(rec[c]) for c in cols):
                ind_is_y.append((r, COL0 + k, float(sum(rec[c] for c in cols))))
    kr_ind = pd.concat([kr_ind[["row", "col", "value"]], pd.DataFrame(ind_is, columns=["row", "col", "value"])], ignore_index=True)
    kr_ind_y = pd.concat([kr_ind_y[["row", "col", "value"]], pd.DataFrame(ind_is_y, columns=["row", "col", "value"])], ignore_index=True)

    import win32com.client as win32
    xl = win32.DispatchEx("Excel.Application"); xl.Visible = False; xl.DisplayAlerts = False; xl.ScreenUpdating = False
    try:
        t0 = time.time()
        src = xl.Workbooks.Open(os.path.abspath(wbp), UpdateLinks=0, ReadOnly=True)
        src.Worksheets(SHEETS).Copy()
        wb = xl.ActiveWorkbook
        xl.Calculation = -4135; xl.EnableEvents = False            # xlCalculationManual trong luc ghi
        log(f"  copy {len(SHEETS)} sheet [{time.time() - t0:.0f}s]")
        src.Close(False); src = None                              # dong nguon ngay: khong de CalculateFull tinh lai file goc 68 MB
        com_retry(lambda: wb.Worksheets.Count); time.sleep(3)      # cho Excel ranh sau khi dong file lon
        # FS Industry, Drivers: giá trị pipeline
        for sn in ("FS Industry", "Drivers"):
            ws = wb.Worksheets(sn); freeze(ws)
            sub = cells[cells.sheet == sn]; com_retry(lambda: put_values(ws, sub)); log(f"  {sn}: đổ {len(sub):,} ô giá trị")
        # 2 sheet DATA trung gian (truoc: cong thuc Key ratios tham chieu Data_FS, dropdown tham chieu Data_DM)
        com_retry(lambda: write_table(wb, "Data_FS", "tbl_FS", DATA_FS_CSV, []))
        tickers = com_retry(lambda: write_data_dm(wb))
        # Key ratios (quý) + (năm)
        ws = wb.Worksheets("Key ratios"); freeze(ws)
        ws.Copy(None, wb.Worksheets("Key ratios")); wsy = wb.Worksheets(ws.Index + 1); wsy.Name = "Key ratios (năm)"   # Copy(Before, After) vi tri
        fsw = wb.Worksheets("FS Industry"); hdr_vals = fsw.Range(fsw.Cells(4, 1), fsw.Cells(4, 80)).Value[0]
        fs_hdr = {}
        for i, v in enumerate(hdr_vals):                              # {nhan ky: cot} - quy 'Qn-yyyy' (U..BM), nam so (H..T)
            if v is None:
                continue
            fs_hdr[v if isinstance(v, str) else int(v)] = i + 1
        fill_key_ratios(ws, per_q, kr_ind, "Q", fs_hdr, fs_cols); fill_key_ratios(wsy, per_y, kr_ind_y, "Y", fs_hdr, fs_cols)
        for w in (ws, wsy):
            w.Range("G36").Value = "VCBS"
            try:
                if w.ProtectContents:
                    w.Unprotect()
                rg = w.Range("G36")
                if rg.MergeCells:
                    rg = rg.MergeArea
                rg.Validation.Delete()
                rg.Validation.Add(3, 1, 1, "=dm_ma_list")               # xlValidateList
                log(f"  dropdown G36 OK ({w.Name})")
            except Exception as e:                                       # noqa: BLE001
                log(f"  ! dropdown G36 khong tao duoc ({w.Name}; protect={w.ProtectContents}; merge={w.Range('G36').MergeCells}): {e}")
        log(f"  Key ratios: {len(per_q)} quý ({per_q[0]}..{per_q[-1]}) / {len(per_y)} năm; {len(tickers)} mã")
        try:                                                         # So sanh ma + Calc_SoSanh (compare_sheet.py)
            import compare_sheet
            compare_sheet.build(wb, per_q, per_y, fs_cols)
        except Exception as e:                                       # noqa: BLE001
            log(f"  ! So sánh mã: {e}")
        try:
            com_retry(lambda: update_table2(wb))
        except Exception as e:                                       # noqa: BLE001
            log(f"  ! Table2 So TK: {e}")
        try:                                                         # Drivers: cong thuc cho cac khoi co dropdown (sau khi Table2 + Data_FS + Data_DM da co)
            com_retry(lambda: write_ms_lists(wb)); com_retry(lambda: restore_drivers(wb, fs_cols)); unmerge_dropdowns(wb)
        except Exception as e:                                       # noqa: BLE001
            log(f"  ! Drivers: {e}")
        try:                                                         # khoi du lieu bieu do (FS Industry 144+) + 16 bieu do DASHBOARD (dashboard_data.py)
            import drivers_extra
            drivers_extra.build(wb)                                    # Drivers: GTGD tu pipeline + dong 64+ khoi ngoai, lai suat, cung co phieu HOSE
        except Exception as e:                                       # noqa: BLE001
            log(f"  ! DASHBOARD charts: {e}")
        if not a.no_data:
            for name, tbl, csvp, dcols in DATA_SHEETS:
                try:
                    com_retry(lambda: write_table(wb, name, tbl, csvp, dcols))
                except Exception as e:                               # noqa: BLE001
                    log(f"  ! {name}: {e}")
        try:                                                         # DASHBOARD: khoi du lieu + 21 bieu do (sau Data_DinhGia vi bieu do P/B dung Name tren tbl_DinhGia)
            import dashboard_data
            dashboard_data.build(wb, charts=not a.no_data)
        except Exception as e:                                       # noqa: BLE001
            log(f"  ! DASHBOARD charts: {e}")
        # DASHBOARD chart: series nào còn trỏ '[file gốc]Sheet'! -> đổi về sheet cùng tên trong file này (đã copy kèm)
        try:
            dash = wb.Worksheets("DASHBOARD"); n = dash.ChartObjects().Count; fixed = ext = 0
            base = os.path.basename(wbp)
            for i in range(1, n + 1):
                ch = dash.ChartObjects(i).Chart
                for si in range(1, ch.SeriesCollection().Count + 1):
                    ser = ch.SeriesCollection(si); f = str(ser.Formula)
                    if f"[{base}]" in f:
                        try:
                            ser.Formula = f.replace(f"[{base}]", ""); fixed += 1
                        except Exception:                            # noqa: BLE001
                            ext += 1
            log(f"  DASHBOARD: {n} biểu đồ, series đổi về nội bộ {fixed}, còn link ngoài {ext}")
        except Exception as e:                                       # noqa: BLE001
            log(f"  (chart) {e}")
        wb.Worksheets("DASHBOARD").Activate()
        xl.Calculation = -4105; xl.CalculateFull()                  # xlCalculationAutomatic
        if os.path.exists(OUTX):
            os.remove(OUTX)
        wb.SaveAs(os.path.abspath(OUTX), FileFormat=51); wb.Close(False)
        log(f"-> {OUTX} [{time.time() - t0:.0f}s]  ({os.path.getsize(OUTX) / 1e6:.1f} MB)")
        if not a.no_copy:
            try:
                copy_final(OUTX, a.replace_final)
            except Exception as e:                                   # noqa: BLE001
                log(f"  ! khong chep duoc sang OneDrive ({e}) - file dang mo?")
    finally:
        try:
            xl.Quit()
        except Exception:                                            # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
