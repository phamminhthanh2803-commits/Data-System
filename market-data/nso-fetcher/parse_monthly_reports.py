# -*- coding: utf-8 -*-
r"""parse_monthly_reports.py - doc cac file Excel "Bieu so lieu" bao cao KT-XH thang/quy (monthly-reports\*.xlsx)
thanh 1 file long-format so lieu THANG + QUY cua NSO: nso_monthly_master.csv.

    python parse_monthly_reports.py            # doc tat ca file, dung lai master tu dau (~45 file / 30s)
    python parse_monthly_reports.py --debug --only 2026-09   # in sheet/cot da phan loai de do loi bo cuc

Sheet nhan dien theo TIEU DE (o A1, ten sheet doi lung tung giua cac thang). Nhom (group) va metric:
  CPI     Chi so gia tieu dung: IDX_BASE / YOY / VS_DEC / MOM / AVG_YTD_YOY (chi so, 104,9 = +4,9%), 11 nhom + vang + USD + lam phat co ban
  PPI     Chi so gia san xuat (quy): YOY_Q / QOQ / YOY_YTD / YOY_YEAR theo nganh
  XK, NK  Hang hoa xuat/nhap khau: LEVEL (trieu USD, (luong) nghin tan) thang, _Q, _YTD, _YEAR; YOY tuong ung; tong + khu vuc + mat hang
  IIP     Chi so san xuat cong nghiep: YOY, MOM, YOY_Q, YOY_YTD theo nganh cap 2
  RETAIL  Tong muc ban le & doanh thu DVTD: LEVEL / LEVEL_Q / LEVEL_YTD (ty dong), YOY / YOY_Q / YOY_YTD; 4 nhom
  FDI     FDI dang ky luy ke tu dau nam (trieu USD): PROJECTS_YTD, REG_NEW_YTD, REG_ADJ_YTD; tong + dia phuong + nuoc
  GDP     Tong san pham trong nuoc (quy): LEVEL_HH_Q/_YTD/_YEAR (gia hien hanh, ty dong), LEVEL_SS_* (gia so sanh), YOY_Q/_YTD/_YEAR
          (tang truong, chi so) theo nganh kinh te
  SVC     Xuat, nhap khau dich vu (quy, trieu USD): LEVEL_Q/_YTD/_YEAR, YOY_*
  INVEST  Von dau tu thuc hien toan xa hoi (quy, nghin ty dong): LEVEL_*, YOY_* theo nguon von
  NSNN    Von dau tu thuc hien tu NSNN (thang + quy, ty dong): LEVEL, LEVEL_YTD, LEVEL_Q, YOY_YTD...; trung uong/bo/dia phuong
  TOURIST Khach quoc te den VN (thang + quy, luot nguoi): LEVEL, LEVEL_YTD, YOY... theo phuong tien / thi truong
  LABOR   Mot so chi tieu lao dong (quy, nghin nguoi / %): LEVEL_Q, LEVEL_YTD, LEVEL_YEAR
  UNEMP   Ty le that nghiep & thieu viec lam (quy, %): RATE_Q, RATE_YTD, RATE_YEAR; item = chi tieu - Chung/Thanh thi/Nong thon

Quy uoc:
  date   = YYYY-MM: thang cua ky; cot quy -> thang cuoi quy (metric _Q); "K thang" -> YYYY-K (metric _YTD); nam -> YYYY-12 (_YEAR)
  status = "So bo" / "Uoc tinh" / "Thuc hien" theo tieu de cot. File sau ghi de file truoc (doc theo thu tu thoi gian, giu dong cuoi)
  series_id = group|metric|item ; item chuan hoa (hoa/hoa, "(*)", "Trong do:", ten nhom CPI doi theo nam) -> ten cua file moi nhat
  Cot "so voi" binh thuong la CHI SO; neu dong tong cua cot < 50 (NSO ghi %) thi ca cot duoc cong 100.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import unicodedata

import openpyxl
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from mdlib import log, safe_to_csv, setup_stdout                  # noqa: E402

SRC = os.path.join(HERE, "monthly-reports")
OUT = os.path.join(HERE, "nso_monthly_master.csv")
COLS = ["date", "series_id", "group", "metric", "item", "section", "unit", "status", "value", "src"]

# (group, regex tieu de sheet) - thu tu uu tien; 1 sheet thuoc toi da 1 nhom
TITLE_PATTERNS = [
    ("GDP_HH", r"tổng sản phẩm trong nước.*hiện hành"),
    ("GDP_SS", r"tổng sản phẩm trong nước.*so sánh"),
    ("GDP", r"tổng sản phẩm trong nước"),
    ("CPI", r"chỉ số giá tiêu dùng"),
    ("PPI", r"^chỉ số giá sản xuất"),
    ("IIP", r"chỉ số sản xuất công nghiệp"),
    ("RETAIL", r"tổng mức (hàng h[oó]a )?bán lẻ"),
    ("XK", r"hàng h(?:oá|óa|oa) xuất khẩu|^xuất khẩu (tháng|hàng|quý|năm)"),     # "hoá" (2011-2013) / "hóa"
    ("NK", r"hàng h(?:oá|óa|oa) nhập khẩu|^nhập khẩu (tháng|hàng|quý|năm)"),
    ("SVC", r"xuất, nhập khẩu dịch vụ"),
    ("FDI", r"đầu tư (trực tiếp )?(của )?nước ngoài"),
    ("INVEST", r"vốn đầu tư (thực hiện|phát triển) toàn xã hội"),
    ("NSNN", r"vốn đầu tư thực hiện từ nguồn ngân sách"),
    ("TOURIST", r"khách quốc tế đến"),
    ("LABOR", r"một số chỉ tiêu (về )?lao động"),
    ("UNEMP", r"^tỷ lệ thất nghiệp"),
]
UNITS = {"CPI": "%", "PPI": "%", "XK": "Triệu USD", "NK": "Triệu USD", "IIP": "%", "RETAIL": "Tỷ đồng",
         "FDI": "Triệu USD", "GDP": "Tỷ đồng", "SVC": "Triệu USD", "INVEST": "Nghìn tỷ đồng", "NSNN": "Tỷ đồng",
         "TOURIST": "Lượt người", "LABOR": "", "UNEMP": "%"}
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
SUB_LABELS = {"nam", "nữ", "thành thị", "nông thôn", "nông, lâm nghiệp và thủy sản", "công nghiệp và xây dựng", "dịch vụ"}

# ---------------------------------------------------------------- ten muc chuan hoa
_TONE = {"oá": "óa", "oà": "òa", "oả": "ỏa", "oã": "õa", "oạ": "ọa", "uý": "úy", "uỳ": "ùy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy",
         "oé": "óe", "oè": "òe", "oẻ": "ỏe", "oẽ": "õe", "oẹ": "ọe"}
ITEM_ALIAS = {   # khoa chuan hoa -> khoa dich (ten dai/ngan hoac ten doi han)
    "sanxuatvaphanphoidienkhidotnuocnonghoinuocvadieuhoakhongkhi": "sanxuatvaphanphoidien",
    "suachuabaoduongvalapdatmaymocthietbi": "suachuabaoduongvalapdatmaymocvathietbi",
    "chebiengovasanxuatsanphamtugotrenuatrugiuongtubanghesanxuatsanphamturomravavatlieutetben":
        "chebiengovasanxuatsanphamtugotrenuatrugiuongtubanghesanxuatsanphamturomravavatlieutetben",
    "nhaovavatlieuxaydung": "nhaodiennuocchatdotvavlxd",
    "nhaodiennuocchatdotvavatlieuxaydung": "nhaodiennuocchatdotvavlxd",
    "maymacgiaydepvamunon": "maymacmunongiaydep",
    "maymacmunonvagiaydep": "maymacmunongiaydep",
    "buuchinhvienthong": "thongtinvatruyenthong",
    "dodungvadichvukhac": "hanghoavadichvukhac",
    "chisogiatieudung": "cpichung",
    "chisodolamy": "chisogiadolamy",
    "tongtrigia": "tongso",
    "ixuatkhaudichvu": "xuatkhaudichvu",
    "iinhapkhaudichvu": "nhapkhaudichvu",
    "laodongtu15tuoitrolendanglamviechangnam": "laodongcoviedlam",
    "laodongcovieclam": "laodongcoviedlam",
    "nongnghieplamnghiepvathuysan": "nonglamnghiepvathuysan",
    "nuoctunhienkhaithacdichvuquanlynuocvaxulyracthainuocthai": "nuoctunhienkhaithacdichvuquanlyvaxulyracthainuocthai",
    "phivantaihanghoank": "phivantaihanghoanhapkhau",
    "phibaohiemhanghoank": "phibaohiemhanghoanhapkhau",
    "tylethatnghiepthanhnientu1524tuoi": "tylethatnghiepcuathanhnientu1524tuoi",
    "toanquoc": "toannganhcongnghiep",
    "sphoachat": "sanphamhoachat",
}
_KNOWN: dict[str, set] = {}       # group -> khoa da gap o file MOI (doc file moi truoc) de sua ten mojibake file cu
UNIT_SUFFIX = re.compile(r"\s*\((nghìn người|người|%|triệu usd|tỷ đồng|nghìn tỷ đồng|lượt người|dự án)\)\s*$", re.I)
DISPLAY = {"cpichung": "CPI chung", "tongso": "Tổng số", "chisogiadolamy": "Chỉ số giá đô la Mỹ",
           "chisogiavang": "Chỉ số giá vàng", "lamphatcoban": "Lạm phát cơ bản",
           "toannganhcongnghiep": "Toàn ngành công nghiệp", "xuatkhaudichvu": "Xuất khẩu dịch vụ",
           "nhapkhaudichvu": "Nhập khẩu dịch vụ"}
_CANON: dict[str, str] = {}      # khoa -> ten hien thi (file moi nhat thang)


# Bang ma TCVN3 (font ABC .VnTime) -> Unicode: file .xls 2000-2010 luu chu Viet theo bang ma nay ("S¶n xuÊt c«ng nghiÖp")
_TCVN3 = {
    "¨": "ă", "©": "â", "ª": "ê", "«": "ô", "¬": "ơ", "\xad": "ư", "®": "đ", "¡": "Ă", "¢": "Â", "£": "Ê", "¤": "Ô", "¥": "Ơ", "¦": "Ư", "§": "Đ",
    "µ": "à", "¶": "ả", "·": "ã", "¸": "á", "¹": "ạ", "»": "ằ", "¼": "ẳ", "½": "ẵ", "¾": "ắ", "Æ": "ặ",
    "Ç": "ầ", "È": "ẩ", "É": "ẫ", "Ê": "ấ", "Ë": "ậ", "Ì": "è", "Î": "ẻ", "Ï": "ẽ", "Ð": "é", "Ñ": "ẹ",
    "Ò": "ề", "Ó": "ể", "Ô": "ễ", "Õ": "ế", "Ö": "ệ", "×": "ì", "Ø": "ỉ", "Ü": "ĩ", "Ý": "í", "Þ": "ị",
    "ß": "ò", "á": "ỏ", "â": "õ", "ã": "ó", "ä": "ọ", "å": "ồ", "æ": "ổ", "ç": "ỗ", "è": "ố", "é": "ộ",
    "ê": "ờ", "ë": "ở", "ì": "ỡ", "í": "ớ", "î": "ợ", "ï": "ù", "ñ": "ủ", "ò": "ũ", "ó": "ú", "ô": "ụ",
    "õ": "ừ", "ö": "ử", "÷": "ữ", "ø": "ứ", "ù": "ự", "ú": "ỳ", "û": "ỷ", "ü": "ỹ", "ý": "ý", "þ": "ỵ",
}
_TCVN3_RE = re.compile("[" + "".join(re.escape(k) for k in _TCVN3) + "]")
_VIET_RE = re.compile("[ăơưđĂƠƯĐẠ-ỹ]")      # khong tinh â ê ô (Latin-1, trung ky tu TCVN3 nhu "Ê"=ấ)
# ky tu TCVN3 KHONG trung voi chu Viet Unicode (Latin-1) -> doi duoc ca trong chuoi tron lan ("XuÊt khÈu th¸ng 7 đầu năm 2008")
_TCVN3_SAFE = {k: v for k, v in _TCVN3.items() if k not in "áàâãèéêìíòóôõùúýÈÉÊÌÍÒÓÔÕÙÚÝ"}
_TCVN3_SAFE_RE = re.compile("[" + "".join(re.escape(k) for k in _TCVN3_SAFE) + "]")
# file 2008-2019: NSO doi TCVN3 -> Unicode nham tren chu da la Unicode (á -> ỏ, â -> õ, ê -> ờ ...): "Thỏng", "Khai khoỏng"
_MOJI_REV = {"ỏ": "á", "õ": "â", "ộ": "é", "ờ": "ê", "ớ": "í", "ũ": "ò", "ú": "ó", "ụ": "ô", "ự": "ù", "ỳ": "ú", "ỡ": "ì", "ố": "è", "ó": "ã"}


def tcvn3(s: str) -> str:
    """Chuoi TCVN3 thuan -> doi het; chuoi tron (co chu Viet Unicode) -> chi doi ky tu khong trung.
    Chi coi la TCVN3 khi co ky tu DAC TRUNG (¸ µ ¶ ® Ê Ø...), khong phai chi vi co ô/ê/â ("Giao thông" la Unicode)."""
    dau_hieu = _TCVN3_SAFE_RE.search(s) or re.search(r"[a-zđ][ÈÉÊÌÍÒÓÔÕÙÚÝ]", s)     # "Thùc phÈm" khong co ky tu dac trung
    if not dau_hieu:
        return s
    if not _VIET_RE.search(s):
        return _TCVN3_RE.sub(lambda m: _TCVN3[m.group(0)], s)
    s = _TCVN3_SAFE_RE.sub(lambda m: _TCVN3_SAFE[m.group(0)], s)
    # chu HOA Latin-1 (Ê, È, Ì...) dung giua tu thuong ("XuÊt khÈu") chac chan la TCVN3
    return re.sub(r"(?<=[a-zđ])([ÈÉÊÌÍÒÓÔÕÙÚÝ])", lambda m: _TCVN3.get(m.group(1), m.group(1)), s)


def moji_rev(s: str) -> str:
    return "".join(_MOJI_REV.get(ch, ch) for ch in s)


# Loi font con sot trong file 2008-2019 (NSO tu doi TCVN3 -> Unicode sai mot so chu): "Thỏng 7", "so sỏnh", "cïng kú"
_MOJIBAKE = [(re.compile(p, re.I), r) for p, r in (
    (r"\bthỏng\b", "tháng"), (r"so sỏnh", "so sánh"), (r"giỏ (hiện hành|so s)", r"giá \1"),
    (r"c[ïù]ng k[úỳ]", "cùng kỳ"), (r"\bquí\b", "quý"), (r"®Çu", "đầu"), (r"n¨m", "năm"), (r"th¸ng", "tháng"),
)]


def norm(s) -> str:
    # NFC: vai file ghi "quý"/"tháng" dang to hop dau roi (y + U+0301) -> regex "quý" khong khop -> cot quy bi doc thanh nam
    t = re.sub(r"\s+", " ", tcvn3(unicodedata.normalize("NFC", str(s))).replace("\n", " ")).strip()
    for p, r in _MOJIBAKE:
        t = p.sub(r, t)
    return t


def item_key(name: str) -> str:
    s = name.lower()
    for a, b in _TONE.items():
        s = s.replace(a, b)
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").replace("đ", "d")
    s = re.sub(r"\(\*+\)", "", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return ITEM_ALIAS.get(s, s)


def canon_item(name: str, group: str = "") -> str:
    """Dang ky ten hien thi thong nhat cho 1 muc trong 1 nhom (file doc sau thay ten); tra ve khoa.
    Ten hien thi giu rieng tung nhom: cung khoa 'nonglamnghiepvathuysan' nhung GDP viet 'Nong, lam nghiep va thuy san',
    PPI viet 'Nong nghiep, lam nghiep va thuy san'."""
    disp = re.sub(r"\s*\(\*+\)\s*", "", name).strip()
    disp = re.sub(r"^(I|II|III|IV)\.\s*", "", disp)
    disp = UNIT_SUFFIX.sub("", disp).strip()          # "Luc luong lao dong (Nghin nguoi)" -> bo don vi (co cot unit)
    name = disp
    if disp.isupper():                       # "CHỈ SỐ GIÁ VÀNG" -> "Chỉ số giá vàng"
        disp = disp[:1] + disp[1:].lower()
    k = item_key(name)
    known = _KNOWN.setdefault(group, set())
    if k not in known:
        k2 = item_key(moji_rev(name))        # "Khai khoỏng" -> "Khai khoáng" neu ten sua ve trung ten da biet
        if k2 in known:
            k = k2
    known.add(k)
    _CANON.setdefault((group, k), DISPLAY.get(k, disp))    # file MOI doc truoc -> ten hien thi theo file moi nhat
    return k


# ---------------------------------------------------------------- doc luoi
def report_month(fname: str):
    m = re.match(r"(\d{4})-(\d{2})_", os.path.basename(fname))
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def is_num(c):
    return isinstance(c, (int, float)) and not isinstance(c, bool)


def open_sheets(path: str):
    """[(ten sheet, luoi o)] cho ca .xlsx (openpyxl) va .xls (xlrd, file 2000-2015)."""
    if path.lower().endswith(".xls"):
        import xlrd
        wb = xlrd.open_workbook(path)
        out = []
        for sh in wb.sheets():
            rows = []
            for i in range(min(sh.nrows, 220)):
                r = []
                for j in range(20):
                    v = sh.cell_value(i, j) if j < sh.ncols else ""
                    r.append(None if v in ("", None) else v)
                rows.append(r)
            out.append((sh.name, rows))
        return out
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = [(ws.title, read_grid(ws)) for ws in wb.worksheets]
    wb.close()
    return out


def read_grid(ws, max_rows=220, max_cols=20):
    rows = []
    for r in ws.iter_rows(min_row=1, max_row=max_rows, max_col=max_cols, values_only=True):
        rows.append(list(r) + [None] * (max_cols - len(r)))
    return fix_grid(rows)


_NUMSTR = re.compile(r"^\s*-?\d{1,3}(?:[ ,]?\d{3})*(?:\.\d+)?\s*$|^\s*-?\d+(?:\.\d+)?\s*$")


def fix_grid(rows):
    # file 2000-2002: so luu dang chuoi ('105506.2') -> float; dong "A | 1 | 2 | 3 | 4" (so thu tu cot) -> bo
    out = []
    for r in rows:
        r = [float(c.replace(",", "").replace(" ", "")) if isinstance(c, str) and _NUMSTR.match(c) and len(c.strip()) < 16 else c
             for c in r]
        nums = [c for c in r[1:] if is_num(c)]
        if len(nums) >= 3 and nums == [float(i) for i in range(1, len(nums) + 1)]:
            continue
        out.append(r)
    rows = out
    # vai sheet (Du lich 2024) co cot A la so thu tu dong 1,2,3... -> bo cot do
    stt = [r[0] for r in rows if is_num(r[0])]
    if len(stt) >= 5 and all(float(v).is_integer() for v in stt) and stt[:5] == [1, 2, 3, 4, 5] \
            and not any(isinstance(r[0], str) and r[0].strip() for r in rows[3:]):
        rows = [r[1:] + [None] for r in rows]
    return rows


def sheet_title(rows) -> str:
    for r in rows[:3]:
        for c in r[:4]:
            if isinstance(c, str) and c.strip():
                return norm(c)
    return ""


def detect_group(title: str):
    t = re.sub(r"^\d+[\.,]?\s*", "", title.lower())
    for g, pat in TITLE_PATTERNS:
        if re.search(pat, t):
            return g
    return None


def first_data_row(rows):
    """Dong dau tien co nhan chu o 3 cot dau VA >= 2 o so (dong header chi co nam dang so, khong co nhan)."""
    for i, r in enumerate(rows):
        if i < 2:
            continue
        has_label = any(isinstance(c, str) and c.strip() for c in r[:3])
        nums = [c for c in r[1:] if is_num(c)]
        if has_label and len(nums) >= 2 and not all(float(v).is_integer() and 1990 <= v <= 2100 for v in nums):
            return i                         # dong header "quý III | 2025 | 2025" (nam dang so) khong phai du lieu
    return None


def label_cols(rows, fd):
    first_num = 99
    for r in rows[fd:fd + 40]:
        for j, c in enumerate(r):
            if is_num(c):
                first_num = min(first_num, j)
                break
    return max(first_num, 1)


def col_headers(rows, fd, ncol):
    out = []
    for j in range(ncol):
        parts = [norm(r[j]) for r in rows[1:fd] if r[j] is not None and norm(r[j])]
        out.append(" ".join(parts))
    return out


# ---------------------------------------------------------------- phan loai cot
def period_in(text: str, ry: int, rm: int):
    """Ky trong tieu de cot -> (kind, year, month) kind in month|ytd|quarter|year|None."""
    t = text.lower()
    t = re.sub(r"\b(\d{1,2})\s*tháng\s*/\s*(20\d{2})", r"\1 tháng năm \2", t)       # "6 thang/2000" (file 2000-2002)
    t = re.sub(r"tháng\s*(\d{1,2})\s*/\s*(20\d{2})", r"tháng \1 năm \2", t)          # "thang 7/2001"
    mq = re.search(r"quý\s*(iv|iii|ii|i|[1-4])\b(?:\s*năm\s*(20\d{2}))?", t)
    mk = re.search(r"\b(\d{1,2})\s*tháng(?:\s*đầu)?(?:\s*năm)?(?:\s*năm)?\s*(20\d{2})?(?!\s*so với\s*tháng)", t)
    mm = re.search(r"tháng\s*(\d{1,2})\b(?:\s*năm\s*(20\d{2})?)?", t)
    my = re.search(r"(?<![\d/])(?:cả\s*)?năm\s*(20\d{2})", t)
    if mq:
        q = ROMAN.get(mq.group(1), mq.group(1))
        y = int(mq.group(2)) if mq.group(2) else ry
        return "quarter", y, 3 * int(q)
    if mk:
        y = int(mk.group(2)) if mk.group(2) else ry
        return "ytd", y, int(mk.group(1))
    if mm:
        n = int(mm.group(1))
        y = int(mm.group(2)) if mm.group(2) else (ry if n <= rm else ry - 1)
        return "month", y, n
    if my and "tháng" not in t:
        return "year", int(my.group(1)), 12
    return None, None, None


def status_in(text: str) -> str:
    t = text.lower()
    for k, v in (("sơ bộ", "Sơ bộ"), ("ước tính", "Ước tính"), ("ước tinh", "Ước tính"), ("thực hiện", "Thực hiện")):
        if k in t:
            return v
    return ""


def period_date(kind, y, m, ry, rm):
    if kind == "month":
        return "", f"{y}-{m:02d}"
    if kind == "quarter":
        return "_Q", f"{y}-{m:02d}"
    if kind == "ytd":
        return "_YTD", f"{y}-{m:02d}"
    return "_YEAR", f"{y}-12"


def classify_cpi(hl, h, ry, rm, kind, y, m, st, ctx):
    """Cot CPI/PPI: "Thang N nam Y so voi: Ky goc | Thang N nam Y-1 | Thang 12 nam Y-1 | Thang N-1 | Binh quan ..."""
    if "kỳ gốc" in hl:
        return "IDX_BASE", f"{ry}-{rm:02d}", st, ""
    if "bình quân" in hl or (kind == "ytd" and "so với" in hl):     # file cu: "Chi so gia 7 thang nam 2008 so voi cung ky"
        kind2 = "Q" if "quý" in hl else ("YEAR" if re.search(r"bình quân\s*năm", hl) else "YTD")
        return f"AVG_{kind2}_YOY", f"{ry}-{rm:02d}", st, ""
    if kind == "month":
        if (y, m) == (ry - 1, rm) and not ctx.seen_yoy:
            ctx.seen_yoy = True                  # bao cao thang 12: cot "Thang 12 nam truoc" dau = YOY, cot sau = VS_DEC
            return "YOY", f"{ry}-{rm:02d}", st, ""
        if m == 12 and y == ry - 1 and rm != 1:
            return "VS_DEC", f"{ry}-{rm:02d}", st, ""
        if (y, m) in ((ry, rm - 1), (ry - 1, 12)):
            return "MOM", f"{ry}-{rm:02d}", st, ""
        return None
    if kind == "year" and "so với" in hl:
        return "AVG_YEAR_YOY", f"{ry}-{rm:02d}", st, ""
    return None


