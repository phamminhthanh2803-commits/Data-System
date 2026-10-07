# -*- coding: utf-8 -*-
r"""build_workbook_bds.py — BƯỚC 3: dựng file ngành BĐS D:\bctc\nganh-bat-dong-san\Nganh_BDS.xlsx.

Khung giống file ngành CK (IB&Brokerage_Nganh.xlsx): số liệu gốc = GIÁ TRỊ ở sheet Data_*, sheet trình bày = CÔNG THỨC ngắn
(INDEX/MATCH vào Data_FS + tỷ lệ tính trong Excel theo metrics_bds.BLOCK). Dựng bằng openpyxl (không cần workbook mẫu),
sau đó Excel COM tính lại toàn bộ + lưu (để file mở ra có sẵn số, biểu đồ có dữ liệu) và tự kiểm tra lỗi công thức + đối chiếu Python.

Sheet: Hướng dẫn · DASHBOARD (chọn nhóm) · Key ratios / Key ratios (năm) (khối nhóm ngành + khối 1 mã, đều có dropdown)
       · So sánh mã / So sánh mã (năm) (1 chỉ tiêu × 12 mã + trung vị + 1 nhóm) · Bảng mã (mọi mã tại 1 kỳ chọn)
       · Drivers (thị trường, TPDN BĐS, lãi suất, khối ngoại) · Chart_Data, Calc_SoSanh, Calc_SoSanh_Nam (trung gian)
       · Data_FS (toàn bộ dòng BCTC VCI của mọi mã + dòng tổng nhóm), Data_DM (danh mục dropdown), Data_DinhGia (định giá ngày)
"""
import argparse
import os
import time

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.axis import DateAxis
from openpyxl.chart.layout import Layout, ManualLayout
from openpyxl.chart.series import SeriesLabel, StrRef
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.chart.text import RichText, Text
from openpyxl.chart.title import Title
from openpyxl.drawing.line import LineProperties
from openpyxl.drawing.text import CharacterProperties, Font as DFont, Paragraph, ParagraphProperties, RegularTextRun, RichTextProperties
from openpyxl.formatting.rule import FormulaRule, Rule
from openpyxl.styles.numbers import NumberFormat
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.styles.differential import DifferentialStyle
from openpyxl.utils import get_column_letter as L
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

from common_bds import HERE, NHOM_TONG, OUT_XLSX, log, qidx, qlabel, qname, utf8_stdout
from metrics_bds import BLOCK, FMT, NROW, ROW_OF, expand

C0 = 8                     # cột kỳ đầu tiên (H) ở MỌI sheet trình bày và Data_FS
INK, INK2, GRID, ORANGE = "262626", "595959", "D9D9D9", "ED7D31"
PALETTE = ["262626", "ED7D31", "A6A6A6", "F4B183", "C00000", "00B050", "4472C4", "843C0C", "7F7F7F", "BF9000",
           "2E75B6", "D9D9D9", "70AD47", "FFC000"]
F_TITLE = Font(name="Segoe UI", size=14, bold=True, color=INK)
F_B = Font(name="Segoe UI", size=9, bold=True, color=INK)
F_N = Font(name="Segoe UI", size=9, color=INK)
F_S = Font(name="Segoe UI", size=8, italic=True, color=INK2)
FILL_HDR = PatternFill("solid", fgColor="F2F2F2")
FILL_SEL = PatternFill("solid", fgColor="FCE4D6")
FILL_TOP = PatternFill("solid", fgColor="262626")
B_BOT = Border(bottom=Side(style="thin", color="A6A6A6"))
N_SS = 12                  # số mã trong So sánh mã


# ------------------------------------------------------------------ dữ liệu
def load():
    fs = pd.read_csv(os.path.join(HERE, "data_fs.csv"), low_memory=False)
    di = pd.read_csv(os.path.join(HERE, "dim_item.csv"))
    dc = pd.read_csv(os.path.join(HERE, "dim_company.csv"), keep_default_na=False)
    val = pd.read_csv(os.path.join(HERE, "valuation_bds_nhom_daily.csv"), parse_dates=["date"])
    vs = pd.read_csv(os.path.join(HERE, "valuation_bds_stocks_daily.csv"), parse_dates=["date"])
    dr = pd.read_csv(os.path.join(HERE, "drivers_bds.csv"))
    mat = pd.read_csv(os.path.join(HERE, "bond_maturity_bds.csv"))
    return fs, di, dc, val, vs, dr, mat


def item_row(di):
    m = {(r.bc, r.key_item): int(r.row_order) for r in di.itertuples()}
    m[("CNT", "n_cong_ty")] = 0
    return m


# ------------------------------------------------------------------ tiện ích định dạng
def setw(ws, widths):
    for c, w in widths.items():
        ws.column_dimensions[c].width = w


def title(ws, text, sub=None):
    ws["B1"] = text
    ws["B1"].font = F_TITLE
    if sub:
        ws["B2"] = sub
        ws["B2"].font = F_S
    ws.sheet_view.showGridLines = False


def dropdown(ws, cell, formula, default):
    dv = DataValidation(type="list", formula1=formula, allow_blank=False)
    ws.add_data_validation(dv)
    dv.add(cell)
    ws[cell] = default
    ws[cell].fill = FILL_SEL
    ws[cell].font = Font(name="Segoe UI", size=10, bold=True, color="843C0C")
    ws[cell].border = Border(*(Side(style="thin", color=ORANGE),) * 4)


# ------------------------------------------------------------------ KHỐI chỉ tiêu (dùng chung mọi sheet)
def write_block(ws, top, prefix, labels, mode, head, irow):
    """Khối BLOCK từ dòng `top` (dòng tiêu đề + nhãn kỳ), dòng chỉ tiêu top+1..top+NROW.
    prefix: tham chiếu ô chứa tiền tố khoá ('NLG' hoặc 'G:ALL'); labels: nhãn kỳ; mode 'Q'|'Y'."""
    nq = len(labels)
    fs_off = 0 if mode == "Q" else irow["_nq"]
    ws.cell(top, 2, head).font = F_B
    for j, lb in enumerate(labels):
        c = ws.cell(top, C0 + j, lb)
        c.font, c.alignment, c.border, c.fill = F_B, Alignment(horizontal="right"), B_BOT, FILL_HDR
    ws.cell(top, 2).fill = FILL_HDR
    ws.cell(top, 3).fill = FILL_HDR
    key_row = {k: top + ROW_OF[k] for k in ROW_OF}
    for i, (key, label, typ, bc, item, fmt) in enumerate(BLOCK):
        r = top + 1 + i
        cl = ws.cell(r, 2, label)
        if typ == "hdr":
            cl.font = F_B
            for j in range(-6, nq):
                ws.cell(r, C0 + j).fill = FILL_HDR
            continue
        cl.font = F_N
        ws.cell(r, 3, {"ty": "tỷ đồng", "pct": "%", "x": "lần", "n": "cty"}[fmt]).font = F_S
        if typ == "raw":
            ws.cell(r, 4, bc)
            ws.cell(r, 5, irow[(bc, item)])
            ws.cell(r, 6, f'=IFERROR(MATCH({prefix}&"|"&$D{r}&"|"&$E{r},Data_FS!$A:$A,0),"")')
            for j in range(nq):
                fc = L(C0 + fs_off + j)
                x = f"INDEX(Data_FS!{fc}:{fc},$F{r})"
                c = ws.cell(r, C0 + j, f'=IF($F{r}="","",IF({x}="","",{x}))')
                c.number_format, c.font = FMT[fmt], F_N
        else:
            for j in range(nq):
                f = expand(item, key_row, C0 + j, C0, mode)
                if f is not None:
                    c = ws.cell(r, C0 + j, f)
                    c.number_format, c.font = FMT[fmt], F_N
        if key in ("npatmi", "eq_me", "debt", "adv_all", "roe", "gm_ttm", "nde"):
            for j in range(nq):
                ws.cell(r, C0 + j).font = F_B
            cl.font = F_B
    return key_row


# ------------------------------------------------------------------ SHEET FS (BCTC đầy đủ của 1 nhóm hoặc 1 mã)
FS_NOTE = ["noc15", "noc17", "noc19", "noc20", "noc21", "noc24", "noc65", "noc66", "noc67", "noc93", "noc94", "noc95",
           "noc96", "noc97", "noc102", "noc103", "noc104", "noc105", "noc113", "noc122", "noc123", "noc131", "noc132"]
