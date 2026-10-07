# -*- coding: utf-8 -*-
r"""kr_formulas.py - CONG THUC EXCEL cho sheet Key ratios / Key ratios (nam) trong IB&Brokerage_Nganh.xlsx (16/09/2026).

Dinh nghia da chot voi PV2 (audit AUDIT-Logic-Sheet-TrinhBay.md):
  - ROE, ROA: TTM / binh quan (t, t-4 quy | t, t-1 nam)        - Yield tung loai TS, Earning yield, COF, NIM: QUY x4 (nam: so nam), binh quan (t, t-1)
  - NIM = (thu nhap tu IEA - chi phi lai vay) / IEA binh quan  - Spread = Earning yield - COF
  - CIR (TTM) chuan bank, cung 1 cong thuc cho nganh va cong ty: -(CP ban hang + quan ly) / TOI,  TOI = DTHD - CP HDKD + co tuc/lai tien gui - CP lai vay
  - No/VCSH chi dung no CO LAI (vay + trai phieu phat hanh, 6 dong)
Khoi NGANH (dong 6-33) tham chieu sheet 'FS Industry' (gia tri tong nganh) + dong 167-174 (IS nganh: lai/lo tung loai TS, gia tri) ;
khoi CONG TY (dong 38-64) tham chieu dong 91-145 (so lieu goc cua ma chon, INDEX tu KR_wide_Q/Y).
Dau (FiinProX): CHI PHI va LO la so AM -> cong thuc dung dau + khi "tru chi phi".
"""
from build_presentation import col_letter

FS = "'FS Industry'!"
IEA_FS = "SUM({fs}41:{fs}44)"          # FVTPL + HTM + Margin + AFS (FS Industry dong 41-44)
DEBT_FS = "SUM({fs}47:{fs}52)"         # 6 dong vay + trai phieu phat hanh

# dong 167-174: IS nganh (gia tri tu fs_all_wide) - (dong, nhan, row_order IS, dau nhan metric)
IND_IS_ROWS = [
    (167, "Lãi FVTPL – ngành (IS dòng 2)", 2, "Lãi từ các tài sản tài chính ghi nhận thông qua lãi/lỗ"),
    (168, "Lỗ FVTPL – ngành (IS dòng 23)", 23, "Lỗ các tài sản tài chính ghi nhận thông qua lãi lỗ"),
    (169, "Lãi AFS – ngành (IS dòng 8)", 8, "Lãi từ các tài sản tài chính sẵn sàng để bán"),
    (170, "Lỗ AFS – ngành (IS dòng 29)", 29, "Lỗ và ghi nhận chênh lệch đánh giá theo giá trị hợp lý tài sản tài chính sẵn sàng để bán"),
    (171, "Lãi HTM – ngành (IS dòng 6)", 6, "Lãi từ các khoản đầu tư nắm giữ đến ngày đáo hạn"),
    (172, "Lỗ HTM – ngành (IS dòng 27)", 27, "Lỗ các khoản đầu tư nắm giữ đến ngày đáo hạn"),
    (173, "Lãi cho vay & phải thu – ngành (IS dòng 7)", 7, "Lãi từ các khoản cho vay và phải thu"),
    (174, "Lỗ cho vay – ngành (IS dòng 28)", 28, "Chi phí lãi vay, lỗ từ các khoản cho vay và phải thu"),
]
CIR_LABEL = "CIR chuẩn bank (TTM) = (CP nghiệp vụ + bán hàng + quản lý) / TOI"   # 17/09/2026: TOI = DTHĐ − lỗ tự doanh − lãi vay + cổ tức, dự phòng để ngoài
LABELS = {   # nhan moi (cot F) theo dinh nghia da chot
    8: "Nợ có lãi / VCSH", 15: CIR_LABEL, 16: "ROE (TTM / VCSH bình quân)", 17: "ROA (TTM / TTS bình quân)",
    21: "Yield FVTPL (Q, quy năm)", 22: "Yield AFS (Q, quy năm)", 23: "Yield HTM (Q, quy năm)", 24: "Yield cho vay margin (Q, quy năm)",
    25: "Earning yield (Q, quy năm)", 26: "COF (Q, quy năm, nợ có lãi; lãi vay = IS 51 + phần ở IS 30)", 27: "Spread (Q, quy năm) = EY − COF", 28: "NIM (Q, quy năm) = (thu nhập IEA − CP lãi vay) / IEA BQ",
    40: "Nợ có lãi / VCSH", 47: CIR_LABEL, 48: "ROE (TTM / VCSH bình quân)", 49: "ROA (TTM / TTS bình quân)",
    53: "Yield FVTPL (Q, quy năm)", 54: "Yield AFS (Q, quy năm)", 55: "Yield HTM (Q, quy năm)", 56: "Yield cho vay margin (Q, quy năm)",
    57: "Earning yield (Q, quy năm)", 58: "COF (Q, quy năm, nợ có lãi; lãi vay = IS 51 + phần ở IS 30)", 59: "NIM (Q, quy năm) = (thu nhập IEA − CP lãi vay) / IEA BQ",
}
LABELS_Y = {k: v.replace("(Q, quy năm)", "(năm)").replace("(Q, quy năm, ", "(năm, ").replace("(TTM", "(năm") for k, v in LABELS.items()}


