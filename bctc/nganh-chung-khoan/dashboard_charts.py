# -*- coding: utf-8 -*-
r"""dashboard_charts.py - TOAN BO bieu do sheet DASHBOARD (17/09/2026).

- 16 bieu do theo spec PV2 (Chart 1-16) + 5 bieu do goc cua workbook gop vao cung khoi (Chart 17-21):
    17 Co cau thu nhap toan nganh (%)   18 Thi phan moi gioi HOSE        19 Ty le room margin da su dung (donut)
    20 Chu ky tang von toan nganh        21 Dinh gia P/B toan nganh (dung lai tu Data_DinhGia, bo link ngoai 'Downloads\Dinh gia')
  Bieu do goc "Du no margin toan he thong" trung Chart 8 -> bo.
- Dinh dang theo bang mau "Bao cao" cua Market Data App (D:\market-data\app\app.py MAU_BAOCAO):
    nen trang, khong vien; chu truc #595959 co 8pt; luoi ngang #D9D9D9, khong luoi doc, khong tick; chu thich duoi;
    thu tu mau #262626, #ED7D31, #A6A6A6, #F4B183, #C00000, #00B050, #4472C4, ...; 1 cot + duong -> cot xam #BFBFBF, duong den/cam;
    duong 1,5pt khong marker. Font App = Source Sans Pro (may khong cai) -> Segoe UI.
Du lieu: khoi FS Industry dong 144+ (dashboard_data.py), Drivers, Name mang tren bang tbl_DinhGia (tu gian khi cap nhat hang ngay).
"""
FS = "FS Industry"
QC1 = 66                    # BN = Q2-2026
CH_C0 = 33                  # AG = Q1-2018
PURPLE, WHITE = 0xA03070, 0xFFFFFF


def _rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16) + int(h[2:4], 16) * 256 + int(h[4:6], 16) * 65536


APP = {"bg": "#FFFFFF", "ink": "#262626", "ink2": "#595959", "grid": "#D9D9D9", "bar": "#BFBFBF", "nhan": "#ED7D31"}
APP_RANGE = ["#262626", "#ED7D31", "#A6A6A6", "#F4B183", "#C00000", "#00B050", "#4472C4", "#843C0C", "#7F7F7F", "#BF9000", "#2E75B6", "#D9D9D9"]
FONT = "Segoe UI"
DRV_X = "=Drivers!$I$8:$AP$8"


def _drv(r, kind, x=DRV_X):
    return ({"name": f"=Drivers!$F${r}", "values": f"=Drivers!$I${r}:$AP${r}", "x": x}, kind)