FS_BOLD = {"net_sales", "gross_profit", "operating_profit_loss", "net_accounting_profit_loss_before_tax",
           "net_profit_loss_after_tax", "attributable_to_parent_company", "current_assets", "long_term_assets", "total_assets",
           "liabilities", "current_liabilities", "long_term_liabilities", "owners_equity", "total_resource",
           "net_cash_inflows_outflows_from_operating_activities", "net_cash_inflows_outflows_from_investing_activities",
           "net_cash_inflows_outflows_from_financing_activities", "net_increase_in_cash_and_cash_equivalents",
           "noc15", "noc65", "noc93", "noc102"}


def sheet_fs(ws, di, labels, mode, irow, group):
    """BCTC đầy đủ (KQKD, CĐKT, LCTT, thuyết minh chọn lọc) của nhóm (group=True) hoặc 1 mã, chọn ở ô B4.
    Mọi ô = INDEX/MATCH vào Data_FS. Trả {(bc, key_item): dòng} để Key ratios tham chiếu."""
    nq = len(labels)
    fs_off = 0 if mode == "Q" else irow["_nq"]
    ky = "QUÝ" if mode == "Q" else "NĂM"
    if group:
        title(ws, f"FS INDUSTRY – BCTC TỔNG HỢP NHÓM NGÀNH BĐS ({ky})",
              "Tổng BCTC hợp nhất các công ty trong nhóm (VCI, tỷ đồng). VIC, DXS không cộng (tránh đếm đôi). "
              + ("Năm: dòng chảy = tổng 4 quý, số dư = Q4." if mode == "Y" else "Số riêng từng quý."))
        ws["B3"] = "Chọn nhóm ngành:"
        dropdown(ws, "B4", "=dm_nhom", NHOM_TONG[0][1])
        ws["E4"] = '=IFERROR(INDEX(Data_DM!$I:$I,MATCH($B$4,Data_DM!$H:$H,0)),"G:ALL")'
    else:
        title(ws, f"FS CÔNG TY – BCTC HỢP NHẤT 1 MÃ ({ky})",
              "BCTC hợp nhất VCI, tỷ đồng (EPS: đồng). " + ("Năm: dòng chảy = tổng 4 quý, số dư = Q4." if mode == "Y" else "Số riêng từng quý."))
        ws["B3"] = "Chọn mã:"
        dropdown(ws, "B4", "=dm_ma", "NLG")
        ws["E4"] = "=$B$4"
        ws.cell(4, C0, '=IFERROR(INDEX(Data_DM!$B:$B,MATCH($B$4,Data_DM!$A:$A,0))&"  |  nhóm: "&'
                       'INDEX(Data_DM!$C:$C,MATCH($B$4,Data_DM!$A:$A,0)),"")').font = F_B
    ws["B3"].font = F_S
    block_cols(ws)
    top = 6
    ws.cell(top, 2, "Chỉ tiêu").font = F_B
    ws.cell(top, 3, "Đơn vị").font = F_B
    for j, lb in enumerate(labels):
        c = ws.cell(top, C0 + j, lb)
        c.font, c.alignment = F_B, Alignment(horizontal="right")
        ws.column_dimensions[L(C0 + j)].width = 10 if mode == "Q" else 11
    for j in range(-6, nq):
        ws.cell(top, C0 + j).fill, ws.cell(top, C0 + j).border = FILL_HDR, B_BOT
    rowmap = {}
    r = top + 1

    def hdr(text):
        nonlocal r
        r += 1
        ws.cell(r, 2, text).font = F_B
        for j in range(-6, nq):
            ws.cell(r, C0 + j).fill = FILL_HDR
        r += 1

    def raw(bc, ro, key, label, unit):
        nonlocal r
        bold = key in FS_BOLD
        ws.cell(r, 2, label).font = F_B if bold else F_N
        ws.cell(r, 3, unit).font = F_S
        ws.cell(r, 4, bc)
        ws.cell(r, 5, int(ro))
        ws.cell(r, 6, f'=IFERROR(MATCH($E$4&"|"&$D{r}&"|"&$E{r},Data_FS!$A:$A,0),"")')
        nf = "#,##0" if unit == "VND" else ("0" if bc == "CNT" else FMT["ty"])
        for j in range(nq):
            fc = L(C0 + fs_off + j)
            x = f"INDEX(Data_FS!{fc}:{fc},$F{r})"
            c = ws.cell(r, C0 + j, f'=IF($F{r}="","",IF({x}="","",{x}))')
            c.number_format, c.font = nf, F_B if bold else F_N
        rowmap[(bc, key)] = r
        r += 1

    if group:
        raw("CNT", 0, "n_cong_ty", "Số công ty có BCTC", "công ty")
    secs = [("IS", "KẾT QUẢ KINH DOANH", None), ("BS", "BẢNG CÂN ĐỐI KẾ TOÁN", 94),
            ("CF", "LƯU CHUYỂN TIỀN TỆ (gián tiếp)", None), ("NOTE", "THUYẾT MINH (chọn lọc)", None)]
    for bc, text, split in secs:
        hdr(text)
        d = di[di.bc == bc].sort_values("row_order")
        if bc == "NOTE":
            d = d[d.key_item.isin(FS_NOTE)]
        for it in d.itertuples():
            if split and it.row_order == split + 1:
                hdr("   Chỉ tiêu bổ sung theo mẫu VCI (chi tiết / mẫu sau 2015)")
            if bc == "IS" and group and it.don_vi == "VND":
                continue                                            # EPS không cộng theo nhóm
            raw(bc, it.row_order, it.key_item, it.item, "đồng/CP" if it.don_vi == "VND" else "tỷ đồng")
    ws.freeze_panes = ws.cell(top + 1, C0)
    return rowmap


def write_ratio_block(ws, top, fs_sheet, fs_rows, labels, mode, head, irow):
    """Khối CHỈ SỐ (chỉ dòng công thức của BLOCK); số gốc tham chiếu thẳng dòng tương ứng ở sheet FS."""
    nq = len(labels)
    ws.cell(top, 2, head).font = F_B
    for j, lb in enumerate(labels):
        c = ws.cell(top, C0 + j, lb)
        c.font, c.alignment, c.border, c.fill = F_B, Alignment(horizontal="right"), B_BOT, FILL_HDR
    ws.cell(top, 2).fill = ws.cell(top, 3).fill = FILL_HDR
    pref = f"'{fs_sheet}'!"
    key_row = {}
    for key, label, typ, bc, item, fmt in BLOCK:
        if typ == "raw" and (bc, item) in fs_rows:                 # 'Số công ty' chỉ có ở FS Industry
            key_row[key] = (pref, fs_rows[(bc, item)])
    r = top + 1
    sec_of = {}
    cur = "SỐ LIỆU TÍNH TOÁN (tỷ đồng)"
    for key, label, typ, bc, item, fmt in BLOCK:
        if key == "_h4":
            cur = "CHỈ SỐ"
        if typ == "f":
            sec_of.setdefault(cur, []).append((key, label, item, fmt))
    for sec, rows in sec_of.items():
        ws.cell(r, 2, sec).font = F_B
        for j in range(-6, nq):
            ws.cell(r, C0 + j).fill = FILL_HDR
        r += 1
        for key, label, item, fmt in rows:
            key_row[key] = r
            r += 1
        r += 0
    # ghi công thức sau khi biết hết dòng (dòng f có thể tham chiếu dòng f khác)
    for sec, rows in sec_of.items():
        for key, label, item, fmt in rows:
            rr = key_row[key]
            bold = key in ("eq_me", "debt", "adv_all", "roe", "gm_ttm", "nde", "npatmi_ttm")
            ws.cell(rr, 2, label).font = F_B if bold else F_N
            ws.cell(rr, 3, {"ty": "tỷ đồng", "pct": "%", "x": "lần", "n": "cty"}[fmt]).font = F_S
            for j in range(nq):
                f = expand(item, key_row, C0 + j, C0, mode)
                if f is not None:
                    c = ws.cell(rr, C0 + j, f)
                    c.number_format, c.font = FMT[fmt], F_B if bold else F_N
    return key_row, r


def block_cols(ws):
    setw(ws, {"A": 2, "B": 50, "C": 8, "D": 5, "E": 5, "F": 7, "G": 2})
    for c in ("D", "E", "F"):
        ws.column_dimensions[c].hidden = True


# ------------------------------------------------------------------ biểu đồ
def _cp(sz=8, col=INK2, b=False):
    return CharacterProperties(sz=int(sz * 100), b=b, solidFill=col, latin=DFont(typeface="Segoe UI"))


def _tx(sz=8, col=INK2, b=False):
    return RichText(bodyPr=RichTextProperties(), p=[Paragraph(pPr=ParagraphProperties(defRPr=_cp(sz, col, b)),
                                                              endParaRPr=_cp(sz, col, b))])


