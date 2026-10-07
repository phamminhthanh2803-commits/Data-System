# -*- coding: utf-8 -*-
r"""dashboard_data.py - KHOI DU LIEU BIEU DO (FS Industry tu dong 144) + BIEU DO sheet DASHBOARD (dashboard_charts.py) (17/09/2026).

Theo spec PV2:
 I   QUY MÔ & TĂNG TRƯỞNG          Chart 1 cơ cấu doanh thu + %YoY | Chart 2 LN hoạt động theo mảng | Chart 3 LNTT + %YoY
 II  LỢI NHUẬN CÓ CHẤT LƯỢNG KHÔNG Chart 4 biên LN (hoạt động → sau SG&A → LNTT → LNST) | Chart 5 NIM (cột), Asset yield, CoF (đường)
                                   Chart 6 CP hoạt động chuẩn bank (cột) + dự phòng (đường) + CIR (đường, trục phụ) | Chart 7 để trống (trao đổi sau)
 III TÀI SẢN SINH LỜI              Chart 8 dư nợ margin + Margin/VCSH | Chart 9 GTGD 3 sàn + ADTV | Chart 10 cơ cấu IEA (margin/fixed income/equity/khác)
                                   Chart 11 Fixed income/IEA, Equity/IEA
 IV  CÂN ĐỐI VỐN & RỦI RO          Chart 12–13 cơ cấu tài sản % / tỷ | Chart 14–15 cơ cấu nguồn vốn % / tỷ | Chart 16 Nợ vay/VCSH + ROE
Mọi ô là CÔNG THỨC: cùng cột kỳ của FS Industry (năm H..R, quý U..BN). Nguồn: dòng FS Industry (#n), tỷ lệ đã chốt ở Key ratios / Key ratios (năm)
(tra theo nhãn kỳ), GTGD ở Drivers, dòng ALL của Data_FS. Ô không có số = #N/A (biểu đồ bỏ qua, định dạng xám).
Chạy riêng (vá file có sẵn):  python dashboard_data.py [--file <xlsx>] [--no-copy]
"""
import argparse, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_presentation import col_letter, com_retry, log, OUTX, copy_final   # noqa: E402

FS = "FS Industry"
YC0, YC1 = 8, 18            # H..R = 2015..2025
QC0, QC1 = 21, 66           # U..BN = Q1-2015..Q2-2026
ROW0 = 144
CH_C0 = 33                  # bieu do quy tu AG = Q1-2018 (Drivers bat dau 2018)
PURPLE, WHITE, GREY = 0xA03070, 0xFFFFFF, 0x808080