class F:
    """Sinh cong thuc cho 1 cot ky. freq 'Q': x4, TTM = 4 cot, BQ4 = (t, t-4); 'Y': x1, TTM = chinh no, BQ = (t, t-1).
    off: do lech dong (khoi cong ty lap lai trong Calc_SoSanh: khoi b o dong 38+off .. 145+off)."""
    def __init__(self, freq, kr_col, fs_col, kr_first, fs_first, off=0):
        self.freq, self.c, self.fc = freq, kr_col, fs_col
        self.kr_first, self.fs_first, self.off = kr_first, fs_first, off
        self.ann = "4*" if freq == "Q" else ""
        self.n_avg = 4 if freq == "Q" else 1          # lui bao nhieu cot cho binh quan TTM

    # ---- tham chieu
    def kr(self, r, back=0):
        return f"{col_letter(self.c - back)}{r + self.off}"
    def fs(self, r, back=0):
        return f"{FS}{col_letter(self.fc - back)}{r}"
    def ok_kr(self, back):
        return self.c - back >= self.kr_first
    def ok_fs(self, back):
        return self.fc - back >= self.fs_first

    # ---- TTM / binh quan
    def ttm_kr(self, r):
        if self.freq == "Y":
            return self.kr(r)
        return f"SUM({self.kr(r, 3)}:{self.kr(r)})" if self.ok_kr(3) else None
    def ttm_fs(self, r):
        if self.freq == "Y":
            return self.fs(r)
        return f"SUM({FS}{col_letter(self.fc - 3)}{r}:{col_letter(self.fc)}{r})" if self.ok_fs(3) else None
    def avg_kr(self, r, back):
        return f"AVERAGE({self.kr(r)},{self.kr(r, back)})" if self.ok_kr(back) else self.kr(r)
    def avg_fs(self, r, back):
        return f"AVERAGE({self.fs(r)},{self.fs(r, back)})" if self.ok_fs(back) else self.fs(r)
    def avg_fs_expr(self, tpl, back):
        cur = tpl.format(fs=col_letter(self.fc)); cur = FS + cur if not cur.startswith("SUM(") else cur.replace("SUM(", f"SUM({FS}", 1)
        if not self.ok_fs(back):
            return cur
        prev = tpl.format(fs=col_letter(self.fc - back)); prev = prev.replace("SUM(", f"SUM({FS}", 1)
        return f"AVERAGE({cur},{prev})"

    def wrap(self, expr):
        return "" if expr is None else f"=IFERROR({expr},\"\")"

    # ---- khoi NGANH
    def _cir_den_ind(self):
        t, tk = self.ttm_fs, self.ttm_kr
        return f"({t(5)}+{tk(168)}+{tk(170)}+{tk(172)}+{tk(177)}+{t(25)}+{t(27)}+{tk(176)})"

    def _debt_at(self, back):
        c = col_letter(self.fc - back)
        return f"(SUM({FS}{c}47:{c}52)+{self.kr(178, back)})"

    def _debt_ind(self, back):
        return f"AVERAGE({self._debt_at(0)},{self._debt_at(back)})" if (self.ok_fs(back) and self.ok_kr(back)) else self._debt_at(0)

    def industry(self):
        a, n4, n1 = self.ann, self.n_avg, 1 if self.freq == "Q" else 1
        t = self.ttm_fs; tk = self.ttm_kr
        iea = lambda back: self.avg_fs_expr(IEA_FS, back)
        debt = self._debt_ind                                      # no co lai nganh = FS 47:52 + phai tra NH khac (vay qua dem, kr 178)
        d = {
            6: f"={self.fs(43)}", 7: f"={self.fs(53)}",
            8: self.wrap(f"{self._debt_at(0)}/{self.fs(53)}"),
            9: self.wrap(f"{self.fs(43)}/{self.fs(53)}"),
            10: self.wrap(f"({self.fs(42)}+{self.fs(44)})/{self.fs(53)}"),
            11: self.wrap(f"({self.fs(80)}+{self.fs(87)}+{self.fs(94)})/{self.fs(53)}"),
            14: self.wrap(f"{self.fs(43)}/{self.fs(38)}"),
            # CIR chuan bank (17/09/2026): tu = SG&A (FS 28, 29) + chi phi nghiep vu nganh (kr 175) ;
            # mau = doanh thu (FS 5) + lo FVTPL/AFS/HTM (kr 168/170/172) + lo phai sinh (kr 177) + co tuc (FS 25) + lai vay (FS 27) + lai vay o dong 30 (kr 176)
            15: self.wrap(f'IF({self._cir_den_ind()}<=0,"",-({t(28)}+{t(29)}+{tk(175)})/{self._cir_den_ind()})' if (t(28) and tk(175)) else None),
            16: self.wrap(f"{t(33)}/{self.avg_fs(53, n4)}" if t(33) else None),
            17: self.wrap(f"{t(33)}/{self.avg_fs(38, n4)}" if t(33) else None),
            18: self.wrap(f"{t(33)}/{t(5)}" if t(33) else None),
            21: self.wrap(f"{a}({self.kr(167)}+{self.kr(168)})/{self.avg_fs(41, n1)}"),
            22: self.wrap(f"{a}({self.kr(169)}+{self.kr(170)})/{self.avg_fs(44, n1)}"),
            23: self.wrap(f"{a}({self.kr(171)}+{self.kr(172)})/{self.avg_fs(42, n1)}"),
            24: self.wrap(f"{a}({self.kr(173)}+{self.kr(174)})/{self.avg_fs(43, n1)}"),
            # FS 35 "Net Interest income" = thu nhap IEA GOP (lai - lo FVTPL/HTM/cho vay/AFS) DA TRU IS 51 (FS 27) -> EY = FS35 - FS27 (gop);
            # NIM = FS35 + kr176 (chi tru them phan lai vay o IS 30); lai vay hieu luc nganh = FS 27 + kr 176 - sua 17/09/2026 (truoc do NIM tru IS 51 hai lan)
            25: self.wrap(f"{a}({self.fs(35)}-{self.fs(27)})/{iea(n1)}"),
            26: self.wrap(f"-{a}({self.fs(27)}+{self.kr(176)})/{debt(n1)}"),
            27: self.wrap(f"{self.kr(25)}-{self.kr(26)}"),
            28: self.wrap(f"{a}({self.fs(35)}+{self.kr(176)})/{iea(n1)}"),
            31: self.wrap(f"{self.fs(43)}/{IEA_FS.format(fs=col_letter(self.fc)).replace('SUM(', 'SUM(' + FS, 1)}"),
            32: self.wrap(f"{self.kr(164)}/{IEA_FS.format(fs=col_letter(self.fc)).replace('SUM(', 'SUM(' + FS, 1)}"),
            33: self.wrap(f"{self.kr(165)}/{IEA_FS.format(fs=col_letter(self.fc)).replace('SUM(', 'SUM(' + FS, 1)}"),
        }
        return d

    # ---- khoi CONG TY (dong 91-145 = so lieu goc cua ma chon)
    def company(self):
        a, n4, n1 = self.ann, self.n_avg, 1
        t = self.ttm_kr
        d = {
            38: f"={self.kr(93)}", 39: f"={self.kr(96)}",
            40: self.wrap(f"{self.kr(122)}/{self.kr(96)}"),
            41: self.wrap(f"{self.kr(93)}/{self.kr(96)}"),
            42: self.wrap(f"({self.kr(92)}+{self.kr(94)})/{self.kr(96)}"),
            43: self.wrap(f"{self.kr(123)}/{self.kr(96)}"),
            46: self.wrap(f"{self.kr(93)}/{self.kr(95)}"),
            47: self.wrap(f'IF({t(84)}<=0,"",-{t(83)}/{t(84)})' if t(83) else None),    # CIR chuan bank: dong 83 / 84 (TOI <= 0 -> trong)
            48: self.wrap(f"{t(120)}/{self.avg_kr(96, n4)}" if t(120) else None),
            49: self.wrap(f"{t(120)}/{self.avg_kr(95, n4)}" if t(120) else None),
            50: self.wrap(f"{t(120)}/{t(106)}" if t(120) else None),
            53: self.wrap(f"{a}{self.kr(124)}/{self.avg_kr(91, n1)}"),
            54: self.wrap(f"{a}{self.kr(125)}/{self.avg_kr(94, n1)}"),
            55: self.wrap(f"{a}{self.kr(126)}/{self.avg_kr(92, n1)}"),
            56: self.wrap(f"{a}{self.kr(127)}/{self.avg_kr(93, n1)}"),
            57: self.wrap(f"{a}{self.kr(128)}/{self.avg_kr(121, n1)}"),
            58: self.wrap(f"-{a}SUM({self.kr(116)},{self.kr(81)})/{self.avg_kr(122, n1)}"),        # lai vay hieu luc = IS 51 + phan lai vay o IS 30 (SUM: o "" khi ma khong co dong)
            59: self.wrap(f"{a}SUM({self.kr(128)},{self.kr(116)},{self.kr(81)})/{self.avg_kr(121, n1)}"),
            62: self.wrap(f"{self.kr(93)}/{self.kr(121)}"),
            63: self.wrap(f"{self.kr(144)}/{self.kr(121)}"),
            64: self.wrap(f"{self.kr(145)}/{self.kr(121)}"),
        }
        return d