def classify_ppi(hl, h, ry, rm, kind, y, m, st):
    """PPI quy: "Quy III nam 2026 so voi: Quy III nam 2025 (YOY_Q) | Quy II nam 2026 (QOQ) | 9 thang so voi cung ky | Nam 2025 so voi nam 2024"."""
    rq = (rm - 1) // 3 + 1
    if kind == "ytd":
        return "YOY_YTD", f"{ry}-{rm:02d}", st, ""
    if kind == "quarter":
        q = m // 3
        if "so với" in hl and (y, q) == (ry, rq):        # tieu de khoi "Quy III nam 2026 so voi:" -> cot dau = cung ky nam truoc
            return "YOY_Q", f"{ry}-{rm:02d}", st, ""
        if (y, q) == (ry - 1, rq):
            return "YOY_Q", f"{ry}-{rm:02d}", st, ""
        if (y, q) in ((ry, rq - 1), (ry - 1, 4)):
            return "QOQ", f"{ry}-{rm:02d}", st, ""
        return None
    if kind == "year":
        return "YOY_YEAR", f"{y}-12", st, ""
    return None


class Ctx:
    def __init__(self):
        self.state = "level"       # level | yoy | mom | skip
        self.basis = ""            # GDP: HH | SS
        self.seen_yoy = False      # CPI: da gan cot YOY chua