# (key, nhan, don vi, kind, arg, style)   kind: sec|chart|fs|yoy|kr|krsum|drv|dfs ; style: b = dam, i = thut le 1, ii = 2
# fs: bieu thuc, "#n" = dong n FS Industry cung cot, "[key]" = dong khac cua khoi cung cot ; ty le -> unit % / x (IFERROR -> NA)
ROWS = [
    ("s1", "I - QUY MÔ & TĂNG TRƯỞNG", None, "sec", None, ""),
    ("c1", "Chart 1 - Cơ cấu doanh thu hoạt động", None, "chart", None, ""),
    ("rev_prop", "Tự doanh", "tỷ VND", "fs", "#6", "i"),
    ("rev_margin", "Margin", "tỷ VND", "fs", "#7", "i"),
    ("rev_brok", "Môi giới", "tỷ VND", "fs", "#8", "i"),
    ("rev_ib", "IB", "tỷ VND", "fs", "#9", "i"),
    ("rev_oth", "Khác (= DT − 4 mảng chính)", "tỷ VND", "fs", "#5-(#6+#7+#8+#9)", "i"),
    ("rev_total", "Doanh thu hoạt động", "tỷ VND", "fs", "#5", "b"),
    ("rev_yoy", "%YoY doanh thu", "%", "yoy", "rev_total", ""),
    ("c2", "Chart 2 - Lợi nhuận hoạt động theo mảng", None, "chart", None, ""),
    ("op_prop", "Tự doanh", "tỷ VND", "fs", "#18", "i"),
    ("op_margin", "Margin", "tỷ VND", "fs", "#19", "i"),
    ("op_brok", "Môi giới", "tỷ VND", "fs", "#20", "i"),
    ("op_ib", "IB", "tỷ VND", "fs", "#21", "i"),
    ("op_oth", "Khác (= LN hoạt động − 4 mảng chính)", "tỷ VND", "fs", "#17-(#18+#19+#20+#21)", "i"),
    ("op_total", "Lợi nhuận hoạt động", "tỷ VND", "fs", "#17", "b"),
    ("c3", "Chart 3 - LNTT & tăng trưởng", None, "chart", None, ""),
    ("pbt", "LNTT", "tỷ VND", "fs", "#32", "b"),
    ("pbt_yoy", "%YoY LNTT", "%", "yoy", "pbt", ""),
    ("s2", "II - LỢI NHUẬN CÓ CHẤT LƯỢNG KHÔNG", None, "sec", None, ""),
    ("c4", "Chart 4 - Biên lợi nhuận ngành", None, "chart", None, ""),
    ("m_op", "Biên LN hoạt động", "%", "fs", "#17/#5", ""),
    ("m_sga", "Biên sau SG&A", "%", "fs", "(#17+#28+#29)/#5", ""),
    ("m_pbt", "Biên LNTT", "%", "fs", "#32/#5", ""),
    ("m_npat", "Biên LNST", "%", "fs", "#33/#5", ""),
    ("c5", "Chart 5 - Vietnam Brokerage Net Interest Margin", None, "chart", None, ""),
    ("nim", "NIM", "%", "kr", (28, 1), ""),
    ("ey", "Asset yield (Earning yield)", "%", "kr", (25, 1), ""),
    ("cof", "CoF", "%", "kr", (26, 1), ""),
    ("c6", "Chart 6 - Vietnam Brokerage cost to income ratio", None, "chart", None, ""),
    ("cost_svc", "Chi phí nghiệp vụ (môi giới, tự doanh, IB, lưu ký…)", "tỷ VND", "kr", (175, -1), "i"),
    ("cost_sga", "Chi phí bán hàng + quản lý (SG&A)", "tỷ VND", "fs", "-(#28+#29)", "i"),
    ("cost_total", "CP hoạt động chuẩn bank (tử số CIR)", "tỷ VND", "fs", "[cost_svc]+[cost_sga]", "b"),
    ("is30", "IS 30 – dự phòng TSTC, phải thu khó đòi & CP đi vay", "tỷ VND", "dfs", "ALL|IS|30", "ii"),
    ("der2", "trong đó lãi vay (DER 2)", "tỷ VND", "kr", (176, 1), "ii"),
    ("prov", "Dự phòng TSTC & phải thu khó đòi (ngoài CIR)", "tỷ VND", "fs", "-([is30]-[der2])", "i"),
    ("cir", "CIR chuẩn bank (TTM)", "%", "kr", (15, 1), ""),
    ("c7", "Chart 7 - Yield các loại tài sản sinh lời (quý, quy năm; HTM = tiền gửi, CD, trái phiếu giữ đến đáo hạn; FVTPL tổng = lãi bán + đánh giá lại + cổ tức, lãi − lỗ; carry = cổ tức & tiền lãi)", None, "chart", None, ""),
    ("y_margin", "Margin", "%", "kr", (24, 1), ""),
    ("y_htm", "HTM", "%", "kr", (23, 1), ""),
    ("y_afs", "AFS", "%", "kr", (22, 1), ""),
    ("y_fvtpl", "FVTPL tổng", "%", "kr", (21, 1), ""),
    ("is5", "Cổ tức, tiền lãi phát sinh từ FVTPL (IS 5)", "tỷ VND", "dfs", "ALL|IS|5", "ii"),
    ("y_fvtpl_carry", "FVTPL carry", "%", "yield", ("is5", 41), ""),
    ("s3", "III - TÀI SẢN SINH LỜI", None, "sec", None, ""),
    ("c8", "Chart 8 - Dư nợ margin & mức sử dụng vốn", None, "chart", None, ""),
    ("margin", "Dư nợ margin", "tỷ VND", "fs", "#43", "b"),
    ("margin_eq", "Margin / VCSH", "x", "fs", "#43/#53", ""),
    ("room_used", "Room margin đã sử dụng (margin / 2×VCSH)", "%", "fs", "#43/(2*#53)", ""),
    ("room_left", "Room margin còn lại", "%", "fs", "1-[room_used]", ""),
    ("c9", "Chart 9 - GTGD thị trường", None, "chart", None, ""),
    ("gtgd_hose", "HOSE", "tỷ VND", "drv", ([28], "sum"), "i"),
    ("gtgd_hnx", "HNX", "tỷ VND", "drv", ([29], "sum"), "i"),
    ("gtgd_upcom", "UPCOM", "tỷ VND", "drv", ([30], "sum"), "i"),
    ("gtgd_total", "GTGD toàn thị trường", "tỷ VND", "fs", "[gtgd_hose]+[gtgd_hnx]+[gtgd_upcom]", "b"),
    ("adtv", "ADTV 3 sàn (bình quân ngày)", "tỷ VND", "drv", ([33, 34, 35], "avg"), ""),
    ("c10", "Chart 10–15 - Bảng cân đối (cấu trúc tài sản sinh lời & nguồn vốn)", None, "chart", None, ""),
    ("bs_ta", "Total assets", "tỷ VND", "fs", "#38", "b"),
    ("bs_iea", "Interest earning assets (IEA)", "tỷ VND", "fs", "[bs_inv]+[bs_margin]", "b"),
    ("bs_inv", "Investments (FVTPL + HTM + AFS)", "tỷ VND", "fs", "#41+#42+#44", "i"),
    ("bs_fvtpl", "FVTPL", "tỷ VND", "fs", "#41", "ii"),
    ("bs_htm", "HTM", "tỷ VND", "fs", "#42", "ii"),
    ("bs_afs", "AFS", "tỷ VND", "fs", "#44", "ii"),
    ("bs_fi", "Fixed-income", "tỷ VND", "kr", (164, 1), "i"),
    ("bs_dep", "Deposits (tiền gửi + CD)", "tỷ VND", "krsum", [152, 156, 157, 158, 160], "ii"),
    ("bs_bond", "Bonds", "tỷ VND", "krsum", [161, 162, 163], "ii"),
    ("bs_eq", "Equity", "tỷ VND", "kr", (165, 1), "i"),
    ("bs_listed", "Listed", "tỷ VND", "krsum", [149, 153], "ii"),
    ("bs_unlisted", "Unlisted", "tỷ VND", "krsum", [150, 154], "ii"),
    ("bs_ccq", "Chứng chỉ quỹ", "tỷ VND", "krsum", [151, 155, 159], "ii"),
    ("bs_inv_oth", "Đầu tư khác (ngoài fixed-income & equity)", "tỷ VND", "fs", "[bs_inv]-[bs_fi]-[bs_eq]", "i"),
    ("bs_margin", "Margin", "tỷ VND", "fs", "#43", "i"),
    ("bs_cash", "Cash", "tỷ VND", "fs", "#40", "b"),
    ("bs_other", "Other assets", "tỷ VND", "fs", "[bs_ta]-[bs_iea]-[bs_cash]", "b"),
    ("bs_ibl", "Interest bearing liabilities (total borrowings)", "tỷ VND", "fs", "SUM(#47:#52)+[bs_on]", "b"),
    ("bs_st_bor", "Short-term borrowings", "tỷ VND", "fs", "#47", "ii"),
    ("bs_st_bond", "Short-term bonds (gồm chuyển đổi)", "tỷ VND", "fs", "#48+#49", "ii"),
    ("bs_lt_bor", "Long-term borrowings", "tỷ VND", "fs", "#50", "ii"),
    ("bs_lt_bond", "Long-term bonds (gồm chuyển đổi)", "tỷ VND", "fs", "#51+#52", "ii"),
    ("bs_on", "ON borrowings (phải trả ngắn hạn khác, BS 116)", "tỷ VND", "dfsbal", "ALL|BS|116", "ii"),
    ("bs_nonint", "Non interest-bearing liabilities", "tỷ VND", "fs", "[bs_ta]-[bs_ibl]-[bs_equity]", "b"),
    ("bs_equity", "Owner's equity", "tỷ VND", "fs", "#53", "b"),
    ("bs_paidin", "Paid-in capital", "tỷ VND", "fs", "#54", "i"),
    ("bs_oeq", "Others equity", "tỷ VND", "fs", "[bs_equity]-[bs_paidin]", "i"),
    ("c11", "Chart 11 - Fixed-income / IEA & Equity / IEA", None, "chart", None, ""),
    ("fi_iea", "Fixed income / IEA", "%", "kr", (32, 1), ""),
    ("eq_iea", "Equity / IEA", "%", "kr", (33, 1), ""),
    ("s4", "IV - CÂN ĐỐI VỐN & RỦI RO", None, "sec", None, ""),
    ("c12", "Chart 12–13 - Cơ cấu tài sản", None, "chart", None, ""),
    ("as_cash", "Tiền", "tỷ VND", "fs", "#40", "i"),
    ("as_fvtpl", "FVTPL", "tỷ VND", "fs", "#41", "i"),
    ("as_afs", "AFS", "tỷ VND", "fs", "#44", "i"),
    ("as_htm", "HTM", "tỷ VND", "fs", "#42", "i"),
    ("as_margin", "Margin", "tỷ VND", "fs", "#43", "i"),
    ("as_rec", "Phải thu", "tỷ VND", "fs", "#45", "i"),
    ("as_oth", "Khác", "tỷ VND", "fs", "#38-(#40+#41+#42+#43+#44+#45)", "i"),
    ("asp_cash", "Tiền", "%", "fs", "[as_cash]/[bs_ta]", "i"),
    ("asp_fvtpl", "FVTPL", "%", "fs", "[as_fvtpl]/[bs_ta]", "i"),
    ("asp_afs", "AFS", "%", "fs", "[as_afs]/[bs_ta]", "i"),
    ("asp_htm", "HTM", "%", "fs", "[as_htm]/[bs_ta]", "i"),
    ("asp_margin", "Margin", "%", "fs", "[as_margin]/[bs_ta]", "i"),
    ("asp_rec", "Phải thu", "%", "fs", "[as_rec]/[bs_ta]", "i"),
    ("asp_oth", "Khác", "%", "fs", "[as_oth]/[bs_ta]", "i"),
    ("c14", "Chart 14–15 - Cơ cấu nguồn vốn", None, "chart", None, ""),
    ("fu_debt", "Nợ vay", "tỷ VND", "fs", "[bs_ibl]", "i"),
    ("fu_nonint", "Nợ không chịu lãi", "tỷ VND", "fs", "[bs_nonint]", "i"),
    ("fu_eq", "VCSH", "tỷ VND", "fs", "[bs_equity]", "i"),
    ("fup_debt", "Nợ vay", "%", "fs", "[fu_debt]/[bs_ta]", "i"),
    ("fup_nonint", "Nợ không chịu lãi", "%", "fs", "[fu_nonint]/[bs_ta]", "i"),
    ("fup_eq", "VCSH", "%", "fs", "[fu_eq]/[bs_ta]", "i"),
    ("c16", "Chart 16 - Tỷ lệ đòn bẩy & hiệu quả sử dụng vốn", None, "chart", None, ""),
    ("debt_eq", "Nợ vay / VCSH", "x", "kr", (8, 1), ""),
    ("roe", "ROE (TTM / VCSH bình quân)", "%", "kr", (16, 1), ""),
]
NUMFMT = {"tỷ VND": "#,##0;(#,##0)", "%": "0.0%", "x": '0.00"x"'}