RATIO_ROWS_IND = [6, 7, 8, 9, 10, 11, 14, 15, 16, 17, 18, 21, 22, 23, 24, 25, 26, 27, 28, 31, 32, 33]
RATIO_ROWS_CO = [38, 39, 40, 41, 42, 43, 46, 47, 48, 49, 50, 53, 54, 55, 56, 57, 58, 59, 62, 63, 64]
RAW_ROWS_CO = list(range(80, 86)) + list(range(91, 146))
FLOW_ROWS_CO = set(range(80, 85)) | set(range(106, 121)) | set(range(124, 132))     # dong chay: nam = tong 4 quy
# dong 79-84 (khoi peer cu, nay = SO LIEU BO SUNG cho CIR chuan bank): (dong -> (cot E ghi chu nguon, cot F nhan))
EXTRA_LABELS = {
    79: ("", "SỐ LIỆU BỔ SUNG cho CIR chuẩn bank (tỷ đồng, mã ở G36)"),
    80: ("DER 1 = Σ IS 32–39", "Chi phí nghiệp vụ (tự doanh, môi giới, bảo lãnh, tư vấn, lưu ký, TVTC, khác)"),
    81: ("DER 2 = phần lãi vay trong IS 30", "Lãi vay ghi ở dòng 30 (phần có CF chứng minh; cộng với IS 51 = lãi vay hiệu lực)"),
    82: ("IS 31", "Lỗ phái sinh phòng ngừa rủi ro"),
    83: ("= 80 + 118 + 119", "CP hoạt động chuẩn bank = nghiệp vụ + bán hàng + quản lý"),
    84: ("= 106 + 111 + 112 + 114 + 82 + 117 + 116 + 81", "TOI chuẩn bank = DTHĐ − lỗ tự doanh − lãi vay + cổ tức"),
    85: ("BS 116 (số dư)", "Phải trả ngắn hạn khác = vay qua đêm (cộng vào nợ có lãi, dòng 122)"),
    122: ("= 97..102 + 85", "Tổng nợ có lãi (vay + TP phát hành + vay qua đêm)"),
}
# dong 175-177: so lieu nganh (ALL trong Data_FS) cho CIR chuan bank - (dong, nhan, stmt, row_order)
IND_BAL_ROWS = {178}                                         # dong nganh la SO DU: nam = Q4 (khac: tong 4 quy)
IND_DER_ROWS = [
    (175, "Chi phí nghiệp vụ – ngành (Σ IS 32–39)", "DER", 1),
    (176, "Lãi vay ghi ở IS 30 – ngành (phần có CF chứng minh)", "DER", 2),
    (177, "Lỗ phái sinh phòng ngừa – ngành (IS 31)", "IS", 31),
    (178, "Phải trả ngắn hạn khác – ngành (= vay qua đêm, BS 116, số dư)", "BS", 116),
]