# so: (tieu de, [(nguon, kieu)], dinh dang truc chinh, truc phu, max truc chinh, dang dac biet)
# nguon: key dong khoi FS Industry | dict(name, values, x) ; kieu: col (chong) | col100 | ccol (cot) | line | line2 (truc phu) | dash
CHARTS = {
    1: ("Chart 1 - Cơ cấu doanh thu hoạt động | tỷ đồng",
        [("rev_prop", "col"), ("rev_margin", "col"), ("rev_brok", "col"), ("rev_ib", "col"), ("rev_oth", "col"), ("rev_yoy", "line2")], "#,##0", "0%", None, None),
    17: ("Chart 17 - Cơ cấu thu nhập toàn ngành | %",
         [("rev_prop", "col100"), ("rev_margin", "col100"), ("rev_brok", "col100"), ("rev_ib", "col100"), ("rev_oth", "col100")], "0%", None, None, None),
    2: ("Chart 2 - Lợi nhuận hoạt động theo mảng | tỷ đồng",
        [("op_prop", "col"), ("op_margin", "col"), ("op_brok", "col"), ("op_ib", "col"), ("op_oth", "col")], "#,##0", None, None, None),
    3: ("Chart 3 - LNTT & tăng trưởng | tỷ đồng", [("pbt", "ccol"), ("pbt_yoy", "line2")], "#,##0", "0%", None, None),
    18: ("Chart 18 - Thị phần môi giới HOSE của các CTCK | %", [_drv(r, "line") for r in range(12, 19)], "0%", None, None, None),
    4: ("Chart 4 - Biên lợi nhuận ngành | %", [("m_op", "line"), ("m_sga", "line"), ("m_pbt", "line"), ("m_npat", "line")], "0%", None, None, None),
    5: ("Chart 5 - Vietnam Brokerage Net Interest Margin | %", [("nim", "ccol"), ("ey", "line"), ("cof", "line")], "0.0%", None, None, None),
    6: ("Chart 6 - Vietnam Brokerage cost to income ratio | tỷ đồng, %",
        [("cost_svc", "col"), ("cost_sga", "col"), ("prov", "line"), ("cir", "line2")], "#,##0", "0%", None, None),
    7: ("Chart 7 - Yield các loại tài sản sinh lời (quý, quy năm) | %",
        [("y_margin", "line"), ("y_htm", "line"), ("y_afs", "line"), ("y_fvtpl", "line"), ("y_fvtpl_carry", "line"), ("cof", "dash")], "0%", None, None, None),
    8: ("Chart 8 - Dư nợ margin & mức sử dụng vốn | tỷ đồng", [("margin", "ccol"), ("margin_eq", "line2")], "#,##0", '0.0"x"', None, None),
    19: ("Chart 19 - Tỷ lệ room margin đã sử dụng toàn ngành (quý gần nhất) | %", None, None, None, None, "donut"),
    9: ("Chart 9 - GTGD | tỷ đồng", [("gtgd_hose", "col"), ("gtgd_hnx", "col"), ("gtgd_upcom", "col"), ("adtv", "line2")], "#,##0", "#,##0", None, None),
    10: ("Chart 10 - Cơ cấu tài sản sinh lời | tỷ đồng",
         [("bs_margin", "col"), ("bs_fi", "col"), ("bs_eq", "col"), ("bs_inv_oth", "col")], "#,##0", None, None, None),
    11: ("Chart 11 - Đầu tư Fixed-income / IEA & Equity / IEA | %", [("fi_iea", "line"), ("eq_iea", "line")], "0%", None, None, None),
    12: ("Chart 12 - Cơ cấu tài sản | %",
         [("asp_cash", "col"), ("asp_fvtpl", "col"), ("asp_afs", "col"), ("asp_htm", "col"), ("asp_margin", "col"), ("asp_rec", "col"), ("asp_oth", "col")], "0%", None, 1, None),
    13: ("Chart 13 - Cơ cấu tài sản | tỷ đồng",
         [("as_cash", "col"), ("as_fvtpl", "col"), ("as_afs", "col"), ("as_htm", "col"), ("as_margin", "col"), ("as_rec", "col"), ("as_oth", "col")], "#,##0", None, None, None),
    14: ("Chart 14 - Cơ cấu nguồn vốn | %", [("fup_debt", "col"), ("fup_nonint", "col"), ("fup_eq", "col")], "0%", None, 1, None),
    15: ("Chart 15 - Cơ cấu nguồn vốn | tỷ đồng", [("fu_debt", "col"), ("fu_nonint", "col"), ("fu_eq", "col")], "#,##0", None, None, None),
    16: ("Chart 16 - Tỷ lệ đòn bẩy & hiệu quả sử dụng vốn | %", [("debt_eq", "ccol"), ("roe", "line2")], '0.0"x"', "0%", None, None),
    20: ("Chart 20 - Chu kỳ tăng vốn toàn ngành | tỷ đồng",
         [_drv(61, "col", "=Drivers!$I$54:$AP$54"), _drv(62, "col", "=Drivers!$I$54:$AP$54")], "#,##0", None, None, None),
    21: ("Chart 21 - Định giá P/B toàn ngành (trung bình ± 1σ, 2σ từ 2015) | x", None, '0.0"x"', None, None, "pb"),
}
LAYOUT = [
    ("I - QUY MÔ & TĂNG TRƯỞNG", [1, 17, 2, 3, 18]),
    ("II - LỢI NHUẬN CÓ CHẤT LƯỢNG KHÔNG", [4, 5, 6, 7]),
    ("III - TÀI SẢN SINH LỜI", [8, 19, 9, 10, 11]),
    ("IV - CÂN ĐỐI VỐN & RỦI RO", [12, 13, 14, 15, 16, 20]),
    ("V - ĐỊNH GIÁ", [21]),
]
DB_ROW0 = 2
DB_COLS = [2, 10, 18, 26]            # B, J, R, Z
CH_ROWS = 15
PB_NAMES = {
    "db_pb_date": "=tbl_DinhGia[date]",
    "db_pb": "=tbl_DinhGia[pb]",
    "db_pb_avg": "=tbl_DinhGia[pb]*0+AVERAGE(tbl_DinhGia[pb])",
    "db_pb_p1": "=tbl_DinhGia[pb]*0+AVERAGE(tbl_DinhGia[pb])+STDEV.S(tbl_DinhGia[pb])",
    "db_pb_m1": "=tbl_DinhGia[pb]*0+AVERAGE(tbl_DinhGia[pb])-STDEV.S(tbl_DinhGia[pb])",
    "db_pb_p2": "=tbl_DinhGia[pb]*0+AVERAGE(tbl_DinhGia[pb])+2*STDEV.S(tbl_DinhGia[pb])",
    "db_pb_m2": "=tbl_DinhGia[pb]*0+AVERAGE(tbl_DinhGia[pb])-2*STDEV.S(tbl_DinhGia[pb])",
}
BAR = ("col", "col100", "ccol")