def row_map():
    return {k: ROW0 + i for i, (k, *_rest) in enumerate(ROWS)}


def _expr(tpl, L, rm):
    s = re.sub(r"#(\d+)", lambda m: f"{L}{m.group(1)}", tpl)
    return re.sub(r"\[(\w+)\]", lambda m: f"{L}{rm[m.group(1)]}", s)


def _kr(freq, r, L):
    sh, hdr = ("'Key ratios'", "$I$4:$AX$4") if freq == "Q" else ("'Key ratios (năm)'", "$I$4:$AX$4")
    return f"INDEX({sh}!$I${r}:$AX${r},MATCH({L}$4,{sh}!{hdr},0))"


def cell_formula(key, unit, kind, arg, c, freq, rm):
    """Cong thuc 1 o (cot c, freq Q/Y)."""
    L = col_letter(c); r = rm[key]
    ratio = unit in ("%", "x")
    if kind == "fs":
        e = _expr(arg, L, rm)
        return f"=IFERROR({e},NA())" if (ratio or "[" in arg) else f"={e}"
    if kind == "yoy":
        back = 4 if freq == "Q" else 1; c0 = QC0 if freq == "Q" else YC0
        if c - back < c0:
            return "=NA()"
        b = rm[arg]; P = col_letter(c - back)
        return f"=IFERROR({L}{b}/{P}{b}-1,NA())"
    if kind == "yield":                                          # thu nhap (dong khoi) / so du binh quan (t, t-1) dong FS; quy x4
        inc, bal = arg; c0 = QC0 if freq == "Q" else YC0; ann = "4*" if freq == "Q" else ""
        if c - 1 < c0:
            return "=NA()"
        P = col_letter(c - 1)
        return f"=IFERROR({ann}{L}{rm[inc]}/AVERAGE({L}{bal},{P}{bal}),NA())"
    if kind in ("kr", "krsum"):
        parts = [(arg[0], arg[1])] if kind == "kr" else [(x, 1) for x in arg]
        e = "+".join(f"{'-' if s < 0 else ''}({_kr(freq, rr, L)}+0)" for rr, s in parts)
        return f"=IFERROR({e},NA())"
    if kind == "dfsbal" and freq == "Y":                          # so du: nam = o Q4 cua chinh dong nay
        return f'=IFERROR(INDEX($U${r}:$BN${r},MATCH("Q4-"&{L}$4,$U$4:$BN$4,0))+0,NA())'
    if kind in ("drv", "dfs") and freq == "Y":                     # nam: tu cac o quy cua chinh dong nay
        agg = "AVERAGE" if (kind == "drv" and arg[1] == "avg") else "SUM"
        rng, cond = f"$U${r}:$BN${r}", f'RIGHT($U$4:$BN$4,4)=TEXT({L}$4,"0")'
        return f"=IFERROR(LET(v,FILTER({rng},{cond}),IF(COUNT(v)<4,NA(),{agg}(IFERROR(v,0)))),NA())"
    if kind == "drv":
        idx = [f"INDEX(Drivers!$I${rr}:$AX${rr},MATCH({L}$4,Drivers!$I$8:$AX$8,0))" for rr in arg[0]]
        tot = "+".join(idx)                                         # GTGD/ADTV <= 0 (vd Drivers Q4-2018 = 0) -> coi la thieu so
        return f"=IFERROR(IF(COUNT({','.join(idx)})<{len(idx)},NA(),IF(({tot})>0,{tot},NA())),NA())"
    if kind in ("dfs", "dfsbal"):
        return f'=IFERROR(INDEX(Data_FS!$A:$CZ,MATCH("{arg}",Data_FS!$A:$A,0),MATCH({L}$4,Data_FS!$1:$1,0))+0,NA())'
    raise ValueError(kind)