def _title(text):
    cp = _cp(10.5, INK, True)
    t = Title(tx=Text(rich=RichText(bodyPr=RichTextProperties(), p=[
        Paragraph(pPr=ParagraphProperties(defRPr=cp), r=[RegularTextRun(rPr=cp, t=text)])])), overlay=False)
    t.layout = Layout(manualLayout=ManualLayout(x=0.01, y=0.0, xMode="edge", yMode="edge"))
    return t


def style(ch, text, yfmt="#,##0", skip=None, date=False):
    ch.title = _title(text)
    ch.graphical_properties = GraphicalProperties(solidFill="FFFFFF", ln=LineProperties(noFill=True))
    ch.plot_area.graphicalProperties = GraphicalProperties(solidFill="FFFFFF", ln=LineProperties(noFill=True))
    for ax in (ch.x_axis, ch.y_axis):
        ax.delete = False
        ax.txPr = _tx()
        ax.spPr = GraphicalProperties(ln=LineProperties(solidFill=GRID, w=9525))
    ch.x_axis.majorGridlines = None
    ch.y_axis.majorGridlines.spPr = GraphicalProperties(ln=LineProperties(solidFill=GRID, w=7620))
    ch.y_axis.spPr = GraphicalProperties(ln=LineProperties(noFill=True))
    ch.y_axis.majorTickMark = "none"
    ch.y_axis.number_format = yfmt
    ch.x_axis.tickLblPos = "low"
    if date:
        ch.x_axis.number_format = "yyyy"
        ch.x_axis.majorTimeUnit = "years"
        ch.x_axis.majorUnit = 1
    elif skip:
        ch.x_axis.tickLblSkip = skip
        ch.x_axis.tickMarkSkip = skip
    if ch.legend is not None:
        ch.legend.position = "b"
        ch.legend.overlay = False
        ch.legend.txPr = _tx()
    ch.height, ch.width = 7.6, 15.5
    return ch


def _series_color(s, color, line=False, w=1.75, dash=None):
    if line:
        s.graphicalProperties.line = LineProperties(solidFill=color, w=int(w * 12700))
        if dash:
            s.graphicalProperties.line.prstDash = dash
        s.smooth = False
        s.marker.symbol = "none"
    else:
        s.graphicalProperties = GraphicalProperties(solidFill=color, ln=LineProperties(noFill=True))
        s.invertIfNegative = False


def rows_chart(ws_src, rows, c1, c2, kind, text, yfmt="#,##0", sec=None, stacked=False, skip=4, hdr_row=None,
               colors=None, sec_fmt="0.0%"):
    """Biểu đồ từ các DÒNG của ws_src (tiêu đề ở cột B), cột c1..c2; sec = các dòng vẽ đường trục phụ."""
    colors = colors or PALETTE
    ch = BarChart() if kind == "bar" else LineChart()
    if kind == "bar":
        ch.type, ch.gapWidth = "col", 40
        if stacked:
            ch.grouping, ch.overlap = "stacked", 100
    for i, r in enumerate(rows):
        ref = Reference(ws_src, min_col=c1, max_col=c2, min_row=r, max_row=r)
        ch.add_data(ref, from_rows=True, titles_from_data=False)
        s = ch.series[-1]
        s.tx = SeriesLabel(strRef=StrRef(f"'{ws_src.title}'!$B${r}"))
        _series_color(s, colors[i % len(colors)], line=(kind == "line"))
    cats = Reference(ws_src, min_col=c1, max_col=c2, min_row=hdr_row, max_row=hdr_row)
    ch.set_categories(cats)
    if kind == "line":
        ch.display_blanks = "gap"
    style(ch, text, yfmt, skip)
    if sec:
        ln = LineChart()
        for i, r in enumerate(sec):
            ln.add_data(Reference(ws_src, min_col=c1, max_col=c2, min_row=r, max_row=r), from_rows=True, titles_from_data=False)
            s = ln.series[-1]
            s.tx = SeriesLabel(strRef=StrRef(f"'{ws_src.title}'!$B${r}"))
            _series_color(s, [ORANGE, "C00000"][i % 2], line=True, w=2)
        ln.y_axis.axId = 200
        ln.y_axis.crosses = "max"
        ln.y_axis.number_format = sec_fmt
        ln.y_axis.majorGridlines = None
        ln.y_axis.delete = False
        ln.y_axis.txPr = _tx()
        ln.y_axis.spPr = GraphicalProperties(ln=LineProperties(noFill=True))
        ch += ln
    return ch


def date_chart(ws, date_col, cols, r1, r2, text, yfmt="0.00", colors=None, dashed=()):
    ch = LineChart()
    ch.x_axis = DateAxis(crossAx=100)
    ch.y_axis.crossAx = 500
    for i, c in enumerate(cols):
        ch.add_data(Reference(ws, min_col=c, max_col=c, min_row=r1 - 1, max_row=r2), titles_from_data=True)
        _series_color(ch.series[-1], (colors or PALETTE)[i % len(colors or PALETTE)], line=True, w=1.5,
                      dash="dash" if c in dashed else None)
    ch.set_categories(Reference(ws, min_col=date_col, min_row=r1, max_row=r2))
    ch.display_blanks = "gap"
    return style(ch, text, yfmt, date=True)


# ------------------------------------------------------------------ sheet DATA
def sheet_data_fs(ws, fs, nq):
    cols = list(fs.columns)
    ws.append(cols)
    for c in ws[1]:
        c.font = F_B
    for row in fs.itertuples(index=False):
        ws.append([None if (isinstance(v, float) and np.isnan(v)) else v for v in row])
    ws.freeze_panes = "H2"
    setw(ws, {"A": 22, "B": 8, "C": 5, "D": 5, "E": 26, "F": 40, "G": 8})
    return len(fs) + 1


def sheet_dm(ws, dc, labels_q, labels_y, top12):
    ws.append(["ma", "ten_cong_ty", "nhom", "cong_vao_nganh", "ky_gan_nhat", "ghi_chu"])
    dc = dc.sort_values("ticker")
    for r in dc.itertuples():
        ws.append([r.ticker, r.ten_cong_ty, r.nhom, int(r.cong_vao_nganh), r.ky_gan_nhat, r.ghi_chu])
    n_ma = len(dc) + 1
    ws["H1"], ws["I1"] = "ten_nhom", "tien_to_khoa"
    for i, (code, ten, _) in enumerate(NHOM_TONG):
        ws.cell(2 + i, 8, ten)
        ws.cell(2 + i, 9, "G:" + code)
    ws["K1"], ws["L1"], ws["M1"] = "chi_tieu", "dong_trong_khoi", "dinh_dang"
    k = 2
    for key, label, typ, *_rest in BLOCK:
        if typ == "hdr":
            continue
        ws.cell(k, 11, label.strip())
        ws.cell(k, 12, ROW_OF[key])
        ws.cell(k, 13, BLOCK[ROW_OF[key] - 1][5])
        k += 1
    n_ct = k - 1
    ws["O1"], ws["P1"] = "ky_quy", "ky_nam"
    for i, lb in enumerate(labels_q):
        ws.cell(2 + i, 15, lb)
    for i, lb in enumerate(labels_y):
        ws.cell(2 + i, 16, lb)
    for c in ws[1]:
        c.font = F_B
    setw(ws, {"A": 8, "B": 60, "C": 24, "H": 28, "I": 12, "K": 52})
    return {"dm_ma": f"Data_DM!$A$2:$A${n_ma}", "dm_nhom": f"Data_DM!$H$2:$H${1 + len(NHOM_TONG)}",
            "dm_ct": f"Data_DM!$K$2:$K${n_ct}", "dm_ky": f"Data_DM!$O$2:$O${1 + len(labels_q)}"}