def classify(group: str, h: str, j: int, ry: int, rm: int, ncol_lbl: int, ctx: Ctx):
    """-> (metric, date, status, measure) hoac None. measure: 'Lượng'/'Trị giá'/''."""
    h = norm(h)
    hl = h.lower()
    if j < ncol_lbl:
        return None
    # trang thai keo dai sang cac cot sau (tieu de gop o)
    if "cơ cấu" in hl or "kế hoạch" in hl:
        ctx.state = "skip"
    elif ctx.state == "skip" and ("hiện hành" in hl or "so sánh" in hl or re.search(r"\btổng số\b", hl)):
        ctx.state = "level"                  # bang GDP quy I: "Co cau (%)" roi "Theo gia so sanh 2020 Tong so"
    elif "so với tháng trước" in hl or "so với thời điểm tháng trước" in hl:
        ctx.state = "mom"
    elif re.search(r"so với tháng \d", hl):
        # "so voi thang 6 nam 2014" = thang truoc (MOM); "so voi thang 7 nam 2011" (nam truoc) = cung ky (YOY)
        mb = re.search(r"so với tháng (\d{1,2})(?:\s*năm\s*(?:năm\s*)?(20\d{2}))?", hl)
        ctx.state = "yoy" if mb and mb.group(2) and int(mb.group(2)) == ry - 1 else "mom"
    elif "so với cùng kỳ" in hl or re.search(r"so với.*năm trước", hl) or "tốc độ tăng" in hl or "tốc độ phát triển" in hl:
        ctx.state = "yoy"
    elif group == "CPI" and "so với" in hl:
        ctx.state = "level"
    if "hiện hành" in hl:
        ctx.basis = "HH"
    elif "so sánh" in hl:
        ctx.basis = "SS"
    if not h:
        return None
    measure = "Lượng" if hl.endswith("lượng") else ("Trị giá" if "trị giá" in hl else "")
    kind, y, m = period_in(h, ry, rm)
    st = status_in(h)
    if group == "CPI":
        return classify_cpi(hl, h, ry, rm, kind, y, m, st, ctx)
    if group == "PPI":
        return classify_ppi(hl, h, ry, rm, kind, y, m, st)
    if group == "FDI":
        d = f"{ry}-{rm:02d}"
        if "số dự án" in hl:
            return "PROJECTS_YTD", d, st, ""
        if "cấp mới" in hl:
            return "REG_NEW_YTD", d, st, ""
        if "điều chỉnh" in hl or "tăng thêm" in hl:
            return "REG_ADJ_YTD", d, st, ""
        if "pháp định" in hl or "điều lệ" in hl:
            return None
        if "vốn đăng ký" in hl:                                   # file 2003-2019: 1 cot "So von dang ky (Nghin/Trieu USD)"
            return "REG_TOTAL_YTD", d, st, "nghìn" if "nghìn usd" in hl else ""
        return None
    if ctx.state == "skip":
        return None
    if group == "GDP" and (kind is None or re.search(r"(so với|tốc độ tăng|tốc độ phát triển).*quý", hl) and "cùng kỳ" not in hl):
        # bang GDP quy I (1 sheet): khong co ky trong tieu de cot / "Toc do tang so voi quy I nam 2025" (moc so sanh)
        # -> ky = quy bao cao
        kind, y, m = "quarter", ry, rm
    if kind is None:
        return None
    base = {"level": "LEVEL", "yoy": "YOY", "mom": "MOM"}[ctx.state]
    if group == "UNEMP":
        base = "RATE"
    if group == "GDP" and base == "LEVEL":
        base = f"LEVEL_{ctx.basis or 'HH'}"
    suffix, date = period_date(kind, y, m, ry, rm)
    return base + suffix, date, st, measure