def build_block(wb):
    ws = wb.Worksheets(FS)
    rm = row_map(); last = ROW0 + len(ROWS) + 2
    ws.Range(ws.Cells(ROW0 - 1, 1), ws.Cells(ROW0 + 200, QC1)).Clear()
    t = ws.Cells(ROW0 - 1, 6)
    t.Value = "DASHBOARD DATA – nguồn 16 biểu đồ sheet DASHBOARD (công thức, không sửa tay; #N/A = chưa có số, biểu đồ bỏ qua)"
    t.Font.Bold = True; t.Font.Size = 11
    n = 0
    for key, lab, unit, kind, arg, style in ROWS:
        r = rm[key]
        ws.Cells(r, 6).Value = lab
        if kind in ("sec", "chart"):
            rg = ws.Range(ws.Cells(r, 6), ws.Cells(r, QC1))
            rg.Font.Bold = True
            if kind == "sec":
                rg.Interior.Color = PURPLE; rg.Font.Color = WHITE
                ws.Range(ws.Cells(r, YC0), ws.Cells(r, YC1)).Value = [[ws.Cells(4, c).Value for c in range(YC0, YC1 + 1)]]
                ws.Range(ws.Cells(r, QC0), ws.Cells(r, QC1)).Value = [[ws.Cells(4, c).Value for c in range(QC0, QC1 + 1)]]
            else:
                rg.Font.Italic = True
            continue
        ws.Cells(r, 7).Value = unit
        ws.Range(ws.Cells(r, YC0), ws.Cells(r, YC1)).Formula2 = [[cell_formula(key, unit, kind, arg, c, "Y", rm) for c in range(YC0, YC1 + 1)]]
        ws.Range(ws.Cells(r, QC0), ws.Cells(r, QC1)).Formula2 = [[cell_formula(key, unit, kind, arg, c, "Q", rm) for c in range(QC0, QC1 + 1)]]
        body = ws.Range(ws.Cells(r, YC0), ws.Cells(r, QC1))
        body.NumberFormat = NUMFMT[unit]
        if style == "b":
            ws.Range(ws.Cells(r, 6), ws.Cells(r, QC1)).Font.Bold = True
        ws.Cells(r, 6).IndentLevel = {"": 0, "b": 0, "i": 1, "ii": 2}[style]
        n += (YC1 - YC0 + 1) + (QC1 - QC0 + 1)
    blk = ws.Range(ws.Cells(ROW0, YC0), ws.Cells(last, QC1))
    fc = blk.FormatConditions.Add(Type=16); fc.Font.Color = 0xC0C0C0                 # xlErrorsCondition: #N/A mau xam nhat
    return n


def build(wb, charts=True):
    """Khoi du lieu FS Industry 144+; charts=True -> dung lai toan bo DASHBOARD (can Data_DinhGia da co)."""
    import dashboard_charts as DC
    n = com_retry(lambda: build_block(wb))
    msg = f"  DASHBOARD DATA: FS Industry dòng {ROW0}–{ROW0 + len(ROWS) - 1}, {n:,} ô công thức"
    if charts:
        k = com_retry(lambda: DC.build(wb, row_map()))
        nref = DC.clean_ref_names(wb)
        msg += f" | DASHBOARD: {k} biểu đồ (21, định dạng App) | xoá {nref} Name #REF!"
    log(msg)


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
        build(wb)
        xl.Calculation = -4105; xl.CalculateFull()
        wb.Worksheets("DASHBOARD").Activate()
        wb.Save(); wb.Close(False)
        log(f"-> {a.file} [{time.time() - t0:.0f}s]")
    finally:
        try:
            xl.Quit()
        except Exception:                                            # noqa: BLE001
            pass
    if not a.no_copy and os.path.abspath(a.file) == os.path.abspath(OUTX):
        copy_final(OUTX)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