def sheet_dinhgia(ws, val):
    codes = [c for c, _, _ in NHOM_TONG]
    names = dict((c, t) for c, t, _ in NHOM_TONG)
    p = val.pivot_table(index="date", columns="nhom", values=["pe", "pb", "mcap_ty"]).sort_index()
    p = p[p.index >= "2018-06-01"]
    hdr = ["Ngày"]
    cols = []
    for c in codes:
        for m, lab in (("pb", "P/B"), ("pe", "P/E"), ("mcap_ty", "Vốn hoá (nghìn tỷ)")):
            if (m, c) in p.columns:
                cols.append((m, c))
                hdr.append(f"{lab} {names[c]}")
    ws.append(hdr)
    for d, row in p.iterrows():
        vals = []
        for m, c in cols:
            v = row[(m, c)]
            vals.append(None if pd.isna(v) else round(float(v) / (1e3 if m == "mcap_ty" else 1), 4))
        ws.append([d.to_pydatetime()] + vals)
    n = len(p) + 1
    for r in range(2, n + 1):
        ws.cell(r, 1).number_format = "dd/mm/yyyy"
    # P/B toàn ngành: trung bình ± 1 độ lệch chuẩn (công thức)
    cpb = 2 + cols.index(("pb", "ALL"))
    base = len(hdr) + 1
    for j, (lab, f) in enumerate((("P/B toàn ngành - trung bình", "AVERAGE"), ("+1 độ lệch chuẩn", "+"), ("-1 độ lệch chuẩn", "-"))):
        ws.cell(1, base + j, lab)
        rng = f"${L(cpb)}$2:${L(cpb)}${n}"
        for r in range(2, n + 1):
            ws.cell(r, base + j, f"=AVERAGE({rng})" if f == "AVERAGE" else f"=AVERAGE({rng}){f}STDEV({rng})").number_format = "0.00"
    for c in ws[1]:
        c.font, c.alignment = F_B, Alignment(wrap_text=True)
    ws.freeze_panes = "B2"
    ws.column_dimensions["A"].width = 11
    colmap = {mc: 2 + i for i, mc in enumerate(cols)}
    colmap["pb_mean"], colmap["pb_up"], colmap["pb_dn"] = base, base + 1, base + 2
    return n, colmap


# ------------------------------------------------------------------ sheet TRÌNH BÀY
def sheet_key_ratios(ws, labels, mode, irow, fs_ind, fs_ind_rows, fs_cty, fs_cty_rows):
    """Chỉ số tính từ sheet FS: khối trên từ FS Industry (nhóm chọn ở đó), khối dưới từ FS Công ty (mã chọn ở đó)."""
    title(ws, f"NGÀNH BẤT ĐỘNG SẢN – KEY RATIOS ({'QUÝ' if mode == 'Q' else 'NĂM'})",
          f"Tỷ lệ là công thức tham chiếu sheet '{fs_ind}' và '{fs_cty}' (đổi nhóm/mã ở ô B4 của 2 sheet đó). "
          + ("TTM = tổng 4 quý; bình quân = (kỳ này + cùng kỳ năm trước)/2." if mode == "Q"
             else "Năm = tổng 4 quý (dòng chảy) hoặc số dư Q4; bình quân = (năm này + năm trước)/2."))
    block_cols(ws)
    ws["B4"] = f"=\"Nhóm: \"&'{fs_ind}'!$B$4"
    ws["B4"].font = Font(name="Segoe UI", size=10, bold=True, color="843C0C")
    top1 = 6
    kr1, end1 = write_ratio_block(ws, top1, fs_ind, fs_ind_rows, labels, mode,
                                  f"KHỐI NHÓM NGÀNH – tính từ '{fs_ind}'", irow)
    top2 = end1 + 3
    ws.cell(top2 - 1, 2, f"=\"Mã: \"&'{fs_cty}'!$B$4&\"  –  \"&'{fs_cty}'!$H$4").font = Font(
        name="Segoe UI", size=10, bold=True, color="843C0C")
    kr2, _ = write_ratio_block(ws, top2, fs_cty, fs_cty_rows, labels, mode, f"KHỐI CÔNG TY – tính từ '{fs_cty}'", irow)
    for j in range(len(labels)):
        ws.column_dimensions[L(C0 + j)].width = 9.5 if mode == "Q" else 11
    ws.freeze_panes = ws.cell(top1 + 1, C0)
    return kr1, kr2


def sheet_calc(ws, labels, mode, irow, ss_name):
    ws.sheet_properties.tabColor = "A6A6A6"
    block_cols(ws)
    tops = []
    for b in range(N_SS + 1):
        top = 1 + b * (NROW + 3)
        pref = f"'{ss_name}'!$B${8 + b}" if b < N_SS else f"'{ss_name}'!$D$21"
        write_block(ws, top, pref, labels, mode, f"Khối {b + 1}: " + ("mã ở dòng " + str(8 + b) if b < N_SS else "nhóm dòng 21"), irow)
        tops.append(top)
    return tops


def sheet_so_sanh(ws, labels, mode, calc_name, tops, top12):
    title(ws, f"SO SÁNH NHIỀU MÃ – {'QUÝ' if mode == 'Q' else 'NĂM'}",
          "Chọn 1 chỉ tiêu ở ô C4 và tối đa 12 mã ở B8:B19; dòng 20 = trung vị các mã đã chọn; dòng 21 = 1 nhóm ngành (chọn ở C21).")
    setw(ws, {"A": 2, "B": 9, "C": 46, "D": 7, "E": 5, "F": 5, "G": 2})
    for c in ("D", "E", "F"):
        ws.column_dimensions[c].hidden = True
    ws["B4"] = "Chỉ tiêu:"
    ws["B4"].font = F_B
    dropdown(ws, "C4", "=dm_ct", "ROE TTM (VCSH CĐ mẹ bình quân)")
    ws["E4"] = "=IFERROR(INDEX(Data_DM!$L:$L,MATCH($C$4,Data_DM!$K:$K,0)),1)"
    ws["F4"] = '=IFERROR(INDEX(Data_DM!$M:$M,MATCH($C$4,Data_DM!$K:$K,0)),"ty")'
    ws["B6"], ws["C6"] = "Mã", "Tên công ty / nhóm"
    for j, lb in enumerate(labels):
        ws.cell(6, C0 + j, lb)
        ws.column_dimensions[L(C0 + j)].width = 9.5 if mode == "Q" else 11
    for c in ws[6]:
        c.font, c.fill, c.border = F_B, FILL_HDR, B_BOT
    dv_ma = DataValidation(type="list", formula1="=dm_ma", allow_blank=True)
    ws.add_data_validation(dv_ma)
    for b in range(N_SS):
        r = 8 + b
        dv_ma.add(f"B{r}")
        ws.cell(r, 2, top12[b] if b < len(top12) else None).fill = FILL_SEL
        ws.cell(r, 3, f'=IFERROR(INDEX(Data_DM!$B:$B,MATCH($B{r},Data_DM!$A:$A,0)),"")').font = F_N
    ws.cell(20, 3, "Trung vị các mã đã chọn").font = F_B
    ws.cell(21, 2, "Nhóm").font = F_B
    dropdown(ws, "C21", "=dm_nhom", NHOM_TONG[0][1])
    ws["D21"] = '=IFERROR(INDEX(Data_DM!$I:$I,MATCH($C$21,Data_DM!$H:$H,0)),"G:ALL")'
    for j in range(len(labels)):
        col = L(C0 + j)
        for b in range(N_SS + 1):
            r = 8 + b if b < N_SS else 21
            x = f"INDEX({calc_name}!{col}:{col},{tops[b]}+$E$4)"
            ws.cell(r, C0 + j, f'=IFERROR(IF({x}="",NA(),{x}),NA())')
        ws.cell(20, C0 + j, f"=IFERROR(_xlfn.AGGREGATE(12,6,{col}8:{col}19),NA())").font = F_B   # hàm sau 2007 cần _xlfn.
    rng = f"H8:{L(C0 + len(labels) - 1)}21"
    ws.conditional_formatting.add(rng, FormulaRule(formula=["ISNA(H8)"], font=Font(color="FFFFFF")))
    for i, (code, nf) in enumerate(FMT.items()):               # định dạng số theo loại chỉ tiêu đang chọn (F4)
        dxf = DifferentialStyle(numFmt=NumberFormat(numFmtId=180 + i, formatCode=nf))
        ws.conditional_formatting.add(rng, Rule(type="expression", dxf=dxf, formula=[f'$F$4="{code}"']))
    for r in range(8, 22):
        for j in range(len(labels)):
            ws.cell(r, C0 + j).font = F_B if r in (20, 21) else F_N
    ws.freeze_panes = "H7"
    # biểu đồ: 12 mã + trung vị + nhóm
    ch = LineChart()
    c2 = C0 + len(labels) - 1
    for i, r in enumerate(list(range(8, 8 + N_SS)) + [20, 21]):
        ch.add_data(Reference(ws, min_col=C0, max_col=c2, min_row=r, max_row=r), from_rows=True, titles_from_data=False)
        s = ch.series[-1]
        s.tx = SeriesLabel(strRef=StrRef(f"'{ws.title}'!${'C' if r == 20 else 'B'}${r}" if r != 21 else f"'{ws.title}'!$C$21"))
        if r == 20:
            _series_color(s, INK, line=True, w=2.25, dash="dash")
        elif r == 21:
            _series_color(s, ORANGE, line=True, w=2.75)
        else:
            _series_color(s, PALETTE[2:][i % (len(PALETTE) - 2)], line=True, w=1.25)
    ch.set_categories(Reference(ws, min_col=C0, max_col=c2, min_row=6, max_row=6))
    ch.display_blanks = "gap"
    style(ch, "Chỉ tiêu đang chọn (C4) – 12 mã, trung vị (nét đứt) và nhóm (cam)", "General", 4 if mode == "Q" else 1)
    ch.width, ch.height = 30, 11
    ws.add_chart(ch, "B24")