# ---------------------------------------------------------------- doc 1 sheet
def parse_sheet(rows, group: str, ry: int, rm: int, src: str, debug=False):
    rows = fix_grid(rows)
    if group == "UNEMP":
        return parse_unemp(rows, ry, rm, src, debug)
    fd = first_data_row(rows)
    if fd is None:
        return []
    ncol_lbl = label_cols(rows, fd)
    hdrs = col_headers(rows, fd, len(rows[0]))
    ctx = Ctx()
    if group in ("GDP_HH", "GDP_SS"):
        ctx.basis = group[-2:]
        group = "GDP"
    spec = {}
    for j, h in enumerate(hdrs):
        hl = h.lower()
        c = classify(group, h, j, ry, rm, ncol_lbl, ctx)
        if group in ("XK", "NK") and c is None and "trị giá" in hl and (j - 1) in spec:
            p = spec[j - 1]                     # cot "Tri gia" chi co sub-header -> ke thua ky cua cot "Luong"
            c = (p[0], p[1], p[2], "Trị giá")
        if c:
            spec[j] = c
        if debug and h and j >= ncol_lbl:
            log(f"      c{j} [{h[:72]}] -> {c}")
    if not spec:
        return []
    # cot "so voi" binh thuong la CHI SO (107,4); vai file ghi % (7,4): dong TONG |v| < 50 -> ca cot cong 100
    cong100 = set()
    tong = rows[fd]
    for j, (metric, *_r) in spec.items():
        if (metric.startswith("YOY") or metric.startswith("MOM") or metric.startswith("AVG_") or metric == "QOQ") \
                and j < len(tong) and is_num(tong[j]) and abs(tong[j]) < 50:
            cong100.add(j)
    out = []
    section, parent = "", ""
    for r in rows[fd:]:
        labels = [norm(c) for c in r[:ncol_lbl] if isinstance(c, str) and norm(c)]
        labels = [re.sub(r"(?i)^trong đó\s*:?\s*", "", x).strip() for x in labels]
        labels = [x for x in labels if x]
        if not labels:
            continue
        item = labels[-1].rstrip(":").strip()
        nums = {j: r[j] for j in spec if j < len(r) and is_num(r[j])}
        if not nums:
            if not any(is_num(c) for c in r):
                if re.match(r"^\d{1,2}[\.,]\s*\S", item):      # bang moi trong cung sheet (vd "34. Ty le that nghiep")
                    if re.search(r"tỷ lệ thất nghiệp", item.lower()):
                        i0 = rows.index(r)
                        out += parse_unemp(rows[i0:], ry, rm, src, debug)
                    break
                section = item
            continue
        if item.lower().startswith("(*)"):
            continue
        if group == "FDI" and item.lower().startswith("phân theo") and not any(o[4] == "tongso" for o in out):
            item = "Tổng số"                     # file T3/2026: NSO ghi so tong vao dong "Phan theo dia phuong"
        if group in ("LABOR",):
            item = UNIT_SUFFIX.sub("", item).strip()
        il = item.lower()
        if group in ("LABOR",):
            if il in SUB_LABELS:
                item = f"{parent} - {item}" if parent else item
            else:
                parent = UNIT_SUFFIX.sub("", item).strip()
            if "cơ cấu" in section.lower():
                item += " (cơ cấu %)"
        key = canon_item(item, group)
        for j, v in nums.items():
            metric, date, st, measure = spec[j]
            unit = "Nghìn tấn" if measure == "Lượng" else UNITS[group]
            if metric.startswith(("YOY", "MOM", "AVG_", "QOQ", "IDX")) or group in ("CPI", "IIP", "PPI", "UNEMP"):
                unit = "%"
            if group == "FDI" and metric == "PROJECTS_YTD":
                unit = "Dự án"
            if group == "LABOR":
                unit = "%" if il.startswith("tỷ lệ") or "cơ cấu" in item else "Nghìn người"
            k2 = key + ("|luong" if measure == "Lượng" else "")
            if j in cong100 and key != "lamphatcoban":
                v = v + 100
            if measure == "nghìn":                                 # FDI file cu: nghin USD -> trieu USD
                v, measure = v / 1000, ""
            out.append((date, f"{group}|{metric}|{k2}", group, metric, k2, section, unit, st, float(v), src))
    return out