def _style_axis(ax, grid):
    ax.Format.Line.Visible = True; ax.Format.Line.ForeColor.RGB = _rgb(APP["grid"]); ax.Format.Line.Weight = 0.75
    ax.MajorTickMark = -4142; ax.MinorTickMark = -4142
    ax.TickLabels.Font.Name = FONT; ax.TickLabels.Font.Size = 8; ax.TickLabels.Font.Color = _rgb(APP["ink2"])
    ax.HasMajorGridlines = grid; ax.HasMinorGridlines = False
    if grid:
        gl = ax.MajorGridlines.Format.Line; gl.Visible = True; gl.ForeColor.RGB = _rgb(APP["grid"]); gl.Weight = 0.6


def style_chart(ch, kinds):
    """Bang mau 'Bao cao' cua App."""
    ca = ch.ChartArea.Format
    ca.Fill.Visible = True; ca.Fill.Solid(); ca.Fill.ForeColor.RGB = _rgb(APP["bg"]); ca.Line.Visible = False
    ch.PlotArea.Format.Fill.Visible = False; ch.PlotArea.Format.Line.Visible = False
    tf = ch.ChartArea.Format.TextFrame2.TextRange.Font
    tf.Name = FONT; tf.Size = 8; tf.Fill.ForeColor.RGB = _rgb(APP["ink2"])
    if ch.HasLegend:
        ch.Legend.Position = -4107
        ch.Legend.Font.Name = FONT; ch.Legend.Font.Size = 8; ch.Legend.Font.Color = _rgb(APP["ink2"])
    if ch.ChartType not in (-4120, 5):
        for t, g in ((1, 1), (2, 1), (1, 2), (2, 2)):
            try:
                if not ch.HasAxis(t, g):                             # truc phu khong hien -> Axes() van tra doi tuong nhung Format loi
                    continue
                _style_axis(ch.Axes(t, g), grid=(t == 2 and g == 1))
            except Exception:                                        # noqa: BLE001
                continue
    n_bar = sum(k in BAR for k in kinds)
    lone_bar = n_bar == 1 and len(kinds) > 1
    pi = li = 0
    for i, k in enumerate(kinds, 1):
        se = ch.SeriesCollection(i)
        if k in BAR:
            colr = APP["bar"] if lone_bar else APP_RANGE[pi % len(APP_RANGE)]
            if not lone_bar:
                pi += 1
            se.Format.Fill.Visible = True; se.Format.Fill.Solid(); se.Format.Fill.ForeColor.RGB = _rgb(colr); se.Format.Line.Visible = False
        else:
            if lone_bar:
                colr = [APP["ink"], APP["nhan"]][li] if li < 2 else APP_RANGE[(li) % len(APP_RANGE)]; li += 1
            else:
                colr = APP_RANGE[pi % len(APP_RANGE)]; pi += 1
            se.MarkerStyle = -4142
            ln = se.Format.Line; ln.Visible = True; ln.ForeColor.RGB = _rgb(colr); ln.Weight = 1.5
            if k == "dash":
                ln.DashStyle = 4
    if n_bar:
        try:
            ch.ChartGroups(1).GapWidth = 60
        except Exception:                                            # noqa: BLE001
            pass