def write(ws, freq, periods, fs_hdr, col0, company_only=False, off=0):
    """Ghi cong thuc ty le vao sheet Key ratios (freq Q) / Key ratios (nam) (freq Y); company_only + off: 1 khoi cong ty trong Calc_SoSanh.
    fs_hdr: {nhan ky: cot} cua 'FS Industry' (quy: 'Q1-2016'..., nam: 2015...); None khi company_only."""
    fs_first = None
    if not company_only:
        fs_cols = sorted(c for lab, c in fs_hdr.items() if (str(lab).startswith("Q") if freq == "Q" else not str(lab).startswith("Q")))
        fs_first = min(fs_cols)
    n_ind = n_co = 0
    for k, p in enumerate(periods):
        c = col0 + k
        fc = None
        if not company_only:
            key = p if freq == "Q" else int(p)
            fc = fs_hdr.get(key) or fs_hdr.get(float(key) if freq == "Y" else key)
            if fc is None:
                continue
        f = F(freq, c, fc, col0, fs_first, off)
        if not company_only:
            for r, formula in f.industry().items():
                ws.Cells(r, c).Formula = formula; n_ind += 1
        for r, formula in f.company().items():
            ws.Cells(r + off, c).Formula = formula; n_co += 1
    labs = LABELS if freq == "Q" else LABELS_Y
    for r, lab in labs.items():
        if company_only and r < 38:
            continue
        ws.Cells(r + off, 6).Value = lab
    return n_ind, n_co