def sheet_bang_ma(ws, dc, vs_last, labels_q, irow, nq):
    title(ws, "BẢNG MÃ – TOÀN BỘ CÔNG TY BĐS TẠI 1 KỲ",
          "Chọn kỳ ở C3 (số TTM tính đến kỳ đó). Vốn hoá, P/E, P/B = giá ngày gần nhất (giá TradingView × số CP hiện hành; BCTC VCI). "
          "Lọc/sắp xếp bằng nút lọc ở dòng tiêu đề.")
    ws["B3"] = "Kỳ BCTC:"
    ws["B3"].font = F_B
    dropdown(ws, "C3", "=dm_ky", labels_q[-1])
    ws["E3"] = f"=IFERROR(MATCH($C$3,Data_FS!$H$1:${L(C0 + nq - 1)}$1,0),{nq})"
    ws["D3"] = "cột kỳ:"
    ws["D3"].font = F_S
    hdr = ["Mã", "Tên công ty", "Nhóm", "Vốn hoá (tỷ)", "P/E", "P/B", "Ngày giá", "DT thuần TTM", "LNST CĐ mẹ TTM",
           "Tăng trưởng LNST TTM", "Biên gộp TTM", "ROE TTM", "Nợ vay ròng / VCSH", "Tồn kho", "Người mua trả trước",
           "Người mua trả trước / Tồn kho", "CFO TTM", "Kỳ BCTC gần nhất"]
    items = [("rev", "IS", "net_sales"), ("gp", "IS", "gross_profit"), ("np", "IS", "attributable_to_parent_company"),
             ("eq", "BS", "owners_equity"), ("mi", "BS", "minority_interests"), ("sd", "BS", "short_term_borrowings"),
             ("ld", "BS", "long_term_borrowings"), ("cash", "BS", "cash_and_cash_equivalents"),
             ("sti", "BS", "short_term_investments#1"), ("inv", "BS", "inventories"), ("adv", "BS", "advances_from_customers"),
             ("advl", "BS", "long_term_advances_from_customers"), ("cfo", "CF", "net_cash_inflows_outflows_from_operating_activities")]
    h0 = 22                                                           # cột helper đầu (V)
    hc = {k: L(h0 + i) for i, (k, _, _) in enumerate(items)}
    R0 = 5
    for j, h in enumerate(hdr):
        c = ws.cell(R0, 1 + j, h)
        c.font, c.fill, c.border, c.alignment = F_B, FILL_HDR, B_BOT, Alignment(wrap_text=True, vertical="center")
    for i, (k, bc, it) in enumerate(items):
        ws.cell(R0, h0 + i, f"r_{k}").font = F_S
    d = dc.merge(vs_last, left_on="ticker", right_on="ticker", how="left").sort_values("mcap_ty", ascending=False, na_position="last")
    Q = "fs_q"

    def v(k, r, off=0):
        return f"N(INDEX({Q},${hc[k]}{r},$E$3-{off}))" if off else f"N(INDEX({Q},${hc[k]}{r},$E$3))"

    def ttm(k, r, off=0):
        a, b = f"$E$3-{off + 3}", (f"$E$3-{off}" if off else "$E$3")
        return f"SUM(INDEX({Q},${hc[k]}{r},{a}):INDEX({Q},${hc[k]}{r},{b}))"

    for n, row in enumerate(d.itertuples()):
        r = R0 + 1 + n
        vals = [row.ticker, row.ten_cong_ty, row.nhom,
                None if pd.isna(row.mcap_ty) else round(row.mcap_ty, 1),
                None if pd.isna(row.pe) else round(row.pe, 2), None if pd.isna(row.pb) else round(row.pb, 2),
                None if pd.isna(row.date) else row.date.to_pydatetime()]
        for j, x in enumerate(vals):
            ws.cell(r, 1 + j, x)
        for i, (k, bc, it) in enumerate(items):
            ws.cell(r, h0 + i, f'=IFERROR(MATCH($A{r}&"|{bc}|{irow[(bc, it)]}",Data_FS!$A:$A,0),"")')
        ok = f"$E$3>=4"
        eq_now = f"({v('eq', r)}-{v('mi', r)})"
        eq_4 = f"({v('eq', r, 4)}-{v('mi', r, 4)})"
        f = {
            8: f'=IFERROR(IF({ok},{ttm("rev", r)},""),"")',
            9: f'=IFERROR(IF({ok},{ttm("np", r)},""),"")',
            10: f'=IFERROR(IF($E$3<8,"",IF({ttm("np", r, 4)}<=0,"",{ttm("np", r)}/{ttm("np", r, 4)}-1)),"")',
            11: f'=IFERROR(IF({ok},{ttm("gp", r)}/{ttm("rev", r)},""),"")',
            12: f'=IFERROR(IF($E$3<5,"",{ttm("np", r)}/(({eq_now}+{eq_4})/2)),"")',
            13: f'=IFERROR(({v("sd", r)}+{v("ld", r)}-{v("cash", r)}-{v("sti", r)})/{v("eq", r)},"")',
            14: f'=IFERROR({v("inv", r)},"")',
            15: f'=IFERROR({v("adv", r)}+{v("advl", r)},"")',
            16: f'=IFERROR(({v("adv", r)}+{v("advl", r)})/{v("inv", r)},"")',
            17: f'=IFERROR(IF({ok},{ttm("cfo", r)},""),"")',
        }
        for c, fx in f.items():
            ws.cell(r, c, fx)
        ws.cell(r, 18, row.ky_gan_nhat)
        for j, nf in {4: "#,##0", 5: "0.0", 6: "0.00", 7: "dd/mm/yyyy", 8: "#,##0", 9: "#,##0", 10: "0.0%", 11: "0.0%",
                      12: "0.0%", 13: '0.00"x"', 14: "#,##0", 15: "#,##0", 16: "0.0%", 17: "#,##0"}.items():
            ws.cell(r, j).number_format = nf
        for j in range(1, 19):
            ws.cell(r, j).font = F_N
    last = R0 + len(d)
    ws.auto_filter.ref = f"A{R0}:R{last}"
    setw(ws, {"A": 7, "B": 44, "C": 22, "D": 11, "E": 7, "F": 7, "G": 10, "H": 11, "I": 11, "J": 10, "K": 9, "L": 9,
              "M": 9, "N": 11, "O": 11, "P": 11, "Q": 11, "R": 9})
    for i in range(len(items)):
        ws.column_dimensions[L(h0 + i)].hidden = True
    ws.row_dimensions[R0].height = 30
    ws.freeze_panes = f"C{R0 + 1}"


DRV = [
    ("A. THỊ TRƯỜNG & ĐỊNH GIÁ", None, None),
    ("vnindex", "0.0", None), ("mcap_ALL", "#,##0", None), ("pe_ALL", "0.0", None), ("pb_ALL", "0.00", None),
    ("pe_EXVIN", "0.0", None), ("pb_EXVIN", "0.00", None), ("pb_NHA", "0.00", None), ("pb_KCN", "0.00", None),
    ("pb_VIN", "0.00", None),
    ("B. TRÁI PHIẾU DOANH NGHIỆP BĐS (riêng lẻ, HNX CBIS)", None, None),
    ("tp_ph", "#,##0", None), ("tp_ph_n", "0", None), ("tp_ls", "0.00", None), ("tp_dh", "#,##0", None),
    ("tp_net", "#,##0", ("tp_ph", "tp_dh")),
    ("C. LÃI SUẤT & TÍN DỤNG (%)", None, None),
    ("lending_rate_avg", "0.00", None), ("lending_rate_big4", "0.00", None), ("deposit_12m_avg", "0.00", None),
    ("ib_on", "0.00", None), ("ib_3m", "0.00", None), ("policy_refinance", "0.00", None),
    ("credit_growth_ytd", "0.00", None), ("m2_growth_yoy", "0.00", None),
    ("D. KHỐI NGOẠI (tỷ đồng)", None, None),
    ("kn_ALL", "#,##0", None), ("kn_EXVIN", "#,##0", None), ("kn_VIN", "#,##0", ("kn_ALL", "kn_EXVIN")),
]