def parse_unemp(rows, ry, rm, src, debug=False):
    """Bang Ty le that nghiep: DONG = ky ("Quy I nam 2025", "Uoc tinh nam 2025"), COT = Chung | Thanh thi | Nong thon,
    tieu de nhom (Ty le that nghiep trong do tuoi / thanh nien / thieu viec lam) la dong khong co so."""
    hdr_cols = {}
    for r in rows[0:8]:
        for j, c in enumerate(r):
            if isinstance(c, str) and norm(c) and j >= 1:
                t = norm(c)
                if t.lower() in ("chung", "thành thị", "nông thôn"):
                    hdr_cols[j] = t
    if not hdr_cols:
        return []
    out, section = [], ""
    for r in rows[2:]:
        lab = next((norm(c) for c in r[:1] if isinstance(c, str) and norm(c)), "")
        if not lab:
            continue
        nums = {j: r[j] for j in hdr_cols if is_num(r[j])}
        if not nums:
            if re.match(r"^\d{1,2}[\.,]\s*\S", lab) and section:
                break
            if not re.match(r"^\d{1,2}[\.,]", lab):
                section = re.sub(r"\s*\(\*+\)\s*$", "", lab)
            continue
        kind, y, m = period_in(lab, ry, rm)
        if kind is None or not section:
            continue
        suffix, date = period_date(kind, y, m, ry, rm)
        st = status_in(lab)
        for j, v in nums.items():
            key = canon_item(f"{section} - {hdr_cols[j]}", "UNEMP")
            out.append((date, f"UNEMP|RATE{suffix}|{key}", "UNEMP", "RATE" + suffix, key, section, "%", st, float(v), src))
    if debug:
        log(f"      UNEMP: {len(out)} o, cot {hdr_cols}")
    return out