def _series(ch, src, Q, L0, L1, rm):
    s = ch.SeriesCollection().NewSeries()
    if isinstance(src, dict):
        s.Name = src["name"]; s.Values = src["values"]; s.XValues = src["x"]
    else:
        r = rm[src]; s.Name = f"={Q}$F${r}"; s.Values = f"={Q}${L0}${r}:${L1}${r}"; s.XValues = f"={Q}${L0}$4:${L1}$4"
    return s


def _col(c):
    s = ""
    while c:
        c, r = divmod(c - 1, 26); s = chr(65 + r) + s
    return s


def build(wb, rm):
    ds = wb.Worksheets("DASHBOARD")
    for i in range(ds.Shapes.Count, 0, -1):
        ds.Shapes(i).Delete()
    ds.Cells.Clear(); ds.Cells.Font.Name = FONT; ds.Cells.Font.Size = 10
    try:
        ds.Activate(); ds.Application.ActiveWindow.DisplayGridlines = False
    except Exception:                                                # noqa: BLE001
        pass
    for nm, ref in PB_NAMES.items():
        wb.Names.Add(nm, ref)
    Q = f"'{FS}'!"; L0, L1 = _col(CH_C0), _col(QC1)
    row = DB_ROW0; placed = 0
    for sec, nums in LAYOUT:
        hdr = ds.Range(ds.Cells(row, 2), ds.Cells(row, DB_COLS[-1] + 7))
        ds.Cells(row, 2).Value = sec; hdr.Interior.Color = PURPLE; hdr.Font.Color = WHITE; hdr.Font.Bold = True; hdr.Font.Size = 12
        row += 1
        for j, no in enumerate(nums):
            if j and j % len(DB_COLS) == 0:
                row += 1 + CH_ROWS + 1
            c = DB_COLS[j % len(DB_COLS)]
            title, series, fmt1, fmt2, ymax, special = CHARTS[no]
            cell = ds.Cells(row, c); cell.Value = title; cell.Font.Bold = True; cell.Font.Size = 10; cell.Font.Color = _rgb(APP["ink"])
            left, top = ds.Cells(row + 1, c).Left, ds.Cells(row + 1, c).Top
            width = ds.Cells(row + 1, c + 8).Left - left - 6; height = ds.Cells(row + 1 + CH_ROWS, c).Top - top
            name = f"DB_C{no:02d}"
            if special == "placeholder":
                sh = ds.Shapes.AddShape(1, left, top, width, height); sh.Name = name
                sh.Fill.ForeColor.RGB = _rgb("#F7F7F7"); sh.Line.ForeColor.RGB = _rgb(APP["grid"]); sh.Line.DashStyle = 4
                tr = sh.TextFrame2.TextRange; tr.Text = "Để trống – trao đổi sau\n(Fixed-income yield, Equity yield, Margin yield)"
                tr.Font.Name = FONT; tr.Font.Size = 10; tr.Font.Fill.ForeColor.RGB = _rgb(APP["ink2"])
                sh.TextFrame2.VerticalAnchor = 3; tr.ParagraphFormat.Alignment = 2
                placed += 1; continue
            co = ds.ChartObjects().Add(left, top, width, height); co.Name = name; ch = co.Chart
            if special == "donut":
                ch.ChartType = -4120
                while ch.SeriesCollection().Count:
                    ch.SeriesCollection(1).Delete()
                r1, r2 = rm["room_used"], rm["room_left"]
                s = ch.SeriesCollection().NewSeries()
                s.Name = "Room margin"; s.Values = f"={Q}${L1}${r1}:${L1}${r2}"; s.XValues = f"={Q}$F${r1}:$F${r2}"
                ch.HasTitle = False; ch.HasLegend = True
                style_chart(ch, [])
                s.Points(1).Format.Fill.ForeColor.RGB = _rgb(APP["nhan"]); s.Points(2).Format.Fill.ForeColor.RGB = _rgb(APP["grid"])
                s.Format.Line.Visible = True; s.Format.Line.ForeColor.RGB = _rgb(APP["bg"])
                ch.ChartGroups(1).DoughnutHoleSize = 60; ch.HasTitle = False
                s.Points(1).HasDataLabel = True; dl = s.Points(1).DataLabel
                dl.ShowValue = True; dl.ShowCategoryName = False; dl.ShowSeriesName = False; dl.NumberFormat = "0.0%"
                dl.Font.Name = FONT; dl.Font.Size = 12; dl.Font.Bold = True; dl.Font.Color = _rgb(APP["ink"])
                placed += 1; continue
            if special == "pb":
                ch.ChartType = 4
                while ch.SeriesCollection().Count:
                    ch.SeriesCollection(1).Delete()
                book = f"'{wb.Name}'!"; kinds = []
                for nm, lab, k in (("db_pb", "P/B ngành", "line"), ("db_pb_avg", "Trung bình", "line"), ("db_pb_p1", "+1σ", "dash"),
                                   ("db_pb_m1", "−1σ", "dash"), ("db_pb_p2", "+2σ", "dash"), ("db_pb_m2", "−2σ", "dash")):
                    s = ch.SeriesCollection().NewSeries(); s.Name = lab; s.Values = f"={book}{nm}"; s.XValues = f"={book}db_pb_date"
                    kinds.append(k)
                ch.HasTitle = False; ch.HasLegend = True
                ax = ch.Axes(1); ax.CategoryType = 3; ax.TickLabels.NumberFormat = "yyyy"
                ax.TickLabelPosition = -4134
                try:
                    ax.MajorUnitScale = 2; ax.MajorUnit = 1
                except Exception:                                    # noqa: BLE001
                    pass
                ch.Axes(2, 1).TickLabels.NumberFormat = fmt1
                style_chart(ch, kinds)
                for i, colr in ((1, APP["ink"]), (2, APP["nhan"]), (3, "#A6A6A6"), (4, "#A6A6A6"), (5, "#F4B183"), (6, "#F4B183")):
                    ch.SeriesCollection(i).Format.Line.ForeColor.RGB = _rgb(colr)
                ch.SeriesCollection(1).Format.Line.Weight = 1.75
                placed += 1; continue
            kinds = [k for _, k in series]
            ch.ChartType = 53 if "col100" in kinds else (52 if "col" in kinds else (51 if "ccol" in kinds else 4))
            while ch.SeriesCollection().Count:
                ch.SeriesCollection(1).Delete()
            for src, kind in series:
                s = _series(ch, src, Q, L0, L1, rm)
                s.ChartType = {"col": 52, "col100": 53, "ccol": 51, "line": 4, "line2": 4, "dash": 4}[kind]
                if kind == "line2":
                    s.AxisGroup = 2
            ch.HasTitle = False; ch.HasLegend = True; ch.DisplayBlanksAs = 1
            ax = ch.Axes(1); ax.TickLabelSpacing = 4; ax.TickMarkSpacing = 4; ax.TickLabels.Orientation = 0
            ax.TickLabelPosition = -4134                             # xlLow: nhan ky o day bieu do, khong de len vung am
            ch.Axes(2, 1).TickLabels.NumberFormat = fmt1
            if ymax is not None:
                ch.Axes(2, 1).MaximumScale = ymax; ch.Axes(2, 1).MinimumScale = 0
            if fmt2:
                ch.Axes(2, 2).TickLabels.NumberFormat = fmt2
            style_chart(ch, kinds)
            placed += 1
        row += 1 + CH_ROWS + 1 + 1
    return placed


def clean_ref_names(wb):
    """Xoa Name loi #REF! thua ke tu workbook goc (vd ____tk1111), khong duoc dung o dau."""
    n = 0
    for i in range(wb.Names.Count, 0, -1):
        try:
            if "#REF!" in str(wb.Names(i).RefersTo):
                wb.Names(i).Delete(); n += 1
        except Exception:                                            # noqa: BLE001
            pass
    return n