def sheet_drivers(ws, dr, mat, periods):
    title(ws, "DRIVERS – THỊ TRƯỜNG, TPDN BĐS, LÃI SUẤT, KHỐI NGOẠI (THEO QUÝ)",
          "Giá trị lấy từ pipeline D:\\market-data (bond-pivot, transmission-fetcher, index-fetcher, Vietcap IQ) và định giá ngành tự tính; "
          "dòng dẫn xuất là công thức. Quý cuối có thể đang chạy (số tới ngày gần nhất).")
    setw(ws, {"A": 2, "B": 52, "C": 10, "D": 2, "E": 2, "F": 2, "G": 2})
    labels = [qlabel(p) for p in periods]
    R0 = 5
    ws.cell(R0, 2, "Chỉ tiêu")
    ws.cell(R0, 3, "Đơn vị")
    for j, lb in enumerate(labels):
        ws.cell(R0, C0 + j, lb)
        ws.column_dimensions[L(C0 + j)].width = 9.5
    for c in ws[R0]:
        c.font, c.fill, c.border = F_B, FILL_HDR, B_BOT
    meta = dr.drop_duplicates("ma").set_index("ma")
    piv = dr.pivot_table(index="ma", columns="period", values="value", aggfunc="first")
    rowof = {}
    r = R0 + 1
    for key, nf, expr in DRV:
        if nf is None:
            ws.cell(r, 2, key).font = F_B
            for j in range(-6, len(labels)):
                ws.cell(r, C0 + j).fill = FILL_HDR
            r += 1
            continue
        rowof[key] = r
        if expr is None:
            ws.cell(r, 2, meta.chi_tieu.get(key, key)).font = F_N
            ws.cell(r, 3, meta.don_vi.get(key, "")).font = F_S
            for j, p in enumerate(periods):
                v = piv.at[key, p] if key in piv.index and p in piv.columns else np.nan
                if pd.notna(v):
                    c = ws.cell(r, C0 + j, float(v))
                    c.number_format, c.font = nf, F_N
        else:
            ws.cell(r, 2, {"tp_net": "Phát hành ròng TPDN BĐS (phát hành − đến hạn)",
                           "kn_VIN": "  trong đó: nhóm Vingroup (VIC, VHM, VRE)"}[key]).font = F_N
            ws.cell(r, 3, "tỷ đồng").font = F_S
            a, b = expr                                           # dòng dẫn xuất = a − b
            for j in range(len(periods)):
                col = L(C0 + j)
                ra, rb = f"{col}{rowof[a]}", f"{col}{rowof[b]}"
                c = ws.cell(r, C0 + j, f'=IF(COUNT({ra},{rb})=0,"",N({ra})-N({rb}))')
                c.number_format, c.font = nf, F_N
        r += 1
    r += 2
    ws.cell(r, 2, "LỊCH ĐÁO HẠN TPDN BĐS ĐANG LƯU HÀNH (các quý tới, tỷ đồng)").font = F_B
    r += 1
    mat_r0 = r
    for p, v in zip(mat.period, mat.tp_den_han_ty):
        ws.cell(r, 2, qlabel(p)).font = F_N
        c = ws.cell(r, 3, float(v))
        c.number_format, c.font = "#,##0", F_N
        r += 1
    ws.freeze_panes = ws.cell(R0 + 1, C0)
    return rowof, labels, (mat_r0, r - 1)


def sheet_chart_data(ws, labels, irow):
    ws.sheet_properties.tabColor = "A6A6A6"
    title(ws, "Dữ liệu biểu đồ DASHBOARD (theo nhóm chọn ở DASHBOARD!B4) – không sửa")
    block_cols(ws)
    top = 4
    kr = write_block(ws, top, "DASHBOARD!$E$4", labels, "Q", "Khối nhóm ngành cho DASHBOARD", irow)
    # dòng cho biểu đồ: ô trống -> #N/A để đường không rơi về 0
    series = [("rev", "Doanh thu thuần"), ("npatmi", "LNST CĐ mẹ"), ("gm_ttm", "Biên gộp TTM"), ("nm_ttm", "Biên LNST CĐ mẹ TTM"),
              ("sga", "(CP BH + QLDN)/DT TTM"), ("inv", "Hàng tồn kho"), ("adv_all", "Người mua trả tiền trước"),
              ("adv_inv", "Người mua trả trước / Tồn kho (trục phải)"), ("st_debt", "Vay ngắn hạn"), ("lt_debt", "Vay dài hạn"),
              ("nde", "Nợ vay ròng / VCSH (trục phải)"), ("cfo_ttm", "CFO TTM"), ("npatmi_ttm", "LNST CĐ mẹ TTM"),
              ("roe", "ROE TTM"), ("roa", "ROA TTM"), ("cod", "Chi phí vốn vay TTM"), ("bond_debt", "Trái phiếu / Nợ vay")]
    r = top + NROW + 3
    ws.cell(r, 2, "DÒNG VẼ BIỂU ĐỒ").font = F_B
    for j, lb in enumerate(labels):
        ws.cell(r, C0 + j, lb).font = F_B
    hdr = r
    rows = {}
    for key, lab in series:
        r += 1
        rows[key] = r
        ws.cell(r, 2, lab)
        fmt = BLOCK[ROW_OF[key] - 1][5]
        for j in range(len(labels)):
            src = f"{L(C0 + j)}{kr[key]}"
            c = ws.cell(r, C0 + j, f"=IF(ISNUMBER({src}),{src},NA())")
            c.number_format = FMT[fmt]
    return hdr, rows