# ---- SO LIEU GOC cua ma (dong 91-145): tra thang sheet Data_FS (key = ticker|stmt|row_order, cot = quy) thay cho KR_wide_Q/Y (16/09/2026)
DATA_FS = "Data_FS"
RAW_MAP = {   # dong Key ratios -> (bao cao, row_order FiinProX) - theo GETPIVOTDATA cua workbook goc (AUDIT-Logic-Sheet-TrinhBay.md)
    80: ("DER", 1), 81: ("DER", 2), 82: ("IS", 31), 85: ("BS", 116),                                   # bo sung CIR chuan bank (17/09/2026)
    91: ("BS", 6), 92: ("BS", 7), 93: ("BS", 8), 94: ("BS", 9), 95: ("BS", 92), 96: ("BS", 142),
    97: ("BS", 95), 98: ("BS", 99), 99: ("BS", 100), 100: ("BS", 122), 101: ("BS", 126), 102: ("BS", 127),
    103: ("NOTE", 125), 104: ("NOTE", 138), 105: ("NOTE", 150),
    106: ("IS", 1), 107: ("IS", 2), 108: ("IS", 6), 109: ("IS", 7), 110: ("IS", 8), 111: ("IS", 23), 112: ("IS", 27), 113: ("IS", 28),
    114: ("IS", 29), 115: ("IS", 41), 116: ("IS", 51), 117: ("IS", 45), 118: ("IS", 57), 119: ("IS", 58), 120: ("IS", 72),
    132: ("NOTE", 122), 133: ("NOTE", 123), 134: ("NOTE", 124), 135: ("NOTE", 127), 136: ("NOTE", 135), 137: ("NOTE", 136),
    138: ("NOTE", 137), 139: ("NOTE", 139), 140: ("NOTE", 147), 141: ("NOTE", 148), 142: ("NOTE", 149), 143: ("NOTE", 151),
}
DERIVED = {   # dong tong = SUM cac dong trong sheet ((a, b) = a:b ; so = 1 dong)
    83: [80, 118, 119], 84: [106, 111, 112, 114, 82, 117, 116, 81],                    # CIR chuan bank: chi phi / TOI
    121: [(91, 94)], 122: [(97, 102), 85], 123: [(103, 105)], 124: [107, 111], 125: [110, 114], 126: [108, 112], 127: [109, 113],
    128: [(124, 127)], 129: [(118, 119)], 130: [106, 115], 131: [106, 115, 116, 117],
    144: [123, 135, 139, 140, 141, 143], 145: [(132, 134), (136, 138), 142],
}