def finalize_items(df: pd.DataFrame) -> pd.DataFrame:
    def disp(g, k):
        base, _, lg = k.partition("|")
        name = _CANON.get((g, base), base)
        return f"{name} (lượng)" if lg else name
    df = df.copy()
    df["item"] = [disp(g, k) for g, k in zip(df["group"], df["item"])]
    df["series_id"] = df["group"] + "|" + df["metric"] + "|" + df["item"]
    return df


# ---------------------------------------------------------------- main
def main() -> int:
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--only", help="chi file co ten chua chuoi nay")
    a = ap.parse_args()
    return main_parse(a.only, a.debug)


def main_parse(only: str | None = None, debug: bool = False) -> int:
    files = sorted(glob.glob(os.path.join(SRC, "*.xls")) + glob.glob(os.path.join(SRC, "*.xlsx")), key=os.path.basename)
    if only:
        files = [f for f in files if only in os.path.basename(f)]
    log(f"=== Parse {len(files)} file Bieu so lieu thang/quy ===")
    rows = []
    for f in reversed(files):                # MOI truoc: ten hien thi + bo khoa chuan lay tu file moi, file cu khop theo
        ry, rm = report_month(f)
        if not ry:
            log(f"  - bo qua (khong doc duoc thang): {os.path.basename(f)}")
            continue
        try:
            sheets = open_sheets(f)
        except Exception as e:                                    # noqa: BLE001
            log(f"  X {os.path.basename(f)}: {e}")
            continue
        n_f, groups = 0, []
        for name, grid in sheets:
            try:
                group = detect_group(sheet_title(grid[:3]))
                if not group:
                    continue
                if debug:
                    log(f"  {ry}-{rm:02d} {group} <- '{name}' | {sheet_title(grid[:3])[:60]}")
                r = parse_sheet(grid, group, ry, rm, os.path.basename(f), debug)
            except Exception as e:                                # noqa: BLE001
                log(f"  X {ry}-{rm:02d} {name}: {type(e).__name__}: {e}")
                continue
            if not r:
                log(f"  ! {ry}-{rm:02d} {group} ('{name}'): khong nhan ra cot nao")
                continue
            rows += r
            n_f += len(r)
            groups.append(group.replace("GDP_HH", "GDP").replace("GDP_SS", "GDP"))
        log(f"  {ry}-{rm:02d}: {n_f} dong | {', '.join(sorted(set(groups)))}")
    if not rows:
        log("LOI: khong co dong nao")
        return 1
    df = finalize_items(pd.DataFrame(rows, columns=COLS))
    # bao cao thang 12: "so voi thang 12 nam truoc" trung voi "so voi cung ky" -> NSO chi in 1 cot; them ban sao VS_DEC
    dec = df[(df.group == "CPI") & (df.metric == "YOY") & df.date.str.endswith("-12")].copy()
    dec["metric"] = "VS_DEC"
    dec["series_id"] = dec["series_id"].str.replace("|YOY|", "|VS_DEC|", regex=False)
    df = pd.concat([df, dec], ignore_index=True)
    # file sau ghi de file truoc (So bo thay Uoc tinh): sap theo thang bao cao (ten file) roi giu dong cuoi
    df = (df.assign(_k=df.src.str[:7]).sort_values("_k", kind="stable").drop(columns="_k")
            .drop_duplicates(["date", "series_id"], keep="last").sort_values(["group", "series_id", "date"]))
    safe_to_csv(df, OUT)
    g = df.groupby("group").agg(n=("value", "size"), series=("series_id", "nunique"), first=("date", "min"), last=("date", "max"))
    for grp, r in g.iterrows():
        log(f"  {grp:<8} {r.n:>6} dong, {r.series:>4} series, {r['first']}..{r['last']}")
    log(f"Da luu {OUT}: {len(df):,} dong, {df.series_id.nunique():,} series")
    log("=== XONG ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