def sheet_dashboard(ws, cd, cd_hdr, cd_rows, nq, dg, dg_n, dg_cols, drv, drv_rows, drv_n):
    title(ws, "DASHBOARD NGÀNH BẤT ĐỘNG SẢN",
          "Chọn nhóm ở ô B4: 7 biểu đồ đầu theo nhóm đang chọn (dữ liệu quý, Chart_Data). Định giá, TPDN, lãi suất, khối ngoại: toàn ngành.")
    setw(ws, {"A": 2, "B": 30})
    ws["B3"] = "Chọn nhóm ngành:"
    ws["B3"].font = F_S
    dropdown(ws, "B4", "=dm_nhom", NHOM_TONG[0][1])
    ws["E4"] = '=IFERROR(INDEX(Data_DM!$I:$I,MATCH($B$4,Data_DM!$H:$H,0)),"G:ALL")'
    ws["E4"].font = Font(color="FFFFFF")
    c1, c2 = C0, C0 + nq - 1
    R = cd_rows
    charts = [
        rows_chart(cd, [R["rev"], R["npatmi"]], c1, c2, "bar", "Doanh thu thuần & LNST CĐ mẹ theo quý (tỷ đồng)", hdr_row=cd_hdr,
                   colors=["BFBFBF", ORANGE]),
        rows_chart(cd, [R["gm_ttm"], R["nm_ttm"], R["sga"]], c1, c2, "line", "Biên lợi nhuận TTM", "0%", hdr_row=cd_hdr),
        rows_chart(cd, [R["inv"], R["adv_all"]], c1, c2, "bar", "Tồn kho & người mua trả tiền trước (tỷ đồng)",
                   sec=[R["adv_inv"]], hdr_row=cd_hdr, colors=["A6A6A6", "262626"]),
        rows_chart(cd, [R["st_debt"], R["lt_debt"]], c1, c2, "bar", "Nợ vay (tỷ đồng) & nợ vay ròng / VCSH",
                   sec=[R["nde"]], stacked=True, hdr_row=cd_hdr, colors=["A6A6A6", "262626"], sec_fmt='0.00"x"'),
        rows_chart(cd, [R["cfo_ttm"], R["npatmi_ttm"]], c1, c2, "line", "Dòng tiền HĐKD TTM so với LNST CĐ mẹ TTM (tỷ đồng)",
                   hdr_row=cd_hdr, colors=["262626", ORANGE]),
        rows_chart(cd, [R["roe"], R["roa"]], c1, c2, "line", "ROE & ROA TTM", "0%", hdr_row=cd_hdr, colors=[ORANGE, "262626"]),
        rows_chart(cd, [R["cod"], R["bond_debt"]], c1, c2, "line", "Chi phí vốn vay TTM & tỷ trọng trái phiếu trong nợ vay", "0%",
                   hdr_row=cd_hdr, colors=["262626", ORANGE]),
    ]
    charts.append(date_chart(dg, 1, [dg_cols[("pb", "ALL")], dg_cols[("pb", "NHA")], dg_cols[("pb", "KCN")], dg_cols[("pb", "VIN")],
                                     dg_cols["pb_mean"]], 2, dg_n, "P/B theo ngày: toàn ngành, nhà ở, KCN, Vingroup",
                             colors=["262626", ORANGE, "A6A6A6", "4472C4", "BFBFBF"], dashed=(dg_cols["pb_mean"],)))
    charts.append(date_chart(dg, 1, [dg_cols[("pe", "ALL")], dg_cols[("pe", "EXVIN")]], 2, dg_n,
                             "P/E theo ngày (gồm công ty lỗ): toàn ngành & trừ Vingroup", "0.0", colors=["262626", ORANGE]))
    d1, d2 = C0, C0 + drv_n - 1
    charts.append(rows_chart(drv, [drv_rows["tp_ph"], drv_rows["tp_dh"]], d1, d2, "bar",
                             "TPDN BĐS: phát hành và đến hạn theo quý (tỷ đồng)", hdr_row=5, colors=["262626", ORANGE]))
    charts.append(rows_chart(drv, [drv_rows["lending_rate_avg"], drv_rows["ib_on"], drv_rows["ib_3m"], drv_rows["policy_refinance"]],
                             d1, d2, "line", "Lãi suất (%): cho vay BQ, liên ngân hàng, tái cấp vốn", "0.0", hdr_row=5))
    charts.append(rows_chart(drv, [drv_rows["kn_EXVIN"], drv_rows["kn_VIN"]], d1, d2, "bar",
                             "Khối ngoại mua/bán ròng cổ phiếu BĐS theo quý (tỷ đồng)", stacked=True, hdr_row=5,
                             colors=["A6A6A6", ORANGE]))
    for i, ch in enumerate(charts):
        row = 7 + (i // 2) * 16
        col = "B" if i % 2 == 0 else "L"
        ws.add_chart(ch, f"{col}{row}")


def sheet_huong_dan(ws, n_ma, periods, stamp, nh_counts):
    title(ws, "FILE NGÀNH BẤT ĐỘNG SẢN – HƯỚNG DẪN")
    ws.column_dimensions["A"].width = 2
    ws.column_dimensions["B"].width = 150
    lines = [
        ("Cập nhật", f"Dựng lúc {stamp}. {n_ma} công ty, BCTC quý {qlabel(periods[0])} → {qlabel(periods[-1])}."),
        ("Nguồn BCTC", "Vietcap (VCI) qua D:\\bctc\\fs-extractor (dump toàn sàn), hợp nhất, số riêng từng quý. VCI chỉ có từ 2018-Q1. "
                       "DNSE đã thử: API công khai chỉ 10 quý gần nhất và ~40 chỉ tiêu rút gọn, khớp tuyệt đối VCI → không thêm được lịch sử."),
        ("Phạm vi", "ICB cấp 2 'Bất động sản' của VCI + mọi mã thêm tay vào nhom_bds.csv. Nhóm: " + ", ".join(f"{k} {v}" for k, v in nh_counts.items())
         + ". VIC (đã hợp nhất VHM, VRE + VinFast) và DXS (con của DXG) KHÔNG cộng vào tổng ngành để khỏi đếm đôi; vẫn xem riêng được."),
        ("Sửa nhóm", "Mở D:\\bctc\\nganh-bat-dong-san\\nhom_bds.csv, đổi cột nhom (Phát triển nhà ở & khác / Khu công nghiệp / Vingroup / Dịch vụ BĐS) "
                     "hoặc cong_vao_nganh (1/0), rồi chạy lại: python run_nganh_bds.py"),
        ("Cập nhật số", "python run_nganh_bds.py (đọc lại dump VCI + giá mới, ~3 phút). Khi có BCTC quý mới: python run_nganh_bds.py --refresh "
                        "(kéo lại BCTC VCI cho các mã BĐS qua fsx.py rồi dựng lại)."),
        ("FS Industry / FS Công ty", "BCTC đầy đủ (KQKD, CĐKT, LCTT, thuyết minh chọn lọc) của nhóm ngành / 1 mã chọn ở ô B4; mỗi ô = INDEX/MATCH vào "
                                     "Data_FS (khoá mã|báo cáo|dòng). Bản (năm): dòng chảy = tổng 4 quý, số dư = Q4."),
        ("Key ratios", "Chỉ gồm số tính toán + tỷ lệ, là CÔNG THỨC tham chiếu thẳng các dòng của FS Industry (khối trên) và FS Công ty (khối dưới). "
                       "Đổi nhóm/mã ở ô B4 của sheet FS tương ứng. Key ratios (năm) tính từ FS Industry (năm) / FS Công ty (năm)."),
        ("Định nghĩa", "TTM = tổng 4 quý liên tiếp. ROE = LNST CĐ mẹ TTM / VCSH CĐ mẹ bình quân (t, t−4). ROA = LNST TTM / tổng TS bình quân. "
                       "Nợ vay = vay & nợ thuê TC ngắn + dài hạn (đã gồm trái phiếu). Nợ vay ròng = nợ vay − tiền − đầu tư tài chính ngắn hạn. "
                       "Chi phí vốn vay = chi phí lãi vay TTM / nợ vay bình quân. Người mua trả tiền trước = ngắn + dài hạn (chỉ báo doanh số đã bán chưa bàn giao)."),
        ("Định giá", "Vốn hoá = giá TradingView (đã điều chỉnh) × số CP hiện hành; BCTC quý có hiệu lực sau cuối quý + 45 ngày; "
                     "P/E nhóm = Σ vốn hoá / Σ LNST CĐ mẹ TTM (gồm công ty lỗ); P/B = Σ vốn hoá / Σ VCSH CĐ mẹ."),
        ("Drivers", "TPDN BĐS = phát hành riêng lẻ trên HNX CBIS (bond-pivot, cột nganh = Bất động sản). Đến hạn = giá trị phát hành − đã mua lại "
                    "(quý tới dùng giá trị đang lưu hành). Lãi suất, tín dụng: transmission-fetcher. Khối ngoại: Vietcap IQ theo mã."),
        ("Lưu ý dữ liệu", "Thuyết minh VCI (dòng 'trong đó' của tồn kho, trái phiếu) không phủ đủ mọi công ty/kỳ. Nhóm Dịch vụ BĐS nhỏ, P/E dễ nhiễu. "
                          "7 mã chưa có giá TradingView nên không có trong định giá ngày."),
    ]
    for i, (k, v) in enumerate(lines):
        ws.cell(3 + i * 2, 2, k).font = F_B
        c = ws.cell(4 + i * 2, 2, v)
        c.font, c.alignment = F_N, Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[4 + i * 2].height = 30


# ------------------------------------------------------------------ dựng file
def build(out=OUT_XLSX, no_com=False):
    t0 = time.time()
    fs, di, dc, val, vs, dr, mat = load()
    irow = item_row(di)
    qcols = [c for c in fs.columns if c.startswith("Q")]
    ycols = [c for c in fs.columns if c.isdigit()]
    nq = len(qcols)
    irow["_nq"] = nq
    assert list(fs.columns[:7]) == ["key", "ma", "bc", "dong", "item_id", "chi_tieu", "don_vi"]
    periods = [f"{c[3:]}-Q{c[1]}" for c in qcols]
    # 12 mã lớn nhất (vốn hoá gần nhất) cho So sánh mã
    vs_last = vs.sort_values("date").groupby("ticker").tail(1)[["ticker", "date", "mcap_ty", "pe", "pb"]]
    mem = dc[dc.cong_vao_nganh.astype(int) == 1].ticker
    top12 = vs_last[vs_last.ticker.isin(mem)].sort_values("mcap_ty", ascending=False).ticker.head(N_SS).tolist()

    wb = Workbook()
    names = ["Hướng dẫn", "DASHBOARD", "FS Industry", "FS Industry (năm)", "FS Công ty", "FS Công ty (năm)",
             "Key ratios", "Key ratios (năm)", "So sánh mã", "So sánh mã (năm)", "Bảng mã", "Drivers",
             "Chart_Data", "Calc_SoSanh", "Calc_SoSanh_Nam", "Data_FS", "Data_DM", "Data_DinhGia"]
    ws = {n: (wb.active if i == 0 else wb.create_sheet(n)) for i, n in enumerate(names)}
    ws["Hướng dẫn"].title = "Hướng dẫn"

    log("  Data_FS ...")
    n_fs = sheet_data_fs(ws["Data_FS"], fs, nq)
    dmn = sheet_dm(ws["Data_DM"], dc, qcols, ycols, top12)
    dmn["fs_q"] = f"Data_FS!$H:${L(C0 + nq - 1)}"
    for k, ref in dmn.items():
        wb.defined_names[k] = DefinedName(k, attr_text=ref)
    log("  Data_DinhGia ...")
    dg_n, dg_cols = sheet_dinhgia(ws["Data_DinhGia"], val)
    log("  FS Industry, FS Công ty, Key ratios, So sánh mã, Calc ...")
    fsr = {}
    for n, lab, mode, grp in (("FS Industry", qcols, "Q", True), ("FS Industry (năm)", ycols, "Y", True),
                              ("FS Công ty", qcols, "Q", False), ("FS Công ty (năm)", ycols, "Y", False)):
        fsr[n] = sheet_fs(ws[n], di, lab, mode, irow, grp)
    krq = sheet_key_ratios(ws["Key ratios"], qcols, "Q", irow, "FS Industry", fsr["FS Industry"], "FS Công ty", fsr["FS Công ty"])
    sheet_key_ratios(ws["Key ratios (năm)"], ycols, "Y", irow, "FS Industry (năm)", fsr["FS Industry (năm)"],
                     "FS Công ty (năm)", fsr["FS Công ty (năm)"])
    tq = sheet_calc(ws["Calc_SoSanh"], qcols, "Q", irow, "So sánh mã")
    ty = sheet_calc(ws["Calc_SoSanh_Nam"], ycols, "Y", irow, "So sánh mã (năm)")
    sheet_so_sanh(ws["So sánh mã"], qcols, "Q", "Calc_SoSanh", tq, top12)
    sheet_so_sanh(ws["So sánh mã (năm)"], ycols, "Y", "Calc_SoSanh_Nam", ty, top12)
    log("  Bảng mã, Drivers, DASHBOARD ...")
    sheet_bang_ma(ws["Bảng mã"], dc, vs_last, qcols, irow, nq)
    last_p = qidx(periods[-1])
    drv_last = max(last_p, max(qidx(p) for p in dr.period))
    drv_periods = [qname(i) for i in range(qidx(periods[0]), drv_last + 1)]
    drv_rows, drv_labels, _ = sheet_drivers(ws["Drivers"], dr, mat, drv_periods)
    cd_hdr, cd_rows = sheet_chart_data(ws["Chart_Data"], qcols, irow)
    sheet_dashboard(ws["DASHBOARD"], ws["Chart_Data"], cd_hdr, cd_rows, nq, ws["Data_DinhGia"], dg_n, dg_cols,
                    ws["Drivers"], drv_rows, len(drv_periods))
    nh_counts = dc.groupby("nhom").size().to_dict()
    sheet_huong_dan(ws["Hướng dẫn"], len(dc), periods, time.strftime("%d/%m/%Y %H:%M"), nh_counts)
    for n in ("Chart_Data", "Calc_SoSanh", "Calc_SoSanh_Nam"):
        ws[n].sheet_state = "visible"
    for n in ("Data_FS", "Data_DM", "Data_DinhGia"):
        ws[n].sheet_properties.tabColor = "BFBFBF"
    wb.calculation.fullCalcOnLoad = True
    wb.active = 1
    tmp = out + ".tmp.xlsx"
    wb.save(tmp)
    log(f"  openpyxl: {time.time() - t0:.0f}s, {os.path.getsize(tmp) / 1e6:.1f} MB, Data_FS {n_fs - 1:,} dòng")
    if no_com:
        os.replace(tmp, out)
        return out
    recalc_and_check(tmp, out, fs, di, krq, fsr)
    return out


# ------------------------------------------------------------------ Excel COM: tính lại + lưu + kiểm tra
def py_ref(fs, di, ma, period_label):
    """Tính lại vài tỷ lệ bằng Python từ data_fs để đối chiếu với công thức Excel."""
    irow = item_row(di)
    qcols = [c for c in fs.columns if c.startswith("Q")]
    j = qcols.index(period_label)
    x = fs[fs.ma == ma].set_index(["bc", "dong"])

    def g(bc, it, jj):
        k = (bc, irow[(bc, it)])
        return float(x.loc[k, qcols[jj]]) if k in x.index and pd.notna(x.loc[k, qcols[jj]]) else np.nan

    def ttm(bc, it):
        v = [g(bc, it, jj) for jj in range(j - 3, j + 1)]
        return np.nan if any(np.isnan(v)) else sum(v)

    def eqme(jj):
        return g("BS", "owners_equity", jj) - np.nan_to_num(g("BS", "minority_interests", jj))

    debt = np.nan_to_num(g("BS", "short_term_borrowings", j)) + np.nan_to_num(g("BS", "long_term_borrowings", j))
    return {
        "gm_ttm": ttm("IS", "gross_profit") / ttm("IS", "net_sales"),
        "roe": ttm("IS", "attributable_to_parent_company") / ((eqme(j) + eqme(j - 4)) / 2),
        "nde": (debt - np.nan_to_num(g("BS", "cash_and_cash_equivalents", j)) - np.nan_to_num(g("BS", "short_term_investments#1", j)))
               / g("BS", "owners_equity", j),
        "adv_inv": (np.nan_to_num(g("BS", "advances_from_customers", j)) + np.nan_to_num(g("BS", "long_term_advances_from_customers", j)))
                   / g("BS", "inventories", j),
    }


def recalc_and_check(tmp, out, fs, di, krq, fsr):
    import pythoncom
    import win32com.client as win32
    pythoncom.CoInitialize()
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible, xl.DisplayAlerts, xl.ScreenUpdating = False, False, False
    t0 = time.time()
    try:
        wb = xl.Workbooks.Open(os.path.abspath(tmp))
        xl.CalculateFull()
        log(f"  Excel tính lại: {time.time() - t0:.0f}s")
        # quét lỗi công thức (bỏ #N/A có chủ đích ở So sánh/Chart_Data)
        errs = {}
        for sh in wb.Worksheets:
            if sh.Name.startswith("Data_"):
                continue
            vals = sh.UsedRange.Value
            if not isinstance(vals, tuple):
                continue
            n = 0
            for row in vals:
                for v in row:
                    if isinstance(v, int) and v < -2146820000:          # mã lỗi COM (#VALUE!, #REF!, #NAME?, #DIV/0!, #N/A)
                        if v == -2146826246 and sh.Name in ("So sánh mã", "So sánh mã (năm)", "Chart_Data"):
                            continue
                        n += 1
            if n:
                errs[sh.Name] = n
        log(f"  lỗi công thức: {errs if errs else 'không có'}")
        # đối chiếu Python: khối ngành (ALL) và khối công ty (NLG) ở kỳ mới nhất của Key ratios
        kr = wb.Worksheets("Key ratios")
        qcols = [c for c in fs.columns if c.startswith("Q")]
        ycols = [c for c in fs.columns if c.isdigit()]
        col = C0 + len(qcols) - 1
        ma = wb.Worksheets("FS Công ty").Range("B4").Value
        bad = []
        irow = item_row(di)
        # FS sheet = đúng số Data_FS (quý mới nhất + năm cuối)
        for sn, pref, cols in (("FS Industry", "G:ALL", qcols), ("FS Industry (năm)", "G:ALL", ycols), ("FS Công ty", ma, qcols)):
            for bc, it in (("IS", "net_sales"), ("BS", "total_assets"), ("CF", "net_cash_inflows_outflows_from_operating_activities")):
                x = fs[(fs.ma == pref) & (fs.bc == bc) & (fs.dong == irow[(bc, it)])][cols[-1]]
                v = float(x.iloc[0]) if len(x) else np.nan
                xv = wb.Worksheets(sn).Cells(fsr[sn][(bc, it)], C0 + len(cols) - 1).Value
                ok = isinstance(xv, float) and abs(xv - v) < 1e-6 * max(1, abs(v))
                log(f"    {sn:18s} {it[:28]:28s} Excel={xv}  data_fs={v}  {'OK' if ok else 'LỆCH'}")
                if not ok:
                    bad.append((sn, it))
        for pref, kmap in (("G:ALL", krq[0]), (ma, krq[1])):
            ref = py_ref(fs, di, pref, qcols[-1])
            for k, v in ref.items():
                xv = kr.Cells(kmap[k], col).Value
                ok = (xv in ("", None) and np.isnan(v)) or (isinstance(xv, float) and abs(xv - v) < 1e-9 * max(1, abs(v)))
                log(f"    {pref:6s} {k:8s} Excel={xv if not isinstance(xv, float) else round(xv, 6)}  Python={round(v, 6)}  {'OK' if ok else 'LỆCH'}")
                if not ok:
                    bad.append((pref, k))
        wb.Worksheets("DASHBOARD").Activate()
        wb.SaveAs(os.path.abspath(out) + ".x.xlsx", 51)
        wb.Close(False)
    finally:
        try:
            xl.Quit()
        except Exception:  # noqa: BLE001
            pass
    os.replace(os.path.abspath(out) + ".x.xlsx", out)
    os.remove(tmp)
    log(f"  -> {out} ({os.path.getsize(out) / 1e6:.1f} MB){'  | ĐỐI CHIẾU LỆCH: ' + str(bad) if bad else ''}")
    return errs, bad


if __name__ == "__main__":
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-com", action="store_true", help="không mở Excel để tính lại/kiểm tra")
    a = ap.parse_args()
    build(no_com=a.no_com)