def write_raw_block(ws, freq, periods, fs_cols, col0, off=0, ticker_ref="$G$36"):
    """Dong 91-145 (+off): so lieu goc cua ma = INDEX vao Data_FS (cot H an = MATCH key 1 lan/dong) + dong tong = SUM trong sheet.
    fs_cols: {nhan quy 'Qn-yyyy': so cot trong Data_FS}. freq 'Y': dong chay = tong 4 quy (du 4 quy moi tinh), so du = Q4.
    Cot C = bao cao, cot D = row_order (nhin thay, sua duoc). O trong trong Data_FS -> ''."""
    ncol = len(periods); n = 0
    for r, (stmt, ro) in RAW_MAP.items():
        rr = r + off
        ws.Cells(rr, 3).Value = stmt; ws.Cells(rr, 4).Value = ro
        ws.Cells(rr, 8).Formula = f'=IFERROR(MATCH({ticker_ref}&"|"&$C{rr}&"|"&$D{rr},{DATA_FS}!$A:$A,0),"")'
        ws.Cells(rr, 8).NumberFormat = ";;;"
        row = []
        for p in periods:
            if freq == "Q":
                c = fs_cols.get(p)
                if c is None:
                    row.append(""); continue
                v = f"INDEX({DATA_FS}!{col_letter(c)}:{col_letter(c)},$H{rr})"
                row.append(f'=IF($H{rr}="","",IF({v}="","",{v}))')          # IF long (OR khong short-circuit -> #VALUE! khi H trong)
            else:
                cs = [fs_cols.get(f"Q{q}-{p}") for q in (1, 2, 3, 4)]
                if None in cs:
                    row.append(""); continue
                if r in FLOW_ROWS_CO:
                    rg = f"INDEX({DATA_FS}!{col_letter(cs[0])}:{col_letter(cs[3])},$H{rr},0)"
                    row.append(f'=IF($H{rr}="","",IF(COUNT({rg})<4,"",SUM({rg})))')
                else:
                    v = f"INDEX({DATA_FS}!{col_letter(cs[3])}:{col_letter(cs[3])},$H{rr})"
                    row.append(f'=IF($H{rr}="","",IF({v}="","",{v}))')
        ws.Range(ws.Cells(rr, col0), ws.Cells(rr, col0 + ncol - 1)).Formula = [row]; n += ncol
    for r, parts in DERIVED.items():
        rr = r + off
        ws.Cells(rr, 3).ClearContents(); ws.Cells(rr, 4).ClearContents(); ws.Cells(rr, 8).ClearContents()
        row = []
        for k in range(ncol):
            c = col_letter(col0 + k)
            args = ",".join(f"{c}{a + off}:{c}{b + off}" if isinstance(x, tuple) else f"{c}{x + off}" for x in parts for a, b in [x if isinstance(x, tuple) else (x, x)])
            row.append(f"=SUM({args})")
        ws.Range(ws.Cells(rr, col0), ws.Cells(rr, col0 + ncol - 1)).Formula = [row]; n += ncol
    return n
